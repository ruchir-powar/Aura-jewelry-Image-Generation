// static/js/pages/variantPage.js
import { byId } from "../core/utils.js";

(function initVariants() {
  // only run on Variants page (or if the drop zone exists)
  const pageOk = (document.body.dataset.page || "") === "variants";
  if (!pageOk && !byId("dropZone")) return;

  // elements
  const dropZone        = byId("dropZone");
  const fileInput       = byId("base_image");
  const fileMeta        = byId("file-meta");
  const previewBox      = byId("previewBox");
  const previewImg      = byId("previewImg");
  const clearPreviewBtn = byId("clearPreviewBtn");
  const resultsGrid     = byId("resultsGrid");
  const generateBtn     = byId("generateVariants");

  // form controls
  const baseType      = byId("baseType");
  const baseMotif     = byId("baseMotif");
  const metalSel      = byId("metal");
  const stoneSel      = byId("stone");
  const weightTarget  = byId("weightTarget");

  // helpers
  function setPreviewEmpty() {
    if (previewImg) previewImg.src = "";
    if (previewBox) previewBox.classList.add("hidden");
    if (fileMeta) fileMeta.textContent = "No file selected";
  }

  function showPreview(file) {
    if (!file || !file.type?.startsWith?.("image/")) {
      setPreviewEmpty();
      return;
    }
    const url = URL.createObjectURL(file);
    previewImg.onload = () => {
      if (fileMeta) {
        fileMeta.textContent = `${file.name} — ${previewImg.naturalWidth}×${previewImg.naturalHeight}`;
      }
      URL.revokeObjectURL(url);
    };
    previewImg.alt = "Selected motif preview";
    previewImg.src = url;
    previewBox.classList.remove("hidden");
  }

  // events — open file picker
  dropZone.addEventListener("click", () => fileInput.click());
  dropZone.addEventListener("keydown", (e) => {
    if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      fileInput.click();
    }
  });

  // input change
  fileInput.addEventListener("change", () => {
    const f = fileInput.files?.[0];
    showPreview(f);
  });

  // drag & drop
  ["dragenter", "dragover"].forEach(evt =>
    dropZone.addEventListener(evt, (e) => {
      e.preventDefault();
      e.stopPropagation();
      dropZone.classList.add("dragover");
    })
  );
  ["dragleave", "dragexit", "drop"].forEach(evt =>
    dropZone.addEventListener(evt, (e) => {
      e.preventDefault();
      e.stopPropagation();
      dropZone.classList.remove("dragover");
    })
  );
  dropZone.addEventListener("drop", (e) => {
    const files = e.dataTransfer?.files;
    if (files && files.length) {
      fileInput.files = files; // keep input in sync for FormData
      showPreview(files[0]);
    }
  });

  // clear preview
  clearPreviewBtn.addEventListener("click", () => {
    fileInput.value = "";
    setPreviewEmpty();
    dropZone.focus();
  });

  // render results
  function renderResults(list = []) {
    if (!list.length) {
      resultsGrid.innerHTML = `<p class="vx-subtle">No variants returned.</p>`;
      return;
    }
    resultsGrid.innerHTML = list.map((v) => `
      <figure>
        <img src="${v.url}" alt="${v.label}">
        <figcaption>${v.label}</figcaption>
      </figure>
    `).join("");
  }

  // request builder
  function buildFormData() {
    const fd = new FormData();
    const file = fileInput.files?.[0];
    if (file) fd.append("base_image", file);

    fd.append("base_type", baseType.value);
    fd.append("base_motif", baseMotif.value.trim());
    fd.append("metal", metalSel.value);
    fd.append("stone", stoneSel.value);
    fd.append("weight_target", weightTarget.value);

    const targets = Array.from(document.querySelectorAll("input[name='targets']:checked"))
      .map(cb => cb.value);
    fd.append("targets", JSON.stringify(targets));
    return fd;
  }

  async function generateVariants() {
    const formData = buildFormData();
    const oldTxt = generateBtn.textContent;
    try {
      generateBtn.disabled = true;
      generateBtn.textContent = "Generating…";

      const res = await fetch("/api/design-variants", { method: "POST", body: formData });
      if (!res.ok) throw new Error(`Server error (${res.status})`);
      const data = await res.json();

      renderResults(data?.variants || []);
    } catch (err) {
      resultsGrid.innerHTML = `<p style="color:#c0392b;">${err?.message || "Failed to generate variants."}</p>`;
    } finally {
      generateBtn.textContent = oldTxt;
      generateBtn.disabled = false;
    }
  }

  generateBtn.addEventListener("click", generateVariants);

  // init state
  setPreviewEmpty();
})();
