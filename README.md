# GridSentinel — Phase 2: OT SCADA Simulation & Cyber-Physical Attack Injector

GridSentinel is a physics-aware cyber-physical anomaly detection platform designed for Indian power distribution SCADA networks (11kV/33kV).

Phase 2 builds an industrial OT simulation layer directly on top of Phase 1's `pandapower` feeder physics and WLS state estimation engine:
- **5 Simulated Modbus TCP RTUs** running asynchronously on ports `5021-5025`.
- **SCADA Master Polling Client** communicating over real Modbus TCP (FC 03) on continuous intervals.
- **Traffic Logger** recording all transactions to a rolling buffer with automated unexpected write flagging.
- **Diurnal Load Simulation** advancing a simulated clock with smooth day/night load curves.
- **Scenario Injector** supporting 3 cyber attack types and 2 physical fault types.
- **Real-Time WebSocket Feed** (`/ws/live`) streaming live electrical states, telemetry, and security events.

---

## 1. Architecture Overview

```
                          ┌───────────────────────────┐
                          │   pandapower Physics      │
                          │   (Ground Truth Model)    │
                          └─────────────┬─────────────┘
                                        │ Power Flow & Diurnal Scaling
                                        ▼
                          ┌───────────────────────────┐
                          │  5x Modbus TCP RTUs       │
                          │  Ports 5021 - 5025        │
                          └─────────────┬─────────────┘
                                        │ Modbus TCP Polling (FC 03)
                                        ▼
┌─────────────────────────┐  Decoded    ┌───────────────────────────┐
│  Modbus Traffic Logger  │◄────────────┤    SCADA Master Client    │
│  (Rolling Event Buffer) │             └─────────────┬─────────────┘
└─────────────────────────┘                           │ Telemetry Feed
                                                      ▼
                                        ┌───────────────────────────┐
                                        │   WLS State Estimation    │
                                        │  + Bad-Data Detector      │
                                        └─────────────┬─────────────┘
                                                      │
                                                      ▼
                                        ┌───────────────────────────┐
                                        │  WebSocket Stream /ws/live│
                                        │  (Frontend Live Dashboard)│
                                        └───────────────────────────┘
```

---

## 2. Modbus Register Map & RTU Deployment

Each RTU monitors a key distribution substation/feeder point and exposes standard 16-bit holding registers:

| Register Address | Name | Data Type | Scaling Factor | Unit / Range | Description |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **0** | `VOLTAGE_PU` | `uint16` | $\times 10,000$ | $0.0 - 6.5535\text{ pu}$ | Bus voltage magnitude |
| **1** | `ACTIVE_POWER_KW` | `int16` (signed) | $\times 1.0\text{ kW}$ | $\pm 32,767\text{ kW}$ | Active power flow ($1\text{ MW} = 1000\text{ kW}$) |
| **2** | `REACTIVE_POWER_KVAR`| `int16` (signed) | $\times 1.0\text{ kVAR}$| $\pm 32,767\text{ kVAR}$ | Reactive power flow ($1\text{ MVAR} = 1000\text{ kVAR}$) |
| **3** | `STATUS_FLAG` | `uint16` | $\times 1.0$ | `1=OK, 2=WARN, 3=TRIP` | Health / breaker status |

### RTU Port Allocation:
- **RTU 1 (Port 5021)**: Substation-11kV (Bus 1) & Transformer LV Injection
- **RTU 2 (Port 5022)**: Bus-1-FeederA (Bus 2) & Line 0 Flow
- **RTU 3 (Port 5023)**: Bus-2-FeederB (Bus 3) & Line 1 Flow
- **RTU 4 (Port 5024)**: Bus-3-FeederC (Bus 4) & Line 2 Flow
- **RTU 5 (Port 5025)**: Bus-4-FeederA2 (Bus 5) & Line 3 Flow

---

## 3. Quickstart & Server Execution

### Prerequisites & Installation
```powershell
cd gridsentinel/backend
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
```

### Running the API Server
```powershell
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```
Interactive Swagger API docs will be available at `http://127.0.0.1:8000/docs`.

### Running All Automated Tests
```powershell
python -m pytest tests/ -v
```
*(Runs all 89 unit & integration tests covering physics, state estimation, Modbus communications, attack scenarios, and WebSockets).*

---

## 4. Scenario Guide & Manual Verification via HTTP/cURL

### 4.1. Start and Stop the Simulation
**Start Simulation & RTU Servers:**
```bash
curl -X POST http://127.0.0.1:8000/ot/start
```

**Check Simulation Status & Diurnal Clock:**
```bash
curl http://127.0.0.1:8000/ot/status
```

**View Live Polled Modbus Telemetry:**
```bash
curl http://127.0.0.1:8000/ot/rtus
```

---

### 4.2. Cyber Attacks (Telemetry Manipulation)

#### Attack 1: Silent Data Injection (FDI)
Overrides the telemetry served by RTU 2 (e.g. fakes voltage to 1.15 pu). The real pandapower physical grid is **untouched**, and no anomalous network packets are sent (simulates compromised sensor/firmware).
```bash
curl -X POST http://127.0.0.1:8000/ot/attack/data-injection \
  -H "Content-Type: application/json" \
  -d '{"rtu_id": 2, "voltage_pu": 1.150, "duration_ticks": 20}'
```

#### Attack 2: Command Injection
Sends an unauthorized Modbus TCP write command (FC 06) from an external attacker IP. This is immediately flagged in the Modbus traffic log.
```bash
curl -X POST http://127.0.0.1:8000/ot/attack/command-injection \
  -H "Content-Type: application/json" \
  -d '{"rtu_id": 3, "register_address": 0, "value": 12000}'
```

**Inspect Traffic Log to See Flagged Anomalous Write:**
```bash
curl http://127.0.0.1:8000/ot/traffic?limit=5
```

#### Attack 3: Telemetry Replay
Freezes and re-serves historical telemetry packets on RTU 4.
```bash
curl -X POST http://127.0.0.1:8000/ot/attack/replay \
  -H "Content-Type: application/json" \
  -d '{"rtu_id": 4, "duration_ticks": 15}'
```

---

### 4.3. Physical Faults (Grid Disturbances)

#### Fault 1: Physical Line Outage (Line Trip)
Takes Line 0 out of service in pandapower. This physically changes power flows and de-energizes downstream buses, naturally propagating to telemetry.
```bash
curl -X POST http://127.0.0.1:8000/ot/fault/line-trip \
  -H "Content-Type: application/json" \
  -d '{"line_index": 0}'
```

#### Fault 2: Short-Circuit Fault Stub
Attaches a temporary fault impedance causing voltage sag across the feeder.
```bash
curl -X POST http://127.0.0.1:8000/ot/fault/short-circuit \
  -H "Content-Type: application/json" \
  -d '{"bus_index": 4, "fault_load_mw": 2.5, "fault_load_mvar": 1.5, "duration_ticks": 3}'
```

---

### 4.4. Resetting Normal Operation
Clears all cyber overrides, restores all lines to service, and clears the traffic log:
```bash
curl -X POST http://127.0.0.1:8000/ot/reset
```

---

## 5. Live WebSocket Feed (`/ws/live`)

Clients connecting to `ws://127.0.0.1:8000/ws/live` receive a real-time JSON broadcast on every simulation tick:
```json
{
  "tick": 42,
  "sim_time": "18:30:00",
  "diurnal_multiplier": 1.284,
  "power_flow_converged": true,
  "true_physical_state": {
    "bus_voltages": [...],
    "line_loadings": [...],
    "total_load_mw": 1.515,
    "total_loss_mw": 0.028
  },
  "polled_modbus_telemetry": {
    "1": {"voltage_pu": 0.972, "p_mw": -1.543, "q_mvar": -0.961, "status_flag": 1},
    "2": {"voltage_pu": 0.966, "p_mw": 0.642, "q_mvar": 0.401, "status_flag": 1}, ...
  },
  "state_estimation": {
    "success": true,
    "chi2_test_passed": true,
    "bad_data_detected": false,
    "flagged_measurements": []
  },
  "active_scenarios": {
    "summary": "NORMAL_OPERATION"
  },
  "recent_traffic_log": [...]
}
```
