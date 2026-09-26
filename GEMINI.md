# Gemini instructions

This repo is built by six agents in parallel. Before doing anything:

1. Read `AGENTS.md` (roles, file ownership, git workflow, non-negotiable rules).
2. Read your brief in `agents/` (A3 web-core or A4 community-care). If you don't know which agent
   you are, ask the user.
3. Code against `docs/API.md`. Keep `web/src/lib/types.ts` in sync with it.

Backend for local development: `export PATH="$HOME/.local/bin:$PATH"; uv sync; uv run airmate-api`
(http://localhost:8000/docs). Web: `cd web && npm install && npm run dev` with
`NEXT_PUBLIC_API_URL=http://localhost:8000` in `web/.env.local`.
