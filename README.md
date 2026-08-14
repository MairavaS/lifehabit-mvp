# Momentum — Habit Tracker (MVP)

A minimal habit-tracking single-page app with optional AI-powered coach features.

This repository contains a static frontend (HTML/CSS/JS) that stores data in your browser's localStorage and an optional small Python/Flask backend which proxies AI requests to Anthropic/Claude and can optionally persist a server-side copy of your habits.

Contents
- index.html — single-page frontend UI
- style.css  — theme and layout styles
- app.js     — frontend logic (localStorage, UI rendering, AI fallbacks)
- server.py  — optional Flask backend (AI proxy + simple persistence)
- requirements.txt — Python dependencies (Flask, requests)
- package.json — minimal npm scaffolding for convenience

Quick start (recommended)

1. Clone the repo

   git clone https://github.com/MairavaS/lifehabit-mvp.git
   cd lifehabit-mvp

2. Python backend (serves static files and proxies AI requests)

   python -m venv venv
   source venv/bin/activate   # Windows: venv\Scripts\activate
   pip install -r requirements.txt

3. (Optional) Add your Anthropic API key for AI features

   Copy the example (create a file named `.env` next to `server.py`) and add:

   ANTHROPIC_API_KEY=sk-ant-...   # your key here
   # Optional: override model names
   # FAST_MODEL=claude-haiku-4-5-20251001
   # SMART_MODEL=claude-sonnet-5

   With the key set the AI panels (emoji picker, habit suggestions, coach, report reader) will call the Claude API via the local server. If you do not add a key, the app falls back to built-in heuristics and starter suggestions — it still works fine without an API key.

4. Run the app

   python server.py
   # then open http://127.0.0.1:5000

Notes on persistence and syncing
- By default the frontend stores habits in localStorage under the key `momentum-habits-v2`.
- This branch adds a simple server-side persistence API (GET/POST /api/habits) that stores a JSON file on the server (data/habits.json).
- Frontend behavior: when the server is present and responsive the frontend will try to load habits from the server on startup. If the server returns a non-empty list, the frontend will replace the local list with the server copy. If the server returns an empty list and localStorage has data, the frontend will keep the local copy (to avoid accidental data loss).
- Any changes in the frontend (add / edit / delete / toggle / timer commit) will POST the full habit list to the server so it stays in sync.

Security & limitations
- This project is intentionally minimal: there is no authentication for the persistence API, it is file-backed and not production hardened. Only use this on a trusted local network or adjust the server to add auth.
- The AI key is never stored in the browser; put it in the server `.env` file.

Next steps you can ask me to do
- Add per-habit server CRUD endpoints (PATCH/DELETE) instead of replacing the whole list on every change.
- Add basic HTTP auth or a token to protect the persistence endpoints.
- Migrate the frontend to a small build step (ES modules + bundler) and add tests.

