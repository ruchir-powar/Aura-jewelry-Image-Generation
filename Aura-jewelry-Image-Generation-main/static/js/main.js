// /static/js/main.js
// Central router: boots the correct page module based on <body data-page="...">

// --- Diagnostics (safe to keep) ---
window.addEventListener("error",  e =>
  console.error("[GlobalError]", e.message, "@", e.filename, ":", e.lineno)
);
window.addEventListener("unhandledrejection", e =>
  console.error("[PromiseRejection]", e.reason)
);

// --- Page inits (match your tree exactly) ---
import { initIndex }            from "./pages/indexPage.js";
import { initGallery }          from "./pages/galleryPage.js";
import { initInspiration }      from "./pages/inspirationPage.js";
import { initMotif }            from "./pages/motifPage.js";
import { initVariantGenerator } from "./pages/variantPage.js";
import { initVectorize }        from "./pages/vector.js";

// These two may export different names; import * and pick what's available:
import * as SetMod              from "./pages/setPage.js";
import * as TextAutoMod         from "./pages/textAutoPage.js";

let booted = false;

function safeInit(label, fn) {
  if (!fn) { console.warn(`[init] ${label} missing`); return; }
  try {
    console.debug(`[init] ${label}`);
    fn();
  } catch (err) {
    console.error(`[init:${label}]`, err);
  }
}

function start(endpoint) {
  console.debug("[boot] data-page =", endpoint);

  if (endpoint === "index")                    safeInit("index",       initIndex);
  if (endpoint === "gallery")                  safeInit("gallery",     initGallery);
  if (endpoint === "inspiration")              safeInit("inspiration", initInspiration);
  if (endpoint === "motif")                    safeInit("motif",       initMotif);
  if (endpoint === "design_variant_generator") safeInit("variants",    initVariantGenerator);

  if (endpoint === "set_generator") {
    const fn = SetMod.initSetGenerator || SetMod.initSet || SetMod.initSetPage || SetMod.default;
    safeInit("set", fn);
  }

  if (endpoint === "text_automation") {
    const fn = TextAutoMod.initTextAutomation || TextAutoMod.initTextAuto || TextAutoMod.init || TextAutoMod.default;
    safeInit("textauto", fn);
  }

  if (endpoint === "vector" || endpoint === "motif_vector") {
    safeInit("vector", initVectorize);
  }

  // Tiny debug helper
  window.JewelGen = Object.freeze({
    page: endpoint,
    ping: () => "pong",
  });
}

document.addEventListener("DOMContentLoaded", () => {
  if (booted) return; booted = true;

  const body = document.body;
  let endpoint = body?.dataset?.page || "";

  // If present, boot immediately; else, observe until it's set (race-proof).
  if (endpoint) return start(endpoint);

  const obs = new MutationObserver(() => {
    endpoint = body?.dataset?.page || "";
    if (!endpoint) return;
    obs.disconnect();
    start(endpoint);
  });
  obs.observe(body, { attributes: true, attributeFilter: ["data-page"] });

  setTimeout(() => {
    const fallback = body?.dataset?.page || "";
    if (fallback) {
      try { obs.disconnect(); } catch {}
      start(fallback);
    } else {
      console.warn("[boot] data-page not set; no page initialized.");
    }
  }, 1500);
});
