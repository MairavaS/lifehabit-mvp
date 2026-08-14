# LifeHabit MVP

A pilot for your life — LifeHabit helps you form and track small daily habits.

This repository is a Python-based MVP with a simple AI assistant you can run locally to prototype conversational habit-coaching interactions.

Quick start

1. Clone the repo

   git clone https://github.com/MairavaS/lifehabit-mvp.git
   cd lifehabit-mvp

2. (Optional) Create and activate a Python virtual environment:

   python -m venv .venv
   source .venv/bin/activate  # macOS / Linux
   .\.venv\Scripts\activate   # Windows PowerShell

3. Install dependencies:

   pip install -r requirements.txt

4. (Optional) Provide an OpenAI API key to enable smarter responses (recommended):

   export OPENAI_API_KEY="sk-..."   # macOS / Linux
   setx OPENAI_API_KEY "sk-..."     # Windows (restart terminal after setx)

5. Run the simple AI assistant from the repository root:

   python ai/assistant.py "How can I build a habit of reading daily?"

Files added or updated

- README.md — this file (updated)
- ai/assistant.py — minimal CLI assistant using OpenAI if available, otherwise a local fallback
- ai/README.md — instructions for the assistant
- requirements.txt — lists Python dependencies

Notes about the repository description

- To change the repository metadata (the short description shown on GitHub) you must update it on GitHub itself:
  - On the web: go to the repo page, click the gear icon next to the description and edit the text to: "a pilot for your life".
  - Or using GitHub CLI: gh repo edit MairavaS/lifehabit-mvp --description "a pilot for your life"

Next steps you can ask me to do

- Add habit CRUD endpoints and SQLite-backed storage.
- Add a small Flask web UI to create/log habits and talk to the AI coach.
- Add tests and CI.
