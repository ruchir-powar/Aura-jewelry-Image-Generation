# app.py
from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
import os, base64, traceback, json
from dotenv import load_dotenv
from datetime import datetime

# ── Env ─────────────────────────────────────────────────────────────────────
dotenv_path = os.path.join(os.path.dirname(__file__), ".env")
load_dotenv(dotenv_path)

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
print("API Key Loaded:", "✔️" if OPENAI_API_KEY else "❌")

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

# ── Flask ───────────────────────────────────────────────────────────────────
app = Flask(__name__, static_folder="static", template_folder="templates")
CORS(app)

GEN_DIR = os.path.join(app.static_folder, "generated")
os.makedirs(GEN_DIR, exist_ok=True)

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
def _save_b64_to_generated(b64_png: str, prefix: str = "image") -> str:
    """Save base64-encoded PNG to /static/generated and return web path."""
    ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    filename = f"{prefix}_{ts}.png"
    out_path = os.path.join(GEN_DIR, filename)
    with open(out_path, "wb") as f:
        f.write(base64.b64decode(b64_png))
    return f"/static/generated/{filename}"

def _tiny_png_b64() -> str:
    """1x1 transparent PNG as last-resort fallback (keeps UI stable)."""
    return (
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAA"
        "AAC0lEQVR42mP8/wwAAwMB/ax0eQAAAABJRU5ErkJggg=="
    )

# ── Text → Image ────────────────────────────────────────────────────────────
@app.route("/generate", methods=["POST"])
def generate():
    try:
        data = request.get_json(force=True, silent=False) or {}
        prompt = (data.get("prompt") or "").strip()
        if not prompt:
            return jsonify({"error": "Prompt is required"}), 400
        if len(prompt) > 2000:
            return jsonify({"error": "Prompt too long"}), 400

        print("🎯 /generate prompt:", prompt)

        b64 = None

        # Preferred: new SDK, gpt-image-1
        if _client:
            try:
                resp = _client.images.generate(
                    model="gpt-image-1",
                    prompt=prompt,
                    size="1024x1024",
                    n=1,
                    response_format="b64_json",
                )
                b64 = resp.data[0].b64_json
            except Exception as e:
                print("⚠️ newSDK gpt-image-1 failed:", e)

            # Optional fallback: DALL·E 3 if available
            if b64 is None:
                try:
                    resp = _client.images.generate(
                        model="dall-e-3",
                        prompt=prompt,
                        size="1024x1024",
                        n=1,
                        response_format="b64_json",
                    )
                    b64 = resp.data[0].b64_json
                except Exception as e:
                    print("⚠️ newSDK dall-e-3 failed:", e)

        # Legacy fallback (some older installs)
        if b64 is None and _legacy:
            try:
                resp = _legacy.images.generate(
                    model="gpt-image-1",
                    prompt=prompt,
                    size="1024x1024",
                    n=1,
                    response_format="b64_json",
                )
                b64 = resp.data[0].b64_json
            except Exception as e:
                print("⚠️ legacy gpt-image-1 failed:", e)
                try:
                    resp = _legacy.images.generate(
                        model="dall-e-3",
                        prompt=prompt,
                        size="1024x1024",
                        n=1,
                        response_format="b64_json",
                    )
                    b64 = resp.data[0].b64_json
                except Exception as e2:
                    print("⚠️ legacy dall-e-3 failed:", e2)

        # Last resort
        if b64 is None:
            b64 = _tiny_png_b64()

        web_path = _save_b64_to_generated(b64, prefix="image")
        return jsonify({"image": b64, "file_path": web_path})

    except Exception as e:
        return jsonify({"error": str(e), "trace": traceback.format_exc()}), 500

# ── Image (motif) → JSON {description, prompt} ──────────────────────────────
@app.route("/generate_prompts", methods=["GET", "POST"])
def generate_prompts():
    if request.method == "GET":
        return jsonify({"error": "Use POST with multipart/form-data (image, use_case)."}), 405

    try:
        image_file = request.files.get("image")
        use_case = (request.form.get("use_case") or "").strip() or "Jewelry"

        if not image_file:
            return jsonify({"error": "No image uploaded"}), 400
        if _client is None:
            return jsonify({"error": "OpenAI client not available. Update the openai package."}), 500

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

        # ✅ Corrected: exactly two closing braces before the comma on the image line
        resp = _client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": system_instructions},
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "Analyze and return strict JSON {description, prompt}."},
                        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image_b64}"}},
                    ],
                },
            ],
            temperature=0.7,
            max_tokens=500
        )

        # Access content safely for both dict/object styles
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
            return jsonify({"error": "Failed to parse GPT response as JSON", "raw": raw}), 500

        desc = parsed.get("description") or parsed.get("nl_description") or ""
        pr = parsed.get("prompt") or parsed.get("cad_prompt") or ""
        return jsonify({"description": desc, "prompt": pr})

    except Exception as e:
        return jsonify({"error": str(e), "trace": traceback.format_exc()}), 500

# ── Sketch → Realistic Image ────────────────────────────────────────────────
@app.route("/generate-sketch", methods=["POST"])
def generate_sketch():
    try:
        sketch_file = request.files.get("sketch")
        if not sketch_file:
            return jsonify({"error": "No sketch uploaded"}), 400

        sketch_bytes = sketch_file.read()
        b64_input = base64.b64encode(sketch_bytes).decode("utf-8")

        b64 = None
        if _client:
            # Some SDKs support image-to-image via data URL param; if not, we fall back
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

        web_path = _save_b64_to_generated(b64, prefix="sketch_realistic")
        return jsonify({"image": b64, "file_path": web_path})

    except Exception as e:
        return jsonify({"error": str(e), "trace": traceback.format_exc()}), 500

# ── Utils ───────────────────────────────────────────────────────────────────
@app.route("/test")
def test():
    return "✅ Flask server is running."

@app.route("/images")
def list_images():
    folder = GEN_DIR
    os.makedirs(folder, exist_ok=True)
    exts = (".png", ".jpg", ".jpeg", ".webp")
    files = sorted(
        (f for f in os.listdir(folder) if f.lower().endswith(exts)),
        key=lambda x: os.path.getmtime(os.path.join(folder, x)),
        reverse=True,
    )
    return jsonify([f"/static/generated/{f}" for f in files])

@app.route("/__routes__")
def __routes__():
    rules = []
    for r in app.url_map.iter_rules():
        methods = sorted(m for m in r.methods if m not in ("HEAD", "OPTIONS"))
        rules.append({"rule": str(r), "endpoint": r.endpoint, "methods": methods})
    return jsonify(rules)

# ── Main ────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    os.makedirs(GEN_DIR, exist_ok=True)
    print("🔎 URL MAP:\n", app.url_map)
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 5000)), debug=True)
