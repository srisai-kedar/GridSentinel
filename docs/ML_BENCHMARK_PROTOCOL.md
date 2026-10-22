# GridSentinel ML clean-data benchmark protocol

## Purpose

Retrain only after NBD features are derived from observed Modbus requests and master-measured polling outcomes. Simulator scenario flags, attack names, source labels, and ground-truth state must not be model inputs.

## Reproducible split

The workflow generates independent simulator runs: training seed 42 (1,500 ticks), threshold-tuning/model-selection seed 999 (700 ticks), and held-out test seed 1337 (700 ticks). Random Forest, LightGBM, and XGBoost are compared with the existing trainer. Candidate and threshold selection use validation data, not the held-out test set.

## Pre-registered promotion gate

A candidate model may be proposed as the replacement only if backend tests, frontend tests/build and the no-label-leak tests pass, and these held-out test checks pass:

- Feature schema is 3.0.0.
- Cyber recall improves by at least 3 percentage points over the historical 52.65% baseline.
- Cyber false-positive rate increases by no more than 0.2 percentage points over the historical 0.43% baseline.
- Single-row inference latency is below 50 ms.
- Shuffled-label leakage smoke test passes.

A candidate that fails stays a benchmark artifact only; it does not replace the tracked model. These are prototype promotion rules, not claims of production readiness.

## Reporting and limitations

Record the selected model, decision threshold, accuracy, cyber precision/recall/FNR/FPR/F1/F2, subtype accuracy, inference latency, confusion matrix, model and dataset SHA-256 hashes, feature schema/count, data split seeds and runtime. The dashboard serves benchmark results only when the report's feature schema matches the active schema.

All results are from synthetic pandapower and simulated Modbus TCP data. They do not establish performance on live utility telemetry or field hardware.
