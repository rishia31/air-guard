# A0 · lead (Claude, Rishi's main account)

**Mission:** keep six agents converging on one demo. Own the foundation and contracts, review and
merge every PR, run integration, and protect the demo path.

## Done in the foundation PR
* Runnable backend: `app.py` factory + `main.py` (`uv run airmate-api`), `deps.AppState`,
  core `schemas.py`, routers `devices` (ingest, events, registration), `users` (profile, puffs,
  symptoms, events, readings, risk, risk history), `stream` (SSE).
* `services/risk.py`: rebuilds a person's week from `events`, scores with the ML engine off the
  loop, stores `risk` events, publishes, and calls listeners (check-ins plug in here).
* Stubs mounted for every feature endpoint (501) with their models, so all paths exist on day one.
* Seams so owners never edit lead files: `checkin.register/on_button` (A1), `outdoor.get_outdoor`
  and `seed.seed_if_empty` (A2), feature routers (A1, A4).
* Minimal demo cast seed, backend tests, `.env.example`, `docs/API.md`, `AGENTS.md`, briefs, README.
* Settings for the jump-based check-in (`CHECKIN_JUMP_POINTS`, `CHECKIN_JUMP_WINDOW_S`).

## Ongoing
1. **Merge queue.** Review for: contract drift (`docs/API.md`), file ownership, safety rules, tests
   green, no secrets. Merge small PRs quickly; A3's scaffold and A1's chat/check-in PRs unblock others,
   so review those first.
2. **Integration runs** after every few merges: reset seed → backend → simulator dust scenario →
   dashboard jumps → call overlay → answer → red flag → Jordan's phone. File issues to owners.
3. **Contract changes**: only through you; update `schemas.py`, `docs/API.md`, and ping A3 for
   `types.ts` in the same PR.
4. ~~**Performance guard**~~ done: a week of 15 s readings took 1.1 s per update and blocked the event
   loop; now an incremental in-memory `HistoryWindow` (0.2 s, off the loop). Throttled updates are
   deferred, not dropped. Community stream carries community devices only (home-location leak fixed).
5. **Deployment for the demo**: one laptop runs `uv run airmate-api` serving `web/out`; phone and
   ESP32 on the same Wi-Fi (or a `cloudflared` tunnel). Rehearse on venue Wi-Fi.
6. **Final README**: screenshots, how to run, architecture, the honesty note, team credits.

## Status
- [x] foundation · [ ] A3 scaffold merged · [ ] A1 check-in merged · [ ] A2 spike fix merged · [ ] end-to-end demo on main · [ ] feature freeze · [ ] submission
