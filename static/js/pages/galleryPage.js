// /static/js/pages/galleryPage.js
import { byId, fetchJSON } from "../core/utils.js";

// ---- Config ---------------------------------------------------------------
const API_IMAGES =
  document.querySelector('meta[name="api-images"]')?.content || "/images";

// ---- State ----------------------------------------------------------------
const state = {
  items: [],          // all items loaded so far
  album: "all",       // current album filter (lowercase) — "all" means no filter
  search: "",         // text filter for album sidebar search
  nextCursor: null,   // server pagination cursor
  loading: false,
  reachedEnd: false,
};

// ---- Helpers --------------------------------------------------------------
function fmtWhen(s) {
  if (!s) return "";
  try {
    const d = new Date(s);
    const date = d.toLocaleDateString(undefined, { year: "numeric", month: "short", day: "2-digit" });
    const time = d.toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" });
    return `${date} • ${time}`;
  } catch {
    return s;
  }
}

function escapeHTML(str = "") {
  return String(str)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;");
}

// for data-* attributes
function escapeAttr(str = "") {
  return String(str)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function groupByAlbum(items) {
  const map = new Map();
  for (const it of items) {
    const name = (it.album || "unknown").toLowerCase();
    map.set(name, (map.get(name) || 0) + 1);
  }
  const order = ["all", "index", "set", "vector", "variants", "motif", "inspiration", "unknown"];
  const entries = [["all", items.length], ...[...map.entries()].sort((a, b) => {
    const ia = order.indexOf(a[0]); const ib = order.indexOf(b[0]);
    if (ia !== -1 || ib !== -1) return (ia === -1 ? 999 : ia) - (ib === -1 ? 999 : ib);
    return a[0].localeCompare(b[0]);
  })];
  return entries;
}

// ---- Rendering ------------------------------------------------------------
function cardHTML(it, i) {
  const prompt = (it.prompt || "").trim();
  const safe = escapeHTML(prompt);
  const album = (it.album || "unknown").toLowerCase();
  const when = it.created_at || "";

  return `
    <article
      class="gallery-card"
      data-public="${it.public_id}"
      data-album="${album}"
      data-idx="${i}"
      data-prompt="${escapeAttr(prompt)}"
      data-when="${escapeAttr(when)}"
    >
      <div class="imgwrap">
        <img loading="lazy" src="${it.url}" alt="${safe ? safe.slice(0, 140) : `jewelry ${i + 1}`}" />
      </div>

      <div class="caption" title="${safe}">
        ${safe || "(no saved prompt)"}
      </div>

      <div class="meta" style="display:flex;align-items:center;justify-content:space-between;padding:8px 12px;border-top:1px solid #f3f3f3;">
        <span class="chip" style="font-size:11px;padding:4px 8px;border-radius:999px;border:1px solid #eee;background:#fffdf7;">
          ${album}
        </span>
        <span class="when" style="font-size:11px;color:#6b7280;">${fmtWhen(when)}</span>
      </div>
    </article>`;
}

function renderGallery() {
  const grid = byId("galleryItems");
  if (!grid) return;

  grid.style.gridTemplateColumns = "repeat(3, 1fr)"; // fixed 3 cols

  grid.innerHTML = "";
  const filtered = state.album !== "all"
    ? state.items.filter(it => (it.album || "unknown").toLowerCase() === state.album)
    : state.items;

  if (!filtered.length) {
    grid.innerHTML = `<div class="muted" style="color:#6b7280;">No photos yet.</div>`;
    return;
  }
  grid.insertAdjacentHTML("beforeend", filtered.map(cardHTML).join(""));
}

function renderAlbums() {
  const ul = byId("albumList");
  if (!ul) return;

  const entries = groupByAlbum(state.items);
  const q = (state.search || "").toLowerCase();

  ul.innerHTML = entries
    .filter(([name]) => !q || name.includes(q))
    .map(([name, count]) =>
      `<li class="${state.album === name ? "active" : ""}" data-album="${name}">
         ${name.charAt(0).toUpperCase() + name.slice(1)} (${count})
       </li>`
    )
    .join("");

  ul.onclick = (e) => {
    const li = e.target.closest("li[data-album]");
    if (!li) return;
    state.album = li.dataset.album;
    renderAlbums();
    renderGallery();
  };

  byId("showAll")?.addEventListener("click", () => {
    state.album = "all";
    renderAlbums();
    renderGallery();
  });
}

// ---- Data loading ---------------------------------------------------------
async function fetchPage({ cursor = null, limit = 30 } = {}) {
  const params = new URLSearchParams();
  params.set("limit", String(limit));
  if (cursor) params.set("cursor", cursor);

  return fetchJSON(`${API_IMAGES}?${params.toString()}`);
}

async function loadMore() {
  if (state.loading || state.reachedEnd) return;
  state.loading = true;
  try {
    const data = await fetchPage({ cursor: state.nextCursor, limit: 30 });
    const items = Array.isArray(data.items) ? data.items : [];
    state.items = state.items.concat(items);
    state.nextCursor = data.next_cursor || null;
    state.reachedEnd = !state.nextCursor;
    renderAlbums();
    renderGallery();
  } catch (err) {
    console.error("Gallery load failed:", err);
  } finally {
    state.loading = false;
  }
}

// ---- Modal + interactions -------------------------------------------------
function setupCardClicks() {
  const grid = byId("galleryItems");
  const modal = byId("imgModal");
  const mImg = byId("modalImg");
  const mPrompt = byId("modalPrompt");
  const mMeta = byId("modalMetaLine");
  const mClose = byId("modalClose");
  const copyBtn = byId("copyPromptModal");

  function openModal(el) {
    const img = el.querySelector("img");
    const prompt = el.dataset.prompt || "";
    const when = el.dataset.when || "";
    const album = el.dataset.album || "unknown";

    mImg.src = img?.src || "";
    mPrompt.textContent = prompt || "(no saved prompt)";
    mMeta.textContent = `${album} • ${fmtWhen(when)}`;

    modal.setAttribute("aria-hidden", "false");
    document.body.style.overflow = "hidden";
    mClose?.focus(); // accessibility improvement
  }

  function closeModal() {
    modal.setAttribute("aria-hidden", "true");
    document.body.style.overflow = "";
    mImg.src = "";
  }

  grid.addEventListener("click", (e) => {
    const card = e.target.closest(".gallery-card");
    if (!card) return;
    openModal(card);
  });

  mClose?.addEventListener("click", closeModal);
  modal?.querySelector(".modal__backdrop")?.addEventListener("click", closeModal);
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && modal.getAttribute("aria-hidden") === "false") closeModal();
  });

  copyBtn?.addEventListener("click", async () => {
    const text = (mPrompt?.textContent || "").trim();
    if (!text) return;
    try {
      if (navigator.clipboard && window.isSecureContext) {
        await navigator.clipboard.writeText(text);
      } else {
        const ta = document.createElement("textarea");
        ta.value = text;
        ta.style.position = "fixed";
        ta.style.top = "-9999px";
        document.body.appendChild(ta);
        ta.select();
        document.execCommand("copy");
        document.body.removeChild(ta);
      }
      copyBtn.textContent = "Copied!";
      setTimeout(() => (copyBtn.textContent = "Copy Prompt"), 1100);
    } catch {
      copyBtn.textContent = "Copy failed";
      setTimeout(() => (copyBtn.textContent = "Copy Prompt"), 1100);
    }
  });
}

// ---- Infinite scroll ------------------------------------------------------
function setupInfiniteScroll() {
  const sentinel = byId("scrollSentinel");
  if (!sentinel) return;
  const io = new IntersectionObserver((entries) => {
    if (entries.some(e => e.isIntersecting)) loadMore();
  }, { rootMargin: "800px 0px 800px 0px" });
  io.observe(sentinel);

  window.addEventListener("beforeunload", () => io.disconnect());
}

// ---- Boot -----------------------------------------------------------------
export function initGallery() {
  if ((document.body.dataset.page || "") !== "gallery") return;

  // initial load
  loadMore();
  setupCardClicks();
  setupInfiniteScroll();

  // search input listener (attached once here)
  const search = byId("albumSearch");
  search?.addEventListener("input", () => {
    state.search = search.value.trim();
    renderAlbums();
  });

  const grid = byId("galleryItems");
  if (grid) grid.style.gridTemplateColumns = "repeat(3, 1fr)";
}
