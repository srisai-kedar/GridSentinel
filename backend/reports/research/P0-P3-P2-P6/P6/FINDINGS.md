# P6 findings

All reported values below are read from the machine-generated P6 result files; no metric was hand-entered.

## Supported

- Fresh run inputs: 25 CSV files from train seeds 100–119 and validation seeds 200–204.
- Generated row counts: train=1000, validation=250.
- Candidate configuration frozen in `experiments\P0-P3-P2-P6\P6\selected_config.json`: model `tree`, policy `attack_active`, arm `pcd_only`, threshold `1.0`.
- Validation-selected candidate latency: 0.004696319997310639 ms per verdict; budget: 10.0 ms.
- Validation calibration ECE: 3.400058012914542e-18.
- Best validation row from grouped-CV table: feature arm `pcd_only`, model `tree`, policy `attack_active`, episode recall `1.0`, FPR `0.0`.
- Selected validation precision/recall/F1: 1.0/0.5555555555555556/0.7142857142857143; ROC-AUC/PR-AUC: 0.7344398340248963/0.5740483091787439.
- The nine disputed features were included only as an isolated experimental arm when `full37` or `full37_staleness` was evaluated. They were not added to the production model or production artefacts.

## Not supported

- No final held-out evaluation was performed in P6, so no production improvement or generalization claim is supported.
- Results do not establish that the nine disputed features are safe for production; their provenance and leakage status remain governed by the P2 audit.
- A validation-selected threshold is not an operational approval and is not a production threshold.
- P2 leak-impact table unavailable at report time.

## Unresolved

- The generated corpus size is determined by the recorded CLI tick count and is intentionally not substituted with historical CSVs.
- The validation calibration result is descriptive because calibration and threshold selection use the same validation split under the preregistered P6 constraint.
- Full backend suite status: 1 failed, 399 passed, 521 warnings in 140.15s (0:02:20)
- A final evaluation requires the sole authorized final-evaluation reader and the P5 test-access log; it was not run by this task.

## Evidence paths

- Experiment: `experiments\P0-P3-P2-P6\P6`
- Manifest: `experiments\P0-P3-P2-P6\P6\run_manifest.json`
- Selection: `experiments\P0-P3-P2-P6\P6\selected_config.json`
- Grouped CV: `experiments\P0-P3-P2-P6\P6\grouped_cv_validation_results.csv`
