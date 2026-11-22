# P6 protocol

This protocol was written before the P6 generation and model runs. It uses the
P5 evaluation protocol as the parent protocol (`backend/reports/research/P5/PROTOCOL.md`).

## Data

Fresh data only: seeds 100–119 are training runs and seeds 200–204 are
validation runs. No historical generated CSV is an input. Each run is kept as
an independent group identified by `run_id`.

## Labels

Two policy arms are preregistered:

* `attack_active`: cyber rows are positive whenever `attack_active` is true.
* `evidence_visible`: cyber rows are positive only when `attack_active` and
  `evidence_visible` are true; attack-active rows without visible evidence are
  excluded from the training loss. Evaluation is reported under both label
  semantics.

## Feature arms

The fixed arms are `base28`, `full37`, `base28_staleness`, `full37_staleness`,
`nbd_only`, and `pcd_only`. Staleness features are computed only from prior
rows of the same RTU and run: the exact repeated V/P/Q register run length and
the variance of the most recent three V/P/Q values. No label or scenario field
is used to construct a feature.

## Models and selection

Logistic regression, a depth-4 decision tree, random forest, XGBoost, and
LightGBM are compared when installed. Grouped three-fold CV by `run_id` is
performed on training runs only. The final threshold is selected on validation
rows only: maximize attack-episode recall subject to validation normal-row FPR
at or below 1%; ties prefer the higher threshold. The selected feature/model
arm is the validation arm with the highest episode recall under that rule,
then lowest validation FPR, then lowest median latency.

Isotonic calibration is fitted on validation scores only and its validation
ECE is reported as a descriptive calibration result; it is not used to alter
the production model.

The 10 ms per-verdict latency limit is a gate. A candidate above it is not
eligible for the frozen experimental configuration.

No final held-out evaluation is performed in P6.
