"""Extract and lightly validate React JSX from multimodal model output."""

from __future__ import annotations

import re


FENCE_PATTERN = re.compile(r"```(?:tsx?|jsx?|html)?\s*\n?(.*?)```", re.IGNORECASE | re.DOTALL)


def clean_react_code(text: str) -> str:
    """Strip markdown fences and select the most likely React component block.

    This intentionally avoids destructive formatting. It is a lightweight
    structural check, not a substitute for compiling generated code.
    """
    candidates = [match.strip() for match in FENCE_PATTERN.findall(text) if match.strip()]
    if candidates:
        code = max(candidates, key=lambda item: ("return" in item or "export" in item, len(item)))
    else:
        code = text.strip()
    code = re.sub(r"^```(?:tsx?|jsx?|html)?\s*|\s*```$", "", code, flags=re.IGNORECASE).strip()
    return code


def validate_react_code(code: str) -> tuple[bool, str | None]:
    """Perform conservative checks and return ``(is_valid, reason)``."""
    if not code:
        return False, "No React code was found in the model response."
    if not re.search(r"\b(return|=>)\b|<[A-Za-z][^>]*>", code):
        return False, "Output does not look like a JSX component."
    if code.count("{") != code.count("}"):
        return False, "JSX output has unbalanced curly braces."
    return True, None
