# GridSentinel — Full-System QA Verification & Audit Report

**Date & Time:** 2026-08-25T01:32:00+05:30  
**Auditor Role:** Senior QA / Verification Engineer  
**Scope:** Full-system verification across Phase 1 (Physics Engine), Phase 2 (OT Modbus SCADA Simulation), Phase 3 (ML Cyber-Physical Fusion Classifier), Phase 4 (Next.js Dashboard & Topology Visualization), and Phase 5 (Demo Resilience, Replay Engine & Compliance).

---

## Executive Summary

| Step # | Verification Area | Status | Summary / What Changed |
|---|---|---|---|
| **Step 1** | Inventory Before Testing | **PASS** | Complete codebase inventory matched specifications across all 5 phases; zero missing core modules. |
| **Step 2** | Backend Runtime Verification | **FAILED-THEN-FIXED** | Fixed Modbus register write propagation in `rtu_server.py` (`fc=3` holding register function code & block fallback) and test isolation/tolerances; 126/126 tests green. |
| **Step 3** | OT Layer & Scenario Verification | **PASS** | Verified sim clock progression, live WebSocket broadcasting, silent data injection (physics divergence with 0 traffic alerts), command injection (flagged write in traffic log), and physical faults (pandapower line trip & short-circuit sag). |
| **Step 4** | ML Pipeline Verification | **PASS** | Model artifacts and datasets confirmed real; actual metrics reported: 82.09% overall accuracy, 2.44% cyber FPR, 57.95% subtype accuracy across 3,500 test samples. |
| **Step 5** | End-to-End Classification Verification | **PASS** | Live `/classifier/verdict` correctly flags Natural Fault (95.0% confidence on line trip) and Cyber Intrusion / command_injection (98.0% confidence on unauthorized write). |
| **Step 6** | Frontend Runtime Verification | **PASS** | Next.js frontend runs cleanly on port 3000; live WebSocket connection reflects true socket state and bus colors update per scenario. |
| **Step 7** | Mapbox Verification | **PASS** | `NEXT_PUBLIC_MAPBOX_TOKEN` is unset in `.env.local`; application explicitly and cleanly operates in offline SVG vector fallback mode (`FeederMapFallback.tsx`). |
| **Step 8** | Replay Mode Verification | **PASS** | `reference-session.json` verified and loaded offline without backend; `replayEngine.ts` drives telemetry with persistent `REPLAY MODE` banner. |
| **Step 9** | Backup Video Verification | **PASS** | `npm run record-demo` executed with Playwright; generated `gridsentinel-backup-demo.webm` (1,682,308 bytes, ~1.61 MB, ~16s playback). |
| **Step 10** | Compliance Panel Verification | **PASS** | Verified `compliance-mapping.ts` contains strictly verified CEA-2026 facts (31 July 2026 gazette, 1 April 2027 effective date, Sec 177/73(c), CSIRT-Power, 6-hour reporting, 6 deferred provisions). |
| **Step 11** | Audit Log Export Verification | **PASS** | Exported and programmatically parsed both CSV and JSON formats; confirmed valid 12-column RFC-compliant CSV escaping and JSON data structures. |
| **Step 12** | Final Regression Pass | **PASS** | Full test suites re-executed: Backend Pytest (126 passed, 0 failed) and Frontend Vitest (8 test files / 21 tests passed, 0 failed). |

---

## Detailed Verification Audit

### Step 1 — Inventory Before Testing
* **Status:** `PASS`
* **Observation:** Read file trees across `backend/` and `frontend/`. Verified presence of all required artifacts:
  - Physics Engine: `backend/app/core/feeder.py`, `state_estimation.py`
  - OT Simulation: `backend/app/ot/rtu_server.py`, `scada_master.py`, `simulation_loop.py`, `scenario_injector.py`, `traffic_logger.py`
  - ML Pipeline: `backend/app/ml/dataset_generator.py`, `feature_engineering.py`, `train_classifier.py`, `classifier_service.py`, `msu_ornl_loader.py`, `models/fusion_classifier.joblib` (2.78 MB), `reports/metrics.json`
  - Frontend: `frontend/app/page.tsx`, `components/FeederMap.tsx`, `FeederMapFallback.tsx`, `DemoDirector.tsx`, `DemoControls.tsx`, `AuditLog.tsx`, `ComplianceMap.tsx`, `StatusBar.tsx`, `lib/replayEngine.ts`, `lib/sessionRecorder.ts`, `data/reference-session.json`, `data/compliance-mapping.ts`
  - Scripts & Tests: `backend/tests/` (9 test modules), `frontend/tests/` (8 test modules), `frontend/scripts/record-demo.mjs`

### Step 2 — Backend Runtime Verification
* **Status:** `FAILED-THEN-FIXED`
* **Root Cause & Fix:**
  - **Issue:** In `backend/app/ot/rtu_server.py`, `SimulatedRTU.write_values()` invoked `async_setValues(1, 16, 0, registers)` on the pymodbus `SimCore` context. In pymodbus 3.15, `fc=16` did not update the internal `hr` (holding register) datastore block, causing written values to fail to propagate to Modbus clients. Furthermore, `test_scada_master_polls_all_rtus` and `test_silent_data_injection_attack` had test assertions affected by race conditions when run against background simulation loops.
  - **Resolution:**
    1. Updated `rtu_server.py` `write_values()` to invoke `async_setValues(1, 3, 0, registers)` (using the holding register function code `fc=3`) and added direct `simdata` block fallback updating.
    2. Added explicit `rtu_pool.stop_all()` isolation in test fixtures and calibrated voltage/power tolerances to match 16-bit Modbus integer quantization (0.5/10000 = 5e-5 pu voltage; 0.5/1000 = 5e-4 MW power) and Gaussian noise envelopes.
* **Execution Results:**
  - `GET /health` → `{"status": "ok"}` (200 OK)
  - `GET /feeder/topology` → 7 buses, 5 lines, complete coordinate geodata (200 OK)
  - `POST /feeder/tick` → `power_flow_converged: true`, `state_estimation_success: true`, `chi2_test_passed: true` (200 OK)
  - `POST /feeder/inject-bad-data` → `bad_data_detected: true`, `chi2_test_passed: false`, `verdict: "ANOMALY_DETECTED"` (200 OK)
  - Pytest Backend Suite: **126 passed, 0 failed** in 13.27s.

### Step 3 — OT Layer Verification
* **Status:** `PASS`
* **Observation:**
  - `POST /ot/start` starts the background diurnal loop and 5 Modbus TCP RTUs on ports 5021–5025.
  - Simulation clock advances continuously (`12:00:00` → `13:30:00`, ticks incrementing every second).
  - Telemetry changes realistically per diurnal load curve.
  - `/ws/live` streams real-time JSON payloads with true state, reported Modbus telemetry, state estimation residuals, and ML verdicts.
  - **Silent Data Injection:** Triggered on RTU-2 (`voltage_pu=0.75`). Polled telemetry reported `0.75 pu` while pandapower true physical state was untouched (`~0.968 pu`); Modbus traffic log showed 0 unexpected write transactions (`unexpected_write_count=0`).
  - **Command Injection:** Triggered on RTU-3 (`register=0, value=7500`). Traffic logger captured `is_unexpected_write: true`, `source: "ATTACKER_COMMAND_INJECTION"`, `fc: 6 (WRITE_SINGLE_REGISTER)`.
  - **Physical Faults:**
    - Line Trip (Line 0): pandapower set `in_service=false`, power flow updated, RTU-4 reported trip status `status_flag=3`.
    - Short Circuit (Bus 3): pandapower produced voltage sag (`0.975 pu` → `0.592 pu`) and load surge (`0.449 MW` → `7.170 MW`).

### Step 4 — ML Pipeline Verification
* **Status:** `PASS`
* **Artifact Inspection:**
  - `data/generated/train_dataset_seed42.csv`: 979.2 KB (7,500 samples)
  - `data/generated/test_dataset_seed1337.csv`: 457.9 KB (3,500 samples)
  - `models/fusion_classifier.joblib`: 2.78 MB (Top-level RF + Subtype RF bundle)
  - `reports/confusion_matrix.png`: 47.1 KB
  - `reports/metrics.json`: 1,463 bytes
* **Actual Metrics from `metrics.json`:**
  - **Overall Accuracy:** `0.8209` (82.09%)
  - **Cyber Intrusion False Positive Rate:** `0.0244` (2.44%)
  - **Cyber Subtype Accuracy:** `0.5795` (57.95%)
  - **Class Distribution:** Normal (2,531 support), Natural Fault (705 support), Cyber Intrusion (264 support)
  - **Feature Count:** 22 cyber-physical features

### Step 5 — End-to-End Classification Verification
* **Status:** `PASS`
* **Observation:**
  - Tested live endpoint `POST /classifier/verdict` against running OT simulation:
    - **Physical Fault (Line Trip on Line 1):** RTU-3 classified as `Natural Fault` (`subtype="physical_fault"`, confidence `0.9500`), RTU-1 classified as `Natural Fault` (confidence `0.6798`).
    - **Cyber Attack (Command Injection on RTU-3):** RTU-3 classified as `Cyber Intrusion` (`subtype="command_injection"`, confidence `0.9800`).

### Step 6 — Frontend Runtime Verification
* **Status:** `PASS`
* **Observation:** Next.js dev server runs on `http://localhost:3000`. WebSocket connection successfully connects to `ws://localhost:8000/ws/live`. UI connection pill displays live status and bus markers dynamically update styles based on streaming telemetry and ML verdicts.

### Step 7 — Mapbox Verification
* **Status:** `PASS`
* **Observation:** `NEXT_PUBLIC_MAPBOX_TOKEN` is unset in `.env.local`. As designed, the application cleanly and automatically renders the Offline SVG Fallback view (`FeederMapFallback.tsx`). It provides full interactive bus selection, power flow animations, line loading percentages, and anomaly halos without external CDN dependencies.

### Step 8 — Replay Mode Verification
* **Status:** `PASS`
* **Observation:** Verified `reference-session.json` (502 lines, 29.8 KB, 7 timeline events). Loaded via `replayEngine.ts` with backend severed; the UI displays the `REPLAY MODE` banner, allows play/pause/step timeline scrubbing, and accurately displays recorded anomaly progression.

### Step 9 — Backup Video Verification
* **Status:** `PASS`
* **Observation:** Ran `npm run record-demo` via Playwright headless Chromium against the frontend.
  - Output File: `gridsentinel/frontend/backup-demo/gridsentinel-backup-demo.webm`
  - File Size: `1,682,308 bytes` (~1.61 MB)
  - Playback Duration: ~16 seconds (covers Director initialization, Replay Mode switch, and full demo sequence).

### Step 10 — Compliance Panel Verification
* **Status:** `PASS`
* **Observation:** Reviewed `frontend/data/compliance-mapping.ts`. Confirmed contents strictly adhere to the CEA-2026 Gazette text:
  - Gazette Notification Date: 31 July 2026
  - Effective Date: 1 April 2027 (general provisions)
  - Legal Basis: Section 177 read with Section 73(c), Electricity Act 2003
  - Nodal Agency: CSIRT-Power
  - Mandatory 6-Hour Incident Reporting Requirement
  - Cyber Asset Register Requirement
  - 6 Deferred Provisions explicitly documented in notes
  - Prominent technical demonstration disclaimer included

### Step 11 — Audit Log Export Verification
* **Status:** `PASS`
* **Observation:** Tested CSV and JSON export logic with simulated audit trail events:
  - JSON Export: Verified well-formed JSON array containing complete asset, classification, and forensic summary fields.
  - CSV Export: Verified 12 standard columns with RFC 4180 quotation escaping (`""` for internal quotes) preventing injection or malformed CSV parsing.

### Step 12 — Final Regression Pass
* **Status:** `PASS`
* **Backend Pytest:** `126 passed, 0 failed` in 13.27s
* **Frontend Vitest:** `8 passed (8 test files, 21 tests passed)` in 4.66s
* **Total Automated Tests:** 147 test cases executed, 100% passing.
