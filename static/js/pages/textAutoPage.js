// /static/js/pages/textAutoPage.js
// Text Automation page logic
// - Wires the form on textautomation.html
// - Supports local transforms and image → text via /api/text-from-image
// - Exports: initTextAutomation()

let booted = false;

// ------------- Utilities -------------
const $ = (sel, root = document) => root.querySelector(sel);

function setOutput(text) {
  const out = $("#ta-output");
  if (!out) return;
  out.textContent = text || "No output.";
  $("#ta-copy")?.toggleAttribute("disabled", !text);
  $("#ta-download")?.toggleAttribute("disabled", !text);
}

function toPromptPreview({ mode, tone, length, text }) {
  return [
    `Mode: ${mode}`,
    `Tone: ${tone}`,
    `Length: ${length}`,
    "",
    text || "(no text provided)"
  ].join("\n");
}

async function extractFromImage(file) {
  const fd = new FormData();
  fd.append("image", file);
  const res = await fetch("/api/text-from-image", { method: "POST", body: fd });
  // Server returns JSON; handle errors gracefully
  if (!res.ok) throw new Error(`Server ${res.status}`);
  const data = await res.json().catch(() => ({}));
  return data?.text || JSON.stringify(data, null, 2) || "No result";
}

// ------------- Behaviors -------------
async function onRun() {
  const runBtn = $("#ta-run");
  const mode   = $("#ta-mode")?.value || "rewrite";
  const tone   = $("#ta-tone")?.value || "neutral";
  const length = $("#ta-length")?.value || "medium";
  const textEl = $("#ta-text");
  const imgEl  = $("#ta-image");

  const text = (textEl?.value || "").trim();
  const file = imgEl?.files?.[0] || null;

  // Busy UI
  if (runBtn) {
    runBtn.disabled = true;
    runBtn.dataset.old = runBtn.textContent;
    runBtn.textContent = "Working…";
  }
  setOutput("Processing…");

  try {
    if (mode === "extract") {
      if (!file) {
        setOutput("Please choose an image to extract from.");
      } else {
        const result = await extractFromImage(file);
        setOutput(result);
      }
      return;
    }

    // Local transforms (placeholder); swap with your API if desired.
    if (!text) {
      setOutput("Please add some text (or choose Extract mode with an image).");
      return;
    }

    let result = "";
    switch (mode) {
      case "rewrite":
        result = `Rewritten (${tone}, ${length}):\n\n` + text;
        break;
      case "summarize":
        result = `Summary (${length}):\n\n` + text.split(/\s+/).slice(0, 60).join(" ") + (text.split(/\s+/).length > 60 ? "…" : "");
        break;
      case "keywords":
        result = "Keywords:\n- " + [...new Set(text.toLowerCase().match(/[a-z0-9]+/g) || [])]
          .slice(0, 15).join("\n- ");
        break;
      case "prompt":
        result = toPromptPreview({ mode, tone, length, text });
        break;
      case "caption":
        result = `Caption (${tone}): ${text} #AuraJewels #DailyShine`;
        break;
      case "tags":
        result = "#aura #jewelry #diamond #gold #style #shine #everyday #love";
        break;
      default:
        result = toPromptPreview({ mode, tone, length, text });
    }

    setOutput(result);
  } catch (err) {
    setOutput("Error: " + (err?.message || err));
  } finally {
    if (runBtn) {
      runBtn.disabled = false;
      runBtn.textContent = runBtn.dataset.old || "Generate";
    }
  }
}

function onClear() {
  $("#ta-text") && ($("#ta-text").value = "");
  $("#ta-image") && ($("#ta-image").value = "");
  setOutput("No output yet.");
}

async function onCopy() {
  const text = $("#ta-output")?.textContent || "";
  try { await navigator.clipboard.writeText(text); } catch {}
}

function onDownload() {
  const text = $("#ta-output")?.textContent || "";
  const blob = new Blob([text], { type: "text/plain" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url; a.download = "text_automation.txt";
  document.body.appendChild(a); a.click(); a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 400);
}

// ------------- Public init -------------
export function initTextAutomation() {
  if (booted) return;
  booted = true;

  const pageId = document.body?.dataset?.page || "";
  if (pageId !== "text_automation") {
    console.warn("[TextAutomation] init on unexpected page:", pageId);
  }

  $("#ta-run")?.addEventListener("click", onRun);
  $("#ta-clear")?.addEventListener("click", onClear);
  $("#ta-copy")?.addEventListener("click", onCopy);
  $("#ta-download")?.addEventListener("click", onDownload);

  // Initial UI
  setOutput("No output yet.");

  console.debug("[TextAutomation] initialized");
}
