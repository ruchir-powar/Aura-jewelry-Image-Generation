# app.py
from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
import os, base64, json, io, time, re
from dotenv import load_dotenv

# ── Env ─────────────────────────────────────────────────────────────────────
dotenv_path = os.path.join(os.path.dirname(__file__), ".env")
load_dotenv(dotenv_path)

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
print("API Key Loaded:", "✔️" if OPENAI_API_KEY else "❌")

# Cloudinary creds from .env
CLOUDINARY_CLOUD_NAME = os.getenv("CLOUDINARY_CLOUD_NAME", "")
CLOUDINARY_API_KEY    = os.getenv("CLOUDINARY_API_KEY", "")
CLOUDINARY_API_SECRET = os.getenv("CLOUDINARY_API_SECRET", "")
# Default target folder for uploads
CLOUDINARY_FOLDER     = os.getenv("CLOUDINARY_FOLDER", "ImageGeneration")

# ── OpenAI clients (prefer new SDK; fallback to legacy) ─────────────────────
_client = None
try:
    from openai import OpenAI  # v1+
    _client = OpenAI(api_key=OPENAI_API_KEY or None)
except Exception as e:
    print("⚠️ New OpenAI SDK not available:", e)

_legacy = None
try:
    import openai as _legacy  # legacy
    if OPENAI_API_KEY:
        _legacy.api_key = OPENAI_API_KEY
except Exception as e:
    print("⚠️ Legacy OpenAI SDK not available:", e)

# ── Cloudinary SDK ──────────────────────────────────────────────────────────
import cloudinary
import cloudinary.uploader
import cloudinary.search

cloudinary.config(
    cloud_name=CLOUDINARY_CLOUD_NAME or None,
    api_key=CLOUDINARY_API_KEY or None,
    api_secret=CLOUDINARY_API_SECRET or None,
    secure=True,
)

# ── Flask ───────────────────────────────────────────────────────────────────
app = Flask(__name__, static_folder="static", template_folder="templates")
CORS(app)
app.config["MAX_CONTENT_LENGTH"] = 10 * 1024 * 1024  # 10MB

# ── Helpers ─────────────────────────────────────────────────────────────────
def _tiny_png_b64() -> str:
    """1x1 transparent PNG fallback."""
    return ("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAA"
            "AAC0lEQVR42mP8/wwAAwMB/ax0eQAAAABJRU5ErkJggg==")

def _err(message, status=400, detail=None):
    return jsonify({"ok": False, "error": {"message": message, "detail": detail}}), status

def _safe_prompt_for_context(prompt: str, max_len: int = 950) -> str:
    """
    Make the prompt safe for Cloudinary context:
    - remove newlines/tabs and control chars
    - remove '|' and '=' (reserved separators)
    - collapse spaces
    - hard cap length
    """
    if not prompt:
        return ""
    s = str(prompt)
    # remove control chars, newlines, tabs
    s = re.sub(r"[\r\n\t]", " ", s)
    # remove Cloudinary context separators
    s = re.sub(r"[|=]", " ", s)
    # collapse whitespace
    s = re.sub(r"\s{2,}", " ", s).strip()
    # cap length
    if len(s) > max_len:
        s = s[:max_len - 1].rstrip() + "…"
    return s


def _upload_to_cloudinary(*, b64_png: str = None, remote_url: str = None,
                          folder=CLOUDINARY_FOLDER, prompt_ctx: str = "") -> dict:
    """
    Upload to Cloudinary from base64 PNG OR remote URL.
    Saves prompt in context for later retrieval in the Gallery.
    """
    if not (CLOUDINARY_CLOUD_NAME and CLOUDINARY_API_KEY and CLOUDINARY_API_SECRET):
        raise RuntimeError("Cloudinary environment variables are not configured")

    context = {}
    if prompt_ctx:
        context = {"prompt": _safe_prompt_for_context(prompt_ctx)}

    if remote_url:
        return cloudinary.uploader.upload(
            remote_url,
            folder=folder,
            resource_type="image",
            tags=["jewelgen", "generated"],
            context=context,
            unique_filename=True,
            overwrite=False,
        )

    if b64_png is None:
        raise ValueError("Provide either b64_png or remote_url")

    if b64_png.startswith("data:image"):
        b64_png = b64_png.split(",", 1)[-1]

    data = base64.b64decode(b64_png)
    file_obj = io.BytesIO(data)

    return cloudinary.uploader.upload(
        file_obj,
        folder=folder,
        resource_type="image",
        format="png",
        tags=["jewelgen", "generated"],
        context=context,
        unique_filename=True,
        overwrite=False,
    )

def _images_generate_with_retries(prompt: str, model_pref: str = "auto", *, tries=3, timeout=90):
    """
    Calls OpenAI images.generate with retries & timeout.
    Returns (b64, url) – one may be None.
    """
    b64 = None
    url = None
    backoff = 1.5

    # Try new SDK first
    if _client:
        client = _client.with_options(timeout=timeout)
        models = [model_pref] if model_pref in ("gpt-image-1", "dall-e-3") else ["dall-e-3", "gpt-image-1"]
        for m in models:
            for attempt in range(tries):
                try:
                    resp = client.images.generate(model=m, prompt=prompt, size="1024x1024", n=1)
                    d = resp.data[0]
                    b64 = getattr(d, "b64_json", None) or (d.get("b64_json") if isinstance(d, dict) else None)
                    url = getattr(d, "url", None) or (d.get("url") if isinstance(d, dict) else None)
                    if b64 or url:
                        return b64, url
                except Exception as e:
                    msg = str(e).lower()
                    print(f"⚠️ newSDK {m} attempt {attempt+1}/{tries} failed:", e)
                    if any(x in msg for x in ["502", "503", "504", "timeout", "bad gateway", "temporar"]):
                        time.sleep(backoff); backoff *= 2
                        continue
                    break

    # Legacy fallback
    if _legacy:
        models = [model_pref] if model_pref in ("gpt-image-1", "dall-e-3") else ["dall-e-3", "gpt-image-1"]
        for m in models:
            for attempt in range(tries):
                try:
                    resp = _legacy.images.generate(
                        model=m, prompt=prompt, size="1024x1024", n=1, response_format="b64_json"
                    )
                    d = resp.data[0]
                    b64 = getattr(d, "b64_json", None) or (d.get("b64_json") if isinstance(d, dict) else None)
                    url = getattr(d, "url", None) or (d.get("url") if isinstance(d, dict) else None)
                    if b64 or url:
                        return b64, url
                except Exception as e:
                    msg = str(e).lower()
                    print(f"⚠️ legacy {m} attempt {attempt+1}/{tries} failed:", e)
                    if any(x in msg for x in ["502", "503", "504", "timeout", "bad gateway", "temporar"]):
                        time.sleep(backoff); backoff *= 2
                        continue
                    break

    return None, None

# ── Pages ───────────────────────────────────────────────────────────────────
@app.get("/")
def index():
    return render_template("index.html")

@app.get("/gallery")
def gallery():
    return render_template("gallery.html")

@app.get("/inspiration")
def inspiration():
    return render_template("inspiration.html")

@app.get("/motif")
def motif():
    return render_template("motif.html")

@app.get("/about")
def about():
    return render_template("about.html")

# ── Generate → Cloudinary (prompt saved in context) ─────────────────────────
# ── Generate → Cloudinary (prompt saved in context) ─────────────────────────
@app.post("/generate")
def generate():
    import traceback, time
    try:
        data = request.get_json(force=True) or {}
        prompt = (data.get("prompt") or "").strip()
        # default model unless caller overrides
        model_pref = (data.get("model") or "dall-e-3").strip().lower()

        if not prompt:
            return _err("Prompt is required.", 400)
        if len(prompt) > 4000:
            return _err("Prompt too long.", 400)

        print("🎯 /generate prompt:", prompt.replace("\n", " "))

        # --- Call OpenAI with retries (uses your helper) ---
        try:
            b64, url = _images_generate_with_retries(
                prompt, model_pref=model_pref, tries=3, timeout=90
            )
        except Exception as e:
            print("❌ OpenAI call raised:", repr(e))
            traceback.print_exc()
            return _err(f"Upstream (OpenAI) error: {e}", 502, str(e))

        if not (b64 or url):
            return _err("OpenAI image service temporarily unavailable. Please try again.", 503)

        # --- Upload to Cloudinary & SAVE PROMPT in context ---
        try:
            up = _upload_to_cloudinary(
                b64_png=b64,
                remote_url=None if b64 else url,
                folder=CLOUDINARY_FOLDER,
                prompt_ctx=prompt,  # <— saved as context.prompt (sanitized/truncated)
            )
        except Exception as e:
            print("❌ Cloudinary upload error:", repr(e))
            traceback.print_exc()
            return _err(f"Upload to Cloudinary failed: {e}", 502, str(e))

        # Respond (no redirect); front-end can use file_path to show the image
        return jsonify({
            "ok": True,
            "prompt": prompt,
            "image": b64,                         # optional inline preview
            "file_path": up.get("secure_url"),    # canonical URL we use everywhere
            "cloudinary": {
                "url": up.get("secure_url"),
                "public_id": up.get("public_id"),
                "bytes": up.get("bytes"),
                "format": up.get("format"),
                "width": up.get("width"),
                "height": up.get("height"),
                "created_at": up.get("created_at"),
            }
        })

    except Exception as e:
        print("❌ Unhandled error in /generate:", repr(e))
        traceback.print_exc()
        return _err("Failed to generate image (server error). See server logs for details.", 500, str(e))

# ── Image (motif) → JSON {description, prompt} ──────────────────────────────
@app.route("/generate_prompts", methods=["GET", "POST"])
def generate_prompts():
    if request.method == "GET":
        return _err("Use POST with multipart/form-data (image, use_case).", 405)

    try:
        image_file = request.files.get("image")
        use_case = (request.form.get("use_case") or "").strip() or "Jewelry"

        if not image_file:
            return _err("No image uploaded", 400)
        if _client is None:
            return _err("OpenAI client not available. Update the openai package.", 500)

        image_b64 = base64.b64encode(image_file.read()).decode("utf-8")

        system_instructions = f"""
You are a professional fine jewelry designer AI.

The user uploads a motif image to inspire a lightweight, wearable {use_case.lower()}.
Return concise JSON with:
- "description": ≤ 50 words, high-level look & motif usage (no CAD jargon)
- "prompt": one polished, realistic render prompt that ensures:
  • lightweight, comfortable, production-friendly
  • motif used subtly as detailing/pattern (not dominating)
  • accurate materials & natural studio lighting
  • front view on clean soft-lit background
  • no technical marks, no text overlays
Keywords: lightweight, wearable, elegant, subtle motif, realistic, refined, daily wear.
""".strip()

        resp = _client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": system_instructions},
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "Analyze and return strict JSON {description, prompt}."},
                        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image_b64}"}} ,
                    ],
                },
            ],
            temperature=0.7,
            max_tokens=500
        )

        msg = resp.choices[0].message
        raw = (msg.content if hasattr(msg, "content") else (msg.get("content") if isinstance(msg, dict) else "")) or ""
        raw = raw.strip()

        # Strip code fences if any
        if raw.startswith("```"):
            cleaned = raw.strip()
            if cleaned.startswith("```json"):
                cleaned = cleaned[7:]
            elif cleaned.startswith("```"):
                cleaned = cleaned[3:]
            if cleaned.endswith("```"):
                cleaned = cleaned[:-3]
            raw = cleaned.strip()

        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            return _err("Failed to parse GPT response as JSON", 500, raw)

        desc = parsed.get("description") or parsed.get("nl_description") or ""
        pr = parsed.get("prompt") or parsed.get("cad_prompt") or ""
        return jsonify({"ok": True, "description": desc, "prompt": pr})

    except Exception as e:
        return _err("Error during motif analysis", 500, str(e))

# ── Sketch → Realistic Image (uploads to Cloudinary) ────────────────────────
@app.post("/generate-sketch")
def generate_sketch():
    try:
        sketch_file = request.files.get("sketch")
        if not sketch_file:
            return _err("No sketch uploaded", 400)

        sketch_bytes = sketch_file.read()
        b64_input = base64.b64encode(sketch_bytes).decode("utf-8")

        b64 = None
        if _client:
            # Some SDKs may not support i2i; best-effort.
            try:
                resp = _client.images.generate(
                    model="gpt-image-1",
                    prompt=(
                        "Transform this jewelry sketch into a realistic, lightweight, production-friendly design. "
                        "Natural studio lighting, accurate metal/stone textures, front view, clean background. "
                        "No text, no technical marks."
                    ),
                    size="1024x1024",
                    n=1,
                    image=[{"image": f"data:image/png;base64,{b64_input}"}],
                )
                d = resp.data[0]
                b64 = getattr(d, "b64_json", None) or (d.get("b64_json") if isinstance(d, dict) else None)
            except Exception as e:
                print("⚠️ i2i not supported; using placeholder:", e)

        if b64 is None:
            b64 = _tiny_png_b64()

        up = _upload_to_cloudinary(b64_png=b64, folder=CLOUDINARY_FOLDER, prompt_ctx="sketch→realistic")
        return jsonify({
            "ok": True,
            "image": b64,
            "file_path": up.get("secure_url"),
            "cloudinary": {
                "url": up.get("secure_url"),
                "public_id": up.get("public_id")
            }
        })

    except Exception as e:
        return _err("Failed to generate from sketch", 500, str(e))

# ── Gallery APIs ────────────────────────────────────────────────────────────
@app.get("/images")
def list_images():
    """
    Return a list of objects from Cloudinary for the Gallery:
    [{url, prompt, public_id, created_at}]
    Looks in CLOUDINARY_FOLDER (default: ImageGeneration).
    """
    try:
        per = min(int(request.args.get("per", 48)), 100)
        cursor = request.args.get("cursor")

        expr = f'resource_type:image AND folder="{CLOUDINARY_FOLDER}"'

        # IMPORTANT: ask for extra fields so 'context' comes back
        s = (
            cloudinary.search.Search()
            .expression(expr)
            .sort_by("created_at", "desc")
            .max_results(per)
            .with_field("context")   # <-- this is the key bit
            .with_field("tags")      # (optional, nice to have)
        )
        if cursor:
            s = s.next_cursor(cursor)

        res = s.execute()
        items = []
        for r in res.get("resources", []):
            # Retrieve prompt from context (could be in "custom" or directly)
            prompt = None
            ctx = r.get("context") or {}
            if isinstance(ctx, dict):
                if isinstance(ctx.get("custom"), dict):
                    prompt = ctx["custom"].get("prompt")
                if prompt is None:
                    prompt = ctx.get("prompt")

            items.append({
                "url": r.get("secure_url"),
                "prompt": prompt,
                "public_id": r.get("public_id"),
                "created_at": r.get("created_at"),
            })

        return jsonify(items)

    except Exception as e:
        return _err("Failed to list images from Cloudinary", 500, str(e))

# ── Delete a Cloudinary image by public_id ───────────────────────────────────
@app.post("/delete")
def delete_image():
    """
    Request body (JSON): { "public_id": "ImageGeneration/<filename or nested path>" }
    Returns: { ok: true, result: <cloudinary response> }
    """
    try:
        data = request.get_json(force=True, silent=False) or {}
        public_id = (data.get("public_id") or "").strip()
        if not public_id:
            return _err("Missing public_id.", 400)

        if not (CLOUDINARY_CLOUD_NAME and CLOUDINARY_API_KEY and CLOUDINARY_API_SECRET):
            return _err("Cloudinary not configured on server.", 500)

        resp = cloudinary.uploader.destroy(public_id, invalidate=True, resource_type="image")
        result = (resp or {}).get("result")
        if result not in ("ok", "not found", "queued"):
            return _err(f"Cloudinary destroy failed: {resp}", 500)

        return jsonify({"ok": True, "result": resp})
    except Exception as e:
        return _err("Failed to delete image", 500, str(e))

# ── Routes Inspector ────────────────────────────────────────────────────────
@app.get("/__routes__")
def __routes__():
    rules = []
    for r in app.url_map.iter_rules():
        methods = sorted(m for m in r.methods if m not in ("HEAD", "OPTIONS"))
        rules.append({"rule": str(r), "endpoint": r.endpoint, "methods": methods})
    return jsonify(rules)

# ── Main ────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("🔎 URL MAP:\n", app.url_map)
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 5000)), debug=True)
