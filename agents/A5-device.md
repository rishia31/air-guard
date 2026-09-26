# A5 · device (Codex)

**Mission:** the physical Airmate. An ESP32 that reads the room's air, posts it to the backend, and
glows the risk color. A simulator script does the same, so the demo never depends on hardware.

**Branch:** `a5/device` · **Paste to start:** "You are A5 (device). Read AGENTS.md and
agents/A5-device.md, then start with task 1."

## Read first
* `AGENTS.md`, `docs/API.md` ("Device → backend" section: the only endpoints you call)
* `backend/tests/test_foundation.py` shows the exact request shapes the backend accepts

## You own
`firmware/**`, `scripts/device_sim.py`, `docs/HARDWARE.md`.

## Tasks

### P0: required for the demo
1. **`scripts/device_sim.py`** (Python 3.10+, `httpx`, both already in the workspace; run with
   `uv run python scripts/device_sim.py`). Build this first, since A1/A3/A2 use it to test.
   * `--url http://localhost:8000 --device airmate-01 --key $DEVICE_KEY --interval 15`
   * Baseline room air with realistic noise and slow drift (pm25 ≈ 6, pm10 ≈ 14, co2 600–900 with
     occupancy, tvoc ≈ 120, 22 °C, 45 %).
   * `--scenario calm|dust|cooking|spray|smoke|window|stuffy`: **dust** = the demo beat, PM10 to
     ~180 µg/m³ with PM2.5 barely moving, ramping up over ~1 min, holding ~24 min, decaying over ~20 min;
     **cooking** = PM2.5 + TVOC; **spray** = TVOC to ~2500 ppb; **smoke** = PM2.5 to ~80.
   * **Interactive mode** (default when run in a terminal): keys `d` dust, `c` cooking, `s` spray,
     `k` smoke, `w` window, `0` calm, `b` button short, `B` button long, `p` puff, `q` quit. The
     presenter triggers the beat live.
   * `--backfill-hours H` posts past history first (batches of ≤ 500 with past `ts`). The backend
     ignores future timestamps, so rehearse the beat faster with a shorter scenario
     (`--dust-minutes 5`), not by compressing time.
   * `--community N`: also run N map-only devices around Atlanta (register them with
     `PUT /devices/{id}` `{"community": true, "lat", "lon"}`).
   * Print one line per post: time, readings, and the returned `risk` (score, band) in color.
2. **Firmware** (`firmware/`, PlatformIO, Arduino framework, `esp32dev`; note the board you
   assumed in `platformio.ini`):
   * Sensors, each optional and auto-detected at boot (omit its fields when absent): PMS5003/PMSA003
     (UART) → pm25/pm10; SCD40/41 (I²C) → co2/temp/humidity; ENS160 (+AHT21) (I²C) → tvoc (+ temp/
     humidity if no SCD4x). Warm-up handling (ENS160/PMS need ~1 min).
   * Every 15 s: average the samples, `POST /api/devices/{id}/readings` with `ts` from NTP (or
     `age_s` before NTP syncs), header `X-Device-Key`. Offline: ring buffer of up to ~200 readings,
     sent as a backlog with `age_s` when Wi-Fi returns.
   * WS2812/NeoPixel ring shows `risk.color` from the response (breathing animation; fast pulse on
     `high`); blue spinner while connecting.
   * Button: short press → `POST /events {"kind":"button","data":{"press":"short"}}` ("I'm OK"),
     long press (≥ 2 s) → `press: long` (emergency). Optional buzzer chirp on high risk.
   * `include/secrets.example.h` (Wi-Fi SSID/password, `API_BASE`, `DEVICE_ID`, `DEVICE_KEY`);
     real `secrets.h` is gitignored. Support `http://` on the LAN and `https://` (tunnel) with
     `WiFiClientSecure::setInsecure()`.
   * `pio run` must compile with no sensors attached (all drivers optional at runtime).

### P1
3. **`docs/HARDWARE.md`**: parts list with approximate prices, a wiring table (pin ↔ sensor),
   photos/diagram placeholder, flashing steps, and how to point the device at a laptop on hotel/venue
   Wi-Fi (LAN IP, or `cloudflared tunnel --url http://localhost:8000`).
4. Serial console commands (`status`, `wifi`, `url`) and a captive-portal Wi-Fi setup (WiFiManager)
   so the device can be reconfigured on stage without reflashing.

### P2
5. I²S microphone (INMP441) night-cough event (`kind: "cough"`) with a simple energy + band
   heuristic, if hardware exists; A2 may provide a better classifier.

## Done when
`uv run python scripts/device_sim.py --scenario dust` moves the dashboard live and returns the risk
color; the firmware compiles; on real hardware (if available) the ring changes color within ~20 s of
a dusty-cloth wipe.

## Status
- [ ] 1 simulator · [ ] 2 firmware · [ ] 3 HARDWARE.md · [ ] 4 Wi-Fi setup · [ ] 5 cough mic
