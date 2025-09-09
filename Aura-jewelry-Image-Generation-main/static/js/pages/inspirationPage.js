// static/js/pages/inspirationPage.js
import { byId, fetchJSON } from "../core/utils.js";

// Endpoint from <meta> if present; fallback to default
const API_SKETCH =
  document.querySelector('meta[name="api-generate-from-sketch"]')?.content ||
  "/generate_from_sketch";

function setBusy(btn, busy) {
  if (!btn) return;
  btn.disabled = !!busy;
  btn.textContent = busy ? "Generating…" : "Generate Image 🚀";
}

function showResult(imgSrc, promptText) {
  const box = byId("sketchResult");
  const img = byId("sketchPreviewImage");
  const p   = byId("sketchPrompt");
  if (imgSrc) img.src = imgSrc;
  p.textContent = promptText || "";
  box.style.display = "block";
}

export function initInspiration() {
  if ((document.body?.dataset?.page || "") !== "inspiration") return;

  const fileInput = byId("sketchUpload");
  const typeSel   = byId("jewelryType");
  const genBtn    = byId("generateSketchBtn");
  const saveBtn   = byId("saveToGalleryBtn");

  if (!fileInput || !typeSel || !genBtn) return;

  // Optional: preview the uploaded sketch in-console for sanity
  fileInput.addEventListener("change", () => {
    if (fileInput.files?.[0]) console.debug("[sketch] file selected:", fileInput.files[0].name);
  });

  genBtn.addEventListener("click", async (e) => {
    e.preventDefault();
    if (genBtn.disabled) return;

    const file = fileInput.files?.[0];
    const jt   = typeSel.value;
    if (!file)   return alert("Please upload a sketch image.");
    if (!jt)     return alert("Please choose a jewelry type.");

    const fd = new FormData();
    fd.append("sketch", file);
    fd.append("type", jt);

    setBusy(genBtn, true);
    showResult("", ""); // clear

    try {
      const data = await fetchJSON(API_SKETCH, { method: "POST", body: fd });
      // Server may return base64 "image" or a direct URL "file_path"
      const src = data.image ? `data:image/png;base64,${data.image}` : (data.file_path || "");
      const prompt = data.prompt || data.generated_prompt || "";
      if (!src) throw new Error("No image returned from server.");
      showResult(src, prompt);
    } catch (err) {
      console.error(err);
      alert(err.message || "Failed to generate from sketch. Check server logs.");
    } finally {
      setBusy(genBtn, false);
    }
  });

  // For now (no backend write yet): save = download + copy prompt
  saveBtn?.addEventListener("click", async () => {
    const img = byId("sketchPreviewImage");
    const prompt = byId("sketchPrompt")?.textContent || "";
    if (!img?.src) return alert("Generate an image first.");

    // Download image
    const a = document.createElement("a");
    a.href = img.src;
    a.download = "jewelgen_sketch_render.png";
    document.body.appendChild(a);
    a.click();
    setTimeout(() => a.remove(), 0);

    // Copy prompt
    if (prompt) {
      await navigator.clipboard.writeText(prompt).catch(()=>{});
    }
  });
}
