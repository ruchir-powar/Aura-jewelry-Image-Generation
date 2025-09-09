// static/js/core/utils.js

// Get element by ID
export function byId(id) {
  return document.getElementById(id);
}

// Get value of a <select> or <input> by ID
export function getValue(id) {
  const el = byId(id);
  return el ? el.value : "";
}

// Fill a <select> with option values
export function fillSelect(selectEl, options) {
  if (!selectEl) return;
  selectEl.innerHTML = `<option value="">-- Select --</option>`;
  options.forEach(opt => {
    const o = document.createElement("option");
    o.value = opt;
    o.textContent = opt;
    selectEl.appendChild(o);
  });
}

// Convert "Metal Type" → "metalType" for consistent IDs
export function convertLabelToId(label) {
  return label
    .replace(/\s+/g, " ")       // collapse whitespace
    .trim()
    .replace(/\s+([a-zA-Z])/g, (_, c) => c.toUpperCase()) // camelCase
    .replace(/\s/g, "")
    .replace(/[^a-zA-Z0-9]/g, "")
    .replace(/^./, c => c.toLowerCase());
}

// Fetch JSON with error handling
export async function fetchJSON(url, options = {}) {
  const res = await fetch(url, options);
  if (!res.ok) throw new Error(`HTTP ${res.status}: ${res.statusText}`);
  return await res.json();
}

export default {
  byId,
  getValue,
  fillSelect,
  convertLabelToId,
  fetchJSON
};
