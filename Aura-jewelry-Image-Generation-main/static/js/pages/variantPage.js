import { byId } from "../core/utils.js";

(function init() {
  // Initialize if we're on the variants page OR if the upload UI exists.
  const pageOk = (document.body.dataset.page || "") === "variants";
  if (!pageOk && !byId("uploadBox")) return;

  const uploadBox   = byId("uploadBox");
  const fileInput   = byId("baseImage");
  const fileMeta    = byId("file-meta");
  const previewBox  = byId("imagePreview");
  const resultsGrid = byId("resultsGrid");
  const generateBtn = byId("generateVariants");

  function setPreviewEmpty() {
    previewBox.innerHTML = `<span class="vx-subtle">Selected image preview will appear here</span>`;
    if (fileMeta) fileMeta.textContent = "No file selected";
  }

  function showPreview(file) {
    if (!file || !file.type.startsWith("image/")) { setPreviewEmpty(); return; }
    const reader = new FileReader();
    reader.onload = e => {
      const img = new Image();
      img.onload = () => {
        previewBox.innerHTML = "";
        previewBox.appendChild(img);
        if (fileMeta) fileMeta.textContent = `${file.name} — ${img.naturalWidth}×${img.naturalHeight}`;
      };
      img.alt = "Uploaded preview";
      img.src = e.target.result;
    };
    reader.readAsDataURL(file);
  }

  // Click to open file dialog
  uploadBox.addEventListener("click", () => fileInput.click());
  uploadBox.addEventListener("keydown", (e) => {
    if (e.key === "Enter" || e.key === " ") { e.preventDefault(); fileInput.click(); }
  });

  // Native input change
  fileInput.addEventListener("change", () => {
    const f = fileInput.files && fileInput.files[0];
    showPreview(f);
  });

  // Drag & drop
  ["dragenter","dragover"].forEach(evt =>
    uploadBox.addEventListener(evt, e => { e.preventDefault(); uploadBox.classList.add("dragover"); })
  );
  ["dragleave","dragexit","drop"].forEach(evt =>
    uploadBox.addEventListener(evt, e => { e.preventDefault(); uploadBox.classList.remove("dragover"); })
  );
  uploadBox.addEventListener("drop", e => {
    const files = e.dataTransfer?.files;
    if (files && files.length) {
      fileInput.files = files;           // keep input in sync
      showPreview(files[0]);
    }
  });

  // Generate Variants
  async function generateVariants() {
    const formData = new FormData();
    if (fileInput.files[0]) formData.append("base_image", fileInput.files[0]);
    formData.append("base_type", byId("baseType").value);
    formData.append("base_motif", byId("baseMotif").value);
    formData.append("metal", byId("metal").value);
    formData.append("stone", byId("stone").value);
    formData.append("weight_target", byId("weightTarget").value);

    const targets = Array.from(document.querySelectorAll("input[name='targets']:checked"))
      .map(cb => cb.value);
    formData.append("targets", JSON.stringify(targets));

    try {
      generateBtn.disabled = true;
      const oldTxt = generateBtn.textContent;
      generateBtn.textContent = "Generating…";

      const res = await fetch("/api/design-variants", { method:"POST", body: formData });
      if (!res.ok) throw new Error("Failed to generate variants");
      const data = await res.json();

      resultsGrid.innerHTML = (data.variants || []).map(v =>
        `<div>
           <img src="${v.url}" alt="${v.label}">
           <p class="vx-subtle" style="margin:6px 0 0;">${v.label}</p>
         </div>`
      ).join("") || `<p class="vx-subtle">No variants returned.</p>`;

      generateBtn.textContent = oldTxt;
      generateBtn.disabled = false;
    } catch (err) {
      resultsGrid.innerHTML = `<p style="color:#c0392b;">${err.message || "Error"}</p>`;
      generateBtn.disabled = false;
      generateBtn.textContent = "Generate Variants";
    }
  }

  generateBtn.addEventListener("click", generateVariants);

  // initial state
  setPreviewEmpty();
})();
