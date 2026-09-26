# A2 · ml-demo (Claude #3)

**Mission:** make the model react to the demo moment (a 24-minute dust spike) honestly, give the app
a believable week of history, and own the story: demo script, Devpost write-up, verified facts.

**Branch:** `a2/ml-demo` · **Paste to start:** "You are A2 (ml-demo). Read AGENTS.md and
agents/A2-ml-demo.md, then start with task 1."

## Read first
* `AGENTS.md`, `ml/MODEL_CARD.md`, `ml/airmate_ml/{schema,simulate,features,model,train,engine}.py`
* `ml/tests/test_engine.py::test_trained_model_reacts_to_a_dust_spike` (the failing test)
* `backend/airmate_api/services/{seed,outdoor,risk}.py`

## You own
`ml/**` (including the committed `airmate_risk.pt`), `backend/airmate_api/services/{outdoor,seed}.py`,
`backend/tests/test_{seed,outdoor}*.py`, `docs/{DEMO,DEVPOST,FACTS}.md`.

## Contract you must keep
`RiskEngine.assess()` output keys (`score band probabilities factors latest normal ratios
sensors_available outdoor puffs_24h symptoms_24h normal_day_score rule_score model`) are the backend's
`RiskOut`. Don't rename them. If you change `SEQ_FEATURES`/`CTX_FEATURES` you must retrain and
commit the new artifact in the same PR (the engine refuses a mismatched checkpoint).

## Tasks

### P0: required for the demo
1. **Fix the dust-spike response.** Today a 24-min PM10 spike to 180 µg/m³ moves the score ~3 → 7,
   while the simulator's own hazard implies ~25. Find out *why* before tuning: compare the simulator's
   true 4-h risk for that exact history against the model. Likely causes to check: 24 min of
   exposure barely moves the 3-h-window GRU after 24 h baselines; spikes this short and large are rare in
   training; Platt calibration flattens the tail. Candidate fixes (measure each): augment training
   with injected short spikes whose labels come from the simulator's hazard; add short-window
   features (e.g. max `rel_coarse` over 30 min); rebalance sampling toward exposure episodes.
   **Don't** change the test threshold or hard-code a boost at serving time.
   **Clue from the lead's smoke test:** through the backend with only 3 h of calm history, an
   8-minute spike to 180 went 2 → 19 (PM10 "11.6× your normal", baseline 15). With the test's full
   week of history, a 24-minute spike only goes 3 → 7. So the baseline/24 h-exposure context seems
   to damp the response once a week of history exists; start there. The seeded demo will have a full
   week, so the demo hits the damped case.
   Acceptance: `uv run pytest ml/tests` green; test-set AUROC/ECE not worse than the table in
   `MODEL_CARD.md` (report the new table); explanation top-1 accuracy reported again. Commit the
   retrained artifact, regenerated `MODEL_CARD.md`, and `reports/*.png`.
2. **Demo seed** (`services/seed.py`, keep the ids): a week of 3-minute readings for maya (and
   jordan) ending *now*, generated with `airmate_ml.simulate` so baselines ("7× your normal") are
   real; a few puffs and symptoms (one evening flare after cleaning); risk history (score every
   15 min with `engine.assess(history, explain=False)`, or cheaper, so startup stays under ~20 s);
   circle posts. Call A4's `services/community_seed.seed_community(db)` if it exists (use
   try/except ImportError until it lands). Add `python -m airmate_api.services.seed --reset` to wipe
   and reseed before each demo run.
3. **Outdoor data** (`services/outdoor.py`): Open-Meteo air quality (US AQI, pollen) + forecast
   (temperature, humidity), no key; map pollen to the model's 0–5 scale; cache ~15 min per ~1 km
   cell; 3 s timeout; return all-`None` on any error or when `AIRMATE_OFFLINE`. Test with a mocked
   httpx transport.

### P1
4. **`docs/DEMO.md`**: the 3-minute demo script, minute by minute, with the exact commands
   (reset seed, start backend, start the simulator or real device), what each screen shows, what
   the presenter says, and a fallback for every step (no Wi-Fi, no Grok key, device dead → simulator).
   Coordinate the key beat with A1/A3/A5: dusty cloth → score jumps → Airmate calls → "I'm a bit
   wheezy" → plan steps → "my inhaler isn't helping" → 911 script + Jordan's phone lights up.
5. **`docs/FACTS.md`**: every number we'll say out loud, with source URL and the date checked.
   Verify the CDC figures on the *live* page (the previous agent only saw an archived copy):
   27.8 M people in the US with asthma (~1 in 12), 4.8 M children, 3,624 deaths in 2023. Add our
   model numbers with the "simulated data" caveat.
6. **`docs/DEVPOST.md`**: inspiration, what it does, how we built it (PyTorch GRU survival model +
   Captum, Grok voice agent, ESP32), challenges, accomplishments, what's next, built with. State
   plainly that training data is simulated and why.

### P2
7. Night-time cough detector (the `cough` extra, AST from Hugging Face) as a function A5/A1 can
   call with a short WAV. Only if P0/P1 are done.

## Done when
The failing test passes on an honestly retrained model, `uv run airmate-api` starts with a week of
believable history, and a stranger could run the demo from `docs/DEMO.md`.

## Status
- [ ] 1 spike fix · [ ] 2 seed · [ ] 3 outdoor · [ ] 4 DEMO.md · [ ] 5 FACTS.md · [ ] 6 DEVPOST.md
