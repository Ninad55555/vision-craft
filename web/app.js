/* VisionCraft frontend — vanilla ES module, zero dependencies.
 * Talks to the same-origin FastAPI backend; parses SSE manually (EventSource cannot POST).
 */

const PREVIEW_CSP =
  "default-src 'none'; style-src 'unsafe-inline'; script-src 'unsafe-inline'; " +
  "img-src data:; font-src data:; media-src data:; base-uri 'none'; form-action 'none'";

const ERROR_MESSAGES = {
  ACCESS_DENIED: "This server requires an access key. Enter it above and try again.",
  AUTH_MISSING: "The server has no Hugging Face token configured. Add HF_TOKEN to its .env and restart it.",
  AUTH_FAILED: "Hugging Face rejected the server token. It needs a fine-grained token with the “Make calls to Inference Providers” permission.",
  CREDITS_EXHAUSTED: "Monthly Hugging Face inference credits are used up. Upgrade, wait for the reset, or point the server at another provider.",
  RATE_LIMITED: "Too many requests. Wait a moment and retry.",
  IMAGE_INVALID: "That file is not a valid PNG, JPEG, or WebP image (or it is too small).",
  IMAGE_TOO_LARGE: "That image exceeds the server size limit. Try a smaller screenshot.",
  MODEL_UNAVAILABLE: "The configured model is not available right now. The server owner should run scripts/list_models.py and pick one that is live.",
  UPSTREAM_TIMEOUT: "The model took too long. Try a smaller model or a smaller screenshot.",
  UPSTREAM_ERROR: "The model provider returned an error. Retry, or try again later.",
  OUTPUT_NOT_HTML: "The model did not return an HTML document. Retry — a different sample often works.",
  INTERNAL: "Unexpected server error. Check the server logs for the request id.",
};

const state = {
  config: null,
  file: null,          // File/Blob held for (re)generation
  html: "",            // last result
  generating: false,
  aborter: null,
  timerId: null,
  startTime: 0,
  deltaChars: 0,
};

const $ = (id) => document.getElementById(id);
const els = {
  badge: $("model-badge"),
  accessBanner: $("access-banner"),
  accessKey: $("access-key"),
  accessSave: $("access-save"),
  dropzone: $("dropzone"),
  fileInput: $("file-input"),
  fileError: $("file-error"),
  formats: $("dz-formats"),
  thumbWrap: $("thumb-wrap"),
  thumb: $("thumb"),
  thumbMeta: $("thumb-meta"),
  removeImage: $("remove-image"),
  instructions: $("instructions"),
  generate: $("generate"),
  cancel: $("cancel"),
  status: $("status"),
  progress: $("progress"),
  progressStage: $("progress-stage"),
  progressTime: $("progress-time"),
  progressTokens: $("progress-tokens"),
  warnings: $("warnings"),
  previewWrap: $("preview-wrap"),
  previewEmpty: $("preview-empty"),
  preview: $("preview"),
  codeWrap: $("code-wrap"),
  code: $("code"),
  codeMeta: $("code-meta"),
  resultMeta: $("result-meta"),
  errorBox: $("error-box"),
  errorMsg: $("error-msg"),
  retry: $("retry"),
  copy: $("copy"),
  download: $("download"),
  regenerate: $("regenerate"),
};

init();

async function init() {
  bindTabs();
  bindDevices();
  bindInput();
  bindActions();
  try {
    const res = await fetch("/api/config");
    if (!res.ok) throw new Error(`config HTTP ${res.status}`);
    state.config = await res.json();
  } catch (err) {
    setStatus(`Could not reach the server (${err.message}). Is it running?`);
    return;
  }
  els.badge.textContent = state.config.model;
  els.formats.textContent =
    `PNG · JPG · WebP · up to ${state.config.max_upload_mb} MB`;
  if (state.config.requires_access_key && !sessionStorage.getItem("vc-access-key")) {
    els.accessBanner.hidden = false;
  }
  setStatus("Pick a screenshot to begin.");
}

/* ---------- tabs & device toggle ---------- */

function bindTabs() {
  for (const btn of document.querySelectorAll('[role="tab"][data-view]')) {
    if (btn.disabled) continue;
    btn.addEventListener("click", () => showView(btn.dataset.view));
  }
}

function showView(view) {
  const showPreview = view === "preview";
  els.previewWrap.hidden = !showPreview;
  els.codeWrap.hidden = view !== "code";
  for (const btn of document.querySelectorAll('[role="tab"][data-view]')) {
    btn.setAttribute("aria-selected", String(btn.dataset.view === view));
  }
}

function bindDevices() {
  for (const btn of document.querySelectorAll("[data-device]")) {
    btn.addEventListener("click", () => {
      for (const b of document.querySelectorAll("[data-device]")) {
        b.setAttribute("aria-pressed", String(b === btn));
      }
      els.previewWrap.dataset.device = btn.dataset.device;
      sizePreviewFrame();
    });
  }
}

function sizePreviewFrame() {
  const device = els.previewWrap.dataset.device || "fit";
  els.preview.style.width = device === "fit" ? "100%" : `${device}px`;
}

/* ---------- input: picker, drag-drop, paste ---------- */

function bindInput() {
  els.dropzone.addEventListener("click", () => els.fileInput.click());
  els.dropzone.addEventListener("keydown", (e) => {
    if (e.key === "Enter" || e.key === " ") { e.preventDefault(); els.fileInput.click(); }
  });
  els.fileInput.addEventListener("change", () => {
    if (els.fileInput.files.length) acceptFile(els.fileInput.files[0]);
    els.fileInput.value = "";
  });
  for (const name of ["dragenter", "dragover"]) {
    els.dropzone.addEventListener(name, (e) => { e.preventDefault(); els.dropzone.classList.add("drag"); });
  }
  for (const name of ["dragleave", "drop"]) {
    els.dropzone.addEventListener(name, (e) => { e.preventDefault(); els.dropzone.classList.remove("drag"); });
  }
  els.dropzone.addEventListener("drop", (e) => {
    const file = [...(e.dataTransfer?.files || [])].find((f) => f.type.startsWith("image/"));
    if (file) acceptFile(file);
  });
  document.addEventListener("paste", (e) => {
    if (state.generating) return;
    const item = [...(e.clipboardData?.items || [])].find((i) => i.type.startsWith("image/"));
    if (item) {
      const file = item.getAsFile();
      if (file) acceptFile(file);
    }
  });
  els.removeImage.addEventListener("click", () => {
    state.file = null;
    els.thumbWrap.hidden = true;
    els.thumb.src = "";
    els.generate.disabled = true;
    els.regenerate.disabled = true;
    setStatus("Pick a screenshot to begin.");
  });
}

function acceptFile(file) {
  hideFileError();
  const cfg = state.config;
  const okType = (cfg?.accepted_types || ["image/png", "image/jpeg", "image/webp"]).includes(file.type);
  if (!okType) return showFileError(`Unsupported type “${file.type || "unknown"}”. Use PNG, JPEG, or WebP.`);
  const maxBytes = (cfg?.max_upload_mb ?? 10) * 1024 * 1024;
  if (file.size > maxBytes) {
    return showFileError(`File is ${(file.size / 1048576).toFixed(1)} MB; the limit is ${cfg.max_upload_mb} MB.`);
  }
  state.file = file;
  const url = URL.createObjectURL(file);
  els.thumb.onload = () => {
    els.thumbMeta.textContent =
      `${file.name} · ${els.thumb.naturalWidth}×${els.thumb.naturalHeight} · ${(file.size / 1024).toFixed(0)} KB`;
  };
  els.thumb.src = url;
  els.thumbWrap.hidden = false;
  els.generate.disabled = false;
  els.regenerate.disabled = !state.html;
  setStatus("Screenshot ready. Add instructions if you like, then Generate.");
}

function showFileError(msg) {
  els.fileError.textContent = msg;
  els.fileError.hidden = false;
}

function hideFileError() {
  els.fileError.hidden = true;
  els.fileError.textContent = "";
}

/* ---------- actions ---------- */

function bindActions() {
  els.generate.addEventListener("click", () => startGenerate());
  els.regenerate.addEventListener("click", () => startGenerate());
  els.cancel.addEventListener("click", () => state.aborter?.abort());
  els.retry.addEventListener("click", () => startGenerate());
  els.copy.addEventListener("click", copyCode);
  els.download.addEventListener("click", downloadHtml);
  els.accessSave.addEventListener("click", () => {
    const key = els.accessKey.value.trim();
    if (key) sessionStorage.setItem("vc-access-key", key);
    els.accessBanner.hidden = true;
    setStatus(state.file ? "Screenshot ready. Add instructions if you like, then Generate." : "Pick a screenshot to begin.");
  });
}

function accessHeaders() {
  const key = sessionStorage.getItem("vc-access-key");
  return key ? { "X-Access-Key": key } : {};
}

/* ---------- generation + SSE ---------- */

async function startGenerate() {
  if (!state.file || state.generating) return;
  hideError();
  els.warnings.hidden = true;
  els.warnings.replaceChildren();
  els.resultMeta.hidden = true;
  state.generating = true;
  state.aborter = new AbortController();
  state.deltaChars = 0;
  state.startTime = performance.now();
  els.generate.disabled = true;
  els.cancel.disabled = false;
  els.copy.disabled = true;
  els.download.disabled = true;
  els.regenerate.disabled = true;
  els.progress.hidden = false;
  els.previewEmpty.hidden = true;
  tickTimer();
  state.timerId = setInterval(tickTimer, 250);

  const form = new FormData();
  form.append("image", state.file, state.file.name || "screenshot.png");
  form.append("instructions", els.instructions.value);
  form.append("stream", "true");

  let response;
  try {
    response = await fetch("/api/generate", {
      method: "POST",
      body: form,
      headers: accessHeaders(),
      signal: state.aborter.signal,
    });
  } catch (err) {
    return finishGenerateWithError(null, err.name === "AbortError" ? "cancelled" : "network");
  }
  if (!response.ok || !response.body) {
    let code = null;
    try {
      const payload = await response.json();
      code = payload?.detail?.code || null;
    } catch { /* fall through to generic HTTP error */ }
    return finishGenerateWithError(code || `http-${response.status}`, "http");
  }
  try {
    await readSSE(response.body, onSSEEvent);
  } catch (err) {
    if (err.name === "AbortError") return finishGenerateWithError("cancelled", "cancelled");
    return finishGenerateWithError(null, "network");
  }
}

async function readSSE(body, onEvent) {
  const reader = body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    let idx;
    while ((idx = buffer.indexOf("\n\n")) >= 0) {
      const block = buffer.slice(0, idx);
      buffer = buffer.slice(idx + 2);
      let name = null;
      let data = null;
      for (const line of block.split("\n")) {
        if (line.startsWith("event:")) name = line.slice(6).trim();
        else if (line.startsWith("data:")) data = (data === null ? "" : data) + line.slice(5).trim();
        else if (line.startsWith(":")) continue; // comment / ping
      }
      if (name) onEvent(name, data ? JSON.parse(data) : null);
    }
  }
}

function onSSEEvent(name, data) {
  if (name === "status") {
    const labels = {
      preparing: "Preparing image…",
      calling_model: data?.note ? `Calling model… (${data.note})` : "Calling model…",
      generating: "Generating…",
      postprocessing: "Post-processing…",
    };
    els.progressStage.textContent = labels[data?.stage] || data?.stage || "Working…";
    setStatus(els.progressStage.textContent);
  } else if (name === "delta") {
    state.deltaChars += (data?.text || "").length;
    els.progressTokens.textContent = `≈ ${Math.round(state.deltaChars / 4).toLocaleString()} tokens`;
  } else if (name === "result") {
    finishGenerateWithResult(data);
  } else if (name === "error") {
    finishGenerateWithError(data?.code || null, "api", data?.message, data?.retryable);
  }
}

function finishGenerateWithResult(result) {
  stopTimer();
  state.html = result.html || "";
  renderPreview(state.html);
  renderCode(state.html);
  renderWarnings(result.warnings || []);
  const usage = result.usage
    ? `${result.usage.prompt_tokens ?? "?"} in / ${result.usage.completion_tokens ?? "?"} out`
    : "usage n/a";
  els.resultMeta.textContent =
    `Model ${result.model} · ${(result.elapsed_ms / 1000).toFixed(1)} s · ${usage}` +
    (result.truncated ? " · truncated" : "");
  els.resultMeta.hidden = false;
  setStatus("Done. Review the preview, then copy or download.");
  state.generating = false;
  els.generate.disabled = false;
  els.cancel.disabled = true;
  els.copy.disabled = !state.html;
  els.download.disabled = !state.html;
  els.regenerate.disabled = !state.file;
}

function finishGenerateWithError(code, kind, message, retryable) {
  stopTimer();
  state.generating = false;
  els.generate.disabled = !state.file;
  els.cancel.disabled = true;
  els.regenerate.disabled = !state.file;
  if (kind === "cancelled") {
    setStatus("Cancelled. Adjust the instructions and regenerate when ready.");
    return;
  }
  let text;
  if (kind === "network") {
    text = "Could not reach the server. Make sure it is running, then retry.";
  } else if (kind === "http") {
    text = ERROR_MESSAGES[code] || `The server returned an error (${code}).`;
  } else {
    text = ERROR_MESSAGES[code] || message || "Something went wrong.";
  }
  els.errorMsg.textContent = text;
  els.retry.hidden = !(retryable || kind === "network" || kind === "http");
  els.errorBox.hidden = false;
  setStatus("Generation failed — see the error below.");
}

function hideError() {
  els.errorBox.hidden = true;
  els.retry.hidden = true;
}

function stopTimer() {
  clearInterval(state.timerId);
  state.timerId = null;
  els.progress.hidden = true;
}

function tickTimer() {
  els.progressTime.textContent = `${((performance.now() - state.startTime) / 1000).toFixed(1)} s`;
}

function setStatus(text) {
  els.status.textContent = text;
}

/* ---------- result rendering ---------- */

function renderPreview(html) {
  const cspTag =
    `<meta http-equiv="Content-Security-Policy" content="${PREVIEW_CSP}">`;
  let srcdoc = html;
  const headMatch = /<head[^>]*>/i.exec(html);
  if (headMatch) {
    const at = headMatch.index + headMatch[0].length;
    srcdoc = html.slice(0, at) + cspTag + html.slice(at);
  } else {
    srcdoc = cspTag + html;
  }
  els.preview.hidden = false;
  els.previewEmpty.hidden = true;
  // srcdoc is the only sanctioned sink for model output (sandboxed, no same-origin).
  els.preview.setAttribute("srcdoc", srcdoc);
  sizePreviewFrame();
}

function renderCode(html) {
  els.code.textContent = html; // textContent: escaped, no highlighting library
  const bytes = new TextEncoder().encode(html).length;
  els.codeMeta.textContent = `${html.split("\n").length.toLocaleString()} lines · ${(bytes / 1024).toFixed(1)} KB`;
}

function renderWarnings(warnings) {
  if (!warnings.length) return;
  for (const w of warnings) {
    const p = document.createElement("p");
    p.textContent = humanizeWarning(w);
    els.warnings.appendChild(p);
  }
  els.warnings.hidden = false;
}

function humanizeWarning(w) {
  if (w.startsWith("OUTPUT_TRUNCATED")) return "Warning: the model hit its output limit, so the page may be incomplete.";
  if (w.startsWith("Falling back")) return `Notice: ${w}.`;
  return w;
}

async function copyCode() {
  if (!state.html) return;
  try {
    await navigator.clipboard.writeText(state.html);
  } catch {
    const area = document.createElement("textarea");
    area.value = state.html;
    document.body.appendChild(area);
    area.select();
    document.execCommand("copy");
    area.remove();
  }
  setStatus("Copied to clipboard.");
}

function downloadHtml() {
  if (!state.html) return;
  const blob = new Blob([state.html], { type: "text/html;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const stamp = new Date().toISOString().slice(0, 19).replace(/[-:T]/g, "");
  const a = document.createElement("a");
  a.href = url;
  a.download = `visioncraft-${stamp}.html`;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
