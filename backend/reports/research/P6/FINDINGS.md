# P6 findings

All reported values below are read from the machine-generated P6 result files; no metric was hand-entered.

## Supported

- Fresh run inputs: 25 CSV files from train seeds 100–119 and validation seeds 200–204.
- Generated row counts: train=1000, validation=250.
- Candidate configuration frozen in `experiments\P6\selected_config.json`: model `tree`, policy `attack_active`, arm `base28`, threshold `1.0`.
- Validation-selected candidate latency: 0.004097760003060102 ms per verdict; budget: 10.0 ms.
- Validation calibration ECE: 3.4139358007223563e-18.
- Best validation row from grouped-CV table: feature arm `base28`, model `tree`, policy `attack_active`, episode recall `1.0`, FPR `0.0`.
- The nine disputed features were included only as an isolated experimental arm when `full37` or `full37_staleness` was evaluated. They were not added to the production model or production artefacts.

## Not supported

- No final held-out evaluation was performed in P6, so no production improvement or generalization claim is supported.
- Results do not establish that the nine disputed features are safe for production; their provenance and leakage status remain governed by the P2 audit.
- A validation-selected threshold is not an operational approval and is not a production threshold.
- P2 leak-impact table unavailable at report time.

## Unresolved

- The generated corpus size is determined by the recorded CLI tick count and is intentionally not substituted with historical CSVs.
- The validation calibration result is descriptive because calibration and threshold selection use the same validation split under the preregistered P6 constraint.
- The simulator emitted runtime warnings and at least one `KeyError: drift_percent` during generation while still writing CSV outputs; the generated files therefore require repair and rerun before any final evaluation.
- Full backend suite status: !!!!!!!!!!!!!!!!!!! Interrupted: 6 errors during collection !!!!!!!!!!!!!!!!!!! 6 errors in 19.82s
- A final evaluation requires the sole authorized final-evaluation reader and the P5 test-access log; it was not run by this task.

## Evidence paths

- Experiment: `experiments\P6`
- Manifest: `experiments\P6\run_manifest.json`
- Selection: `experiments\P6\selected_config.json`
- Grouped CV: `experiments\P6\grouped_cv_validation_results.csv`
