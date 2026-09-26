# Claude instructions

This repo is built by six agents in parallel. Before doing anything:

1. Read `AGENTS.md` (roles, file ownership, git workflow, non-negotiable rules).
2. Read your brief in `agents/` (A0 lead, A1 agent-voice, A2 ml-demo). If you don't know which
   agent you are, ask the user.
3. Code against `docs/API.md`.

Python: `export PATH="$HOME/.local/bin:$PATH"; uv sync; uv run pytest; uv run ruff check .`
Run the backend: `uv run airmate-api` → http://localhost:8000/docs
