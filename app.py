# app.py
"""
JewelGen — Flask app (OpenAI-only sketch→image)

Setup:
    pip install flask flask-cors python-dotenv openai cloudinary pillow numpy opencv-python svgwrite

.env (put beside app.py):
    OPENAI_API_KEY=sk-...
    CLOUDINARY_CLOUD_NAME=...
    CLOUDINARY_API_KEY=...
    CLOUDINARY_API_SECRET=...
    CLOUDINARY_FOLDER=ImageGeneration   # optional (default shown)
"""

import os, base64, json, io, time
import numpy as np, cv2, svgwrite
from PIL import Image, ImageOps
import os, json
from flask import request, jsonify
import cloudinary
import cloudinary.uploader
from flask import Flask, request, jsonify, render_template, send_from_directory
from flask_cors import CORS
from dotenv import load_dotenv

# ── Env ─────────────────────────────────────────────────────────────────────
dotenv_path = os.path.join(os.path.dirname(__file__), ".env")
load_dotenv(dotenv_path)

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
print("API Key Loaded:", "✔️" if OPENAI_API_KEY else "❌")

# ── OpenAI client (v1 preferred, legacy fallback) ───────────────────────────
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

CLOUDINARY_CLOUD_NAME = os.getenv("CLOUDINARY_CLOUD_NAME", "")
CLOUDINARY_API_KEY    = os.getenv("CLOUDINARY_API_KEY", "")
CLOUDINARY_API_SECRET = os.getenv("CLOUDINARY_API_SECRET", "")
CLOUDINARY_FOLDER     = os.getenv("CLOUDINARY_FOLDER", "ImageGeneration")

cloudinary.config(
    cloud_name=CLOUDINARY_CLOUD_NAME or None,
    api_key=CLOUDINARY_API_KEY or None,
    api_secret=CLOUDINARY_API_SECRET or None,
    secure=True,
)

# ── Flask ───────────────────────────────────────────────────────────────────
# We serve /static ourselves via a route below, so static_folder=None here.
app = Flask(__name__, static_folder=None, template_folder="templates")
CORS(app)
app.config["MAX_CONTENT_LENGTH"] = 10 * 1024 * 1024  # 10MB

# Serve files from ./static as /static/...
@app.get("/static/<path:filename>")
def static_files(filename):
    return send_from_directory(os.path.join(app.root_path, "static"), filename)

# ── Helpers ─────────────────────────────────────────────────────────────────
def _coerce_bool(v):
    if isinstance(v, bool):
        return v
    return str(v).strip().lower() in {"1", "true", "yes", "y", "on"}

def _build_constraint_text(*, allow_solitaires=False, force_cluster=True, attrs=None):
    """
    Returns a single string you can append into prompts to enforce design guardrails.
    `attrs` can be a dict of user selections (type, subcategory, metal, gemstone, shape, setting, etc.)
    """
    attrs = attrs or {}
    lock_bits = []

    # Only add lines for provided fields (keeps the text compact)
    locks_map = [
        ("jewelry_type",       "jewelry type"),
        ("subcategory",        "subcategory"),
        ("metal",              "metal"),
        ("gemstone",           "gemstone"),
        ("diamond_shape",      "diamond shape"),
        ("setting_style",      "setting"),
        ("stone_arrangement",  "stone arrangement"),
        ("num_diamonds",       "number of diamonds"),
        ("carat_weight",       "total carat"),
        ("gold_weight",        "gold weight"),
        ("size_range",         "size"),
    ]
    for key, label in locks_map:
        v = attrs.get(key)
        if v:
            lock_bits.append(f'{label} "{v}"')

    locked = ""
    if lock_bits:
        locked = (
            " Honor these user selections exactly; do not invent or alter them: "
            + ", ".join(lock_bits) + "."
        )

    cluster_line = (
        " Diamonds must be clustered (pavé / micro-pavé / cluster settings)."
        if force_cluster else ""
    )
    solitaire_line = (
        " Do NOT create any solitaire or single oversized center stone, halo-solitaire, or look-alikes."
        if not allow_solitaires else
        " Solitaire center stone is allowed only if consistent with the selections."
    )

    return (
        " Design must be lightweight and suitable for daily wear with production-friendly thicknesses; "
        "avoid bulky metal masses; keep forms slim and comfortable. "
        " Maintain a balanced gold–to–diamond ratio (no excessive metal fill; stone sizes modest and wearable)."
        f"{cluster_line}{solitaire_line}"
        " Subcategory and setting constraints must be respected; do not change stone shapes, counts, or settings."
        " Front elevation (no 3/4 tilt), pure white seamless background, soft studio lighting, crisp reflections,"
        " and absolutely no text, numbers, watermarks, grids, or labels."
        + locked +
        " Avoid: single large center stones, halo-solitaire patterns, random motifs, extra gemstones not requested,"
        " heavy shadows, perspective drift, props/mannequins, and environment scenes."
    )


def _prep_sketch_1024(sketch_bytes: bytes, thresh: int = 200) -> str:
    img = Image.open(io.BytesIO(sketch_bytes)).convert("L")
    img = ImageOps.autocontrast(img)
    bw = img.point(lambda p: 255 if p > thresh else 0, mode="1")
    bbox = bw.getbbox() or (0, 0, img.width, img.height)
    cropped = img.crop(bbox)
    w, h = cropped.size
    side = max(w, h)
    canvas = Image.new("L", (side, side), 255)
    canvas.paste(cropped, ((side - w) // 2, (side - h) // 2))
    canvas = canvas.resize((1024, 1024), Image.LANCZOS)
    buf = io.BytesIO(); canvas.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode("utf-8")

def _extract_structure_json(sketch_data_url: str, jewelry_type_hint: str | None) -> dict:
    if _client is None:
        return {}
    sys = ("You are a jewelry CAD analyst. Output STRICT JSON describing the sketch geometry. "
           "Normalize coordinates 0..1 relative to the full canvas. Be concise. No commentary.")
    ask = [
        {"type":"text","text":(
            "Analyze this jewelry sketch and return JSON per the schema. "
            + (f'Jewelry type hint: "{jewelry_type_hint}". ' if jewelry_type_hint else "")
            + "Count leaves/petals/stones; include bounding boxes for major parts; "
              "record symmetry and any critical spacing/curve constraints.")},
        {"type":"image_url","image_url":{"url": sketch_data_url}},
    ]
    resp = _client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role":"system","content":sys},{"role":"user","content":ask}],
        temperature=0.2, max_tokens=600
    )
    raw = (resp.choices[0].message.content or "").strip()
    if raw.startswith("```"):
        if raw.startswith("```json"): raw = raw[7:]
        else: raw = raw[3:]
        if raw.endswith("```"): raw = raw[:-3]
        raw = raw.strip()
    try:
        return json.loads(raw)
    except Exception:
        return {}

def _make_prompt_from_structure(struct: dict, metal: str, stones: str, background: str, lighting: str) -> str:
    jt = struct.get("jewelry_type","jewelry").lower()
    view = (struct.get("view") or "front").lower()
    symmetry = struct.get("symmetry","none")
    constraints = struct.get("constraints","Preserve all relative positions, counts, and curve flows.")
    comps = struct.get("components", [])
    lines = []
    for c in comps:
        nm = c.get("name","component"); kind = c.get("kind","shape")
        cnt = c.get("count",1); bb = c.get("bbox",[0,0,1,1])
        try:
            x,y,w,h = [round(float(v),2) for v in bb[:4]]
        except Exception:
            x=y=0; w=h=1
        notes = c.get("notes","")
        lines.append(f"• {cnt} × {kind} ({nm}) at {x},{y} size {w}×{h}. {notes}".strip())
    layout = "\n".join(lines) if lines else "• Use components exactly as in the sketch."
    return (
        f"Photoreal CAD-style render of the provided sketch as {jt}. "
        f"STRICTLY preserve geometry and counts from the sketch. View: {view}. Symmetry: {symmetry}.\n"
        f"Layout spec:\n{layout}\n"
        f"Materials: {metal}; stones: {stones}. "
        f"Rendering: {lighting}; {background}. "
        f"Requirements: crisp edges, realistic metal reflections, production-friendly thickness. "
        f"Avoid: text/watermarks, perspective drift, heavy shadows, extra/removed elements, re-layout.\n"
        f"Constraints: {constraints}"
    )

def _critique_and_rewrite_prompt(sketch_b64_png: str, gen_b64_png: str, prev_prompt: str) -> str:
    if _client is None:
        return prev_prompt
    sys = ("You are a strict CAD reviewer. Compare SKETCH vs RENDER and output ONLY an improved prompt "
           "that will correct any geometry mismatches. No commentary.")
    user = [
        {"type":"text","text":"First image is SKETCH, second is RENDER."},
        {"type":"image_url","image_url":{"url": f"data:image/png;base64,{sketch_b64_png}"}},
        {"type":"image_url","image_url":{"url": f"data:image/png;base64,{gen_b64_png}"}},
        {"type":"text","text":f"Previous prompt:\n{prev_prompt}"},
    ]
    try:
        r = _client.chat.completions.create(
            model="gpt-4o",
            messages=[{"role":"system","content":sys},{"role":"user","content":user}],
            temperature=0.2, max_tokens=350
        )
        t = (r.choices[0].message.content or "").strip()
        return t or prev_prompt
    except Exception:
        return prev_prompt

def _binarize_and_center(sketch_bytes: bytes, out_size: int = 1024, thresh: int = 200) -> str:
    img = Image.open(io.BytesIO(sketch_bytes)).convert("L")
    img = ImageOps.autocontrast(img)
    bw = img.point(lambda p: 255 if p > thresh else 0, mode="1")
    bbox = bw.getbbox() or (0, 0, img.width, img.height)
    cropped = img.crop(bbox)
    w, h = cropped.size
    side = max(w, h)
    canvas = Image.new("L", (side, side), 255)
    canvas.paste(cropped, ((side - w) // 2, (side - h) // 2))
    canvas = canvas.resize((out_size, out_size), Image.LANCZOS)
    buf = io.BytesIO()
    canvas.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode("utf-8")

def _sketch_geometry_hints(sketch_bytes: bytes, thresh: int = 200) -> str:
    img = Image.open(io.BytesIO(sketch_bytes)).convert("L")
    bw = ImageOps.autocontrast(img).point(lambda p: 255 if p > thresh else 0, mode="1")
    bbox = bw.getbbox() or (0, 0, img.width, img.height)
    x0, y0, x1, y1 = bbox
    W, H = img.width, img.height
    left   = round((x0 / W) * 100, 1)
    right  = round(((W - x1) / W) * 100, 1)
    top    = round((y0 / H) * 100, 1)
    bottom = round(((H - y1) / H) * 100, 1)
    aw, ah = x1 - x0, y1 - y0
    ar = round((aw / ah) if ah else 1.0, 3)
    return (
        f"Canvas {W}x{H}px. Content bbox margins ≈ L{left}%, R{right}%, T{top}%, B{bottom}%. "
        f"Content aspect ratio ≈ {ar}:1 (width:height). Keep these margins and aspect."
    )

def _tiny_png_b64() -> str:
    return ("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAA"
            "AAC0lEQVR42mP8/wwAAwMB/ax0eQAAAABJRU5ErkJggg==")

def _err(message, status=400, detail=None):
    return jsonify({"ok": False, "error": {"message": message, "detail": detail}}), status

def _safe_prompt_for_context(prompt: str, max_len: int = 950) -> str:
    """
    Return a short, single-line, Cloudinary-safe context string.
    Robust against None / non-string inputs. No regex used.
    """
    s = "" if prompt is None else str(prompt)
    # Normalize whitespace/newlines
    s = s.replace("\r", " ").replace("\n", " ").replace("\t", " ")
    # Remove characters that sometimes break context parsing
    s = s.replace("|", " ").replace("=", " ")
    # Collapse multiple spaces
    while "  " in s:
        s = s.replace("  ", " ")
    s = s.strip()
    # Truncate
    if len(s) > max_len:
        s = s[: max_len - 1].rstrip() + "…"
    return s

def _upload_to_cloudinary(*, b64_png: str = None, remote_url: str = None,
                          folder=CLOUDINARY_FOLDER, prompt_ctx: str = "",
                          album: str = "") -> dict:
    """
    Upload PNG (base64) OR remote URL to Cloudinary.
    Saves prompt and album into `context` so the Gallery can show it later.
    """
    if not (CLOUDINARY_CLOUD_NAME and CLOUDINARY_API_KEY and CLOUDINARY_API_SECRET):
        raise RuntimeError("Cloudinary environment variables are not configured")

    context = {}
    if prompt_ctx:
        context["prompt"] = _safe_prompt_for_context(prompt_ctx)
    if album:
        context["album"] = album

    tags = ["jewelgen", "generated"]
    if album:
        tags.append(album)

    if remote_url:
        return cloudinary.uploader.upload(
            remote_url,
            folder=folder,
            resource_type="image",
            tags=tags,
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
        tags=tags,
        context=context,
        unique_filename=True,
        overwrite=False,
    )

def _images_generate_with_retries(prompt: str, model_pref: str = "auto", *, tries=3, timeout=90):
    b64 = None
    url = None
    backoff = 1.5

    if _client:
        client = _client.with_options(timeout=timeout)
        models = [model_pref] if model_pref in ("gpt-image-1", "dall-e-3") else ["dall-e-3", "gpt-image-1"]
        for m in models:
            for attempt in range(tries):
                try:
                    resp = client.images.generate(
                        model=m,
                        prompt=prompt,
                        size="1024x1024",
                        n=1,
                        response_format="b64_json",
                    )
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

@app.get("/__ls_static")
def __ls_static():
    out = []
    for root, _, files in os.walk(os.path.join(app.root_path, "static")):
        for f in files:
            path = os.path.relpath(os.path.join(root, f), app.root_path)
            size = os.path.getsize(os.path.join(root, f))
            out.append({"path": path, "size": size})
    return jsonify(out)
@app.route("/design-variants")
def design_variants_alias():
    return render_template("design_variant_generator.html")


# ── Generate (text → image) + upload to Cloudinary ──────────────────────────
@app.post("/generate")
def generate():
    import traceback
    try:
        data = request.get_json(force=True) or {}
        base_prompt = (data.get("prompt") or "").strip()
        model_pref  = (data.get("model") or "dall-e-3").strip().lower()
        album       = (data.get("album") or "index").strip().lower()
        jtype       = (data.get("jewelry_type") or "").strip()

        if not base_prompt:
            return _err("Prompt is required.", 400)
        if len(base_prompt) > 4000:
            return _err("Prompt too long.", 400)

        # Start with given prompt
        prompt = base_prompt

        # If jewelry type provided, prepend guidance
        if jtype and (jtype.lower() not in base_prompt.lower()):
            prompt = (
                f"Create a lightweight {jtype.lower()} design. "
                f"Respect proportions, ergonomics, and functional constraints appropriate to a {jtype.lower()}. "
                + base_prompt
            )

        # --- ENFORCE PRODUCTION CONSTRAINTS ---
        prompt += (
            " Ensure design follows lightweight diamond jewellery standards: "
            "target diamond-to-gold weight ratio around 0.8 (example: 0.25–0.35 cts diamonds on ~2.5–3 gms gold). "
            "Use open lattice or halo-style frameworks, clustered melee diamonds, and avoid heavy solitaires unless requested. "
            "Make it production-friendly with realistic thickness, ergonomics for daily wear, "
            "and elegant CAD-style rendering. "
            "Output as hyper-realistic catalog-style render, front view, polished finish, "
            "pure white background, no props, text, or watermarks."
        )

        print("🎯 /generate prompt:", prompt.replace("\n", " "))

        try:
            b64, url = _images_generate_with_retries(prompt, model_pref=model_pref, tries=3, timeout=90)
        except Exception as e:
            print("❌ OpenAI call raised:", repr(e))
            traceback.print_exc()
            return _err(f"Upstream (OpenAI) error: {e}", 502, str(e))

        if not (b64 or url):
            return _err("OpenAI image service temporarily unavailable. Please try again.", 503)

        try:
            up = _upload_to_cloudinary(
                b64_png=b64,
                remote_url=None if b64 else url,
                folder=CLOUDINARY_FOLDER,
                prompt_ctx=prompt,
                album=album or "index",
            )
        except Exception as e:
            print("❌ Cloudinary upload error:", repr(e))
            traceback.print_exc()
            return _err(f"Upload to Cloudinary failed: {e}", 502, str(e))

        return jsonify({
            "ok": True,
            "prompt": prompt,
            "image": b64,
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
        print("❌ Unhandled error in /generate:", repr(e))
        traceback.print_exc()
        return _err("Failed to generate image (server error). See server logs for details.", 500, str(e))

    
# ── Image (motif) → JSON {description, prompt} via GPT-4o Vision ────────────
@app.route("/generate_prompts", methods=["GET", "POST"])
def generate_prompts():
    if request.method == "GET":
        return _err("Use POST with multipart/form-data (image/motif, use_case).", 405)

    try:
        if _client is None:
            return _err("OpenAI client not available. Update the openai package.", 500)

        # accept both keys: "image" (our backend) or "motif" (some JS versions)
        image_file = request.files.get("image") or request.files.get("motif")
        use_case = (request.form.get("use_case") or "").strip() or "Jewelry"
        if not image_file:
            return _err("No image uploaded", 400)

        # Optional user constraints from the form (send them from UI if available)
        attrs = {
            "jewelry_type":      (request.form.get("jewelry_type") or "").strip(),
            "subcategory":       (request.form.get("subcategory") or "").strip(),
            "metal":             (request.form.get("metal") or "").strip(),
            "gemstone":          (request.form.get("gemstone") or "").strip(),
            "diamond_shape":     (request.form.get("diamond_shape") or "").strip(),
            "setting_style":     (request.form.get("setting_style") or "").strip(),
            "stone_arrangement": (request.form.get("stone_arrangement") or "").strip(),
            "num_diamonds":      (request.form.get("num_diamonds") or "").strip(),
            "carat_weight":      (request.form.get("carat_weight") or "").strip(),
            "gold_weight":       (request.form.get("gold_weight") or "").strip(),
            "size_range":        (request.form.get("size_range") or "").strip(),
        }
        allow_solitaires = _coerce_bool(request.form.get("allow_solitaires", "false"))
        force_cluster    = _coerce_bool(request.form.get("force_cluster", "true"))

        constraint_block = _build_constraint_text(
            allow_solitaires=allow_solitaires,
            force_cluster=force_cluster,
            attrs=attrs,
        )

        image_b64 = base64.b64encode(image_file.read()).decode("utf-8")

        system_instructions = f"""
You are a professional fine jewelry designer AI.

The user uploads a motif image to inspire a lightweight, wearable {use_case.lower()}.
Return STRICT JSON with keys: "description" and "prompt".

Rules to follow in the prompt:
{constraint_block}
""".strip()

        resp = _client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": system_instructions},
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": (
                            "Analyze the image and write:\n"
                            "- description: ≤ 50 words (high level, no CAD jargon)\n"
                            "- prompt: one polished, realistic render prompt that obeys ALL rules above."
                        )},
                        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image_b64}"}} ,
                    ],
                },
            ],
            temperature=0.5,
            max_tokens=650
        )

        msg = resp.choices[0].message
        raw = (msg.content if hasattr(msg, "content") else (msg.get("content") if isinstance(msg, dict) else "")) or ""
        raw = raw.strip()
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

        # As a belt-and-suspenders, append a tiny guard if the model omitted it:
        if pr and "cluster" not in pr.lower() and not allow_solitaires:
            pr += " Diamonds arranged in clustered pavé or micro-pavé; no solitaire center stone."

        return jsonify({"ok": True, "description": desc, "prompt": pr})

    except Exception as e:
        return _err("Error during motif analysis", 500, str(e))


# ── Sketch → CAD-style image (OpenAI-only flow) ─────────────────────────────
@app.route("/generate_from_sketch", methods=["POST"])
def generate_from_sketch():
    """
    Sketch → Product-style jewelry render
    Plain white background, centered, front view.
    """
    try:
        if not (_client or _legacy):
            return _err("OpenAI client not available. Check API key.", 500)

        f = request.files.get("sketch")
        if not f:
            return _err("No sketch uploaded", 400)

        jt = (request.form.get("type") or "jewelry").strip()
        raw = f.read()
        sketch_b64 = base64.b64encode(raw).decode("utf-8")

        positive = (
            f"High-quality photorealistic render of a lightweight {jt}, "
            f"based directly on the provided sketch. "
            "Front view, perfectly centered, plain pure white seamless background, "
            "soft studio lighting, realistic gold/diamond textures, "
            "production-friendly proportions, catalog product photo style."
        )
        negative = (
            "sketch, drawing, CAD render, blueprint, rulers, grid, text, watermark, "
            "paper, technical sheet, environment, props, mannequin, hand, shadow"
        )

        b64, url = _images_generate_with_retries(
            f"{positive}\n\nAvoid: {negative}",
            model_pref="dall-e-3",
            tries=3, timeout=90
        )
        if not (b64 or url):
            return _err("Image generation failed.", 502)

        up = _upload_to_cloudinary(
            b64_png=b64,
            remote_url=None if b64 else url,
            folder=CLOUDINARY_FOLDER,
            prompt_ctx=positive,
            album="inspiration",
        )

        return jsonify({
            "ok": True,
            "url": up.get("secure_url"),
            "prompt": positive,
            "public_id": up.get("public_id")
        })

    except Exception as e:
        import traceback; traceback.print_exc()
        return _err("Failed to generate from sketch", 500, str(e))



# --- Design Variant Generator ---
@app.route("/design-variant-generator")
def design_variant_generator():
    return render_template("design_variant_generator.html")

# --- Set Generator ---
@app.route("/setgenerator")
def set_generator():
    return render_template("setgenerator.html")


# --- Text Automation ---
@app.route("/textautomation")
def text_automation():
    return render_template("textautomation.html")
from datetime import datetime

@app.context_processor
def inject_current_year():
    return {"current_year": datetime.now().year}

# ── Gallery APIs ────────────────────────────────────────────────────────────
@app.get("/images")
def list_images():
    """
    Returns paginated images from Cloudinary.
    Query params:
      album   = filter by album (optional)
      cursor  = Cloudinary next_cursor (optional)
      limit   = page size (default 30, max 100)
    """
    try:
        limit = min(max(int(request.args.get("limit") or 30), 10), 100)
        cursor = request.args.get("cursor")
        album_filter = (request.args.get("album") or "").strip().lower()

        expr = f'resource_type:image AND folder="{CLOUDINARY_FOLDER}"'

        search = (
            cloudinary.search.Search()
            .expression(expr)
            .sort_by("created_at", "desc")
            .max_results(limit)
            .with_field("context")   # include context
            .with_field("tags")      # include tags (fallback)
            .with_field("metadata")  # include structured metadata (fallback)
        )
        if cursor:
            search = search.next_cursor(cursor)

        res = search.execute()
        resources = res.get("resources", [])

        items = []
        for r in resources:
            # --- pull prompt robustly ---
            ctx = r.get("context") or {}
            meta = r.get("metadata") or {}
            tags = r.get("tags") or []

            prompt = ""
            album = ""

            # context.custom (most common)
            if isinstance(ctx, dict):
                custom = ctx.get("custom") if isinstance(ctx.get("custom"), dict) else None
                if custom:
                    prompt = custom.get("prompt") or prompt
                    album = custom.get("album") or album
                # flat context (some SDK responses)
                prompt = ctx.get("prompt") or prompt
                album = ctx.get("album") or album

            # structured metadata fallback
            if not prompt and isinstance(meta, dict):
                prompt = meta.get("prompt") or prompt
                if not album:
                    album = meta.get("album") or album

            # tag fallback: prompt:xyz / album:xyz
            if tags:
                for t in tags:
                    if not prompt and t.lower().startswith("prompt:"):
                        prompt = t.split(":", 1)[1].strip()
                    if not album and t.lower().startswith("album:"):
                        album = t.split(":", 1)[1].strip()

            # normalize album
            if not album:
                # last fallback to recognized tags
                for t in tags:
                    tl = t.lower()
                    if tl in {"index", "set", "variants", "vector", "inspiration", "motif", "unknown"}:
                        album = tl
                        break

            # filter
            album_norm = (album or "unknown").lower()
            if album_filter and album_norm != album_filter:
                continue

            items.append({
                "url": r.get("secure_url"),
                "prompt": prompt or "",
                "album": album_norm or "unknown",
                "public_id": r.get("public_id"),
                "created_at": r.get("created_at"),
            })

        return jsonify({"items": items, "next_cursor": res.get("next_cursor")})
    except Exception as e:
        import traceback; traceback.print_exc()
        return jsonify({"ok": False, "error": str(e)}), 500


# --- Variants ---
# --- Design Variants API ---
# --- Design Variants API ---
@app.route("/api/design-variants", methods=["POST"])
def api_design_variants():
    try:
        base_type = request.form.get("base_type", "")
        base_motif = request.form.get("base_motif", "")
        metal = request.form.get("metal", "")
        stone = request.form.get("stone", "")
        weight_target = request.form.get("weight_target", "")
        targets = json.loads(request.form.get("targets", "[]"))

        img_url = None

        # 1️⃣ If file uploaded → upload to Cloudinary
        if "base_image" in request.files:
            file = request.files["base_image"]
            if file.filename:
                try:
                    upload_result = cloudinary.uploader.upload(file, folder="design_variants")
                    img_url = upload_result["secure_url"]
                except Exception as ce:
                    print("⚠️ Cloudinary upload failed, saving locally:", ce)
                    # fallback local save
                    save_dir = os.path.join("static", "generated")
                    os.makedirs(save_dir, exist_ok=True)
                    path = os.path.join(save_dir, file.filename)
                    file.save(path)
                    img_url = "/" + path.replace("\\", "/")

        # 2️⃣ If no image uploaded, use placeholder
        if not img_url:
            img_url = "/static/placeholder.png"

        # 3️⃣ Generate dummy variants (replace later with AI)
        variants = []
        for t in targets:
            variants.append({
                "label": f"{t.capitalize()} variant ({metal}, {stone})",
                "url": img_url
            })

        return jsonify({"variants": variants})

    except Exception as e:
        print("❌ Error in /api/design-variants:", e)
        return jsonify({"error": str(e)}), 500
# --- Set ---
@app.route("/api/set-simple", methods=["POST"])
def api_set_simple():
    """
    Expect multipart/form-data:
      - theme (text)
      - ref_image (file, optional)
      - pieces[] (checkbox values: necklace, earrings, ring, bangle, bracelet, pendant)
    """
    try:
        theme = (request.form.get("theme") or "").strip()
        pieces = [p.strip().lower() for p in request.form.getlist("pieces") if p.strip()]
        if not pieces:
            return _err("No pieces selected.", 400)

        has_ref = False
        if "ref_image" in request.files and request.files["ref_image"]:
            _ = request.files["ref_image"].read()
            has_ref = True

        piece_notes = {
            "necklace": "balanced centerpiece, chain anchors cropped minimally; front elevation; no mannequin.",
            "earrings": "pair symmetry, comfortable post or hook; realistic shadow only; front elevation.",
            "ring":     "proper shank thickness; clean front elevation; no hand/finger.",
            "bangle":   "circular/oval profile; front elevation.",
            "bracelet": "gentle curve, clasp not exaggerated; centered; front elevation.",
            "pendant":  "bail aligned; minimal chain crop; centered; front elevation."
        }

        results = []
        for piece in pieces:
            note = piece_notes.get(piece, "front elevation, centered.")
            img_hint = " Use the uploaded reference image as styling inspiration only (do not copy exactly)." if has_ref else ""
            theme_hint = f"Theme/motif: {theme}. " if theme else ""

            prompt = (
                f"Photoreal, catalog-style CAD render of a lightweight {piece}. "
                f"{theme_hint}{img_hint}"
                f"Pure white seamless background, soft studio lighting, crisp reflections. "
                f"No text, no watermark, no grids, no props. {note}"
            )

            b64, url = _images_generate_with_retries(prompt, model_pref="dall-e-3", tries=3, timeout=90)
            if not (b64 or url):
                continue

            up = _upload_to_cloudinary(
                b64_png=b64,
                remote_url=None if b64 else url,
                folder=CLOUDINARY_FOLDER,
                prompt_ctx=prompt,
                album="set"
            )

            results.append({"piece": piece, "url": up.get("secure_url"), "prompt": prompt})

        return jsonify({"ok": True, "results": results})
    except Exception as e:
        return _err("Failed to generate set", 500, str(e))


# --- Vectorize motif ---
# --- Vectorize motif (badges + banners aware) ---
# --- Vectorize motif (photo-aware, badges+banners, nicer output) ---
@app.route("/api/vectorize", methods=["POST"])
def api_vectorize():
    """
    Accepts multipart/form-data:
      - image or motif (file)
      - layout: badges_banners | flat
      - trace_preset: solid | outline | detailed   (auto-switches to outline for photos)
    Returns:
      { ok, svg, badges, banners, download_url }
    """
    try:
        f = request.files.get("image") or request.files.get("motif")
        if not f:
            return _err("No image/motif uploaded", 400)

        layout = (request.form.get("layout") or "badges_banners").strip().lower()
        preset = (request.form.get("trace_preset") or "solid").strip().lower()

        # --- load grayscale ---
        file_bytes = np.frombuffer(f.read(), np.uint8)
        gray = cv2.imdecode(file_bytes, cv2.IMREAD_GRAYSCALE)
        if gray is None:
            return _err("Failed to read image", 400)

        H, W = gray.shape[:2]
        canvas_area = float(W * H)

        # gentle denoise
        gray = cv2.GaussianBlur(gray, (3, 3), 0)

        # --- decide: photo vs motif ---
        # Heuristic: photos have high gray-level variance & texture
        var = float(gray.var())
        is_photo_like = var > 500.0  # tweakable

        # let user force outline if they asked
        force_outline = (preset == "outline")
        force_detailed = (preset == "detailed")

        # choose path mode
        outline_mode = force_outline or (is_photo_like and not force_detailed)

        # --- build a binary/edge mask ---
        if outline_mode:
            # Edges → thin strokes only
            edges = cv2.Canny(gray, 80, 200)
            # thicken a bit so we get continuous paths
            edges = cv2.dilate(edges, np.ones((2, 2), np.uint8), iterations=1)
            bw = edges
        else:
            # Solid shapes
            # Otsu OR slightly biased threshold
            _, bw = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
            # invert so shapes = white on black? we want contours of shapes:
            bw = 255 - bw
            # clean speckles
            bw = cv2.morphologyEx(bw, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8), iterations=1)

        # --- find contours with hierarchy to support holes ---
        contours, hierarchy = cv2.findContours(bw, cv2.RETR_CCOMP, cv2.CHAIN_APPROX_SIMPLE)
        if hierarchy is None:
            hierarchy = []

        def touches_border(cnt):
            x, y, w, h = cv2.boundingRect(cnt)
            touch = (x <= 1) + (y <= 1) + (x + w >= W - 2) + (y + h >= H - 2)
            return touch >= 2  # touching two or more borders is likely a frame

        # filters
        MIN_AREA = max(12.0, 0.00015 * canvas_area)  # drop tiny dust
        MAX_KEEP_RATIO = 0.93                         # drop huge frame-like regions

        # path approx
        # epsilon relative to perimeter (smoother in solid mode, tighter in detailed)
        def approx_cnt(cnt):
            per = cv2.arcLength(cnt, True)
            if force_detailed:
                eps = 0.005 * per
            elif outline_mode:
                eps = 0.02 * per
            else:
                eps = 0.01 * per
            return cv2.approxPolyDP(cnt, max(0.5, eps), True)

        # convert contour (+holes) to SVG path using evenodd fill rule
        def contour_with_holes_to_path(idx):
            # hierarchy format: [Next, Prev, FirstChild, Parent]
            path_cmds = []
            i = idx
            while i != -1:
                cnt = contours[i]
                a = float(cv2.contourArea(cnt))
                if a < MIN_AREA:
                    i = hierarchy[0][i][0] if len(hierarchy) else -1
                    continue
                ap = approx_cnt(cnt)
                pts = ap.reshape(-1, 2).astype(float)
                if len(pts) >= 2:
                    path_cmds.append("M" + " ".join([f"{pts[0,0]},{pts[0,1]}"]))
                    for p in pts[1:]:
                        path_cmds.append(f"L{p[0]},{p[1]}")
                    path_cmds.append("Z")
                # next sibling
                i = hierarchy[0][i][0] if len(hierarchy) else -1
            return " ".join(path_cmds)

        badges_paths, banners_paths = [], []

        # iterate only top-level components (parent == -1)
        if len(hierarchy):
            for i, h in enumerate(hierarchy[0]):
                parent = h[3]
                if parent != -1:
                    continue  # only outer components; children handled when building path

                cnt = contours[i]
                area = float(abs(cv2.contourArea(cnt)))
                if area < MIN_AREA:
                    continue
                if area / canvas_area > MAX_KEEP_RATIO:
                    continue
                if touches_border(cnt):
                    continue

                path_d = contour_with_holes_to_path(i)

                if outline_mode:
                    fill = "none"
                    stroke = "#000"
                    stroke_w = 1.2 if force_detailed else 1.0
                else:
                    fill = "#000"
                    stroke = "#000"
                    stroke_w = 0.8 if force_detailed else 1.0

                el = f'<path d="{path_d}" fill="{fill}" stroke="{stroke}" stroke-width="{stroke_w}" fill-rule="evenodd"/>'

                # classify banner vs badge
                ratio = area / canvas_area
                ar_w, ar_h, ar = 0, 0, 0
                x, y, ww, hh = cv2.boundingRect(cnt)
                ar = ww / float(hh or 1)
                # banners: bigger OR very wide/tall strips
                is_banner = (ratio >= 0.02) or (ar >= 3.0) or (ar <= (1/3.0))
                if is_banner:
                    banners_paths.append(el)
                else:
                    badges_paths.append(el)
        else:
            # fallback: single contour run
            pass

        if layout == "flat":
            badges_paths = badges_paths + banners_paths
            banners_paths = []

        # build combined svg
        groups = []
        if badges_paths:
            groups.append('<g id="badges">' + "\n".join(badges_paths) + "</g>")
        if banners_paths:
            groups.append('<g id="banners">' + "\n".join(banners_paths) + "</g>")
        if not groups:
            groups.append('<!-- no usable contours (try different image or outline preset) -->')

        svg_text = (
            f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}">\n'
            + "\n".join(groups) + "\n</svg>"
        )

        # optional Cloudinary upload
        download_url = None
        try:
            if CLOUDINARY_CLOUD_NAME and CLOUDINARY_API_KEY and CLOUDINARY_API_SECRET:
                payload = "data:image/svg+xml;base64," + base64.b64encode(svg_text.encode("utf-8")).decode("utf-8")
                up = cloudinary.uploader.upload(
                    payload,
                    resource_type="image",
                    format="svg",
                    folder=CLOUDINARY_FOLDER,
                    tags=["vectorized", "vector", "outline" if outline_mode else "solid"],
                    context={"album": "vector"},
                    unique_filename=True,
                    overwrite=False,
                )
                download_url = up.get("secure_url")
        except Exception as e:
            print("Cloudinary upload failed:", e)

        return jsonify({
            "ok": True,
            "svg": svg_text,
            "badges": badges_paths,
            "banners": banners_paths,
            "download_url": download_url
        })

    except Exception as e:
        import traceback; traceback.print_exc()
        return _err("Vectorization failed", 500, str(e))


# --- Motif → 6-up flat "vector-style" sprite sheet (one PNG) ---
@app.post("/api/vector-sprites")
def api_vector_sprites():
    """
    Multipart form:
      - image (file) or motif (file)
      - style: mono | duotone | color
      - background: transparent | white
    Returns: { ok, url, b64, description, prompt }
    """
    try:
        if not (_client or _legacy):
            return _err("OpenAI client not available. Check API key.", 500)

        f = request.files.get("image") or request.files.get("motif")
        if not f:
            return _err("No image uploaded", 400)

        style = (request.form.get("style") or "mono").strip().lower()
        bg    = (request.form.get("background") or "white").strip().lower()

        # 1) brief description with GPT-4o
        raw = f.read()
        img_b64 = base64.b64encode(raw).decode("utf-8")
        desc = "simple subject"
        try:
            sys = ("You are an expert iconographer. Describe the uploaded image in 2–3 short sentences, "
                   "focusing on silhouette and key visual cues. No extra commentary.")
            r = _client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {"role":"system","content":sys},
                    {"role":"user","content":[
                        {"type":"text","text":"Describe this image briefly for flat vector icons."},
                        {"type":"image_url","image_url":{"url": f"data:image/jpeg;base64,{img_b64}"}}
                    ]}
                ],
                temperature=0.3, max_tokens=160
            )
            desc = (r.choices[0].message.content or "").strip()
        except Exception as e:
            print("⚠️ description fallback:", e)

        # 2) build sprite sheet prompt (3x2 grid → one 1024x1024 image)
        palette = {
            "mono":     "solid single-color fill (use black on light background), minimal negative space",
            "duotone":  "two-color palette, harmonious tones, clean contrast",
            "color":    "limited 3–4 color palette, bold and flat fills",
        }.get(style, "solid single-color fill (use black on light background), minimal negative space")
        bg_line = "transparent background" if bg == "transparent" else "clean white background"
        prompt = (
            "Create a single 1024x1024 sprite sheet with six flat 2D vector-style icon variations "
            f"(arranged in a 3x2 grid) derived from this description: {desc}. "
            "Icon style: crisp silhouettes, smooth contours, no gradients, no textures, no shadows, no text, no watermark. "
            "All icons centered within consistent tiles, equal padding, same stroke weight if any; "
            f"{palette}; {bg_line}. Each tile must be a distinct variation of the same motif."
        )

        # 3) generate image (DALL·E / gpt-image-1)
        b64, url = _images_generate_with_retries(prompt, model_pref="dall-e-3", tries=3, timeout=90)
        if not (b64 or url):
            return _err("Image generation failed upstream.", 502)

        # 4) upload to Cloudinary (optional)
        uploaded = {}
        try:
            uploaded = _upload_to_cloudinary(
                b64_png=b64,
                remote_url=None if b64 else url,
                folder=CLOUDINARY_FOLDER,
                prompt_ctx=_safe_prompt_for_context(prompt),
                album="vector",
            )
        except Exception as e:
            print("Cloudinary upload failed (non-fatal):", e)

        return jsonify({
            "ok": True,
            "url": uploaded.get("secure_url") or url,
            "b64": b64,
            "description": desc,
            "prompt": prompt,
        })
    except Exception as e:
        import traceback; traceback.print_exc()
        return _err("Sprite generation failed", 500, str(e))



# --- Text from image ---
@app.route("/api/text-from-image", methods=["POST"])
def api_text_from_image():
    """
    Expect multipart/form-data:
      - image: file
      - tone: professional|catalog|luxury
      - lang: ISO code (currently 'en')
    Returns: { ok, ppt, catalog }
    """
    try:
        if _client is None:
            return _err("OpenAI client not available.", 500)

        f = request.files.get("image")
        tone = (request.form.get("tone") or "professional").strip().lower()
        lang = (request.form.get("lang") or "en").strip().lower()
        if not f:
            return _err("No image uploaded", 400)

        image_b64 = base64.b64encode(f.read()).decode("utf-8")

        sys = (
            "You are a jewelry copywriter. Produce:\n"
            "1) PPT_BLURB: 40–60 words; bullet-friendly; impact; no fluff.\n"
            "2) CATALOG: 120–180 words; materials, setting, motif, wearability, care cues; SEO-friendly.\n"
            "Adapt tone = professional|catalog|luxury. Language is specified by the user."
        )
        user = [
            {"type":"text","text":f"Tone={tone}; Language={lang}. Return JSON with keys ppt and catalog."},
            {"type":"image_url","image_url":{"url": f"data:image/jpeg;base64,{image_b64}"}}
        ]

        r = _client.chat.completions.create(
            model="gpt-4o",
            messages=[{"role":"system","content":sys},{"role":"user","content":user}],
            temperature=0.6, max_tokens=700
        )
        raw = (r.choices[0].message.content or "").strip()
        if raw.startswith("```"):
            if raw.startswith("```json"): raw = raw[7:]
            else: raw = raw[3:]
            if raw.endswith("```"): raw = raw[:-3]
            raw = raw.strip()
        data = json.loads(raw)
        return jsonify({"ok": True, "ppt": data.get("ppt",""), "catalog": data.get("catalog","")})
    except Exception as e:
        return _err("Failed to generate text", 500, str(e))

# ── Delete a Cloudinary image by public_id ───────────────────────────────────
@app.post("/delete")
def delete_image():
    """
    Request JSON: { "public_id": "ImageGeneration/<file>" }
    Response: { ok: true, result: <cloudinary response> }
    """
    try:
        data = request.get_json(force=True) or {}
        public_id = (data.get("public_id") or "").strip()
        if not public_id:
            return _err("Missing public_id.", 400)

        resp = cloudinary.uploader.destroy(public_id, invalidate=True, resource_type="image")
        result = (resp or {}).get("result")
        if result not in ("ok", "not found", "queued"):
            return _err(f"Cloudinary destroy failed: {resp}", 500)

        return jsonify({"ok": True, "result": resp})
    except Exception as e:
        return _err("Failed to delete image", 500, str(e))

# ── Routes Inspector / Debug ────────────────────────────────────────────────
@app.get("/__routes__")
def __routes__():
    rules = []
    for r in app.url_map.iter_rules():
        methods = sorted(m for m in r.methods if m not in ("HEAD", "OPTIONS"))
        rules.append({"rule": str(r), "endpoint": r.endpoint, "methods": methods})
    return jsonify(rules)


@app.route("/motiftovector")
def motiftovector():
    return render_template("motiftovector.html")

@app.get("/__debug_js")
def __debug_js():
    return send_from_directory("static/js", "main.js")

# ── Main ────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    debug = os.getenv("FLASK_DEBUG", "0") == "1"
    print("🔎 URL MAP:\n", app.url_map)
    app.run(host="0.0.0.0", port=port, debug=debug)
