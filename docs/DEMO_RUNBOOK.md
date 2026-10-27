# GridSentinel — Demo Operator Runbook

**Version:** 3.0.0 — CHANGE 4 (Demo Reliability)  
**Last Updated:** 2026-10-12  
**Audience:** Demo operator, SIH presentation team

---

## Table of Contents

1. [Quick-Start (60 seconds)](#1-quick-start-60-seconds)
2. [Pre-flight Checklist](#2-pre-flight-checklist)
3. [Demo Script — Full 8-Minute Flow](#3-demo-script--full-8-minute-flow)
4. [Fallback Procedures](#4-fallback-procedures)
5. [Known Failure Modes & Fixes](#5-known-failure-modes--fixes)
6. [Environment Reference](#6-environment-reference)
7. [Version Verification](#7-version-verification)

---

## 1. Quick-Start (60 seconds)

> Run this from the repo root on the demo machine.

```powershell
# 1. Start backend (keep this terminal open)
cd gridsentinel\backend
uvicorn app.main:app --host 0.0.0.0 --port 8000

# 2. Start frontend (new terminal)
cd gridsentinel\frontend
npm run dev

# 3. Open dashboard
Start-Process "http://localhost:3000"
```

> **Tip:** If the backend was deployed to Render, it may take up to 60 seconds to
> wake from cold start. Open `https://gridsentinel-72tf.onrender.com/health`
> in a browser tab to force it awake before the room fills.

---

## 2. Pre-flight Checklist

Run the automated preflight script **at least 10 minutes before** the demo:

```powershell
# From repo root:
python scripts/demo-preflight.py --backend-url http://localhost:8000
```

For the deployed version:

```powershell
python scripts/demo-preflight.py --backend-url https://gridsentinel-72tf.onrender.com
```

The script checks 19 conditions and exits `0` (green) or `1` (red). All `[FAIL]`
items must be resolved before going on stage. `[WARN]` items are acceptable.

### Manual checklist (if script unavailable)

| # | Item | Pass condition |
|---|------|---------------|
| 1 | Backend `/health` | Returns `{"status":"ok"}` |
| 2 | Frontend loads | No blank page, no console errors |
| 3 | Live socket pill | Shows **CONNECTED** (green) |
| 4 | Bus markers animate | Colour updates every ~1 s |
| 5 | Version stamp | Run `GET /version` — git_sha ≠ "unknown" |
| 6 | Model loaded | `GET /classifier/status` → `is_loaded: true` |
| 7 | Replay file | `frontend/data/reference-session.json` exists |
| 8 | Backup video | `frontend/backup-demo/gridsentinel-backup-demo.webm` exists |
| 9 | CORS origin | `https://grid-sentinel-sepia.vercel.app` in CORS whitelist |
| 10 | Network is WiFi/LAN | Not a hotel captive portal — verify backend is reachable |

---

## 3. Demo Script — Full 8-Minute Flow

### Phase 0 — Introduction (0:00 – 1:00)

- Open dashboard. Point to the live **CONNECTED** pill in the status bar.
- Explain: "This is a real-time simulation of an Indian 11-kV distribution feeder
  with 7 buses, 5 lines, and 5 Modbus RTU field devices."

### Phase 1 — Normal Operation (1:00 – 2:30)

- Let the feeder run normally for ~30 seconds. Narrate:
  - Diurnal load curve (numbers change gradually).
  - WLS state estimation residuals (χ² test passing).
  - All ML verdicts show **Normal** (green).

### Phase 2 — Silent Data Injection Attack (2:30 – 4:00)

1. Click **"Silent Data Injection"** in DemoControls → RTU-2, voltage = 0.72 pu.
2. Wait for one tick (~1 s). Point out:
   - RTU-2 bus marker turns **orange** (anomaly halo).
   - ML verdict for RTU-2 changes to **Cyber Intrusion / data_injection**.
   - Physical state stays unchanged (pandapower truth vs. reported telemetry diverge).
3. Explain: "No Modbus write — invisible to traditional IDS. Only physics divergence
   triggers our ML fusion classifier."

### Phase 3 — Command Injection Attack (4:00 – 5:30)

1. Click **"Command Injection"** → RTU-3, register 0, value 7500.
2. Open Traffic Log panel. Show the **flagged red** unauthorized write event.
3. ML verdict for RTU-3 → **Cyber Intrusion / command_injection** (high confidence).
4. Explain: "This simulates an APT actor sending a forged Modbus TCP write to a
   protection relay — our OT traffic inspector catches the anomalous function code."

### Phase 4 — Physical Fault (Line Trip) (5:30 – 6:30)

1. Click **"Line Trip"** → Line 1.
2. Map shows line loading drops to 0 % (line is out-of-service).
3. ML verdict: **Natural Fault / physical_fault** — correctly distinguished from cyber.
4. Explain: "State estimation chi-squared test fails on measurement residuals;
   classifier outputs Natural Fault, not cyber — demonstrating correct discrimination."

### Phase 5 — Compliance & Audit (6:30 – 8:00)

1. Click **Compliance** tab. Point to CEA-2026 Regulation mapping table:
   - Gazette date: 31 July 2026
   - Mandatory 6-hour CSIRT-Power incident reporting
   - Section 177 / Electricity Act 2003
2. Click **Export Audit Log** → JSON → show downloaded file structure.
3. Click **Export Audit Log** → CSV → "Ready for SIEM ingestion."
4. Click **"Reset"** → all verdicts clear, simulation returns to Normal.

---

## 4. Fallback Procedures

### 4A — Backend Unreachable ("Failed to fetch")

**Symptoms:** Live socket pill shows **DISCONNECTED** (red). All bus markers grey.

**Immediate action:**
1. Switch to **Replay Mode** in DemoControls (top-right toggle).
2. The UI loads `reference-session.json` locally — **no backend required**.
3. Narrate the timeline events manually using the Replay controls.

> Replay mode has been tested offline. It covers all three attack scenarios.

---

### 4B — Backend Cold Start (Render free tier)

**Symptoms:** `/health` times out for the first 30–60 seconds.

**Prevention:** Open `/health` in a browser tab ~5 minutes before presenting.

**During demo:** If the delay happens:
1. Tell the audience: "Render free tier spins down after inactivity — watch the
   startup latency here — this is exactly the kind of real-world reliability
   issue our preflight harness catches."
2. Once backend is up, proceed normally. Cold-start time is typically < 45 s.

---

### 4C — CORS Preflight Failure ("Access-Control-Allow-Origin missing")

**Symptoms:** Browser console shows CORS error. API calls fail silently.

**Root cause:** Production Vercel URL not in `CORS_ALLOW_ORIGINS` env var on Render.

**Fix (5 minutes):**
```bash
# On Render dashboard → Environment Variables:
CORS_ALLOW_ORIGINS=https://grid-sentinel-sepia.vercel.app,https://grid-sentinel-*.vercel.app
```
Then trigger a manual redeploy. The regex pattern in `main.py` also covers
preview deployments: `^https://grid-sentinel-[a-z0-9]+-srisai-kedars-projects\.vercel\.app$`.

**Immediate fallback:** Use Replay Mode (4A above).

---

### 4D — WebSocket Mixed Content (ws:// on HTTPS page)

**Symptoms:** WS connection immediately drops. Console: "Mixed Content: blocked".

**Fix:**
1. Verify `NEXT_PUBLIC_BACKEND_URL` in Vercel env starts with `https://`.
2. Redeploy frontend.

**Immediate fallback:** Use Replay Mode (4A above).

---

### 4E — Backup Video

If all else fails, play the pre-recorded backup video:

```
frontend/backup-demo/gridsentinel-backup-demo.webm
```

Regenerate it if needed:
```powershell
cd gridsentinel/frontend
npm run build   # build production bundle first
npm run start   # start production server
# In a new terminal:
node scripts/record-demo.mjs
```

---

### 4F — "Simulation loop not responding" (spinner stuck)

**Symptoms:** Bus markers frozen, no tick updates. Backend logs show error.

**Fix:**
```http
POST /ot/stop
POST /ot/reset
POST /ot/start
```
Or use the **Stop → Reset → Start** sequence in DemoControls. The loop supervisor
surfaces errors to the stream (`stream_status: "error"`) so the UI can show a
meaningful state rather than silently freezing.

---

## 5. Known Failure Modes & Fixes

| Regression | Symptom | Root cause | Fix status |
|------------|---------|-----------|-----------|
| CORS preflight fail | "Failed to fetch" on POST | Vercel preview URL not in allowlist | Fixed: regex allow-origin covers all preview URLs |
| WS mixed-content | WS drops immediately on HTTPS | `ws://` used on `https://` page | Fixed: env var validation in preflight script |
| Stale branch deployed | Old API, missing endpoints | Wrong git branch on Render | Fixed: `/version` stamp + preflight check #3 |
| Deployment login wall | 403 from Vercel protection | Preview deployment auth enabled | Fixed: production URL uses no auth; use Replay Mode |
| Zombie verdicts | Old "Cyber Intrusion" after Reset | Classifier cache not cleared on stop | Fixed: `sim_loop.stop()` flushes `classifier_service.latest_verdicts` |
| Tick crash → silent hang | Sim appears running but frozen | Exception swallowed in `_run_loop` | Fixed: `last_error` + `stream_status: error` surfaced to WS |
| `reportlab` missing | Import error on startup | Not installed in system Python | Fix: `pip install reportlab>=4.2.5` |

---

## 6. Environment Reference

### Backend (local)

| Variable | Default | Notes |
|----------|---------|-------|
| `PORT` | `8000` | uvicorn listen port |
| `CORS_ALLOW_ORIGINS` | _(unset)_ | Comma-separated extra origins |
| `RENDER_GIT_COMMIT` | _(set by Render)_ | Used for `/version` git_sha |

### Frontend (local)

| Variable | Default | Notes |
|----------|---------|-------|
| `NEXT_PUBLIC_BACKEND_URL` | `http://localhost:8000` | Must match backend scheme |
| `NEXT_PUBLIC_MAPBOX_TOKEN` | _(unset)_ | If unset: offline SVG fallback (recommended for demo) |

### Endpoints quick-reference

| Endpoint | Purpose |
|----------|---------|
| `GET /health` | Liveness probe |
| `GET /version` | Git SHA + model sha256 + schema version |
| `POST /ot/start` | Start simulation loop |
| `POST /ot/stop` | Stop simulation loop |
| `POST /ot/reset` | Clear all attacks + classifier cache |
| `GET /ot/status` | Simulation status + active scenarios |
| `POST /ot/attack/data-injection` | Silent data injection |
| `POST /ot/attack/command-injection` | Unauthorized Modbus write |
| `POST /ot/fault/line-trip` | Physical line outage |
| `POST /classifier/verdict` | On-demand ML verdict |
| `GET /classifier/status` | Model load status |
| `GET /audit/export?format=json` | Download audit log (JSON) |
| `GET /audit/export?format=csv` | Download audit log (CSV) |
| `WS /ws/live` | Real-time telemetry stream |

---

## 7. Version Verification

Before every demo, confirm the correct build is deployed:

```bash
curl https://gridsentinel-72tf.onrender.com/version
```

Expected response shape:
```json
{
  "git_sha": "a1b2c3d",
  "model_sha256_short": "4e5f6a7b",
  "feature_schema_version": "v3.0-28f",
  "started_at_utc": "2026-10-12T10:00:00+00:00"
}
```

> ⚠️ If `git_sha` is `"unknown"`, the `RENDER_GIT_COMMIT` env var is not set,
> or the server is running from a local working tree with no git history.
> This is acceptable for local demos but should be investigated for production.

The **model sha256** (`model_sha256_short`) lets you verify the same trained
`fusion_classifier.joblib` artifact is loaded in every environment. Compare it
against the SHA printed during training:

```bash
python -c "import hashlib; h=hashlib.sha256(open('backend/models/fusion_classifier.joblib','rb').read()); print(h.hexdigest()[:8])"
```

## 8. Corrected three-scenario verification script

Run this sequence after Render warm-up and preflight. Each scenario is advisory telemetry analysis; none is an attack verdict by itself.

```powershell
$base = "https://gridsentinel-72tf.onrender.com"
Invoke-RestMethod "$base/health"
Invoke-RestMethod "$base/version" | ConvertTo-Json
Invoke-RestMethod "$base/classifier/status" | ConvertTo-Json
Invoke-RestMethod "$base/ot/start" -Method Post -Body '{}' -ContentType 'application/json'
```

Use one-minute spacing between scenarios so the dashboard and the presenter can identify the active condition. For each scenario, inject at `t=0`, collect verdicts at `t=1,2,...,30` seconds, then reset and wait 5 seconds before the next scenario.

| Time | Request | Expected current display |
|---|---|---|
| 00:00 | `POST /ot/attack/data-injection` with `{"rtu_id":2,"voltage_pu":0.72,"duration_ticks":20}` | RTU-2 should show the existing physics/network anomaly response; verify the actual subtype rather than promising a fixed label. |
| 01:00 | `POST /ot/fault/line-trip` with `{"line_index":0}` | The current classifier is expected to show `Natural Fault / physical_fault` when the line-trip residual is classified as a physical fault. |
| 02:00 | `POST /ot/fault/sensor-drift` with `{"rtu_id":1,"drift_percent":0.08,"duration_ticks":25}` | With the decoupled live-feature rule deployed, RTU-1 should show `Sensor Malfunction / sensor_drift` when the live residual signature is present; record every tick and do not infer unobserved ticks. |

After each 30-second observation:

```powershell
Invoke-RestMethod "$base/ot/reset" -Method Post -Body '{}' -ContentType 'application/json'
Start-Sleep -Seconds 5
```

If a scenario produces a different verdict, record the exact `/version` SHA, `/classifier/status`, request body, tick timestamps, and returned RTU verdicts. Do not rewrite the result as a successful demo.

## 9. Offline replay fallback

If Render is cold, unavailable, or the browser cannot establish the live socket, switch the website to Replay Mode and use `frontend/data/reference-session.json`. Replay is a presentation fallback only; it does not verify the deployed backend, the current model hash, or the corrected drift rule. Keep the recorded live API responses separately when claiming a live demonstration.

---

*GridSentinel is a Smart India Hackathon 2024 project. This runbook is for internal
demonstration use only. All CEA-2026 compliance references are for illustrative
purposes.*
