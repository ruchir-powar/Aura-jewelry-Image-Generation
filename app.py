# app.py
from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
import os, base64, traceback, json, io
from dotenv import load_dotenv
from datetime import datetime

# ── Env ─────────────────────────────────────────────────────────────────────
dotenv_path = os.path.join(os.path.dirname(__file__), ".env")
load_dotenv(dotenv_path)

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
print("API Key Loaded:", "✔️" if OPENAI_API_KEY else "❌")

# Cloudinary creds from .env
CLOUDINARY_CLOUD_NAME = os.getenv("CLOUDINARY_CLOUD_NAME", "")
CLOUDINARY_API_KEY = os.getenv("CLOUDINARY_API_KEY", "")
CLOUDINARY_API_SECRET = os.getenv("CLOUDINARY_API_SECRET", "")
CLOUDINARY_FOLDER = os.getenv("CLOUDINARY_FOLDER", "aura/jewelgen")

# ── OpenAI clients (prefer new SDK; fallback to legacy if present) ──────────
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

# Optional: cap uploads (10 MB) to avoid huge posts
app.config["MAX_CONTENT_LENGTH"] = 10 * 1024 * 1024

# ── Pages ───────────────────────────────────────────────────────────────────
@app.route("/")
def index():
    return render_template("index.html")

@app.route("/gallery")
def gallery():
    return render_template("gallery.html")

@app.route("/inspiration")
def inspiration():
    return render_template("inspiration.html")

@app.route("/motif")
def motif():
    return render_template("motif.html")

@app.route("/about")
def about():
    return render_template("about.html")

# ── Helpers ─────────────────────────────────────────────────────────────────
def _tiny_png_b64() -> str:
    """1x1 transparent PNG as last-resort fallback (keeps UI stable)."""
    return (
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAA"
        "AAC0lEQVR42mP8/wwAAwMB/ax0eQAAAABJRU5ErkJggg=="
    )

def _err(message, status=400, detail=None):
    return jsonify({"ok": False, "error": {"message": message, "detail": detail}}), status

def _upload_png_b64_to_cloudinary(b64_png: str, *, folder=CLOUDINARY_FOLDER, prompt_ctx: str = "") -> dict:
    """
    Accepts PNG as base64 string (with or without data URI header), uploads to Cloudinary.
    Returns Cloudinary upload response dict.
    """
    if not (CLOUDINARY_CLOUD_NAME and CLOUDINARY_API_KEY and CLOUDINARY_API_SECRET):
        raise RuntimeError("Cloudinary environment variables are not configured")

    if b64_png.startswith("data:image"):
        b64_png = b64_png.split(",", 1)[-1]

    data = base64.b64decode(b64_png)
    file_obj = io.BytesIO(data)

    resp = cloudinary.uploader.upload(
        file_obj,
        folder=folder,
        resource_type="image",
        format="png",
        tags=["jewelgen", "generated"],
        context={"prompt": prompt_ctx} if prompt_ctx else {},
        unique_filename=True,
        overwrite=False,
    )
    return resp

# ── Text → Image (uploads to Cloudinary) ────────────────────────────────────
@app.route("/generate", methods=["POST"])
def generate():
    try:
        data = request.get_json(force=True, silent=False) or {}
        prompt = (data.get("prompt") or "").strip()
        model_pref = (data.get("model") or "auto").strip().lower()

        if not prompt:
            return _err("Prompt is required.", 400)
        if len(prompt) > 2000:
            return _err("Prompt too long.", 400)

        print("🎯 /generate prompt:", prompt)
        b64 = None

        # Preferred: new SDK
        if _client:
            # Choose model if forced; else try gpt-image-1 → dall-e-3
            preferred_models = []
            if model_pref in ("gpt-image-1", "dall-e-3"):
                preferred_models = [model_pref]
            else:
                preferred_models = ["gpt-image-1", "dall-e-3"]

            for m in preferred_models:
                try:
                    resp = _client.images.generate(
                        model=m,
                        prompt=prompt,
                        size="1024x1024",
                        n=1,
                        response_format="b64_json",
                    )
                    b64 = resp.data[0].b64_json
                    if b64:
                        break
                except Exception as e:
                    print(f"⚠️ newSDK {m} failed:", e)

        # Legacy fallback
        if b64 is None and _legacy:
            for m in ("gpt-image-1", "dall-e-3"):
                try:
                    resp = _legacy.images.generate(
                        model=m,
                        prompt=prompt,
                        size="1024x1024",
                        n=1,
                        response_format="b64_json",
                    )
                    b64 = resp.data[0].b64_json
                    if b64:
                        break
                except Exception as e2:
                    print(f"⚠️ legacy {m} failed:", e2)

        # Last resort
        if b64 is None:
            b64 = _tiny_png_b64()

        # ⬆️ Upload to Cloudinary and return its URL
        up = _upload_png_b64_to_cloudinary(b64, folder=CLOUDINARY_FOLDER, prompt_ctx=prompt)

        return jsonify({
            "ok": True,
            # keep base64 for backward-compat previews if your JS uses it
            "image": b64,
            # make file_path compatible with your existing front-end: use Cloudinary URL
            "file_path": up.get("secure_url"),
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
        return _err("Failed to generate image", 500, str(e))

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
@app.route("/generate-sketch", methods=["POST"])
def generate_sketch():
    try:
        sketch_file = request.files.get("sketch")
        if not sketch_file:
            return _err("No sketch uploaded", 400)

        sketch_bytes = sketch_file.read()
        b64_input = base64.b64encode(sketch_bytes).decode("utf-8")

        b64 = None
        if _client:
            # Some SDKs may not support i2i; we keep this best-effort.
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
                    response_format="b64_json",
                    image=[{"image": f"data:image/png;base64,{b64_input}"}],
                )
                b64 = resp.data[0].b64_json
            except Exception as e:
                print("⚠️ i2i not supported; falling back to tiny placeholder:", e)

        if b64 is None:
            b64 = _tiny_png_b64()

        up = _upload_png_b64_to_cloudinary(b64, folder=CLOUDINARY_FOLDER, prompt_ctx="sketch→realistic")
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

# ── Utils ───────────────────────────────────────────────────────────────────
@app.route("/test")
def test():
    return "✅ Flask server is running."

@app.route("/images")
def list_images():
    """
    Returns a simple list of secure URLs from Cloudinary (keeps your current gallery JS compatible).
    Optional pagination: pass ?per=24&cursor=<next_cursor>
    """
    try:
        per = min(int(request.args.get("per", 48)), 100)
        cursor = request.args.get("cursor")
        search = cloudinary.search.Search() \
                    .expression(f"folder:{CLOUDINARY_FOLDER}") \
                    .sort_by("created_at", "desc") \
                    .max_results(per)
        if cursor:
            search = search.next_cursor(cursor)

        res = search.execute()
        urls = [r.get("secure_url") for r in res.get("resources", []) if r.get("secure_url")]
        # For backward compatibility, return just the list if no cursor requested
        if cursor is None and "cursor" not in request.args:
            return jsonify(urls)

        # If you want pagination, return cursor too (front-end can opt-in)
        return jsonify({
            "ok": True,
            "items": urls,
            "next_cursor": res.get("next_cursor")
        })
    except Exception as e:
        return _err("Failed to list images from Cloudinary", 500, str(e))

@app.route("/__routes__")
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
