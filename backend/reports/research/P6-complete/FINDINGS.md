# P6 findings

All reported values below are read from the machine-generated P6 result files; no metric was hand-entered.

## Supported

- Fresh run inputs: 25 CSV files from train seeds 100–119 and validation seeds 200–204.
- Generated row counts: train=1000, validation=250.
- Candidate configuration frozen in `backend\experiments\P6-complete\selected_config.json`: model `tree`, policy `attack_active`, arm `base28_staleness`, threshold `1.0`.
- Validation-selected candidate latency: 0.0031666399911046026 ms per verdict; budget: 10.0 ms.
- Validation calibration ECE: 3.400058012914542e-18.
- Best validation row from grouped-CV table: feature arm `base28_staleness`, model `tree`, policy `attack_active`, episode recall `1.0`, FPR `0.0`.
- Selected validation precision/recall/F1: 1.0/0.5555555555555556/0.7142857142857143; ROC-AUC/PR-AUC: 0.5610880590133703/0.5715555555555556.
- The nine disputed features were included only as an isolated experimental arm when `full37` or `full37_staleness` was evaluated. They were not added to the production model or production artefacts.

## Not supported

- No final held-out evaluation was performed in P6, so no production improvement or generalization claim is supported.
- Results do not establish that the nine disputed features are safe for production; their provenance and leakage status remain governed by the P2 audit.
- A validation-selected threshold is not an operational approval and is not a production threshold.
- P2 leak-impact rows read from `backend\reports\research\P2\leak_impact.csv`: 2. Values were not retyped; the source remains the authority.

## Unresolved

- The generated corpus size is determined by the recorded CLI tick count and is intentionally not substituted with historical CSVs.
- The validation calibration result is descriptive because calibration and threshold selection use the same validation split under the preregistered P6 constraint.
- Full backend suite status: 1 failed, 383 passed, 521 warnings in 119.39s (0:01:59)
- A final evaluation requires the sole authorized final-evaluation reader and the P5 test-access log; it was not run by this task.

## Evidence paths

- Experiment: `backend\experiments\P6-complete`
- Manifest: `backend\experiments\P6-complete\run_manifest.json`
- Selection: `backend\experiments\P6-complete\selected_config.json`
- Grouped CV: `backend\experiments\P6-complete\grouped_cv_validation_results.csv`
