// static/js/core/api.js

// Read an endpoint from a <meta> tag (with a safe fallback path)
export function meta(name, fallback) {
  return document.querySelector(`meta[name="${name}"]`)?.content || fallback;
}

// Central list of backend endpoints used by the app.
// Fallbacks match your Flask routes in app.py.
export const API = Object.freeze({
  generate:        meta("api-generate",         "/generate"),
  generatePrompts: meta("api-generate-prompts", "/generate_prompts"),
  variants:        meta("api-variants",         "/api/variants"),
  set:             meta("api-set",              "/api/set"),
  vectorize:       meta("api-vectorize",        "/api/vectorize"),
  textFromImage:   meta("api-text-image",       "/api/text-from-image"),
  images:          "/images",
  delete:          "/delete",
  sketch:          "/generate_from_sketch",
});

// Optional helper to get a URL by key with a small safety check.
export function url(key) {
  const u = API[key];
  if (!u) throw new Error(`Unknown API key: ${key}`);
  return u;
}

export default API;
