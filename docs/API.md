# Airmate API contract

Every workstream codes against this file. The pydantic models in `backend/airmate_api/schemas.py`
(core) and in each feature router (`routers/agent.py`, `community.py`, `buddy.py`, `report.py`) are
the source of truth; this page is the readable version. **Changing a shape = PR that updates the
model, this file, and `web/src/lib/types.ts` together, with the lead as reviewer.** Adding optional
fields is always fine; renaming or removing is not.

* Base URL: `http://localhost:8000/api` in development. The web app uses `NEXT_PUBLIC_API_URL`
  (empty string = same origin, which is how FastAPI serves the exported site).
* Times are unix seconds (UTC, float). Ids are short strings (`maya`, `airmate-01`) except event
  ids, which are integers.
* Interactive docs: `http://localhost:8000/docs` once the backend runs.
* Status: ✅ implemented on main · 🚧 stub returning 501 (owner in brackets).

## Demo cast (seeded, ids are stable)

| id | who |
|---|---|
| `maya` | Patient in the demo. Triggers: dust, odors. Buddy: jordan. Caregiver: priya. |
| `jordan` | Maya's asthma buddy (the "buddy phone" in the demo). |
| `priya` | Maya's mother, role `caregiver`. |
| `airmate-01` | Maya's bedroom device. |
| `atl-asthma` | Community circle. |

## Device → backend (A5 firmware + simulator consume; lead implements)

### ✅ `POST /devices/{device_id}/readings`
Header `X-Device-Key: <DEVICE_KEY>` when the server sets one. Send every ~15 s (an average of the
samples since the last post). Buffer while offline and send the backlog with `age_s`.
```json
{"readings": [{"ts": 1790000000.0, "pm25": 6.1, "pm10": 14.2, "co2": 650, "tvoc": 120, "temp_c": 22.4, "humidity": 45}],
 "fw": "0.1.0", "rssi": -61}
```
* Omit or `null` any sensor the device lacks. Use `ts` if the device has NTP time, otherwise
  `age_s` (seconds ago); with neither, arrival time is used. Up to 500 readings per batch.
* Unknown devices are attached to `DEFAULT_USER_ID` (maya).

Response — `risk` is the latest score for the LED (may be a few seconds old, `null` before the first):
```json
{"user_id": "maya", "accepted": 1, "risk": {"score": 7, "band": "low", "color": "#10b981", "ts": 1790000000.0}}
```

### ✅ `POST /devices/{device_id}/events`
```json
{"kind": "button", "data": {"press": "short"}}      // short = "I'm OK" / answer check-in, long = emergency
{"kind": "puff",   "data": {"count": 1}}            // smart-cap or button-logged rescue puff
{"kind": "cough",  "data": {"count": 4, "confidence": 0.8}}
```
→ `{"ok": true, "id": 123, "risk": {...} | null}`

### ✅ `PUT /devices/{device_id}` · `GET /devices`
Register or move a device: `{"user_id": "maya", "label": "Bedroom", "lat": 33.77, "lon": -84.39, "community": false}`.
`community: true` + `user_id: null` = an anonymous map-only sensor.

## People, logs, risk (lead)

| | Endpoint | Body / query | Returns |
|---|---|---|---|
| ✅ | `GET /users` | | `UserOut[]` |
| ✅ | `GET /users/{id}` | | `UserOut` |
| ✅ | `PATCH /users/{id}` | any `UserPatch` field; `triggers` ⊂ `dust smoke pollen humidity odors cold_air` | `UserOut` |
| ✅ | `POST /users/{id}/puffs` | `{"count": 2, "source": "app"}` | `EventOut` |
| ✅ | `POST /users/{id}/symptoms` | `{"symptom": "wheeze", "severity": 2, "note": null}`; symptom ∈ `cough wheeze chest_tight short_breath night_waking other` | `EventOut` |
| ✅ | `GET /users/{id}/events` | `?kinds=puff,symptom&since=&limit=200` (newest first) | `EventOut[]` |
| ✅ | `GET /users/{id}/readings` | `?hours=6` (oldest first) | `ReadingPoint[]` |
| ✅ | `GET /users/{id}/risk` | `?fresh=true` forces a recompute | `RiskOut` |
| ✅ | `GET /users/{id}/risk/history` | `?hours=24` | `[{ts, score, band}]` |
| ✅ | `GET /health` | | `{ok, model, grok, database}` |

`UserOut`: `id name role age lat lon neighborhood tz triggers[] action_plan buddy_id caregiver_ids[]
cares_for_id circle_id doctor_name doctor_email phone emergency_contact bio`.

`action_plan`:
```json
{"controller": "Fluticasone 110 mcg inhaler, 2 puffs twice a day", "rescue": "Albuterol 90 mcg inhaler",
 "green":  {"when": "...", "do": ["..."]},
 "yellow": {"when": "...", "do": ["Take 2 to 4 puffs of albuterol.", "..."]},
 "red":    {"when": "...", "do": ["Take 4 to 6 puffs of albuterol now.", "Call 911 or go to the emergency room."]},
 "notes": "..."}
```

`RiskOut` (what the dashboard renders; also the payload of the `risk` stream message):
```json
{"user_id": "maya", "ts": 1790000000.0,
 "score": 23, "band": "elevated", "color": "#f59e0b",
 "probabilities": {"1h": 0.08, "4h": 0.23, "12h": 0.41},
 "factors": [{"key": "dust", "label": "Dust", "points": 14.2,
              "detail": "Dust (PM10) is 7.1× your normal (180 vs 25 µg/m³)"}],
 "latest": {"pm25": 9.0, "pm10": 180.0, "co2": 700.0, "tvoc": 130.0, "temp_c": 22.1, "humidity": 46.0},
 "normal": {"pm25": 6.0, "pm10": 25.3, "tvoc": 118.0},
 "ratios": {"pm25": 1.5, "pm10": 7.1, "tvoc": 1.1},
 "sensors_available": ["pm", "co2", "voc", "climate"],
 "outdoor": {"aqi": 38, "pollen": 1.2, "temp_c": 24, "humidity": 60},
 "puffs_24h": 0, "symptoms_24h": 0, "normal_day_score": 4.1, "rule_score": 31,
 "model": {"name": "airmate-gru-survival", "trained_on": "simulated cohort (no real patient data)", "...": "..."}}
```
* `score` = P(rescue inhaler needed within 4 h) × 100. Bands: `low` < 20 ≤ `elevated` < 45 ≤ `high`.
* `probabilities` is `null` and `model.name == "rules"` when the rule-based fallback is running.
* `factors` are sorted by points, at most 5; `latest.<sensor>` is `null` for absent sensors.

## Live stream (lead)

### ✅ `GET /stream?user_id=maya&user_id=jordan&community=true`
Server-Sent Events. Every message: `event: <type>` and
`data: {"type": "<type>", "topic": "user:maya" | "community", "ts": ..., "data": {...}}`.
A `: keep-alive` comment arrives every 15 s; reconnect on error (EventSource does this itself).

| type | topic | data | published by |
|---|---|---|---|
| `hello` | — | `{topics}` | lead |
| `reading` | `user:<id>`, `community` | `{device_id, ts, pm25, pm10, co2, tvoc, temp_c, humidity}` (+`lat lon` on community) | lead |
| `risk` | `user:<id>` | `RiskOut` | lead |
| `event` | `user:<id>` | `{id, kind, ts, data}` for puff / symptom / button / cough | lead |
| `checkin` | `user:<id>` | `{id, ts, score, previous_score, reason: "jump"｜"high", factor: Factor｜null, message, audio_url｜null, expires_at}` | A1 |
| `checkin_update` | `user:<id>` | `{id, status: "answered"｜"missed"｜"escalated", answer｜null}` | A1 |
| `chat` | `user:<id>` | `{role: "assistant"｜"user", text, source: "voice"｜"chat"｜"checkin"}` | A1 |
| `emergency` | patient, buddy, caregivers | `{user_id, name, red_flags[], script, lat, lon, ts}` | A1 |
| `buddy_nudge` | `user:<buddy>` | `{alert_id, for_user_id, for_name, score, factor, checkin_id, message, ts}` | A1 |
| `buddy_ack` | `user:<patient>` | `{alert_id, by_user_id, by_name, action}` | A4 |
| `community` | `community` | `{kind: "report"｜"hotspots", ...}` | A4 |

## Event kinds (the single `events` table)

`reading puff symptom button cough` (lead) · `risk` (lead) · `checkin alert emergency chat` (A1;
`alert.data.type` ∈ `buddy_nudge caregiver_alert emergency_alert`) · `alert_ack air_report` (A4).
New kinds are fine; add them to this list in your PR. New **tables or columns** go through the lead.

## 🚧 Grok agent [A1]

| Endpoint | Body | Returns |
|---|---|---|
| `POST /agent/chat` | `{user_id, message, conversation_id?, speak?}` | `{reply, conversation_id, emergency, red_flags[], tool_calls[], audio_url?}` |
| `POST /agent/tts` | `{text, voice?}` | `audio/mpeg` |
| `WS /agent/voice?user_id=maya` | see below | |
| `POST /checkins/{id}/answer` | `{user_id, answer}`; answer ∈ `ok not_ok used_inhaler` or free text | `{ok, reply?, emergency?}` |
| `POST /users/{id}/emergency` | `{text?, lat?, lon?}` | `{ok, script, notified: [ids]}` |

Voice WebSocket (A1 finalizes and updates this section): browser → server binary frames of 16-bit
PCM mono 24 kHz; server → browser binary audio frames of the same format plus JSON text frames
`{"type": "transcript"|"reply"|"tool"|"emergency"|"error", ...}`.
Safety runs server-side on the user's transcript, not only in the model.

## 🚧 Community [A4]

| Endpoint | Body / query | Returns |
|---|---|---|
| `GET /community/hotspots` | `?hours=6` | `{generated_at, hours, cells: [{lat, lon, score, aqi, pm25, pm10, tvoc, contributors, puffs, reports[], label}]}` |
| `POST /community/reports` | `{user_id?, lat, lon, kind: smoke｜dust｜pollen｜odor｜construction｜other, note?}` | `{ok, id}` |
| `GET /circles/{id}/posts` | | `[{id, circle_id, user_id, user_name, text, ts}]` |
| `POST /circles/{id}/posts` | `{user_id, text}` | post |

Privacy: cells are ~500 m and shown only with ≥ 2 contributors or a community device.

## 🚧 Buddy [A4]

| Endpoint | Body / query | Returns |
|---|---|---|
| `GET /users/{id}/buddy` | | `{me, buddy, open_nudges[]}`; people are `{id, name, neighborhood, triggers, risk: RiskBrief, last_seen}` |
| `GET /buddy/matches` | `?user_id=maya` | `[{user_id, name, score, reasons[]}]` |
| `POST /buddy/pair` | `{user_id, buddy_id}` | `{ok}` |
| `POST /buddy/nudges/{alert_id}/ack` | `{user_id, action: on_my_way｜calling｜checked_ok}` | `{ok}` |

## 🚧 Doctor report [A4]

| Endpoint | Body | Returns |
|---|---|---|
| `POST /users/{id}/reports` | `{days: 30, send_to?}` | `{token, url}` (`url` = `{PUBLIC_WEB_URL}/report/?token=…`) |
| `GET /reports/{token}` | | `{token, created_at, user, period_days, summary, totals, daily[], top_factors[], exposure_notes[], disclaimer}` |

## Web routes (static export, so no dynamic segments: use query strings)

| Route | Owner | What |
|---|---|---|
| `/` | A3 | Dashboard (`?user=maya` default) |
| `/talk/` | A3 | Chat + voice with Airmate; the check-in "call" overlay is global (in the layout) |
| `/settings/` | A3 | Triggers, action plan, buddy, doctor, "create doctor report" |
| `/community/` | A4 | Hotspot map + circle |
| `/buddy/?user=jordan` | A4 | Buddy phone view |
| `/report/?token=…` | A4 | Doctor report (printable) |
