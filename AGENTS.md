# AGENTS.md: how six agents build Airmate without stepping on each other

Read this whole file, then your brief in `agents/`. The plan and the architecture are in `README.md`.
The API contract is `docs/API.md`.

## Who is who

| Id | Agent (account) | Workstream | Brief |
|---|---|---|---|
| A0 | Claude (Rishi's main account) | **Lead**: foundation, contracts, reviews, merges, integration | [agents/A0-lead.md](agents/A0-lead.md) |
| A1 | Claude #2 | **agent-voice**: Grok chat + voice, check-in calls, safety, emergency, notifications | [agents/A1-agent-voice.md](agents/A1-agent-voice.md) |
| A2 | Claude #3 | **ml-demo**: fix the dust-spike model, outdoor data, demo seed data, demo script, Devpost | [agents/A2-ml-demo.md](agents/A2-ml-demo.md) |
| A3 | Gemini #1 | **web-core**: Next.js scaffold, dashboard, talk (chat/voice), check-in call UI, settings | [agents/A3-web-core.md](agents/A3-web-core.md) |
| A4 | Gemini #2 | **community-care**: hotspot map, buddy matching + buddy phone, doctor report (backend + pages) | [agents/A4-community-care.md](agents/A4-community-care.md) |
| A5 | Codex | **device**: ESP32 firmware, device simulator, hardware doc | [agents/A5-device.md](agents/A5-device.md) |

## File ownership

You may create and edit files you own. For anything else: open an issue or leave a note in your PR,
tag the owner, and keep going with a local workaround. Never "quickly fix" someone else's file.

| Owner | Paths |
|---|---|
| A0 | `README.md` `AGENTS.md` `CLAUDE.md` `GEMINI.md` `agents/` `docs/API.md` `.env.example` `pyproject.toml` `backend/pyproject.toml` `backend/airmate_api/{app,main,deps,schemas,config,db,models,bus}.py` `backend/airmate_api/routers/{__init__,devices,users,stream}.py` `backend/airmate_api/services/risk.py` `backend/tests/{conftest,test_foundation}.py` |
| A1 | `backend/airmate_api/routers/agent.py` `backend/airmate_api/services/{checkin,grok,safety}.py` new `backend/airmate_api/services/{agent,voice,notify,tools}*.py` `backend/tests/test_{agent,safety,checkin,voice}*.py` |
| A2 | `ml/**` `backend/airmate_api/services/{outdoor,seed}.py` `backend/tests/test_{seed,outdoor}*.py` `docs/{DEMO,DEVPOST,FACTS}.md` |
| A3 | `web/**` **except** the A4 folders below |
| A4 | `backend/airmate_api/routers/{community,buddy,report}.py` new `backend/airmate_api/services/{hotspots,matching,report,community_seed}*.py` `backend/tests/test_{community,buddy,report}*.py` `web/src/app/{community,buddy,report}/**` `web/src/components/{community,buddy,report}/**` |
| A5 | `firmware/**` `scripts/device_sim.py` `docs/HARDWARE.md` |

Shared files with a single writer: `uv.lock` (whoever adds a Python dependency regenerates it with
`uv lock`; on a merge conflict take main's copy and re-run `uv lock`), `web/package-lock.json` (A3;
A4 asks A3 before adding npm packages).

## Git workflow

* Shared remote: **GitHub `rishia31/air-guard`**. Everyone branches from `main`:
  `a1/agent-voice`, `a2/ml-demo`, `a3/web-core`, `a4/community-care`, `a5/device`.
* Small PRs, merged often (aim for one every 1–2 hours). Rebase on `main` before opening one.
  The lead (A0) reviews and merges; nobody pushes to `main` directly except A0.
* Commit messages: imperative, specific ("Add jump-based check-in trigger"), no "WIP" on main.
* Never commit secrets: `.env`, `firmware/include/secrets.h` are gitignored. Use `.env.example`.
* The model artifact `ml/airmate_ml/artifacts/airmate_risk.pt` is committed; only A2 changes it.

## Before every PR

```bash
export PATH="$HOME/.local/bin:$PATH"
uv sync
uv run ruff check .            # Python style (config in pyproject.toml)
uv run pytest                  # ml/tests + backend/tests; must stay green
cd web && npm run build        # A3/A4: the static export must build
cd firmware && pio run         # A5: the firmware must compile
```
Say in the PR what you ran and what you could not run.

## Rules that are not negotiable

1. **Contract first.** Endpoints and message shapes are fixed in `docs/API.md`. Adding optional
   fields is fine. Renaming/removing needs the lead and a same-PR update of the model, `docs/API.md`
   and `web/src/lib/types.ts`.
2. **Safety.** Airmate is support, not a medical device. Red flags always produce the fixed
   `emergency_script` (911), never generated text. Airmate only states doses written in the user's
   action plan (`services/safety.invented_doses` must be empty). No diagnoses.
3. **Honesty.** The model is trained on simulated data only. Every place a score or accuracy number
   is shown or pitched says so. Don't invent statistics; `docs/FACTS.md` lists the verified ones.
4. **Works offline.** No `XAI_API_KEY` → template replies; no internet → outdoor data "unknown";
   no model file → rule-based score. The demo must never hard-fail on a missing key or Wi-Fi.
5. **Stable demo ids**: `maya`, `jordan`, `priya`, `airmate-01`, `atl-asthma`.
6. **Stay in your lane.** If you're blocked on someone, stub it locally, note it in your PR, keep going.

## Status board

Each agent keeps its own section of its brief's **Status** block up to date in its PRs (done /
in progress / blocked on). The lead summarizes in `README.md` → Progress.
