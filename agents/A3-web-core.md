# A3 · web-core (Gemini #1)

**Mission:** the app judges see. A phone-first Next.js app: a live risk dashboard that explains
itself, a talk screen for chat and voice, and the incoming "Airmate is calling" moment.

**Branch:** `a3/web-core` · **Paste to start:** "You are A3 (web-core). Read AGENTS.md and
agents/A3-web-core.md, then start with task 1."

## Read first
* `AGENTS.md`, `docs/API.md` (all of it; you consume nearly every shape)
* Run the backend: `uv sync && uv run airmate-api`, then browse http://localhost:8000/docs

## You own
`web/**` except `web/src/app/{community,buddy,report}/**` and `web/src/components/{community,buddy,report}/**` (A4's).

## Who depends on you
**A4 cannot start their pages until task 1 is on `main`.** Do task 1 first, PR it within about 45 minutes,
and keep it small.

## Tasks

### P0: required for the demo
1. **Scaffold (merge ASAP).** Next.js (latest, App Router, TypeScript, Tailwind) in `web/` with
   `src/`. `next.config` must have `output: "export"`, `trailingSlash: true`,
   `images: { unoptimized: true }`, because FastAPI serves `web/out` as static files, so **no dynamic
   route segments and no server actions/route handlers**; use query strings (`/buddy/?user=jordan`).
   Include:
   * `src/lib/types.ts`: TypeScript mirror of every shape in `docs/API.md`.
   * `src/lib/api.ts`: typed fetch client, base URL `process.env.NEXT_PUBLIC_API_URL ?? ""`.
   * `src/lib/useStream.ts`: an `EventSource` hook on `/api/stream?user_id=…` returning typed
     messages, with reconnect.
   * `src/lib/useUser.ts`: current user id from `?user=` (default `maya`), kept across links.
   * App shell: bottom nav on mobile (Home, Talk, Community, Settings), empty placeholder pages for
     `/community/`, `/buddy/`, `/report/` so A4 fills them in, and a `.env.local.example`.
   * `npm run build` produces `web/out`, and `uv run airmate-api` then serves it at :8000.
2. **Dashboard `/`**: large risk ring (score, band color, "Low/Elevated/High"), the top factors
   with their `detail` sentence (this is the "why", so make it prominent), 1 h / 4 h / 12 h chances,
   live sensor tiles showing value and "× your normal", a 24 h risk chart and a 6 h PM chart
   (`/risk/history`, `/readings`), outdoor strip (AQI, pollen), quick log buttons (rescue puff,
   symptom picker). Updates live from `risk`/`reading` messages without a reload; animate score
   changes, since the jump is the demo moment. Footer: "Risk model trained on simulated data. Not a
   medical device." When `model.name == "rules"`, show "basic mode".
3. **Incoming check-in "call"** (global, in the layout): on a `checkin` message, show a full-screen
   ringing card ("Airmate is calling: dust jumped 7× your normal"), play `audio_url` if present
   (fall back to `speechSynthesis`), buttons **I'm OK** / **Not great** / **Talk** →
   `POST /checkins/{id}/answer` or go to `/talk/`. Handle `checkin_update`.
4. **Emergency state** (global): on `emergency`, a red full-screen card showing the `script`
   verbatim, a big "Call 911" button (`tel:911`), and "Jordan has been alerted".
5. **Talk `/talk/`**: chat bubbles with `/agent/chat`, chips for tool calls ("Logged 2 puffs"),
   emergency replies styled red. Push-to-talk mic using the Web Speech API (SpeechRecognition) →
   `/agent/chat` with `speak: true` → play `audio_url`. Until A1 merges, `/agent/chat` returns 501,
   so show a friendly "Airmate's voice is coming online" state.

### P1
6. **Settings `/settings/`**: triggers (6 toggles), action plan viewer/editor (green/yellow/red),
   buddy and doctor fields (`PATCH /users/{id}`), "Create doctor report" → `POST /users/{id}/reports`
   → show and copy the link (A4 builds the report page).
7. **Realtime voice** once A1 finalizes `WS /agent/voice`: mic → 24 kHz PCM16 via AudioWorklet,
   play returned audio, show transcripts. Keep push-to-talk as the fallback.
8. Onboarding for a new user (name, triggers, pair device id).

### P2
9. PWA manifest + icons so the phone view looks like an app; dark mode.

## Design notes
Calm, clinical, friendly: lots of white space, one accent per band (`#10b981` / `#f59e0b` /
`#ef4444`), big numbers, plain words ("Dust is 7× your normal", not "PM10 ratio 7.1"). Design for a
390 px wide phone first; the demo projects a laptop and holds up a phone.

## Done when
`npm run build` succeeds, the dashboard updates live while `scripts/device_sim.py --scenario dust`
runs, the call overlay appears on a check-in, and the whole app is served by `uv run airmate-api`.

## Status
- [x] 1 scaffold · [ ] 2 dashboard · [ ] 3 call overlay · [ ] 4 emergency · [ ] 5 talk · [ ] 6 settings · [ ] 7 realtime
