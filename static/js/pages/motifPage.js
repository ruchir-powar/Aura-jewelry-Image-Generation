// static/js/pages/motifPage.js
import { byId, fetchJSON } from "../core/utils.js";

(function initMotif() {
  const page = document.body?.dataset?.page || "";
  if (page && page !== "motif") return;
  if (!byId("motifUpload")) return;

  // ---------- Elements ----------
  const fileInput  = byId("motifUpload");
  const dropzone   = byId("motifDrop");
  const chooseBtn  = byId("chooseFileBtn");
  const previewImg = byId("motifPreviewImage");
  const noPreview  = byId("noPreview");

  const fileMeta   = byId("fileMeta");
  const fileNameEl = byId("fileName");
  const fileSizeEl = byId("fileSize");
  const fileDimsEl = byId("fileDims");

  const descBox    = byId("extractedDescription");
  const promptBox  = byId("generatedMotifPrompt");

  const genBtn     = byId("generateMotif");
  const useBtn     = byId("useMotifPromptBtn");

  // NEW: user-selected jewelry type
  const typeSel    = byId("motifJewelryType");

  // Right preview (generated)
  const resultImg  = byId("motifResultImage");
  const noResult   = byId("noResult");

  // ---------- Endpoints ----------
  const API_PROMPTS =
    document.querySelector('meta[name="api-generate-prompts"]')?.content || "/generate_prompts";
  const API_GENERATE =
    document.querySelector('meta[name="api-generate"]')?.content || "/generate";

  // ---------- Helpers ----------
  function setBusy(btn, on, busyText, idleText) {
    if (!btn) return;
    btn.disabled = !!on;
    if (busyText || idleText) btn.textContent = on ? (busyText || "Working…") : (idleText || "Generate");
  }

  function handleFile(file) {
    if (!file) return;
    if (fileNameEl) fileNameEl.textContent = file.name || "image";
    if (fileSizeEl) fileSizeEl.textContent = (file.size / 1024 / 1024).toFixed(2) + " MB";

    const reader = new FileReader();
    reader.onload = (e) => {
      const dataURL = e.target.result;
      if (previewImg) {
        previewImg.src = dataURL;
        previewImg.style.display = "block";
      }
      if (noPreview) noPreview.style.display = "none";

      const probe = new Image();
      probe.onload = () => {
        if (fileDimsEl) fileDimsEl.textContent = `${probe.width} × ${probe.height}`;
        if (fileMeta) fileMeta.style.display = "block";
      };
      probe.src = dataURL;
    };
    reader.readAsDataURL(file);
  }

  // ---------- File selection & Drag-drop ----------
  chooseBtn?.addEventListener("click", () => fileInput?.click());
  fileInput?.addEventListener("change", () => handleFile(fileInput.files?.[0]));

  if (dropzone && fileInput) {
    const hi = (on) => (dropzone.style.background = on ? "#fff8db" : "");
    ["dragenter", "dragover"].forEach((ev) =>
      dropzone.addEventListener(ev, (e) => { e.preventDefault(); hi(true); })
    );
    ["dragleave", "dragexit", "drop"].forEach((ev) =>
      dropzone.addEventListener(ev, (e) => { e.preventDefault(); hi(false); })
    );
    dropzone.addEventListener("drop", (e) => {
      const files = e.dataTransfer?.files;
      if (files && files.length) {
        fileInput.files = files;
        handleFile(files[0]);
      }
    });
    dropzone.addEventListener("click", () => fileInput.click());
  }

  // ---------- Generate Description & Prompt ----------
  genBtn?.addEventListener("click", async (e) => {
    e.preventDefault();
    const file = fileInput?.files?.[0];
    if (!file) return alert("Please upload a motif image first.");

    const fd = new FormData();
    fd.append("image", file);  // our backend supports "image" or "motif"
    fd.append("motif", file);
    const jt = (typeSel?.value || "").trim();
    if (jt) fd.append("use_case", jt); // tell backend what jewelry to design

    setBusy(genBtn, true, "Generating...", "Generate Description & Prompt");
    descBox && (descBox.value = "");
    promptBox && (promptBox.value = "");

    try {
      const data = await fetchJSON(API_PROMPTS, { method: "POST", body: fd });
      descBox && (descBox.value   = data.description || "(no description)");
      promptBox && (promptBox.value = data.prompt || "(no prompt)");
    } catch (err) {
      console.error("[motif] /generate_prompts failed:", err);
      alert(err.message || "Failed to analyze motif.");
    } finally {
      setBusy(genBtn, false, "", "Generate Description & Prompt");
    }
  });

  // ---------- Use This Prompt → generate image ----------
  async function useMotifPrompt() {
    const prompt = (promptBox?.value || "").trim();
    if (!prompt) return alert("No prompt available yet.");
    const jt = (typeSel?.value || "").trim(); // pass to backend so it renders that jewelry

    setBusy(useBtn, true, "Generating...", "Use This Prompt");
    try {
      const res = await fetchJSON(API_GENERATE, {
        method: "POST",
        headers: { Accept: "application/json", "Content-Type": "application/json" },
        body: JSON.stringify({
          prompt,
          jewelry_type: jt || undefined,  // optional
          album: "index"                  // keep gallery grouping consistent
        }),
      });

      const src = res.file_path || (res.image ? `data:image/png;base64,${res.image}` : "");
      if (src && resultImg) {
        resultImg.src = src;
        resultImg.alt = "Generated Jewelry";
        resultImg.style.display = "block";
        noResult && (noResult.style.display = "none");
      }
      // hand off for Home page if needed
      localStorage.setItem("motifPrompt", prompt);
    } catch (err) {
      console.error("[motif] /generate failed:", err);
      alert(err.message || "Failed to generate image from prompt.");
    } finally {
      setBusy(useBtn, false, "", "Use This Prompt");
    }
  }
  useBtn?.addEventListener("click", useMotifPrompt);
})();
