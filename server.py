"""
Habit Tracker — local backend.

Holds your Claude API key server-side (never exposed to the browser) and proxies
a handful of small, purpose-built AI endpoints to the Claude Messages API.

This version adds GitHub OAuth sign-in. Create a GitHub OAuth App and set
GITHUB_CLIENT_ID and GITHUB_CLIENT_SECRET in a .env file in the repo root.

Run:
    pip install -r requirements.txt
    copy .env.example to .env and put your keys in it
    python server.py
Then open http://127.0.0.1:5000
"""

import base64
import functools
import json
import os
import re
import secrets
import urllib.parse

import requests
from flask import Flask, jsonify, request, send_from_directory, session, redirect

# --------------------------------------------------------------------------
# Config
# --------------------------------------------------------------------------

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
# Serve files from the repository root so the existing index.html/app.js/style.css
# work without moving them into a `static/` folder.
STATIC_DIR = BASE_DIR


def load_dotenv(path=os.path.join(BASE_DIR, ".env")):
    """Tiny .env loader so we don't need an extra dependency."""
    if not os.path.exists(path):
        return
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            value = value.strip().strip('"').strip("'")
            os.environ.setdefault(key.strip(), value)


load_dotenv()

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "").strip()
API_URL = "https://api.anthropic.com/v1/messages"
API_VERSION = "2023-06-01"

# Small/fast model for trivial calls (emoji picking), stronger model for advice.
FAST_MODEL = os.environ.get("FAST_MODEL", "claude-haiku-4-5-20251001")
SMART_MODEL = os.environ.get("SMART_MODEL", "claude-sonnet-5")

# GitHub OAuth config (create a GitHub OAuth App and add these to .env)
GITHUB_CLIENT_ID = os.environ.get("GITHUB_CLIENT_ID", "").strip()
GITHUB_CLIENT_SECRET = os.environ.get("GITHUB_CLIENT_SECRET", "").strip()
GITHUB_AUTHORIZE = "https://github.com/login/oauth/authorize"
GITHUB_TOKEN_URL = "https://github.com/login/oauth/access_token"
GITHUB_USER_API = "https://api.github.com/user"

# Flask secret key for sessions. Provide SECRET_KEY in .env for stable sessions.
SECRET_KEY = os.environ.get("SECRET_KEY") or os.urandom(24)

app = Flask(__name__, static_folder=None)
app.secret_key = SECRET_KEY


# --------------------------------------------------------------------------
# Helpers: auth
# --------------------------------------------------------------------------

def login_required(fn):
    """Decorator that returns 401 JSON when not authenticated."""
    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        if not session.get("user"):
            return jsonify({"error": "Authentication required"}), 401
        return fn(*args, **kwargs)
    return wrapper


@app.route("/login")
def login():
    """Start the GitHub OAuth flow by redirecting to GitHub's authorize page."""
    if not GITHUB_CLIENT_ID or not GITHUB_CLIENT_SECRET:
        return (
            "GitHub OAuth not configured. Add GITHUB_CLIENT_ID and GITHUB_CLIENT_SECRET "
            "to a .env file. See .env.example for details.",
            500,
        )
    state = secrets.token_urlsafe(16)
    session["oauth_state"] = state
    params = {
        "client_id": GITHUB_CLIENT_ID,
        "scope": "read:user",
        "state": state,
        # Use redirect back to the callback route
        "redirect_uri": request.url_root.rstrip("/") + "/oauth/callback",
    }
    return redirect(GITHUB_AUTHORIZE + "?" + urllib.parse.urlencode(params))


@app.route("/oauth/callback")
def oauth_callback():
    """Exchange the authorization code for an access token, fetch user info, and
    store it in the session.
    """
    error = request.args.get("error")
    if error:
        return "Authentication failed: %s" % error, 400
    state = request.args.get("state")
    code = request.args.get("code")
    if not code or not state or state != session.get("oauth_state"):
        return "Invalid OAuth state/response", 400

    # Exchange code for token
    try:
        resp = requests.post(
            GITHUB_TOKEN_URL,
            data={
                "client_id": GITHUB_CLIENT_ID,
                "client_secret": GITHUB_CLIENT_SECRET,
                "code": code,
                "redirect_uri": request.url_root.rstrip("/") + "/oauth/callback",
                "state": state,
            },
            headers={"Accept": "application/json"},
            timeout=20,
        )
        resp.raise_for_status()
        token_data = resp.json()
        access_token = token_data.get("access_token")
        if not access_token:
            return "Failed to obtain access token", 400

        # Fetch user info
        u = requests.get(GITHUB_USER_API, headers={"Authorization": f"token {access_token}"}, timeout=20)
        u.raise_for_status()
        user = u.json()
        # Minimal user object stored in session
        session["user"] = {
            "login": user.get("login"),
            "id": user.get("id"),
            "name": user.get("name"),
            "avatar_url": user.get("avatar_url"),
        }
        # Clear the oauth_state
        session.pop("oauth_state", None)
        return redirect("/")

    except requests.RequestException as e:
        return "OAuth token exchange failed: %s" % e, 500


@app.route("/logout")
def logout():
    session.clear()
    return redirect("/")


@app.route("/api/user")
def api_user():
    return jsonify({"user": session.get("user")})


# --------------------------------------------------------------------------
# Config: AI helpers (unchanged)
# --------------------------------------------------------------------------

class AIError(Exception):
    pass


def call_claude(messages, system=None, model=None, max_tokens=1024):
    """POST to the Messages API and return the concatenated text response."""
    if not ANTHROPIC_API_KEY:
        raise AIError(
            "No API key configured. Put ANTHROPIC_API_KEY=sk-ant-... in a .env "
            "file next to server.py, then restart the server."
        )

    payload = {
        "model": model or SMART_MODEL,
        "max_tokens": max_tokens,
        "messages": messages,
    }
    if system:
        payload["system"] = system

    try:
        resp = requests.post(
            API_URL,
            headers={
                "x-api-key": ANTHROPIC_API_KEY,
                "anthropic-version": API_VERSION,
                "content-type": "application/json",
            },
            json=payload,
            timeout=90,
        )
    except requests.RequestException as e:
        raise AIError("Could not reach the Claude API: %s" % e)

    if resp.status_code != 200:
        detail = resp.text[:400]
        try:
            detail = resp.json().get("error", {}).get("message", detail)
        except Exception:
            pass
        raise AIError("Claude API returned %s: %s" % (resp.status_code, detail))

    data = resp.json()
    parts = [b.get("text", "") for b in data.get("content", []) if b.get("type") == "text"]
    return "".join(parts).strip()


def extract_json(text):
    """Pull the first JSON object/array out of a model response."""
    text = text.strip()
    # Strip ```json fences if present
    fence = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
    if fence:
        text = fence.group(1).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    # Fall back to the outermost bracket pair
    for opener, closer in (("{", "}"), ("[", "]")):
        start = text.find(opener)
        end = text.rfind(closer)
        if start != -1 and end > start:
            try:
                return json.loads(text[start:end + 1])
            except json.JSONDecodeError:
                continue
    raise AIError("Could not parse a JSON response from the model.")


def ai_route(fn):
    """Decorator: turn AIError into a clean 503 the frontend can display."""
    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except AIError as e:
            return jsonify({"error": str(e)}), 503
        except Exception as e:  # noqa: BLE001 - surface anything else as 500
            return jsonify({"error": "Server error: %s" % e}), 500
    return wrapper


# --------------------------------------------------------------------------
# Static files
# --------------------------------------------------------------------------

@app.route("/")
def index():
    return send_from_directory(STATIC_DIR, "index.html")


@app.route("/<path:filename>")
def static_files(filename):
    return send_from_directory(STATIC_DIR, filename)


@app.route("/api/health")
def health():
    return jsonify({
        "ok": True,
        "ai_enabled": bool(ANTHROPIC_API_KEY),
        "fast_model": FAST_MODEL,
        "smart_model": SMART_MODEL,
        "authenticated": bool(session.get("user")),
    })


# --------------------------------------------------------------------------
# 1. Word -> emoji
# --------------------------------------------------------------------------

EMOJI_SYSTEM = (
    "You map a habit name to the single most fitting emoji. "
    "Reply with ONLY the emoji character. No words, no quotes, no explanation. "
    "If nothing fits well, reply with a check mark emoji."
)


@app.route("/api/emoji", methods=["POST"])
@login_required
@ai_route
def api_emoji():
    name = (request.json or {}).get("name", "").strip()
    if not name:
        return jsonify({"error": "Habit name is required."}), 400

    text = call_claude(
        messages=[{"role": "user", "content": "Habit: %s" % name}],
        system=EMOJI_SYSTEM,
        model=FAST_MODEL,
        max_tokens=16,
    )
    # Keep only the first non-space character cluster
    emoji = text.strip().split()[0] if text.strip() else ""
    return jsonify({"emoji": emoji})


# --------------------------------------------------------------------------
# 2. Recommend new habits
# --------------------------------------------------------------------------

RECOMMEND_SYSTEM = """You are a practical habit-formation coach. You suggest small, \
specific, achievable habits — never vague goals.

Rules:
- Suggest habits that complement what the user already tracks; never duplicate them.
- Prefer small starts (a 10-minute version beats an hour-long one).
- "build" habits are things to do more of. "break" habits are things to do less of \
(for those, weeklyTarget is the MAXIMUM slip-ups allowed per week).
- durationMin is only for habits genuinely measured in time; use null otherwise.
- "why" must be one short sentence, concrete and motivating, max 90 characters.

Respond with ONLY a JSON array, no prose, in exactly this shape:
[{"name": "...", "emoji": "X", "weeklyTarget": 3, "durationMin": 20, "type": "build", "why": "..."}]
Return exactly 4 suggestions."""


@app.route("/api/recommend", methods=["POST"])
@login_required
@ai_route
def api_recommend():
    body = request.json or {}
    existing = body.get("existing", [])
    goal = (body.get("goal") or "").strip()

    existing_text = ", ".join(existing) if existing else "none yet"
    prompt = "Habits I already track: %s.\n" % existing_text
    if goal:
        prompt += "What I'm trying to achieve: %s\n" % goal
    prompt += "Suggest 4 new habits for me."

    text = call_claude(
        messages=[{"role": "user", "content": prompt}],
        system=RECOMMEND_SYSTEM,
        model=SMART_MODEL,
        max_tokens=1200,
    )
    data = extract_json(text)
    if isinstance(data, dict):
        data = data.get("suggestions", [])
    return jsonify({"suggestions": data})


# --------------------------------------------------------------------------
# 3. Habit coach — asks questions and gives advice
# --------------------------------------------------------------------------

COACH_SYSTEM = """You are a habit coach inside a habit-tracking app. You are given \
the user's real data for one habit and you help them stick with it.

How to behave:
- Be brief. 2-4 short sentences, or a few tight bullets. Never write an essay.
- Look at the actual numbers you are given and reference them specifically.
- When you don't have enough context to give good advice, ask ONE specific \
question instead of guessing (e.g. "What time of day do you usually try this?").
- Give one concrete, small next action rather than general encouragement.
- If the user is doing well, say so briefly and suggest how to make it stick.
- Never shame the user for missed days.
- You are not a doctor. For medical or mental-health concerns, say so plainly and \
suggest they talk to a professional."""


@app.route("/api/coach", methods=["POST"])
@login_required
@ai_route
def api_coach():
    body = request.json or {}
    habit = body.get("habit") or {}
    history = body.get("history") or []
    question = (body.get("question") or "").strip()

    context = (
        "Habit: %s %s\n"
        "Type: %s\n"
        "Weekly target: %s times per week\n"
        "Duration target: %s\n"
        "Done this week: %s\n"
        "Current streak: %s days\n"
        "Last 14 days (most recent last): %s\n"
    ) % (
        habit.get("emoji", ""),
        habit.get("name", "unknown"),
        habit.get("type", "build"),
        habit.get("target", "?"),
        ("%s min" % habit["durationMin"]) if habit.get("durationMin") else "none",
        habit.get("weekCount", "?"),
        habit.get("streak", "?"),
        habit.get("recent", "no data"),
    )

    messages = []
    for turn in history[-8:]:
        role = "assistant" if turn.get("role") == "assistant" else "user"
        messages.append({"role": role, "content": str(turn.get("content", ""))})

    opener = question or "Look at my data for this habit and tell me how I'm doing."
    messages.append({"role": "user", "content": context + "\n" + opener})

    reply = call_claude(
        messages=messages,
        system=COACH_SYSTEM,
        model=SMART_MODEL,
        max_tokens=700,
    )
    return jsonify({"reply": reply})


# --------------------------------------------------------------------------
# 4. Health / doctor's report -> plain language + habit suggestions
# --------------------------------------------------------------------------

REPORT_SYSTEM = """You help someone understand a health document and turn it into \
habit ideas. You are an AI, not a clinician.

Hard rules:
- Do NOT diagnose. Do NOT interpret whether a result is dangerous. Do NOT suggest \
starting, stopping, or changing any medication or dosage.
- Explain terminology and what measurements generally represent, in plain language.
- Point out which items the reader may want to ask their doctor about — framed as \
questions to bring to an appointment, not as conclusions.
- Suggest only everyday lifestyle habits (movement, sleep, hydration, diet \
patterns, stress, follow-up appointments). Keep them gentle and general.
- If the document appears urgent or alarming, say clearly that they should contact \
their doctor rather than rely on this summary.

Respond with ONLY JSON in exactly this shape:
{
  "summary": "2-4 plain-language sentences about what this document appears to be and what it covers.",
  "terms": [{"term": "...", "meaning": "one plain sentence"}],
  "askYourDoctor": ["question 1", "question 2"],
  "habits": [{"name": "...", "emoji": "X", "weeklyTarget": 5, "durationMin": null, "type": "build", "why": "..."}]
}
Include at most 5 terms, 4 questions, and 4 habits."""

DISCLAIMER = (
    "This is an AI-generated summary, not medical advice, and it can be wrong or "
    "incomplete. It cannot diagnose anything. Always confirm with your doctor "
    "before acting on it."
)


@app.route("/api/analyze-report", methods=["POST"])
@login_required
@ai_route
def api_analyze_report():
    content_blocks = []

    uploaded = request.files.get("file")
    pasted = (request.form.get("text") or "").strip()

    if uploaded and uploaded.filename:
        raw = uploaded.read()
        if len(raw) > 12 * 1024 * 1024:
            return jsonify({"error": "File is too large (12 MB max)."}), 400

        name = uploaded.filename.lower()
        b64 = base64.standard_b64encode(raw).decode("ascii")

        if name.endswith(".pdf"):
            content_blocks.append({
                "type": "document",
                "source": {"type": "base64", "media_type": "application/pdf", "data": b64},
            })
        elif name.endswith((".png", ".jpg", ".jpeg", ".gif", ".webp")):
            media = "image/png"
            if name.endswith((".jpg", ".jpeg")):
                media = "image/jpeg"
            elif name.endswith(".gif"):
                media = "image/gif"
            elif name.endswith(".webp"):
                media = "image/webp"
            content_blocks.append({
                "type": "image",
                "source": {"type": "base64", "media_type": media, "data": b64},
            })
        elif name.endswith((".txt", ".md", ".csv")):
            content_blocks.append({
                "type": "text",
                "text": raw.decode("utf-8", errors="replace")[:100000],
            })
        else:
            return jsonify({
                "error": "Unsupported file type. Use PDF, PNG, JPG, TXT, MD or CSV."
            }), 400

    if pasted:
        content_blocks.append({"type": "text", "text": pasted[:100000]})

    if not content_blocks:
        return jsonify({"error": "Attach a file or paste some text first."}), 400

    content_blocks.append({
        "type": "text",
        "text": "Summarise this health document for me and suggest habits, following your JSON format.",
    })

    text = call_claude(
        messages=[{"role": "user", "content": content_blocks}],
        system=REPORT_SYSTEM,
        model=SMART_MODEL,
        max_tokens=2000,
    )
    data = extract_json(text)
    data["disclaimer"] = DISCLAIMER
    return jsonify(data)


# --------------------------------------------------------------------------

if __name__ == "__main__":
    print("\n  Habit Tracker running at http://127.0.0.1:5000")
    if ANTHROPIC_API_KEY:
        print("  AI features: ENABLED (%s / %s)\n" % (FAST_MODEL, SMART_MODEL))
    else:
        print("  AI features: DISABLED - no ANTHROPIC_API_KEY found in .env")
        print("  The tracker still works fully; only the AI panels are off.\n")
    if GITHUB_CLIENT_ID and GITHUB_CLIENT_SECRET:
        print("  GitHub OAuth: ENABLED\n")
    else:
        print("  GitHub OAuth: DISABLED - set GITHUB_CLIENT_ID and GITHUB_CLIENT_SECRET in .env to enable\n")
    app.run(host="127.0.0.1", port=5000, debug=False)
