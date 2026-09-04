# GridSentinel — Phase 3: ML Fusion Classifier

GridSentinel is a physics-aware cyber-physical anomaly detection platform designed for Indian power distribution SCADA networks (11kV/33kV).

Phase 3 adds a trained **Random Forest Fusion Classifier** that fuses both detection channels from Phases 1 & 2 into a single, real-time verdict for every monitored RTU:

| Output Class | Sub-Types | Detection Channel |
|:---|:---|:---|
| **Normal** | `normal` | Both channels agree: no anomaly |
| **Natural Fault** | `physical_fault` | PCD: physics residuals elevated, no rogue writes |
| **Cyber Intrusion** | `data_injection` | PCD: falsified measurement flagged by LNR |
| **Cyber Intrusion** | `command_injection` | NBD: unauthorized Modbus FC06/FC16 write seen |
| **Cyber Intrusion** | `replay` | NBD: frozen/replayed timestamps detected |

---

## 1. Architecture Overview (Phase 3 Additions)

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
┌─────────────────────────┐  Decoded   ┌───────────────────────────┐
│  Modbus Traffic Logger  │◄───────────┤    SCADA Master Client    │
│  (Rolling Event Buffer) │            └─────────────┬─────────────┘
└──────────┬──────────────┘                          │ Telemetry Feed
           │ NBD Signals                              ▼
           │                          ┌───────────────────────────┐
           │                          │   WLS State Estimation    │
           │                          │  + Bad-Data Detector      │
           │                          └─────────────┬─────────────┘
           │                                        │ PCD Signals
           ▼                                        ▼
           ┌────────────────────────────────────────┐
           │    Feature Engineering (28 features)   │
           │  NBD (10) + PCD (18) per target RTU    │
           └──────────────────┬─────────────────────┘
                              │
                              ▼
           ┌──────────────────────────────────────────┐
           │  Stage 1: Primary 3-Way Triage RF Model  │
           │  Normal | Natural Fault | Cyber Intrusion│
           └──────────────────┬───────────────────────┘
                              │ If Cyber Intrusion:
                              ▼
           ┌──────────────────────────────────────────┐
           │  Stage 2: Forensic Subtyping RF Model    │
           │  data_injection | command_injection |    │
           │  replay                                  │
           └──────────────────┬───────────────────────┘
                              │
                              ▼
           ┌──────────────────────────────────────────┐
           │  POST /classifier/verdict                │
           │  WebSocket /ws/live (ml_verdicts field)  │
           └──────────────────────────────────────────┘
```

---

## 2. Feature Schema (28 Features)

### Network-Behavioral Detection (NBD) — 10 Features
| Feature | Description |
|:---|:---|
| `nbd_unexpected_write_count` | Unauthorized write transactions (FC06/FC16) in window |
| `nbd_mean_response_time_ms` | Mean Modbus round-trip latency |
| `nbd_std_response_time_ms` | Latency standard deviation |
| `nbd_distinct_sources_count` | Number of unique source IPs communicating with RTU |
| `nbd_fc3_read_count` | FC03 (Read Holding Registers) count |
| `nbd_fc6_write_count` | FC06 (Write Single Register) count |
| `nbd_fc16_write_count` | FC16 (Write Multiple Registers) count |
| `nbd_error_count` | Failed/timeout Modbus transactions |
| `nbd_traffic_volume` | Total transactions to RTU in window |
| `nbd_modbus_anomaly_rate` | Unexpected-write, anomalous-function-code, and error rate |

### Physics-Consistency Detection (PCD) — 18 Features
| Feature | Description |
|:---|:---|
| `pcd_max_lnr` | Global Largest Normalized Residual across all measurements |
| `pcd_is_target_rtu_max_lnr` | 1.0 if target RTU owns the max system residual |
| `pcd_chi2_statistic` | Global Chi-square test statistic |
| `pcd_chi2_ratio` | χ² / χ²_threshold (>1.0 = hypothesis rejected) |
| `pcd_chi2_failed` | 1.0 if global χ² test failed |
| `pcd_target_rtu_v_residual` | Normalized residual of target RTU voltage measurement |
| `pcd_target_rtu_p_residual` | Normalized residual of target RTU active power measurement |
| `pcd_target_rtu_is_flagged` | 1.0 if target RTU measurement exceeds 3.0σ threshold |
| `pcd_global_bad_data_flag` | 1.0 if global bad data detector triggered |
| `pcd_voltage_pu_reported` | Reported voltage magnitude in per-unit |
| `pcd_voltage_dev_nominal` | Absolute deviation from nominal (\|V - 1.0\|) |
| `pcd_p_mw_reported` | Reported active power in MW |
| `pcd_status_code` | RTU hardware status (1=OK, 2=WARN, 3=TRIP) |
| `pcd_physics_network_disagreement_index` | Normalized reported-power disagreement scaled by residual severity |
| `pcd_temporal_dv_dt_3tick` | Three-tick voltage rate of change |
| `pcd_temporal_dp_dt_3tick` | Three-tick active-power rate of change |
| `pcd_temporal_dq_dt_3tick` | Three-tick reactive-power rate of change |
| `pcd_cross_rtu_voltage_divergence` | Target voltage divergence from electrical neighbors |

---

## 3. Dataset Generation

> Datasets are generated from the live simulation loop.

```powershell
cd gridsentinel/backend

# Training set (seed 42, 7,500 rows)
.venv\Scripts\python -m app.ml.dataset_generator `
    --seed 42 `
    --rows 7500 `
    --out data/generated/train_dataset_seed42.csv

# Test set (seed 1337, 3,500 rows — held out, never used in training)
.venv\Scripts\python -m app.ml.dataset_generator `
    --seed 1337 `
    --rows 3500 `
    --out data/generated/test_dataset_seed1337.csv
```

**Class distribution (training set):**
```
Normal:           5916 (78.9%)
Natural Fault:    1140 (15.2%)
Cyber Intrusion:   444  (5.9%)
```

---

## 4. Model Training

```powershell
.venv\Scripts\python -m app.ml.train_classifier `
    --train data/generated/train_dataset_seed42.csv `
    --test  data/generated/test_dataset_seed1337.csv `
    --out   models/fusion_classifier.joblib `
    --report reports
```

### Evaluation Results (Held-Out Test Set — Seed 1337)

| Metric | Value |
|:---|:---|
| **Overall Accuracy** | **82.09%** |
| **Cyber Intrusion FPR** | **2.44%** (79 / 3,236 non-cyber ticks) |
| Normal F1 | 88.57% |
| Natural Fault F1 | 71.96% |
| Cyber Intrusion F1 | 33.09% |
| Cyber Subtype Accuracy | 57.95% |

> **Note on Cyber Intrusion F1 (33%):** The low recall reflects the severe class imbalance
> (5.9% Cyber vs. 79% Normal). The FPR of 2.44% is the more operationally meaningful number
> — it means the system produces a false alarm roughly once every 40 ticks.

### Model Artifacts
| Path | Contents |
|:---|:---|
| `models/fusion_classifier.joblib` | Bundle: Stage-1 RF + Stage-2 RF + feature schema |
| `reports/confusion_matrix.png` | Confusion matrix on held-out test set |
| `reports/metrics.json` | Machine-readable metric summary |

---

## 5. Quickstart & Server Execution

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
Interactive Swagger API docs: `http://127.0.0.1:8000/docs`

For production, run the container command without `--reload` and with one
Uvicorn worker. CORS is intentionally defined in `app/main.py`: the exact
production origin is allowed, and Vercel Preview deployments are matched by
the project-scoped deployment-hash regex. No wildcard origins or credentials
are enabled.

### Running All Automated Tests
```powershell
python -m pytest tests/ -v
```
*(126 tests across Phases 1, 2 & 3.)*

---

## 6. Phase 3 Classifier API Reference

### `POST /classifier/verdict`
Run the ML Fusion Classifier. With **no request body**, evaluates the live simulation state. Optionally POST a snapshot:

```bash
# Evaluate current live state
curl -X POST http://127.0.0.1:8000/classifier/verdict

# Evaluate an offline snapshot
curl -X POST http://127.0.0.1:8000/classifier/verdict \
  -H "Content-Type: application/json" \
  -d '{
    "traffic_window": [...],
    "state_estimation_result": {...},
    "polled_telemetry": {"1": {...}, "2": {...}}
  }'
```

**Response:**
```json
{
  "tick_timestamp": "2025-01-01T12:00:00+00:00",
  "model_loaded": true,
  "overall_status": "ANOMALY_DETECTED",
  "evaluation_latency_ms": 2.4,
  "rtu_verdicts": [
    {
      "rtu_id": 2,
      "verdict": "Cyber Intrusion",
      "subtype": "data_injection",
      "confidence": 0.78,
      "probabilities": {
        "Normal": 0.08,
        "Natural Fault": 0.14,
        "Cyber Intrusion": 0.78
      },
      "model_status": "loaded"
    }
  ]
}
```

### `POST /classifier/reload`
Hot-reload the trained model from disk (use after retraining without restarting):
```bash
curl -X POST http://127.0.0.1:8000/classifier/reload
```

### `GET /classifier/status`
Return model status, class labels, and count of cached RTU verdicts:
```bash
curl http://127.0.0.1:8000/classifier/status
```

---

## 7. WebSocket `/ws/live` — Phase 3 Addition

The live WebSocket payload now includes `ml_verdicts` on every tick:

```json
{
  "tick": 42,
  "sim_time": "18:30:00",
  ...
  "ml_verdicts": {
    "1": {"verdict": "Normal", "subtype": "normal", "confidence": 0.94, ...},
    "2": {"verdict": "Cyber Intrusion", "subtype": "data_injection", "confidence": 0.78, ...},
    "3": {"verdict": "Normal", "subtype": "normal", "confidence": 0.91, ...},
    "4": {"verdict": "Normal", "subtype": "normal", "confidence": 0.89, ...},
    "5": {"verdict": "Normal", "subtype": "normal", "confidence": 0.96, ...}
  }
}
```

---

## 8. Scenario Guide (Phases 1 & 2 Unchanged)

### Start Simulation
```bash
curl -X POST http://127.0.0.1:8000/ot/start
```

### Attack 1: Silent Data Injection (FDI)
```bash
curl -X POST http://127.0.0.1:8000/ot/attack/data-injection \
  -H "Content-Type: application/json" \
  -d '{"rtu_id": 2, "voltage_pu": 1.150, "duration_ticks": 20}'

# Then check verdict:
curl -X POST http://127.0.0.1:8000/classifier/verdict
```

### Attack 2: Command Injection
```bash
curl -X POST http://127.0.0.1:8000/ot/attack/command-injection \
  -H "Content-Type: application/json" \
  -d '{"rtu_id": 3, "register_address": 0, "value": 12000}'
```

### Attack 3: Telemetry Replay
```bash
curl -X POST http://127.0.0.1:8000/ot/attack/replay \
  -H "Content-Type: application/json" \
  -d '{"rtu_id": 4, "duration_ticks": 15}'
```

### Fault 1: Physical Line Outage
```bash
curl -X POST http://127.0.0.1:8000/ot/fault/line-trip \
  -H "Content-Type: application/json" \
  -d '{"line_index": 0}'
```

### Fault 2: Short-Circuit Stub
```bash
curl -X POST http://127.0.0.1:8000/ot/fault/short-circuit \
  -H "Content-Type: application/json" \
  -d '{"bus_index": 4, "fault_load_mw": 2.5, "fault_load_mvar": 1.5, "duration_ticks": 3}'
```

### Reset Normal Operation
```bash
curl -X POST http://127.0.0.1:8000/ot/reset
```

---

## 9. Modbus Register Map & RTU Deployment

| Register | Name | Type | Scale | Unit | Description |
|:---|:---|:---|:---|:---|:---|
| **0** | `VOLTAGE_PU` | uint16 | ×10,000 | pu | Bus voltage magnitude |
| **1** | `ACTIVE_POWER_KW` | int16 | ×1 kW | kW | Active power (1 MW = 1000 kW) |
| **2** | `REACTIVE_POWER_KVAR` | int16 | ×1 kVAR | kVAR | Reactive power |
| **3** | `STATUS_FLAG` | uint16 | ×1 | code | 1=OK, 2=WARN, 3=TRIP |

**RTU Port Allocation:**
- **RTU 1 (Port 5021):** Substation-11kV (Bus 1) & Transformer LV Injection
- **RTU 2 (Port 5022):** Bus-1-FeederA (Bus 2) & Line 0 Flow
- **RTU 3 (Port 5023):** Bus-2-FeederB (Bus 3) & Line 1 Flow
- **RTU 4 (Port 5024):** Bus-3-FeederC (Bus 4) & Line 2 Flow
- **RTU 5 (Port 5025):** Bus-4-FeederA2 (Bus 5) & Line 3 Flow

---

## 10. External Benchmark: MSU/ORNL ICS Dataset

GridSentinel includes `app/ml/msu_ornl_loader.py` for coarse feature alignment against the [Mississippi State University & ORNL Power System Attack Dataset](https://www.ece.msstate.edu/~donohoe/documentation_powersystem.zip).

The MSU/ORNL dataset captures Modbus TCP traffic from a real ICS testbed under 37 attack scenarios. It can be used as a coarse sanity check (not a direct GridSentinel benchmark, since its physics residuals and feeder topology differ from GridSentinel's Indian 11kV model).

```powershell
# Download dataset manually from:
# https://www.ece.msstate.edu/~donohoe/documentation_powersystem.zip
# Then:
.venv\Scripts\python -c "from app.ml.msu_ornl_loader import load_msu_ornl_dataset; print(load_msu_ornl_dataset('path/to/dataset.csv'))"
```
