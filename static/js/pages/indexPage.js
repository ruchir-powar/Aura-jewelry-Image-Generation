// static/js/pages/indexPage.js
// -----------------------------------------------------------------------------
// Imports (utils + data + API endpoints)
// -----------------------------------------------------------------------------
import { byId, getValue, fetchJSON } from "../core/utils.js";
import {
  VARIATION_HINTS,
  jewelryTypes,
  attributeOptions,
  jewelryTypeToSubcategories,
} from "../core/data.js";
import { API } from "../core/api.js";

// -----------------------------------------------------------------------------
// Small helpers (self-contained; do not depend on fillSelect signature)
// -----------------------------------------------------------------------------
const log = {
  info: (m, x) => console.info(`[index] ${m}`, x ?? ""),
  warn: (m, x) => console.warn(`[index] ${m}`, x ?? ""),
  err:  (m, x) => console.error(`[index] ${m}`, x ?? ""),
};

function must(id) {
  const el = byId(id);
  if (!el) log.warn(`Missing #${id} (check templates/index.html)`);
  return el;
}

function setOptions(sel, arr = []) {
  if (!sel) return;
  // support array of strings or array of {value,label}
  const optHtml = arr
    .map(v => {
      if (typeof v === "string") return `<option value="${v}">${v}</option>`;
      const val = v?.value ?? v?.label ?? "";
      const lab = v?.label ?? v?.value ?? "";
      const selAttr = v?.selected ? " selected" : "";
      return `<option value="${val}"${selAttr}>${lab}</option>`;
    })
    .join("");
  sel.innerHTML = `<option value="">-- Select --</option>${optHtml}`;
}

// -----------------------------------------------------------------------------
// Locked attributes → text snippet for multi image variants
// -----------------------------------------------------------------------------
function buildLockedAttributesText() {
  const fields = [
    ["jewelryType",       "jewelry type"],
    ["jewelrySubCategory","subcategory"],
    ["metalType",         "metal (no plating/tint changes)"],
    ["jewelryStyle",      "style"],
    ["gemstoneType",      "gemstone"],
    ["diamondShape",      "diamond shape"],
    ["settingStyle",      "setting"],
    ["stoneArrangement",  "stone arrangement"],
    ["numDiamonds",       "diamonds"],
    ["caratWeight",       "total carat"],
    ["goldWeight",        "gold weight"],
    ["sizeRange",         "size"],
  ];

  const locks = [];
  for (const [id, label] of fields) {
    const v = getValue(id);
    if (!v) continue;
    if (id === "numDiamonds") locks.push(`${v} diamond${v === "1" ? "" : "s"}`);
    else locks.push(`${label} "${v}"`);
  }
  return locks.length
    ? ` Do not alter locked attributes: ${locks.join(", ")}. Keep materials, colors, counts, proportions, geometry, stone sizes, and settings identical; no motif/engraving changes.`
    : "";
}

// -----------------------------------------------------------------------------
// Prompt builders
// -----------------------------------------------------------------------------
function generatePrompt() {
  const type        = getValue("jewelryType");
  const subcat      = getValue("jewelrySubCategory");
  const metal       = getValue("metalType");
  const style       = getValue("jewelryStyle");
  const gem         = getValue("gemstoneType");
  const shape       = getValue("diamondShape");
  const setting     = getValue("settingStyle");
  const arrangement = getValue("stoneArrangement");
  const carat       = getValue("caratWeight");
  const size        = getValue("sizeRange");
  const goldWeight  = getValue("goldWeight");
  const numDiam     = getValue("numDiamonds");

  let p = `Lightweight`;
  if (type)   p += ` ${type.toLowerCase()}`;
  if (subcat) p += ` (${subcat.toLowerCase()})`;
  if (metal)  p += ` crafted in ${metal.toLowerCase()}`;
  p += ` with a high-polish finish`;

  if (gem) {
    p += `, featuring ${gem.toLowerCase()}`;
    if (shape) p += ` in a ${shape.toLowerCase()} cut`;
  }
  if (setting)     p += `, set using a ${setting.toLowerCase()} setting`;
  if (arrangement) p += `, arranged in ${arrangement.toLowerCase()}`;
  if (numDiam)     p += `, using ${numDiam} diamond${numDiam === "1" ? "" : "s"}`;
  if (carat)       p += ` totaling ${carat}`;
  if (goldWeight)  p += `, with a gold weight of ${goldWeight}`;

  if (style || size) {
    p += `. Designed`;
    if (style) p += ` in a ${style.toLowerCase()} style`;
    if (size)  p += `, size ${size.toLowerCase()}`;
  }

  // Tanmaniya special rules
  if ((type || "").toLowerCase() === "tanmaniyas") {
    p += `. Chain partially visible in a clean, symmetrical V-shape (only the front portion shown), ` +
         `made of alternating black enamel beads and polished gold beads (2–3 mm), evenly spaced; ` +
         `no mesh, snake, tube, link, or tennis-style chain; no gemstones in the chain. ` +
         `Proper front elevation (no angle, no 3/4 tilt, no perspective), pendant perfectly centered`;
  }

  p += `. Hyper-realistic render, front view on a pure white background under studio lighting, ` +
       `accurate metal/stone reflections; absolutely no text, numbers, watermarks, grids, labels, or markings.`;

  p = p.charAt(0).toUpperCase() + p.slice(1);

  // Fill textareas
  byId("promptBox")   && (byId("promptBox").value   = p);
  byId("finalPrompt") && (byId("finalPrompt").value = p);
  return p;
}

function buildPromptVariants(base, n, locksText = "") {
  const out = [];
  const N = Math.max(1, Math.min(4, n | 0 || 1));
  for (let i = 0; i < N; i++) {
    const hint = VARIATION_HINTS[i % VARIATION_HINTS.length];
    out.push(
      `${base}${locksText} Only vary non-substantive presentation aspects: ${hint}. ` +
      `Front view on a clean white background. No text, numbers, watermarks, grids, labels, or markings.`
    );
  }
  return out;
}

// -----------------------------------------------------------------------------
// Preview helpers
// -----------------------------------------------------------------------------
function ensureFrames(n) {
  const container = must("previewContainer");
  if (!container) return;
  const need = Math.max(1, Math.min(4, n | 0 || 1));

  // add frames
  while (container.children.length < need) {
    const idx = container.children.length;
    const frame = document.createElement("div");
    frame.className = "preview-frame";
    frame.id = `previewFrame-${idx}`;
    const img = document.createElement("img");
    img.id = `previewImage-${idx}`;
    img.alt = `Generated ${idx + 1}`;
    frame.appendChild(img);
    container.appendChild(frame);
  }
  // remove extra
  while (container.children.length > need) {
    container.removeChild(container.lastElementChild);
  }
  // clear
  for (let i = 0; i < container.children.length; i++) {
    const img = byId(`previewImage-${i}`) || container.children[i].querySelector("img");
    if (img) img.removeAttribute("src");
    container.children[i]?.querySelector(".ph")?.remove();
  }
}

function setPlaceholder(i, text = "Generating…") {
  const frame = byId(`previewFrame-${i}`);
  if (!frame) return;
  frame.querySelector(".ph")?.remove();
  const ph = document.createElement("div");
  ph.className = "ph";
  ph.textContent = text;
  frame.appendChild(ph);
}

function setImage(i, src) {
  const frame = byId(`previewFrame-${i}`);
  if (!frame) return;
  frame.querySelector(".ph")?.remove();
  const img = byId(`previewImage-${i}`) || frame.querySelector("img");
  if (img) img.src = src;
}

// -----------------------------------------------------------------------------
// Init (entry point for home page)
// -----------------------------------------------------------------------------
export function initIndex() {
  if ((document.body?.dataset?.page || "") !== "index") return;
  log.info("init");

  // Elements
  const selType    = must("jewelryType");
  const selSub     = must("jewelrySubCategory");
  const btnGen     = must("generateBtn");
  const btnImages  = must("generateJewelryBtn");
  const btnDL      = must("downloadImageBtn");
  const selModel   = byId("modelSelect"); // optional; default used if missing

  // 1) Main types
  setOptions(selType, jewelryTypes);

  // 2) Subcategories cascade
  const refreshSubs = () => {
    const subs = jewelryTypeToSubcategories[selType?.value || ""] || [];
    setOptions(selSub, subs);
  };
  selType?.addEventListener("change", refreshSubs);
  refreshSubs();

  // 3) Attribute dropdowns (explicit id→options)
  const map = {
    metalType:        attributeOptions["Metal Type"],
    jewelryStyle:     attributeOptions["Jewelry Style"],
    gemstoneType:     attributeOptions["Gemstone Type"],
    diamondShape:     attributeOptions["Diamond Shape"],
    settingStyle:     attributeOptions["Setting Style"],
    stoneArrangement: attributeOptions["Stone Arrangement"],
    caratWeight:      attributeOptions["Carat Weight"],
    sizeRange:        attributeOptions["Size Range"],
    goldWeight:       attributeOptions["Gold Weight"],
  };
  Object.entries(map).forEach(([id, options]) => setOptions(byId(id), options || []));

  // 4) Generate Prompt (no image call)
  btnGen?.addEventListener("click", (e) => {
    e.preventDefault();
    const p = generatePrompt();
    log.info("prompt built", p);
  });

  // 5) Generate Image(s)
  btnImages?.addEventListener("click", async (e) => {
    e.preventDefault();
    if (!API?.generate) return log.err("Missing API.generate meta tag");

    const count = Math.max(1, Math.min(4, parseInt(byId("imageCount")?.value || "1", 10)));
    const basePrompt = (byId("promptBox")?.value || "").trim() || generatePrompt();
    const model = (selModel?.value || "dall-e-3").trim();

    ensureFrames(count);
    for (let i = 0; i < count; i++) setPlaceholder(i);

    btnImages.disabled = true;
    const oldLabel = btnImages.textContent;
    btnImages.textContent = count === 1 ? "Generating…" : `Generating ${count}…`;

    try {
      if (count === 1) {
        const data = await fetchJSON(API.generate, {
          method: "POST",
          headers: { "Accept": "application/json", "Content-Type": "application/json" },
          body: JSON.stringify({ prompt: basePrompt, model }),
        });
        const src = data.image
          ? `data:image/png;base64,${data.image}`
          : (data.file_path || data.cloudinary?.url || "");
        if (!src) throw new Error("No image returned");
        setImage(0, src);
      } else {
        const locks = buildLockedAttributesText();
        const prompts = buildPromptVariants(basePrompt, count, locks);

        await Promise.all(prompts.map(async (p, i) => {
          try {
            const data = await fetchJSON(API.generate, {
              method: "POST",
              headers: { "Accept": "application/json", "Content-Type": "application/json" },
              body: JSON.stringify({ prompt: p, model }),
            });
            const src = data.image
              ? `data:image/png;base64,${data.image}`
              : (data.file_path || data.cloudinary?.url || "");
            if (src) setImage(i, src); else setPlaceholder(i, "Failed");
          } catch (err) {
            log.err(`Variant ${i + 1} failed`, err);
            setPlaceholder(i, "Failed");
          }
        }));
      }

      byId("finalPrompt") && (byId("finalPrompt").value = basePrompt);
    } catch (err) {
      log.err("Generation error", err);
      alert(err?.message || "Failed to generate. Check server logs/console.");
    } finally {
      btnImages.disabled = false;
      btnImages.textContent = oldLabel || "Generate Jewelry";
    }
  });

  // 6) Download first image
  btnDL?.addEventListener("click", (e) => {
    e.preventDefault();
    const img = byId("previewImage-0") || byId("previewContainer")?.querySelector("img");
    if (!img || !img.src) return alert("No image to download yet.");
    const a = document.createElement("a");
    a.href = img.src;
    a.download = "jewelgen.png";
    document.body.appendChild(a);
    a.click();
    a.remove();
  });

  log.info("ready");
}
