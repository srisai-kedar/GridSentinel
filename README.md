# GridSentinel — Physics-Aware Cyber-Physical Anomaly Detection for SCADA

GridSentinel is an end-to-end cyber-physical intrusion detection and situational awareness platform for Indian 11kV/33kV power distribution networks.

It fuses:
1. **PCD (Physics-Consistency Detection)**: Newton-Raphson power flow & Weighted Least Squares (WLS) state estimation with largest normalized residual bad-data detection in pandapower.
2. **NBD (Network Behaviour Detection)**: Modbus TCP deep packet transaction logging, unexpected write detection, and timing anomaly analysis.
3. **ML Cyber-Physical Fusion Classifier**: Dual-stage Random Forest classifier delivering real-time verdicts (`Normal`, `Natural Fault`, `Cyber Intrusion`) and forensic subtyping (`data_injection`, `command_injection`, `replay`, `line_trip`, `short_circuit`).
4. **Real-Time SCADA Command Center**: Next.js 14+ (App Router), TypeScript, Tailwind CSS, and Mapbox GL dashboard streaming live telemetry over `/ws/live`.

---

## System Architecture

```
                                    ┌────────────────────────┐
                                    │   Mapbox GL & Next.js  │
                                    │   SCADA Command Center │
                                    └───────────▲────────────┘
                                                │ WebSocket (/ws/live) & REST
                                                │
                                    ┌───────────┴────────────┐
                                    │     FastAPI Backend    │
                                    └─────▲────────────▲─────┘
                                          │            │
                         ┌────────────────┴───┐    ┌───┴────────────────┐
                         │ Dual-Stage ML      │    │ pandapower Physics │
                         │ Fusion Classifier  │    │ & WLS State Est.   │
                         └────────▲───────────┘    └───▲────────────────┘
                                  │                    │
                         ┌────────┴───────────┐    ┌───┴────────────────┐
                         │ Modbus Traffic Log │    │ 5x Modbus RTU      │
                         │ & SCADA Master     │◄───┤ Servers (5021-5025)│
                         └────────────────────┘    └────────────────────┘
```

---

## Quickstart: Running Backend + Frontend

### Prerequisites
- Python 3.10+ (with `pandapower`, `fastapi`, `uvicorn`, `pymodbus`, `scikit-learn`, `joblib`)
- Node.js 18+ and npm

---

### Step 1: Start the FastAPI Backend

```bash
# From the gridsentinel/backend directory:
cd gridsentinel/backend

# Activate virtual environment if configured:
# .venv\Scripts\activate  (Windows)
# source .venv/bin/activate  (Linux/macOS)

# Start FastAPI server on port 8000
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

The backend starts at `http://localhost:8000`.
- API Docs: `http://localhost:8000/docs`
- Live WebSocket: `ws://localhost:8000/ws/live`

---

### Step 2: Start the Next.js SCADA Command Center Frontend

```bash
# In a second terminal, navigate to gridsentinel/frontend:
cd gridsentinel/frontend

# Install dependencies (if not already installed)
npm install

# (Optional) Provide your free Mapbox Token:
# cp .env.local.example .env.local
# Set NEXT_PUBLIC_MAPBOX_TOKEN=your_token_here

# Start development server
npm run dev
```

Open [http://localhost:3000](http://localhost:3000) in your browser.

---

### Step 3: Running Tests

```bash
# Backend pytest suite:
cd gridsentinel/backend
pytest -v

# Frontend Vitest test suite:
cd gridsentinel/frontend
npm test
```

---

## Operational Workflow

1. Click **"Start OT"** in the **Demo Controls** panel to start the 5 Modbus TCP RTU servers and continuous simulation loop.
2. Observe live voltages, power flows, and state estimation residuals updating on the **11kV Feeder Map** and **Status Bar**.
3. Trigger cyber attacks (Silent Data Injection, Command Injection, Replay) or physical faults (Line Trip, Short Circuit) from Demo Controls.
4. Review real-time plain-language triage alerts in the **Alert Feed** and inspect accumulated events in the **CEA-2026 Audit Trail Log**.
5. Export audit reports in **CSV** or **JSON** formats with single-click download.
6. Click **"Reset Grid to Clean State"** to restore nominal operation.

---

## Deployment

GridSentinel consists of two primary services:
- **Frontend**: The Next.js web application located in `/frontend`
- **Backend**: The FastAPI Python application located in `/backend`

### Environment Configuration

The frontend connects to backend services via environment variables configured at build/runtime:
- `NEXT_PUBLIC_API_BASE_URL`: Configures the backend REST API base URL.
- `NEXT_PUBLIC_WS_URL`: Configures the backend live telemetry WebSocket URL. Production environments served over TLS/HTTPS **must use `wss://`**.
- `NEXT_PUBLIC_MAPBOX_TOKEN`: (Optional) Mapbox public access token for GIS tile layers. If left unset, the application automatically uses the built-in Vector SCADA Schematic.

> **Security Best Practice**: Never commit production credentials, actual secrets, or live API tokens to version control. Only commit `.env.example` template files.
