# A4 · community-care (Gemini #2)

**Mission:** Airmate isn't just one person's gadget. You build three vertical features, each with its
backend and page: the anonymized community hotspot map, asthma buddies (matching + the buddy's phone
view), and the doctor report.

**Branch:** `a4/community-care` · **Paste to start:** "You are A4 (community-care). Read AGENTS.md
and agents/A4-community-care.md, then start with task 1."

## Read first
* `AGENTS.md`, `docs/API.md` (Community, Buddy, Doctor report, stream, event kinds)
* Your stubs: `backend/airmate_api/routers/{community,buddy,report}.py`, already mounted with
  their request/response models (the contract)
* `backend/airmate_api/{models,deps}.py`, `services/risk.py` (`RiskService.latest`), `services/safety.py`
* `ml/airmate_ml/{aqi,rules}.py` for AQI and exposure scoring you can reuse

## You own
`routers/{community,buddy,report}.py`, new `services/{hotspots,matching,report,community_seed}*.py`,
`backend/tests/test_{community,buddy,report}*.py`, `web/src/app/{community,buddy,report}/**`,
`web/src/components/{community,buddy,report}/**`.

## Order of work
Do the **backend first** (tasks 1–3) while A3 scaffolds the web app. Start pages (4–6) once A3's
scaffold is on `main`. Use `web/src/lib/{api,types,useStream,useUser}.ts` from A3. Don't create a
second API client, and ask A3 before adding npm packages (for the map: `leaflet` + `react-leaflet`
with OpenStreetMap tiles, no key; import it with `next/dynamic` and `ssr: false`).

## Tasks

### P0: backend
1. **Hotspots** `GET /community/hotspots`: aggregate `reading` events that have lat/lon over the
   window into ~500 m cells (round to 0.005°), plus rescue `puff` events (by the user's location) and
   `air_report` events. Score each cell (e.g. PM2.5 AQI via `airmate_ml.aqi.pm25_to_aqi`, dust and
   TVOC boosts, puff density) and write a human `label`. **Privacy:** return a cell only with ≥ 2
   distinct contributors or a `community` device; never return a single home. `POST
   /community/reports` stores `air_report` and publishes `community`.
   Also write `services/community_seed.py::seed_community(db)`: ~12 community devices and a few
   people around Atlanta (Midtown, Home Park, West End, Decatur) with 24 h of readings, and one
   smoky cell. A2's seed will call it.
2. **Buddy** endpoints: `GET /users/{id}/buddy` (me + buddy with `RiskBrief` from
   `state.risk.latest`, and `open_nudges` = `alert` events with `data.type == "buddy_nudge"`
   addressed to me without an `alert_ack`); `POST /buddy/nudges/{alert_id}/ack` stores `alert_ack`
   and publishes `buddy_ack` to the patient. `GET /buddy/matches` with **networkx**: a weighted graph
   over patients (shared triggers, haversine distance, age gap, both have a device), ranked
   candidates with human `reasons`; `POST /buddy/pair` sets both `buddy_id`s (use
   `nx.max_weight_matching` if you add a "pair everyone" helper).
3. **Doctor report** `POST /users/{id}/reports` / `GET /reports/{token}`: over `days`, compute daily
   rows (puffs, symptoms, night symptoms, max/mean score), totals, top factors (share of factor
   points across risk events), exposure notes ("PM10 spikes most evenings 6–8 pm"). The `summary`
   paragraph comes from Grok (`state.grok.text(..., model=settings.grok_report_model)`) with a
   template fallback, and must pass `safety.invented_doses` against the plan. Store it in `reports`
   with `secrets.token_urlsafe(16)`. Include the disclaimer (simulated-data model, not a diagnosis).
   Tests for all three with the `client` fixture from `backend/tests/conftest.py`.

### P0: pages
4. **`/community/`**: Leaflet map of cells colored by score, popups with the label, a "Report
   smoke/dust here" button, live updates from `community` messages; the circle feed below it.
5. **`/buddy/?user=jordan`**: the buddy's phone. Maya's live status (ring + top factor) via the
   stream on both `user:jordan` and `user:maya`. On `buddy_nudge`/`emergency`: a full-screen alert
   with vibration (`navigator.vibrate`), Maya's location link, and the buttons **On my way** /
   **Calling** / **She's OK** → ack. This screen appears on stage, so make it big and obvious.
6. **`/report/?token=…`**: a clean, printable one-pager (print CSS): header, summary paragraph,
   totals, a daily puffs/risk chart, top factors, exposure notes, the action plan, the disclaimer.

### P1
7. Circle posts endpoints + feed; "suggested buddies" list with reasons on `/buddy/`.
8. A QR code on the report page so the doctor can open it on their phone.

## Done when
Tests are green; the map shows seeded Atlanta cells with no single-home cell; Jordan's phone lights
up on a nudge and the ack reaches Maya; a 30-day report renders and prints nicely offline (no key).

## Status
- [ ] 1 hotspots · [ ] 2 buddy · [ ] 3 report · [ ] 4 /community · [ ] 5 /buddy · [ ] 6 /report · [ ] 7 circles
