# A1 · agent-voice (Claude #2)

**Mission:** Airmate talks. When risk jumps it "calls" the person, explains why in one sentence,
reads their own action plan, logs what they say, and if they describe a red flag it switches to the
fixed 911 script and alerts their buddy. You own the most safety-critical code in the repo.

**Branch:** `a1/agent-voice` · **Paste to start:** "You are A1 (agent-voice). Read AGENTS.md and
agents/A1-agent-voice.md, then start with task 1."

## Read first
* `AGENTS.md`, `docs/API.md` (sections: stream, Grok agent, event kinds)
* `backend/airmate_api/services/grok.py` (Responses API + TTS client, already written)
* `backend/airmate_api/services/safety.py` (red flags, emergency script, dose guard, already written)
* `backend/airmate_api/services/checkin.py` and `routers/agent.py`: your stubs, already mounted
* `backend/airmate_api/services/risk.py`: how risk listeners are called; `deps.AppState`

## You own
`routers/agent.py`, `services/{checkin,grok,safety}.py`, new `services/{agent,voice,notify,tools}*.py`,
`backend/tests/test_{agent,safety,checkin,voice}*.py`.

## Who depends on you
* A3 builds the talk page and the incoming-call overlay on your `checkin` / `chat` / `emergency`
  messages and `/agent/*` endpoints. **Merge task 2 early, even with template replies,** so A3 can
  wire the UI against real responses.
* A4's buddy phone shows your `buddy_nudge` alerts and acknowledges them (`alert_ack`).

## Tasks

### P0: required for the demo
1. **Safety tests first.** `backend/tests/test_safety.py`: red-flag detection (positives *and*
   negatives like "my lips are not blue", "the inhaler helped"), `emergency_script`, and
   `invented_doses` against the seeded plan (`services/seed.DEMO_ACTION_PLAN`). Fix anything that fails.
2. **Chat** `POST /agent/chat`:
   * Red flag in the user's message → no model call. Reply = `emergency_script(...)`, run the
     emergency flow (task 5), `emergency: true`.
   * Otherwise Grok Responses via `GrokClient.run_tools` with a system prompt: warm, 1–3 short
     sentences, never diagnose, only quote doses from the plan, suggest calling the doctor/911 per
     the plan. Tools (`services/tools.py`): `get_current_risk`, `get_recent_readings`, `log_puff`,
     `log_symptom`, `get_action_plan`, `notify_buddy`. Tools call the lead's services/DB, not HTTP.
   * Every reply passes `invented_doses(reply, plan_text(plan))`; if not empty, replace it with a
     template that quotes `zone_steps(plan, "yellow")`.
   * No `XAI_API_KEY` → deterministic template replies (risk + top factor + plan step). The demo
     must work without a key.
   * `conversation_id` = the last response id (`previous_response_id` continues the thread).
   * Store user/assistant turns as `chat` events and publish `chat`.
3. **Check-ins** (`services/checkin.py`, `on_risk` listener):
   * Trigger if `score >= settings.high_risk_score` **or** score − (min score in the last
     `checkin_jump_window_s`) ≥ `checkin_jump_points`. This is what makes the demo moment happen
     even while A2 retunes the model: scores sit in single digits, so a 5 → 20 jump must call.
   * Cooldown `checkin_cooldown_s` per person; skip if a check-in is already open.
   * Store a `checkin` event, publish `checkin` with a spoken opener naming the top factor
     ("Hi Maya, dust in your room just jumped to seven times your normal. How's your breathing?"),
     plus `audio_url` when TTS is on (serve cached audio from e.g. `GET /agent/audio/{id}`).
   * `POST /checkins/{id}/answer`: `ok` closes it; `not_ok` → yellow-zone steps from the plan +
     offer to notify the buddy; free text → safety check, then chat.
   * Unanswered after `buddy_nudge_delay_s` → `alert` event (`data.type = "buddy_nudge"`), publish
     `buddy_nudge` to `user:<buddy_id>`, `checkin_update` status `escalated`.
   * `on_button`: short press answers the open check-in with `ok`; long press → emergency.
4. **Speech, reliable path first:** `POST /agent/tts` (Grok TTS, cached by text hash) and
   `chat` with `speak: true` returning `audio_url`. A3 pairs this with the browser's Web Speech API
   for push-to-talk, so voice works even if the realtime API misbehaves.
5. **Emergency** `POST /users/{id}/emergency` and the shared flow: `emergency` event, publish
   `emergency` to the patient, buddy and caregivers with location, ntfy push (`services/notify.py`,
   priority high) when `NTFY_TOPIC_PREFIX` is set.

### P1
6. **Realtime voice** `WS /agent/voice`: relay browser audio ↔ Grok realtime (`XAI_REALTIME_URL`,
   `GROK_VOICE_MODEL`). Same tools, same instructions. Run red-flag detection on the *user
   transcript* server-side and cut in with the emergency script. Finalize the protocol section in
   `docs/API.md` (PR it with the lead as reviewer).
7. **Verify xAI model ids and endpoints** in `config.py` defaults (`grok-4.3`, `grok-4.7`,
   `grok-voice-latest`, `/v1/tts`, realtime URL) against docs.x.ai and fix them. They were written
   without checking.

### P2
8. Caregiver alerts (`priya`) on high-band risk; a daily "how was today" summary via Grok.

## Gotchas
* The emergency script is spoken verbatim; never paraphrase it through the model.
* Don't block the event loop: Grok calls are async (httpx); DB access is short and synchronous.
* Keep all Grok prompts in one module so the lead can review the wording.
* Tests must not hit the network: mock `GrokClient` (monkeypatch `respond`/`tts`).

## Done when
`uv run pytest` is green with your tests. With no key: the check-in fires on a simulated dust spike
(`scripts/device_sim.py --scenario dust` from A5, or post readings by hand), chat answers from
templates, and "my inhaler isn't helping" triggers the emergency flow and a `buddy_nudge`/`emergency`
for jordan. With a key: the same, with Grok wording and audio.

## Status
- [ ] 1 safety tests · [ ] 2 chat · [ ] 3 check-ins · [ ] 4 TTS · [ ] 5 emergency · [ ] 6 realtime · [ ] 7 verify ids
