# P8 findings

All measured/computed values below are rendered from `validation_alert_layers.json`; no metric is hand-entered.

## Supported

- Validation-only alert-layer analysis executed 41 candidates over the existing P7 validation runs.
- Threshold-only, k-of-n persistence with cooldown, per-RTU aggregation followed by system aggregation, and CUSUM candidates were evaluated without retraining.
- The existing P7 fused tree threshold was held at 0.981424148606811 for the fixed-threshold candidates.
- The available validation clean exposure was 0.0055555555555554 hours; exact Poisson intervals are included for every operating-curve row in `operating_curves.csv`.
- Budget 1.0 events/hour: selected `threshold_only` with parameters `{'aggregation': 'system_any', 'threshold': 0.981424148606811}`, episode recall=1.0, false alarms/hour=0.0, exact Poisson 95% interval=[0.0, 663.998301740527].
- Budget 5.0 events/hour: selected `threshold_only` with parameters `{'aggregation': 'system_any', 'threshold': 0.981424148606811}`, episode recall=1.0, false alarms/hour=0.0, exact Poisson 95% interval=[0.0, 663.998301740527].
- Budget 20.0 events/hour: selected `threshold_only` with parameters `{'aggregation': 'system_any', 'threshold': 0.981424148606811}`, episode recall=1.0, false alarms/hour=0.0, exact Poisson 95% interval=[0.0, 663.998301740527].

## Not supported

- P8 acceptance is not met: the required clean validation exposure is at least 24 simulated hours at the real clock rate, while this pilot uses only the short P7 validation clean runs.
- No clean held-out run was generated or read by the authorized final evaluator, so the required once-only clean held-out evaluation was not claimed.
- No benign-event runs were available in the current inputs; load steps, authorized writes, planned switching, and communication stalls were not evaluated.
- The pilot cannot establish that any alert layer meets the target of at most one false alarm per eight-hour shift. Its interval must be read from the short-exposure rows, not from the point estimate alone.
- Full backend suite: 389 passed, 1 failed, 521 warnings in 133.93s (0:02:13). The one allowed baseline failure is citation lint on the pre-existing untracked Data4Cyber report; no new failure was introduced.

## Unresolved

- The exact generation command still required is:
  `backend\.venv\Scripts\python.exe -m app.ml.dataset_generator --seed <seed> --ticks 86400 --mode clean --regime clean --sim-seconds-per-tick 1.0 --run-id P8-clean-validation-<seed> --port-base <unique-port> --out backend\experiments\P8\generated\clean_validation_seed<seed>.csv`
- Run enough distinct clean validation seeds to total at least 24 simulated hours, then generate a disjoint clean held-out set and consume it only through `scripts/eval_final.py`.
- The available simulator throughput and required wall-clock budget must be confirmed before launching the long run; no substitute proxy exposure was used.

## Evidence paths

- Machine results: `experiments\P8\validation_alert_layers.json`
- Operating curves: `reports\research\P8\operating_curves.csv`
- Run manifest: `reports\research\P8\run_manifest.json`
- Existing P7 validation inputs: `backend/experiments/P7-complete/generated/`
