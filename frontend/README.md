# GridSentinel — SCADA Command Center Frontend

High-fidelity real-time command-center dashboard for physics-aware cyber-physical anomaly detection on Indian power distribution SCADA networks.

---

## Features

- **Live Feeder Topology (Mapbox GL & Vector SCADA Schematic)**:
  - Visualizes the 11kV distribution feeder with color-coded bus status (Green=Normal, Amber=Natural Fault, Red=Cyber Intrusion, Gray=No Data).
  - Highlights affected lines with pulsing alert glow during active faults or cyber intrusions.
  - Interactive bus selection popup displaying live voltage magnitude (pu and kV), active power (MW), reactive power (MVAR), and WLS State Estimation residuals.
  - Automatic fallback to high-resolution interactive vector SCADA schematic if no Mapbox token is configured.

- **Real-Time Alert Feed**:
  - Live triage feed capturing only verdict state transitions (avoids repetitive spam).
  - Plain-language forensic templates customized per verdict & subtype combination (e.g., distinguishing silent sensor data injections from physical breaker line trips).
  - Filterable by incident category (Cyber, Fault, Normal).

- **CEA-2026 Cyber-Physical Incident Audit Trail**:
  - Structured incident log capturing detection time (simulated & UTC), affected asset, ML classification, forensic subtype, model confidence, network evidence, physics evidence, and recommended response action.
  - Client-side export to both **CSV** and **JSON** formats.

- **Scenario & Attack Injection Engine**:
  - Live triggers for cyber attacks (Silent Data Injection, Unauthorized Modbus Command Injection, Replay Attack) and physical faults (Line Trip, Short Circuit surge).
  - Real-time active status indicators and single-click **"Reset Grid to Clean State"** control.

- **Honest Connection Status Bar**:
  - Real-time indicator for `/ws/live` WebSocket link (`connected`, `reconnecting`, `disconnected`).
  - Separate telemetry state (`waiting`, `streaming`, `stale`, `stopped`, `error`) so a healthy socket cannot be mistaken for live simulation output.
  - Simulated clock, diurnal load multiplier, and overall feeder health badge.

- **Phase 5 — Demo Resilience & Compliance Panel**:
  - **Demo Director**: 6-beat 150s script pacer with Presenter View (cues, timers, step list) and Audience View (unobtrusive floating cue bar).
  - **Session Recorder**: Arm a one-click in-browser recorder to capture live `/ws/live` payloads and export them as a portable JSON replay session.
  - **Replay Engine**: Load any session JSON (or built-in reference session) and play back recorded incidents offline with scrubber, speed (1x/2x/5x), and seek controls.
  - **Replay Mode Banner**: A persistent, unmissable `"REPLAY MODE — recorded session, not live"` banner prevents any confusion between recorded and live data. All demo triggers are automatically disabled.
  - **Mapbox Resilience Fallback**: 6-second style-load timeout + Mapbox GL `error` event listener automatically switches to an interactive SVG/canvas SCADA schematic. Manual force-fallback toggle is available for offline testing.
  - **Automated Backup Video**: Playwright script records a 150s backup video of the full demo sequence in replay mode (backend-independent).
  - **CEA-2026 Compliance Panel**: Print-friendly compliance matrix mapping verified statutory obligations to GridSentinel operational capabilities.

---

## Environment Configuration

Copy `.env.local.example` to `.env.local`:

```bash
cp .env.local.example .env.local
```

### Environment Variables

| Variable | Required | Default | Description |
| :--- | :--- | :--- | :--- |
| `NEXT_PUBLIC_MAPBOX_TOKEN` | Optional | `""` | Mapbox public access token from [mapbox.com](https://mapbox.com). If empty, the app uses an interactive vector SCADA schematic. |
| `NEXT_PUBLIC_API_BASE_URL` | Optional | Localhost in development; deployed Render origin in browser production | GridSentinel FastAPI backend REST URL. Set the HTTPS backend origin for deployment. |
| `NEXT_PUBLIC_WS_URL` | Optional | Localhost in development; deployed `wss://` Render endpoint in browser production | GridSentinel live telemetry WebSocket stream URL. |

---

## Getting Started

## Public Demo URL

Use the unprotected production alias for judges:

`https://grid-sentinel-sepia.vercel.app/`

Preview deployment URLs may be protected by Vercel authentication. Do not
share a hash-based preview URL for the SIH demo; use the production alias
above after deploying the verified branch.

### 1. Install Dependencies

```bash
cd gridsentinel/frontend
npm install
```

### 2. Start the Development Server

```bash
npm run dev
```

Open [http://localhost:3000](http://localhost:3000) in your browser.

### 3. Run Automated Tests

```bash
npm test
```

### 4. Generate Backup Demo Video

With the Next.js dev server running on port 3000:

```bash
npm run record-demo
```

The recorder runs the complete deterministic 150-second offline replay by
default. For a quick local smoke test, use `DEMO_DURATION_MS=5000 npm run
record-demo` (PowerShell: `$env:DEMO_DURATION_MS=5000; npm run record-demo`).
Set `DEMO_OUTPUT_DIR` to write a smoke-test video outside the tracked
`backup-demo` directory. The script explicitly switches to Replay and Demo
Director modes, so it does not depend on the live backend being available and
returns a failure exit code if any required demo control cannot be driven.

The Playwright script will:
1. Open a headless browser at `http://localhost:3000`
2. Switch to **REPLAY MODE** (no backend connection required)
3. Open the **Demo Director** tab and click **"Run Full Demo"**
4. Switch to **Audience View** for a clean recording
5. Save the recording to `backup-demo/gridsentinel-backup-demo.webm`

> **Note**: To record against a production URL, set `DEMO_URL=https://your-deployment.example.com` before running.

---

## Live Demo — Presenter Rehearsal Checklist

Use this checklist before every presentation to ensure a flawless live demo:

### T-60 minutes: Environment Verification

- [ ] **Backend running**: `cd gridsentinel/backend && .venv/Scripts/uvicorn app.main:app --host 0.0.0.0 --port 8000`
- [ ] **Frontend running**: `cd gridsentinel/frontend && npm run dev`
- [ ] **Health check**: Open [http://localhost:3000](http://localhost:3000) — Status Bar should show **Connected** (green dot).
- [ ] **WebSocket live**: Status Bar simulation clock should be ticking every second.
- [ ] **Mapbox map**: 11kV feeder nodes and lines should be visible on the dark map. If not, check `NEXT_PUBLIC_MAPBOX_TOKEN`. The vector fallback will activate automatically.
- [ ] **Backup video**: Verify `backup-demo/gridsentinel-backup-demo.webm` exists and plays correctly (`npm run record-demo` if not).

### T-15 minutes: Demo Flow Dry-Run

- [ ] Click the **Director** tab → confirm all 6 beats are listed with correct durations (15-30-30-30-30-15).
- [ ] Click **"Run Full Demo"** → confirm the sequence auto-advances.
- [ ] Stop and reset to Step 1.
- [ ] Click **"Audience View"** → confirm the full Presenter panel collapses to a floating cue bar.
- [ ] Click the eye icon to return to Presenter View.
- [ ] Confirm **CONTROLS** tab shows all 5 attack + 2 fault buttons.
- [ ] Click **"Reset Grid to Clean State"** → confirm green toast notification appears.
- [ ] Click **CEA-2026** tab → verify the 5-row compliance matrix renders and the Print button opens the browser print dialog.

### T-5 minutes: Failsafe Preparation

- [ ] Click **REPLAY MODE** → confirm the purple `"REPLAY MODE — recorded session, not live"` banner is visible.
- [ ] Click **Play (▶)** on the replay controls → confirm map buses change color and alert feed populates.
- [ ] Confirm all CONTROLS buttons show the lock icon and are disabled in Replay Mode.
- [ ] Switch back to **LIVE SCADA** mode.
- [ ] Open `backup-demo/gridsentinel-backup-demo.webm` in a separate window/tab as final fallback if the live demo encounters network issues.

---

## 6-Beat Demo Script (150 seconds)

| Beat | Duration | Title | Live Action |
| :--- | :--- | :--- | :--- |
| 1 | 15s | Problem Statement & Threat Landscape | Presenter explains CEA-2026 context |
| 2 | 30s | Live SCADA Baseline & State Estimation | Reset → nominal 5-RTU operation, point to map |
| 3 | 30s | Genuine Physical Fault (Line Outage) | Trip Line 0 via Director or Controls |
| 4 | 30s | Cyber Intrusion (Silent Sensor Tampering) | Inject Silent Data Attack on RTU-2 |
| 5 | 30s | Real-Time Forensic Triage & Audit Trail | Navigate to Alert Feed + Audit Log + export |
| 6 | 15s | Summary & CEA-2026 Readiness | Open Compliance Matrix, reset grid |

---

## Project Architecture

```
gridsentinel/frontend/
├── app/
│   └── page.tsx              # Main SCADA command center page (Phases 4+5)
├── components/
│   ├── StatusBar.tsx          # Live connection & feeder health indicator
│   ├── FeederMap.tsx          # Mapbox GL map with fallback integration
│   ├── FeederMapFallback.tsx  # SVG/canvas vector SCADA schematic
│   ├── AlertFeed.tsx          # Real-time plain-language triage feed
│   ├── AuditLog.tsx           # CEA-2026 structured audit trail
│   ├── DemoControls.tsx       # Attack & fault injection engine
│   ├── DemoDirector.tsx       # 6-beat 150s demo script pacer
│   └── ComplianceMap.tsx      # CEA-2026 verified compliance matrix
├── lib/
│   ├── types.ts               # Shared TypeScript schemas
│   ├── api.ts                 # Typed REST client for FastAPI backend
│   ├── alertText.ts           # Plain-language incident template engine
│   ├── useLiveSocket.ts       # WebSocket hook with exponential backoff
│   ├── sessionRecorder.ts     # In-browser session capture & export
│   └── replayEngine.ts        # Offline session playback hook
├── data/
│   ├── compliance-mapping.ts  # Verified CEA-2026 statutory facts (no invented clauses)
│   └── reference-session.json # Pre-recorded reference session for backup demo
├── scripts/
│   └── record-demo.mjs        # Playwright automated backup video recorder
├── tests/
│   ├── alertText.test.ts
│   ├── auditLog.test.ts
│   ├── useLiveSocket.test.ts
│   ├── sessionRecorder.test.ts
│   ├── replayEngine.test.ts
│   ├── DemoDirector.test.tsx
│   ├── ComplianceMap.test.tsx
│   └── FeederMapFallback.test.tsx
└── backup-demo/               # Generated backup video output directory
```
