import base64
import json
import os
import re
import time
from collections import defaultdict, deque
from functools import wraps
from pathlib import Path

import requests
from flask import Flask, abort, jsonify, request, send_from_directory

BASE_DIR = Path(__file__).resolve().parent
PUBLIC_DIR = (BASE_DIR / "public").resolve()
ENV_FILE = BASE_DIR / ".env"


def load_dotenv(path: Path) -> None:
    """Tiny .env loader. Existing real environment variables always win."""
    if not path.exists():
        return
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if not key or key in os.environ:
            continue
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        os.environ[key] = value


def normalize_api_key(raw_value: str) -> str:
    value = (raw_value or "").strip()
    if not value:
        return ""
    lowered = value.lower()
    blocked_markers = (
        "paste_",
        "your_",
        "example",
        "placeholder",
        "replace_me",
        "not_set",
    )
    if any(marker in lowered for marker in blocked_markers):
        return ""
    return value


load_dotenv(ENV_FILE)

APP_PASSWORD = os.getenv("APP_PASSWORD", "").strip()
MODEL = os.getenv("MODEL", "claude-sonnet-5-5").strip() or "claude-sonnet-5-5"
API_KEY = normalize_api_key(os.getenv("ANTHROPIC_API_KEY", ""))
try:
    RATE_LIMIT_PER_HOUR = max(1, int(os.getenv("RATE_LIMIT_PER_HOUR", "40")))
except ValueError:
    RATE_LIMIT_PER_HOUR = 40

PORT = int(os.getenv("PORT", "3000"))
ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 16 * 1024 * 1024

# In-memory rolling-window limiter. This intentionally stays dependency-free.
_request_log = defaultdict(deque)

EXTRACTION_INSTRUCTION = r'''Convert the attached photo and/or notes into JSON for a college template.
Keep question wording exactly as given (fix only obvious OCR errors).
Number questions 1..N; consecutive pairs (1-2, 3-4, ...) are the two OR choices of one Question group.
Use "" for unknown fields.
If a question refers to a network/graph figure, add figure {"caption":"Fig.1","nodes":[{"id":"A","x":10,"y":50}],"edges":[["A","B",2]]} laid out like the original (x 0-280, y 0-120), else figure null.
Add outcomes [["CO1","text"],...] if the paper lists course outcomes, else [].
Return ONLY JSON:
{"subject":"","code":"","semester":"","maxMarks":"","batch":"","duration":"","date":"","dept":"","instructions":"","questions":[{"no":1,"text":"","marks":10,"co":"","rbt":"","figure":null}],"outcomes":[]}

Spoken or typed notes (for example "question 1: illustrate data link layer design issues, 10 marks, CO2, L2") must be converted into the same JSON.'''

UPDATE_INSTRUCTION = r'''Apply only the changes described by the teacher to the supplied existing JSON and return the full updated JSON.
Do not rewrite, summarize, reorder, or improve unrelated content. Preserve all existing fields and question wording unless the change explicitly targets them.
Return ONLY JSON in exactly this shape:
{"subject":"","code":"","semester":"","maxMarks":"","batch":"","duration":"","date":"","dept":"","instructions":"","questions":[{"no":1,"text":"","marks":10,"co":"","rbt":"","figure":null}],"outcomes":[]}.'''


def client_ip() -> str:
    forwarded = request.headers.get("X-Forwarded-For", "")
    if forwarded:
        return forwarded.split(",")[0].strip() or request.remote_addr or "unknown"
    return request.remote_addr or "unknown"


def prune_rate_log(now: float) -> None:
    cutoff = now - 3600
    for ip, timestamps in list(_request_log.items()):
        while timestamps and timestamps[0] <= cutoff:
            timestamps.popleft()
        if not timestamps:
            _request_log.pop(ip, None)


def rate_limited() -> bool:
    now = time.time()
    prune_rate_log(now)
    bucket = _request_log[client_ip()]
    if len(bucket) >= RATE_LIMIT_PER_HOUR:
        return True
    bucket.append(now)
    return False


def wants_json() -> bool:
    return request.path.startswith("/api/") or request.path == "/health"


def unauthorized():
    response = jsonify({"error": "Authentication required. Enter the configured APP_PASSWORD."})
    response.status_code = 401
    response.headers["WWW-Authenticate"] = 'Basic realm="Question Paper Maker"'
    return response


def require_auth(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not APP_PASSWORD:
            return view(*args, **kwargs)
        auth = request.authorization
        if not auth or auth.password != APP_PASSWORD:
            return unauthorized()
        return view(*args, **kwargs)

    return wrapped


def safe_public_file(path_value: str) -> Path:
    candidate = (PUBLIC_DIR / path_value).resolve()
    if candidate != PUBLIC_DIR and PUBLIC_DIR not in candidate.parents:
        abort(404)
    if not candidate.is_file():
        abort(404)
    return candidate


def normalize_data_url(image_value: str):
    if not image_value:
        return None, None
    if not image_value.startswith("data:image/"):
        raise ValueError("image must be a data URL such as data:image/jpeg;base64,...")
    try:
        header, encoded = image_value.split(",", 1)
    except ValueError as exc:
        raise ValueError("Invalid image data URL.") from exc
    match = re.match(r"data:(image/[a-zA-Z0-9.+-]+);base64$", header)
    if not match:
        raise ValueError("Image must be base64-encoded.")
    try:
        base64.b64decode(encoded, validate=True)
    except Exception as exc:
        raise ValueError("Image base64 data is invalid.") from exc
    # Anthropic image blocks accept the media type and raw base64 separately.
    return match.group(1).lower(), encoded


def extract_json_object(text: str):
    """Best-effort server-side guard in case the model returns fenced JSON."""
    cleaned = text.strip()
    cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.I)
    cleaned = re.sub(r"\s*```$", "", cleaned)
    match = re.search(r"\{[\s\S]*\}", cleaned)
    if not match:
        raise ValueError("The AI response did not contain a JSON object.")
    return json.loads(match.group(0))


def validate_and_shape(payload):
    if not isinstance(payload, dict):
        raise ValueError("AI response JSON must be an object.")
    questions = payload.get("questions")
    if not isinstance(questions, list):
        questions = []
    outcomes = payload.get("outcomes")
    if not isinstance(outcomes, list):
        outcomes = []
    shaped = {
        "subject": str(payload.get("subject", "")),
        "code": str(payload.get("code", "")),
        "semester": str(payload.get("semester", "")),
        "maxMarks": str(payload.get("maxMarks", "")),
        "batch": str(payload.get("batch", "")),
        "duration": str(payload.get("duration", "")),
        "date": str(payload.get("date", "")),
        "dept": str(payload.get("dept", "")),
        "instructions": str(payload.get("instructions", "")),
        "questions": [],
        "outcomes": [],
    }
    for index, q in enumerate(questions, 1):
        if not isinstance(q, dict):
            continue
        figure = q.get("figure") if isinstance(q.get("figure"), dict) else None
        shaped["questions"].append(
            {
                "no": int(q.get("no", index) or index),
                "text": str(q.get("text", "")),
                "marks": q.get("marks", ""),
                "co": str(q.get("co", "")),
                "rbt": str(q.get("rbt", "")),
                "figure": figure,
            }
        )
    for outcome in outcomes:
        if isinstance(outcome, (list, tuple)) and len(outcome) >= 2:
            shaped["outcomes"].append([str(outcome[0]), str(outcome[1])])
        elif isinstance(outcome, dict):
            shaped["outcomes"].append([str(outcome.get("code", "")), str(outcome.get("text", ""))])
    return shaped


@app.after_request
def add_common_headers(response):
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    return response


@app.get("/health")
def health():
    return jsonify(
        {
            "ok": True,
            "service": "question-paper-maker",
            "api_key_configured": bool(API_KEY),
            "auth_enabled": bool(APP_PASSWORD),
            "rate_limit_per_hour": RATE_LIMIT_PER_HOUR,
            "model": MODEL,
        }
    )


@app.post("/api/extract")
@require_auth
def extract():
    if rate_limited():
        return jsonify({"error": "Rate limit reached. Try again later. The limit is per IP and resets over one hour."}), 429

    if not API_KEY:
        return jsonify(
            {
                "error": "ANTHROPIC_API_KEY is not configured. Create your Anthropic API key, then place it in .env as ANTHROPIC_API_KEY=...",
                "code": "missing_api_key",
            }
        ), 503

    body = request.get_json(silent=True) or {}
    prompt = str(body.get("prompt", "")).strip()
    image_value = body.get("image")
    if not prompt and not image_value:
        return jsonify({"error": "Provide a photo, typed notes, spoken notes, or a combination."}), 400
    if len(prompt) > 50000:
        return jsonify({"error": "The notes are too long. Keep them below 50,000 characters."}), 400

    content = []
    if image_value:
        try:
            media_type, image_b64 = normalize_data_url(str(image_value))
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400
        # Do not silently change formats. The browser normally sends JPEG after compression.
        content.append({"type": "image", "source": {"type": "base64", "media_type": media_type, "data": image_b64}})

    mode = str(body.get("mode", "create")).strip().lower()
    existing = body.get("existing")
    if mode == "update" and isinstance(existing, dict):
        prompt_text = (
            UPDATE_INSTRUCTION
            + "\n\nExisting JSON:\n"
            + json.dumps(existing, ensure_ascii=False)
            + "\n\nTeacher change request / new material:\n"
            + (prompt or "[No text; use the attached image only]")
        )
    else:
        prompt_text = EXTRACTION_INSTRUCTION + "\n\nTeacher notes:\n" + (prompt or "[No text; use the attached image only]")

    content.append({"type": "text", "text": prompt_text})

    payload = {
        "model": MODEL,
        "max_tokens": 8000,
        "messages": [{"role": "user", "content": content}],
    }
    headers = {
        "x-api-key": API_KEY,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }

    try:
        result = requests.post(ANTHROPIC_URL, headers=headers, json=payload, timeout=120)
    except requests.RequestException as exc:
        return jsonify({"error": f"AI connection error: {exc}"}), 502

    if result.status_code >= 400:
        try:
            detail = result.json()
        except ValueError:
            detail = result.text[:1000]
        return jsonify({"error": "AI request failed.", "provider_status": result.status_code, "detail": detail}), 502

    try:
        response_json = result.json()
        blocks = response_json.get("content", [])
        text_parts = [b.get("text", "") for b in blocks if isinstance(b, dict) and b.get("type") == "text"]
        text = "\n".join(part for part in text_parts if part).strip()
        # Server validates the object but keeps the response contract simple: {text}.
        extract_json_object(text)
    except Exception as exc:
        return jsonify({"error": f"AI response could not be parsed as JSON: {exc}"}), 502

    return jsonify({"text": text})


@app.get("/")
@require_auth
def root():
    return send_from_directory(PUBLIC_DIR, "index.html")


@app.get("/<path:requested_path>")
@require_auth
def public_file(requested_path):
    # Only serve files below /public; Flask's send_from_directory then handles the final response.
    safe_public_file(requested_path)
    return send_from_directory(PUBLIC_DIR, requested_path)


@app.errorhandler(413)
def request_too_large(_error):
    return jsonify({"error": "Request too large. Keep the photo and notes smaller."}), 413


@app.errorhandler(404)
def not_found(_error):
    if wants_json():
        return jsonify({"error": "Route not found."}), 404
    return jsonify({"error": "Not found."}), 404


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=PORT, debug=False)
