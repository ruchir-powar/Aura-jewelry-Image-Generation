// static/script.js
window.addEventListener("DOMContentLoaded", () => {
  const PAGE = document.body?.dataset?.page || "";

  // ────────────────────────────────────────────────────────────
  // Utilities
  // ────────────────────────────────────────────────────────────
  const byId = (id) => document.getElementById(id);
  const getValue = (id) => byId(id)?.value?.trim() || "";

  async function fetchJSON(url, options) {
    const res = await fetch(url, options);
    const text = await res.text();
    if (!res.ok) {
      const snippet = text.slice(0, 200);
      throw new Error(`HTTP ${res.status} ${res.statusText} at ${url} — ${snippet}`);
    }
    try { return JSON.parse(text); }
    catch {
      const snippet = text.slice(0, 200);
      throw new Error(`Non-JSON response from ${url}: ${snippet}`);
    }
  }

  function convertLabelToId(label) {
    return label
      .replace(/’/g, "")
      .replace(/[^a-zA-Z0-9]/g, " ")
      .split(" ")
      .map((word, idx) =>
        idx === 0 ? word.toLowerCase()
                  : word.charAt(0).toUpperCase() + word.slice(1).toLowerCase()
      )
      .join("");
  }

  function fillSelect(el, items) {
    if (!el) return;
    el.innerHTML = `<option value="">-- Select --</option>`;
    items.forEach((v) => {
      const opt = document.createElement("option");
      opt.value = opt.textContent = v;
      el.appendChild(opt);
    });
  }

  // ────────────────────────────────────────────────────────────
  // Variation hints (for parallel multi-gen)
  // ────────────────────────────────────────────────────────────
  const VARIATION_HINTS = [
    "composition micro-shift: centered slightly left; add subtle negative space on right",
    "composition micro-shift: centered slightly right; add subtle negative space on left",
    "framing tweak: minor zoom-in (~8–10%) to emphasize detail; keep front view",
    "framing tweak: minor zoom-out (~8–10%) to show a touch more context; keep front view",
    "lighting change: soft key from upper-left with gentle fill; avoid hotspots",
    "lighting change: soft key from upper-right with subtle rim light; controlled highlights",
    "shadow treatment: slightly softer ground shadow; preserve clean white background",
    "shadow treatment: slightly crisper, tighter shadow under piece; still soft edges",
    "specular control: slightly reduce metal reflections to improve readability (no color shift)",
    "specular control: slightly increase specular highlights while retaining fine detail",
    "white-balance nuance: neutral-cool studio tone (no color cast on stones/metals)",
    "white-balance nuance: neutral-warm studio tone (no color cast on stones/metals)"
  ];

  // Build a human-readable lock list from current dropdown selections
  function buildLockedAttributesText() {
    const type       = getValue("jewelryType");
    const subcat     = getValue("jewelrySubCategory");
    const metal      = getValue("metalType");
    const style      = getValue("jewelryStyle");
    const gem        = getValue("gemstoneType");
    const shape      = getValue("diamondShape");
    const setting    = getValue("settingStyle");
    const arrangement= getValue("stoneArrangement");
    const carat      = getValue("caratWeight");
    const size       = getValue("sizeRange");
    const goldWeight = getValue("goldWeight");
    const numDiam    = getValue("numDiamonds");

    const locks = [];
    if (type)       locks.push(`jewelry type "${type}"`);
    if (subcat)     locks.push(`subcategory "${subcat}"`);
    if (metal)      locks.push(`metal "${metal}" (no plating/tint changes)`);
    if (style)      locks.push(`style "${style}"`);
    if (gem)        locks.push(`gemstone "${gem}"`);
    if (shape)      locks.push(`diamond shape "${shape}"`);
    if (setting)    locks.push(`setting "${setting}"`);
    if (arrangement)locks.push(`stone arrangement "${arrangement}"`);
    if (numDiam)    locks.push(`${numDiam} diamond${numDiam === "1" ? "" : "s"}`);
    if (carat)      locks.push(`total carat ${carat}`);
    if (goldWeight) locks.push(`gold weight ${goldWeight}`);
    if (size)       locks.push(`size ${size}`);

    if (!locks.length) return ""; // nothing to lock

    return ` Do not alter locked attributes: ${locks.join(", ")}. `
         + `Keep materials, colors, counts, proportions, geometry, stone sizes, and settings identical; `
         + `no motif/engraving changes.`;
  }

  // Build variant prompts while respecting locked attributes
  function buildPromptVariants(base, n, locksText = "") {
    const variants = [];
    for (let i = 0; i < n; i++) {
      const hint = VARIATION_HINTS[i % VARIATION_HINTS.length];
      const lock = locksText ? ` ${locksText}` : "";
      variants.push(
        `${base}${lock} Only vary non-substantive presentation aspects: ${hint}. `
        + `Keep front view on a clean white background. `
        + `Ensure absolutely no text, numbers, watermarks, grids, labels, or markings.`
      );
    }
    return variants;
  }

  // ────────────────────────────────────────────────────────────
  // Dropdown data (static lists)
  // ────────────────────────────────────────────────────────────
  const jewelryTypes = [
    "Ladies Rings","Men’s Ring","Earrings","Pendants","Round Bangles",
    "Oval Bangles","Men’s Wrist Wear","Bracelet","Necklace","Tanmaniyas"
  ];
  const attributeOptions = {
    "Metal Type": ["Gold (Yellow)","Gold (White)","Gold (Rose)","Platinum","Silver","Two-tone"],
    "Jewelry Style": ["Modern","Classic","Traditional","Contemporary"],
    "Gemstone Type": ["Diamond","Ruby","Sapphire","Emerald","Amethyst","Topaz"],
    "Diamond Shape": ["Round","Princess","Asscher","Cushion","Heart","Oval","Radiant","Emerald","Marquise","Pear","Baguette"],
    "Setting Style": ["Prong","Bezel","Channel","Pavé","Tension","Flush"],
    "Stone Arrangement": ["Single Stone","Cluster","Side Stones","Mix Sieve"],
    // Keep Carat Weight as a simple static list (no sieve linkage)
    "Carat Weight": ["0 - 0.10 cts","0.11 - 0.25 cts","0.26 - 0.50 cts","0.51 - 1.00 cts"],
    "Size Range": ["Small","Medium","Large","11 mm"],
    "Gold Weight": ["2-4 gms","4-6 gms","8 gms","10 gms"]
  };
  const jewelryTypeToSubcategories = {
    "Ladies Rings": ["Crossover","Vanki","Eternity","Band","Engagement","Split"],
    "Men’s Ring": ["Band","2 stone","3 stone","4 stone","6 stone","9 stone","12 stone","Others / Basics"],
    "Earrings": ["Studs","Dangler","Chandeliar","Chandbali","Bali","J Bali","Jhumki","Ear Cuff","Sui Dhaga","Multiwear","Hoops"],
    "Pendants": ["Multiwear","Lariat","Kids","Religious"],
    "Round Bangles": ["Eternity","Pacheli","Station","Jali"],
    "Oval Bangles": ["Station","Filigree","Bypass","Tube","Jali","Flexi"],
    "Men’s Wrist Wear": ["Kadas","Cuban Chains","Mens Bracelets"],
    "Bracelet": ["Tennis","Bolo","Charms","Mangalsutra","Others / Basics","Kids","Chain"],
    "Necklace": ["Haraam","Strings","Station","Mini Choker","Choker","Belt","Multiwear","Lariat","Layers","Hasli","Assymetric","Pendant style","Spread"],
    "Tanmaniyas": ["Necklace Style","Haraam","Watimani","Thali","Lariat","Murtamani","Pendant Style","Multiwear","Patta"]
  };

  // ────────────────────────────────────────────────────────────
  // INDEX PAGE
  // ────────────────────────────────────────────────────────────
  function initIndex() {
    if (PAGE !== "index") return;

    // Populate top-level jewelry types
    const jt = byId("jewelryType");
    if (jt) {
      jt.innerHTML = `<option value="">-- Select --</option>`;
      jewelryTypes.forEach((type) => {
        const opt = document.createElement("option");
        opt.value = opt.textContent = type;
        jt.appendChild(opt);
      });
    }

    // Populate attribute dropdowns present in the HTML
    for (const [label, options] of Object.entries(attributeOptions)) {
      const id = convertLabelToId(label);   // e.g., "Metal Type" -> "metalType"
      const dropdown = byId(id);
      if (!dropdown) continue;
      fillSelect(dropdown, options);
    }

    // Sub-categories
    byId("jewelryType")?.addEventListener("change", () => {
      const type = byId("jewelryType").value;
      const sub = byId("jewelrySubCategory");
      if (!sub) return;
      sub.innerHTML = `<option value="">-- Select --</option>`;
      (jewelryTypeToSubcategories[type] || []).forEach((s) => {
        const opt = document.createElement("option");
        opt.value = opt.textContent = s;
        sub.appendChild(opt);
      });
    });

    // Image count dropdown (ensure 1–4)
    const imgCount = byId("imageCount");
    if (imgCount && !imgCount.options.length) {
      fillSelect(imgCount, ["1","2","3","4"]);
      imgCount.value = "1";
    }

    // ── Prompt builder (EXCLUDES commented-out fields: gender, occasion, age, sieve, shank, engraving)
    function generatePrompt() {
      const type       = getValue("jewelryType");
      const subcat     = getValue("jewelrySubCategory");
      const metal      = getValue("metalType");
      const style      = getValue("jewelryStyle");
      const gem        = getValue("gemstoneType");
      const shape      = getValue("diamondShape");
      const setting    = getValue("settingStyle");
      const arrangement= getValue("stoneArrangement");
      const carat      = getValue("caratWeight");
      const size       = getValue("sizeRange");
      const goldWeight = getValue("goldWeight");
      const numDiam    = getValue("numDiamonds"); // NEW

      let prompt = `Lightweight`;
      if (type)   prompt += ` ${type.toLowerCase()}`;
      if (subcat) prompt += ` (${subcat.toLowerCase()})`;

      if (metal) prompt += ` crafted in ${metal.toLowerCase()}`;
      prompt += ` with a high-polish finish`;

      if (gem) {
        prompt += `, featuring ${gem.toLowerCase()}`;
        if (shape) prompt += ` in a ${shape.toLowerCase()} cut`;
      }
      if (setting)     prompt += `, set using a ${setting.toLowerCase()} setting`;
      if (arrangement) prompt += `, arranged in ${arrangement.toLowerCase()}`;

      if (numDiam) prompt += `, using ${numDiam} diamond${numDiam === "1" ? "" : "s"}`;
      if (carat)   prompt += ` totaling ${carat}`;
      if (goldWeight) prompt += `, with a gold weight of ${goldWeight}`;

      if (style || size) {
        prompt += `. Designed`;
        if (style) prompt += ` in a ${style.toLowerCase()} style`;
        if (size)  prompt += `, size ${size.toLowerCase()}`;
      }

      // Render constraints & no-text rule
      prompt += `. Hyper-realistic render, front view on a pure white background under studio lighting, accurate metal/stone reflections; ensure there is absolutely no text, numbers, watermarks, grids, labels, or markings on the image.`;

      // Capitalize first character
      prompt = prompt.charAt(0).toUpperCase() + prompt.slice(1);

      byId("promptBox").value = prompt;
      const fp = byId("finalPrompt");
      if (fp) fp.value = prompt;
      return prompt;
    }
    window.generatePrompt = generatePrompt;

    byId("generateBtn")?.addEventListener("click", (e) => {
      e.preventDefault();
      generatePrompt();
    });

    // ── Preview frame replication helpers (2×2 grid of 300×300 frames)
    const container = byId("previewContainer");

    function ensureFrames(n) {
      const need = Math.max(1, Math.min(4, parseInt(n || 1, 10)));
      // create missing
      while (container.children.length < need) {
        const idx = container.children.length;
        const frame = document.createElement("div");
        frame.className = "preview-frame";
        frame.id = `previewFrame-${idx}`;
        container.appendChild(frame);
      }
      // remove extras
      while (container.children.length > need) {
        container.removeChild(container.lastElementChild);
      }
      // always clear content for generation
      Array.from(container.children).forEach((f) => (f.innerHTML = ""));
    }

    function setPlaceholder(i, text = "Generating…") {
      const frame = container.children[i];
      if (!frame) return;
      const ph = document.createElement("div");
      ph.className = "ph";
      ph.textContent = text;
      frame.appendChild(ph);
    }

    function setImage(i, src) {
      const frame = container.children[i];
      if (!frame) return;
      frame.innerHTML = "";
      const img = document.createElement("img");
      img.alt = `Generated ${i + 1}`;
      img.src = src;
      frame.appendChild(img);
    }

    // file input → preview first box only (initial single state)
    byId("imageInput")?.addEventListener("change", (e) => {
      const file = e.target.files?.[0];
      const img0 = byId("previewImage");
      if (!file || !img0) return;
      const reader = new FileReader();
      reader.onload = (ev) => (img0.src = ev.target.result);
      reader.readAsDataURL(file);
    });

    byId("copyPromptBtn")?.addEventListener("click", async () => {
      const text = byId("finalPrompt")?.value || byId("promptBox")?.value || "";
      if (!text) return;
      try {
        await navigator.clipboard.writeText(text);
        const btn = byId("copyPromptBtn");
        if (btn) {
          const old = btn.textContent;
          btn.textContent = "Copied!";
          setTimeout(() => (btn.textContent = old), 1200);
        }
      } catch {}

    });

    // === Download helpers (multi-image aware) ===
    function collectPreviewImages() {
      const container = byId("previewContainer");
      if (!container) return [];
      return Array.from(container.querySelectorAll(".preview-frame img"))
        .filter(img => img.src && (img.src.startsWith("data:image") || img.src.startsWith("http")));
    }

    function filenameFromSrc(src, index) {
      const pad = String(index + 1).padStart(2, "0");
      // Try to keep original filename if it came from /static
      try {
        const u = new URL(src, location.origin);
        const last = u.pathname.split("/").pop();
        if (last && /\.[a-z]{3,4}$/i.test(last)) return last;
      } catch {}
      return `jewelry_design_${pad}.png`;
    }

    function triggerDownload(src, filename) {
      const a = document.createElement("a");
      a.href = src;
      a.download = filename || "jewelry_design.png";
      document.body.appendChild(a);
      a.click();
      setTimeout(() => document.body.removeChild(a), 0);
    }

    // Optional: keep button label in sync (e.g., "Download 3 Images")
    function updateDownloadButtonLabel() {
      const dlBtn = byId("downloadImageBtn");
      if (!dlBtn) return;
      const imgs = collectPreviewImages();
      dlBtn.textContent = imgs.length > 1 ? `Download ${imgs.length} Images` : "Download Image";
    }

    // New downloader: works for 1 or many frames
    function downloadImage() {
      const imgs = collectPreviewImages();
      if (imgs.length === 0) {
        alert("No image to download.");
        return;
      }
      if (imgs.length === 1) {
        const src = imgs[0].src;
        triggerDownload(src, filenameFromSrc(src, 0));
        return;
      }
      // Multiple: download all (staggered to avoid browser blocking)
      imgs.forEach((img, i) => {
        const src = img.src;
        const name = filenameFromSrc(src, i);
        setTimeout(() => triggerDownload(src, name), i * 250);
      });
    }

    window.downloadImage = downloadImage;
    byId("downloadImageBtn")?.addEventListener("click", downloadImage);

    // === Generate 1–4 images (parallel) and replicate frames dynamically
    async function generateImage() {
      const basePrompt = (byId("promptBox")?.value || "").trim() || generatePrompt();
      const finalPrompt = byId("finalPrompt");
      const button = byId("generateJewelryBtn") || document.querySelector('button[onclick="generateImage()"]');
      const count = Math.max(1, Math.min(4, parseInt(byId("imageCount")?.value || "1", 10)));

      // Build frames (keeps initial single look, then expands on demand)
      ensureFrames(count);
      for (let i = 0; i < count; i++) setPlaceholder(i);

      if (button) { button.disabled = true; button.innerText = (count === 1 ? "Generating..." : `Generating ${count}…`); }

      try {
        if (count === 1) {
          // Single request
          const data = await fetchJSON("/generate", {
            method: "POST",
            headers: { "Accept": "application/json", "Content-Type": "application/json" },
            body: JSON.stringify({ prompt: basePrompt })
          });
          const src = data.image ? `data:image/png;base64,${data.image}` : (data.file_path || "");
          if (!src) throw new Error("No image returned.");
          // Update frame-0; reuse #previewImage if still present
          const img0 = byId("previewImage");
          if (img0) img0.src = src; else setImage(0, src);
        } else {
          // Parallel requests for N frames (time ≈ t, not n·t)
          const locksText = buildLockedAttributesText();              // <— NEW
          const variants = buildPromptVariants(basePrompt, count, locksText); // <— NEW
          await Promise.all(variants.map((v, i) =>
            fetchJSON("/generate", {
              method: "POST",
              headers: { "Accept": "application/json", "Content-Type": "application/json" },
              body: JSON.stringify({ prompt: v })
            })
              .then((res) => {
                const src = res.image ? `data:image/png;base64,${res.image}` : res.file_path;
                if (src) setImage(i, src);
              })
              .catch(() => { setPlaceholder(i, "Failed"); })
          ));
        }

        if (finalPrompt) finalPrompt.value = basePrompt;
      } catch (err) {
        console.error("Generation error:", err);
        alert(err.message || "Failed to generate image(s).");
      } finally {
        if (button) { button.disabled = false; button.innerText = "Generate Jewelry"; }
      }
    }

    window.generateImage = generateImage;
    byId("generateJewelryBtn")?.addEventListener("click", (e) => {
      e.preventDefault();
      generateImage();
    });
  }

  // ────────────────────────────────────────────────────────────
  // MOTIF PAGE (unchanged)
  // ────────────────────────────────────────────────────────────
  function initMotif() {
    if (PAGE !== "motif") return;

    const byId = (id) => document.getElementById(id);
    const genBtn = byId("generateMotif");

    genBtn?.addEventListener("click", async (e) => {
      e.preventDefault();
      const fileInput = byId("motifUpload");
      const useCaseSelect = byId("motifUseCase");
      const file = fileInput?.files?.[0];
      const use_case = useCaseSelect?.value || "";

      if (!file) { alert("Please upload a motif image."); return; }

      const formData = new FormData();
      formData.append("image", file);
      formData.append("use_case", use_case);

      const endpoint =
        genBtn?.dataset?.url ||
        document.querySelector('meta[name="api-generate-prompts"]')?.content ||
        "/generate_prompts";

      genBtn.disabled = true;
      genBtn.innerText = "Generating...";

      try {
        const data = await fetchJSON(endpoint, { method: "POST", body: formData });
        if (byId("extractedDescription")) byId("extractedDescription").value = data.description || "";
        if (byId("generatedMotifPrompt")) byId("generatedMotifPrompt").value = data.prompt || "";
      } catch (err) {
        console.error("Motif prompt error:", err);
        alert(err.message || "Failed to generate prompt from image.");
      } finally {
        genBtn.disabled = false;
        genBtn.innerText = "Generate Description & Prompt";
      }
    });

    byId("motifUpload")?.addEventListener("change", (e) => {
      const file = e.target.files?.[0];
      const preview = byId("motifPreviewImage");
      if (!file || !preview) return;
      const reader = new FileReader();
      reader.onload = (ev) => (preview.src = ev.target.result);
      reader.readAsDataURL(file);
    });

    async function useMotifPrompt() {
      const button = byId("useMotifPromptBtn") || document.querySelector('button[onclick="useMotifPrompt()"]');
      const prompt = byId("generatedMotifPrompt")?.value?.trim();
      if (!prompt) { alert("No prompt to use."); return; }
      if (button) { button.disabled = true; button.innerText = "Generating..."; button.classList.add("disabled"); }

      try {
        const apiGenerate = document.querySelector('meta[name="api-generate"]')?.content || "/generate";
        const data = await fetchJSON(api-generate, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ prompt })
        });
        const imageElement = byId("motifPreviewImage");
        const src = data.file_path || (data.image ? `data:image/png;base64,${data.image}` : "");
        if (imageElement && src) {
          imageElement.src = src;
          imageElement.alt = "Generated Jewelry";
          imageElement.style.display = "block";
        }
        localStorage.setItem("motifPrompt", prompt);
      } catch (err) {
        console.error("Image generation failed:", err);
        alert(err.message || "Failed to generate image from prompt.");
      } finally {
        if (button) { button.disabled = false; button.innerText = "Use This Prompt"; button.classList.remove("disabled"); }
      }
    }
    window.useMotifPrompt = useMotifPrompt;
    byId("useMotifPromptBtn")?.addEventListener("click", useMotifPrompt);
  }

  // ────────────────────────────────────────────────────────────
  // GALLERY PAGE
  // ────────────────────────────────────────────────────────────
  function initGallery() {
    if (PAGE !== "gallery") return;

    async function loadGalleryImages() {
      try {
        const images = await fetchJSON("/images");
        const container = byId("galleryItems");
        if (!container) return;
        container.innerHTML = "";
        images.forEach((url) => {
          const img = document.createElement("img");
          img.src = url;
          img.alt = "Generated jewelry";
          container.appendChild(img);
        });
      } catch (err) {
        console.error("Failed to load gallery images:", err);
      }
    }

    loadGalleryImages();
  }

  // ────────────────────────────────────────────────────────────
  // INSPIRATION PAGE (no-op)
  // ────────────────────────────────────────────────────────────
  function initInspiration() {
    if (PAGE !== "inspiration") return;
  }

  // ────────────────────────────────────────────────────────────
  // Boot
  // ────────────────────────────────────────────────────────────
  initIndex();
  initMotif();
  initGallery();
  initInspiration();
});
