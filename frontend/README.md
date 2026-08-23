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
  - Simulated clock, diurnal load multiplier, and overall feeder health badge.

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
| `NEXT_PUBLIC_API_BASE_URL` | Optional | `http://localhost:8000` | GridSentinel FastAPI backend REST URL. |
| `NEXT_PUBLIC_WS_URL` | Optional | `ws://localhost:8000/ws/live` | GridSentinel live telemetry WebSocket stream URL. |

---

## Getting Started

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
