// /static/js/pages/vector.js
// Upload + Preview + API Vectorize (badges/banners aware)

(function () {
  let booted = false;
  let currentFile = null;
  let previewURL = null;
  let lastSVG = "";

  const $ = (s, r = document) => r.querySelector(s);
  const fmtBytes = (b = 0) => {
    if (!b) return "0 B";
    const k = 1024, u = ["B","KB","MB","GB","TB"];
    const i = Math.floor(Math.log(b)/Math.log(k));
    return `${(b/Math.pow(k,i)).toFixed(i?1:0)} ${u[i]}`;
  };

  // ---------- UI helpers ----------
  function setMeta(text) { $("#file-meta") && ( $("#file-meta").textContent = text || "No file selected" ); }
  function showPreviewMsg(msg) {
    const box = $("#motif-preview");
    if (!box) return;
    box.innerHTML = `<span style="color:#777">${msg}</span>`;
  }
  function setSVGOutput(svgText) {
    lastSVG = svgText || "";
    // Code view (always)
    const out = $("#vector-output");
    if (out) out.textContent = lastSVG || "No output.";
    // Live preview (if container exists)
    const live = $("#svg-live");
    if (live) live.innerHTML = lastSVG || `<div style="color:#777">No SVG to preview.</div>`;
    // Buttons
    const enable = !!lastSVG;
    $("#btn-copy-svg")  && ($("#btn-copy-svg").disabled  = !enable);
    $("#btn-download-svg") && ($("#btn-download-svg").disabled = !enable);
  }

  // ---------- File preview ----------
  function clearPreview() {
    currentFile = null;
    if (previewURL) URL.revokeObjectURL(previewURL);
    previewURL = null;
    setMeta("No file selected");
    showPreviewMsg("Selected image preview will appear here");
    setSVGOutput("");
  }

  function previewFile(file) {
    if (!file) return;
    currentFile = file;
    setMeta(`${file.name} • ${fmtBytes(file.size)}`);
    const isRaster = /image\/(png|jpeg|webp|gif)/.test(file.type);
    const isSVG = file.type === "image/svg+xml";

    if (previewURL) URL.revokeObjectURL(previewURL);
    if (isRaster) {
      previewURL = URL.createObjectURL(file);
      const pv = $("#motif-preview");
      if (pv) {
        pv.innerHTML = "";
        const img = new Image();
        img.alt = file.name;
        img.onload = () => URL.revokeObjectURL(previewURL);
        img.src = previewURL;
        pv.appendChild(img);
      }
    } else if (isSVG) {
      // simple message for uploaded SVG
      showPreviewMsg("SVG selected (will send to API as-is).");
    } else {
      showPreviewMsg("Unsupported file. Please use PNG/JPG/WebP/SVG.");
    }
    setSVGOutput(""); // reset output
  }

  // ---------- API: /api/vectorize ----------
  async function vectorizeViaAPI(file) {
    // Build form-data: the backend can use these keys to shape the output
    const fd = new FormData();
    fd.append("image", file);
    fd.append("layout", "badges_banners");     // ← your requirement
    // Optional knobs (uncomment if your API supports them)
    // fd.append("max_width", "1200");
    // fd.append("colors", "1");               // 1-bit
    // fd.append("smoothing", "low");

    const res = await fetch("/api/vectorize", { method: "POST", body: fd });

    // Try to handle both JSON and raw SVG
    const ctype = res.headers.get("content-type") || "";
    if (!res.ok) {
      const msg = await res.text().catch(() => "");
      throw new Error(`Server ${res.status}: ${msg || "vectorize failed"}`);
    }

    if (ctype.includes("application/json")) {
      const data = await res.json();
      // Shapes the API might return:
      // { svg: "<svg.../>" }
      // { badges: ["<svg...>","..."], banners: ["<svg...>"] }
      // Combine badges/banners into one SVG if needed
      if (data.svg) return data.svg;

      const parts = [];
      if (Array.isArray(data.badges))  parts.push(`<g id="badges">${data.badges.join("\n")}</g>`);
      if (Array.isArray(data.banners)) parts.push(`<g id="banners">${data.banners.join("\n")}</g>`);

      if (parts.length) {
        // Wrap into a single SVG canvas
        const svg =
`<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1024 1024" width="1024" height="1024">
  ${parts.join("\n  ")}
</svg>`;
        return svg;
      }
      // Fallback: stringify whatever we got
      return `<svg xmlns="http://www.w3.org/2000/svg" width="800" height="200"><text x="10" y="24" font-size="20">No svg field; raw JSON shown in code box</text></svg>`;
    }

    // Raw SVG (text/xml or image/svg+xml)
    const text = await res.text();
    return text;
  }

  // ---------- Actions ----------
  async function onVectorize() {
  const btn = $("#btn-vectorize");
  if (!currentFile) { alert("Please choose an image first."); return; }

  if (btn) { btn.disabled = true; btn.dataset.old = btn.textContent; btn.textContent = "Generating…"; }
  setSVGOutput("Processing…"); // we’ll repurpose this area for status text

  try {
    const fd = new FormData();
    fd.append("image", currentFile);
    fd.append("style", "mono");        // mono | duotone | color
    fd.append("background", "white");  // white | transparent
    const res = await fetch("/api/vector-sprites", { method: "POST", body: fd });
    if (!res.ok) throw new Error(`Server ${res.status}`);
    const data = await res.json();

    // show generated sheet image (prefer b64 so no CORS/cache issues)
    const out = document.getElementById("svg-live") || document.getElementById("motif-preview");
    if (out) {
      const url = data.b64 ? `data:image/png;base64,${data.b64}` : (data.url || "");
      out.innerHTML = url ? `<img alt="sprite sheet" src="${url}" style="max-width:100%;height:auto;border-radius:12px;">`
                          : `<div style="color:#777">No image returned.</div>`;
    }

    // Put description & prompt in the code box so you can copy
    const code = document.getElementById("vector-output");
    if (code) {
      code.textContent = JSON.stringify({
        description: data.description,
        prompt: data.prompt,
        url: data.url || null
      }, null, 2);
    }

    // Copy/Download buttons now operate on the PNG, not SVG
    const copyBtn = document.getElementById("btn-copy-svg");
    const dlBtn = document.getElementById("btn-download-svg");
    copyBtn && (copyBtn.disabled = true); // copying big PNG as text is useless
    if (dlBtn) {
      dlBtn.disabled = false;
      dlBtn.onclick = () => {
        const href = data.b64 ? `data:image/png;base64,${data.b64}` : (data.url || "");
        if (!href) return;
        const a = document.createElement("a");
        a.href = href;
        a.download = "vector-sprite-sheet.png";
        document.body.appendChild(a); a.click(); a.remove();
      };
    }
  } catch (err) {
    console.error(err);
    setSVGOutput("Error: " + (err?.message || err));
  } finally {
    if (btn) { btn.disabled = false; btn.textContent = btn.dataset.old || "Vectorize"; }
  }
}


  function onDownload() {
    if (!lastSVG) return;
    const blob = new Blob([lastSVG], { type: "image/svg+xml" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = (currentFile?.name || "vector").replace(/\.[^.]+$/, "") + ".svg";
    document.body.appendChild(a);
    a.click(); a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 350);
  }

  // ---------- Wiring ----------
  function wire() {
    const dz = $("#motif-dropzone");
    const input = $("#motif-input");

    // Picker
    dz && dz.addEventListener("click", () => input && input.click());
    dz && dz.addEventListener("keypress", (e) => {
      if (e.key === "Enter" || e.key === " ") { e.preventDefault(); input && input.click(); }
    });

    // Drag & drop
    ["dragenter", "dragover"].forEach(t => dz && dz.addEventListener(t, e => { e.preventDefault(); dz.classList.add("dragover"); }));
    ["dragleave", "drop"].forEach(t => dz && dz.addEventListener(t, e => { e.preventDefault(); dz.classList.remove("dragover"); }));
    dz && dz.addEventListener("drop", e => {
      const f = e.dataTransfer?.files?.[0];
      if (f) previewFile(f);
    });

    // Input change
    input && input.addEventListener("change", () => {
      const f = input.files?.[0];
      if (f) previewFile(f);
    });

    // Buttons
    $("#btn-vectorize")   && $("#btn-vectorize").addEventListener("click", onVectorize);
    $("#btn-clear")       && $("#btn-clear").addEventListener("click", clearPreview);
    $("#btn-copy-svg")    && $("#btn-copy-svg").addEventListener("click", onCopy);
    $("#btn-download-svg")&& $("#btn-download-svg").addEventListener("click", onDownload);
  }

  function init() {
    if (booted) return;
    booted = true;
    wire();
    clearPreview();
  }

  document.addEventListener("DOMContentLoaded", init);
})();
