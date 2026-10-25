from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Any

from src.core.errors import VisionCraftError, error

log = logging.getLogger(__name__)

NETWORK_DISABLED_SCRIPT = """
(() => {
  const deny = () => { throw new Error('VisionCraft render is offline'); };
  try { window.fetch = deny; } catch (_) {}
  try { window.XMLHttpRequest = deny; } catch (_) {}
  try { window.WebSocket = deny; } catch (_) {}
  try { window.EventSource = deny; } catch (_) {}
  try { navigator.sendBeacon = () => false; } catch (_) {}
  try { window.open = () => null; } catch (_) {}
  try {
    window.alert = () => {};
    window.confirm = () => false;
    window.prompt = () => null;
  } catch (_) {}
})();
"""


@dataclass
class RenderResult:
    png: bytes
    width: int
    height: int
    blocked_requests: int = 0


class HtmlRenderer:
    """Shared headless browser with a fresh, offline context per render."""

    def __init__(self, *, channel: str = "", timeout: float = 20):
        self.channel = (channel or "").strip()
        self.timeout = max(1.0, float(timeout))
        self._playwright: Any = None
        self._browser: Any = None
        self._start_lock = asyncio.Lock()

    @staticmethod
    def _connected(browser: Any) -> bool:
        if browser is None:
            return False
        value = getattr(browser, "is_connected", None)
        try:
            return bool(value() if callable(value) else value)
        except Exception:  # noqa: BLE001
            return False

    async def start(self) -> None:
        if self._connected(self._browser):
            return
        async with self._start_lock:
            if self._connected(self._browser):
                return
            try:
                from playwright.async_api import async_playwright
            except ImportError as exc:
                raise error(
                    "REFINE_UNAVAILABLE",
                    "Visual refinement needs Playwright. Install requirements-refine.txt and run "
                    "'playwright install chromium' (or set REFINE_BROWSER_CHANNEL=msedge).",
                ) from exc

            self._playwright = await async_playwright().start()
            channels: list[str | None]
            if self.channel:
                channels = [self.channel]
            else:
                channels = [None, "msedge", "chrome"]

            last_error: Exception | None = None
            for channel in channels:
                kwargs: dict[str, Any] = {"headless": True}
                if channel:
                    kwargs["channel"] = channel
                try:
                    self._browser = await self._playwright.chromium.launch(**kwargs)
                    if channel:
                        log.info("Visual refinement is using the %s browser channel.", channel)
                    return
                except Exception as exc:  # noqa: BLE001 - try the next installed browser
                    last_error = exc
                    log.debug("Could not launch Playwright channel %s: %s", channel or "chromium", exc)

            await self._stop_playwright()
            raise error(
                "REFINE_UNAVAILABLE",
                "No usable browser for visual refinement. Run 'playwright install chromium' "
                "or set REFINE_BROWSER_CHANNEL to an installed browser channel (for example, msedge).",
            ) from last_error

    async def render(self, html: str, width: int, height: int) -> RenderResult:
        await self.start()
        try:
            return await asyncio.wait_for(
                self._render_page(html, width, height),
                timeout=self.timeout + 5,
            )
        except asyncio.TimeoutError as exc:
            raise error("REFINE_FAILED", "Rendering the HTML timed out.") from exc

    async def _render_page(self, html: str, width: int, height: int) -> RenderResult:
        if self._browser is None:
            raise error("REFINE_UNAVAILABLE", "The visual refinement browser is not running.")

        context = await self._browser.new_context(
            viewport={"width": max(1, width), "height": max(1, height)},
            device_scale_factor=1,
            java_script_enabled=True,
            service_workers="block",
            accept_downloads=False,
            reduced_motion="reduce",
        )
        blocked = 0

        async def route_request(route) -> None:
            nonlocal blocked
            url = route.request.url
            if url.startswith(("data:", "about:", "blob:")):
                await route.continue_()
                return
            blocked += 1
            await route.abort()

        try:
            await context.route("**/*", route_request)
            page = await context.new_page()
            page.set_default_timeout(self.timeout * 1000)
            page.set_default_navigation_timeout(self.timeout * 1000)
            page.on("dialog", lambda dialog: asyncio.create_task(dialog.dismiss()))
            await page.add_init_script(NETWORK_DISABLED_SCRIPT)
            await page.set_content(html, wait_until="load")
            try:
                await page.evaluate("document.fonts.ready.then(() => true)")
            except Exception:  # noqa: BLE001 - font readiness is a best-effort stabilization
                pass
            await page.wait_for_timeout(300)
            png = await page.screenshot(
                type="png",
                full_page=False,
                animations="disabled",
                caret="hide",
            )
            return RenderResult(png=png, width=width, height=height, blocked_requests=blocked)
        except VisionCraftError:
            raise
        except Exception as exc:  # noqa: BLE001 - browser failures become a typed error
            raise error("REFINE_FAILED", f"Could not render the HTML: {str(exc)[:240]}") from exc
        finally:
            try:
                await context.close()
            except Exception:  # noqa: BLE001 - already gone
                pass

    async def aclose(self) -> None:
        browser = self._browser
        self._browser = None
        if browser is not None:
            try:
                await browser.close()
            except Exception:  # noqa: BLE001
                pass
        await self._stop_playwright()

    async def _stop_playwright(self) -> None:
        playwright = self._playwright
        self._playwright = None
        if playwright is not None:
            try:
                await playwright.stop()
            except Exception:  # noqa: BLE001
                pass
