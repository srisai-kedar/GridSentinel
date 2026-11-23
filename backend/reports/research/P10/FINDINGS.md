# P10 findings

This report is generated from `frontier_results.json` by the committed P10 script. It is a physics diagnostic, not a held-out attack-detection benchmark.

## Supported

- The installed pandapower estimator exposed a Jacobian with 18 measurement rows and 13 estimator state variables.
- The current topology map classifies 15 measurements as RTU-reported and the remainder as trusted pseudo-sensors.
- The generated frontier contains 200 measured method/condition rows across the prescribed magnitude sweep and both single-RTU and coordinated two-RTU directions.
- The exact-theory residual check contains 10 measured comparisons. Each value is read from the machine-generated JSON; no metric was hand-entered.
- Full backend suite result: 393 passed, 1 failed (raw output: C:\Users\K Srisai Kedar\OneDrive\Documents\Projects\GridSentinel - SIH\gridsentinel\backend\experiments\P10\full_suite.txt).

### Measured frontier values

| Geometry | Knowledge | Scope | Method | Detected / conditions |
|---|---|---|---|---:|
| single_rtu | exact_current_operating_point | all_measurements_theory | chi2 | 0 / 5 |
| single_rtu | exact_current_operating_point | all_measurements_theory | fusion | 0 / 5 |
| single_rtu | exact_current_operating_point | all_measurements_theory | lnr | 0 / 5 |
| single_rtu | exact_current_operating_point | all_measurements_theory | nbd | 0 / 5 |
| single_rtu | exact_current_operating_point | all_measurements_theory | pcd | 0 / 5 |
| single_rtu | exact_current_operating_point | rtu_reported_only | chi2 | 0 / 5 |
| single_rtu | exact_current_operating_point | rtu_reported_only | fusion | 0 / 5 |
| single_rtu | exact_current_operating_point | rtu_reported_only | lnr | 0 / 5 |
| single_rtu | exact_current_operating_point | rtu_reported_only | nbd | 0 / 5 |
| single_rtu | exact_current_operating_point | rtu_reported_only | pcd | 0 / 5 |
| single_rtu | nominal_topology | all_measurements_theory | chi2 | 0 / 5 |
| single_rtu | nominal_topology | all_measurements_theory | fusion | 0 / 5 |
| single_rtu | nominal_topology | all_measurements_theory | lnr | 0 / 5 |
| single_rtu | nominal_topology | all_measurements_theory | nbd | 0 / 5 |
| single_rtu | nominal_topology | all_measurements_theory | pcd | 0 / 5 |
| single_rtu | nominal_topology | rtu_reported_only | chi2 | 0 / 5 |
| single_rtu | nominal_topology | rtu_reported_only | fusion | 0 / 5 |
| single_rtu | nominal_topology | rtu_reported_only | lnr | 0 / 5 |
| single_rtu | nominal_topology | rtu_reported_only | nbd | 0 / 5 |
| single_rtu | nominal_topology | rtu_reported_only | pcd | 0 / 5 |
| two_rtu_coordinated | exact_current_operating_point | all_measurements_theory | chi2 | 0 / 5 |
| two_rtu_coordinated | exact_current_operating_point | all_measurements_theory | fusion | 0 / 5 |
| two_rtu_coordinated | exact_current_operating_point | all_measurements_theory | lnr | 0 / 5 |
| two_rtu_coordinated | exact_current_operating_point | all_measurements_theory | nbd | 0 / 5 |
| two_rtu_coordinated | exact_current_operating_point | all_measurements_theory | pcd | 0 / 5 |
| two_rtu_coordinated | exact_current_operating_point | rtu_reported_only | chi2 | 0 / 5 |
| two_rtu_coordinated | exact_current_operating_point | rtu_reported_only | fusion | 0 / 5 |
| two_rtu_coordinated | exact_current_operating_point | rtu_reported_only | lnr | 0 / 5 |
| two_rtu_coordinated | exact_current_operating_point | rtu_reported_only | nbd | 0 / 5 |
| two_rtu_coordinated | exact_current_operating_point | rtu_reported_only | pcd | 0 / 5 |
| two_rtu_coordinated | nominal_topology | all_measurements_theory | chi2 | 0 / 5 |
| two_rtu_coordinated | nominal_topology | all_measurements_theory | fusion | 0 / 5 |
| two_rtu_coordinated | nominal_topology | all_measurements_theory | lnr | 0 / 5 |
| two_rtu_coordinated | nominal_topology | all_measurements_theory | nbd | 0 / 5 |
| two_rtu_coordinated | nominal_topology | all_measurements_theory | pcd | 0 / 5 |
| two_rtu_coordinated | nominal_topology | rtu_reported_only | chi2 | 0 / 5 |
| two_rtu_coordinated | nominal_topology | rtu_reported_only | fusion | 0 / 5 |
| two_rtu_coordinated | nominal_topology | rtu_reported_only | lnr | 0 / 5 |
| two_rtu_coordinated | nominal_topology | rtu_reported_only | nbd | 0 / 5 |
| two_rtu_coordinated | nominal_topology | rtu_reported_only | pcd | 0 / 5 |

### Measured theory check

| Knowledge | Magnitude | Clean residual L2 | Attacked residual L2 | Absolute L2 difference |
|---|---:|---:|---:|---:|
| exact_current_operating_point | 1.0 | 2.6961426 | 2.6961426 | 0 |
| exact_current_operating_point | 2.0 | 2.6961426 | 2.6961426 | 0 |
| exact_current_operating_point | 3.0 | 2.6961426 | 2.6961426 | 0 |
| exact_current_operating_point | 5.0 | 2.6961426 | 2.6961426 | 0 |
| exact_current_operating_point | 10.0 | 2.6961426 | 2.6961844 | 0.0001 |
| nominal_topology | 1.0 | 2.6961426 | 2.6961844 | 0.0001 |
| nominal_topology | 2.0 | 2.6961426 | 2.69615 | 0.00014142136 |
| nominal_topology | 3.0 | 2.6961426 | 2.6961745 | 0.0002 |
| nominal_topology | 5.0 | 2.6961426 | 2.6961745 | 0.0002 |
| nominal_topology | 10.0 | 2.6961426 | 2.6961236 | 0.00034641016 |

- Full-measurement `a=Hc` is the only condition for which the linear WLS residual-invariance theory applies. The RTU-only restriction is reported separately because trusted pseudo-sensors are not attackable.

## Not supported

- These results do not establish production detection performance, generalisation, or a failure rate on real or generated attack episodes.
- No test-set file was read, and no training, tuning, or model selection was performed.
- The requested 13-RTU-measurement premise is not supported by the current source of truth: `topology_map.py` exposes 15. The script did not silently coerce the code to 13.
- NBD alarm rows are intentionally zero because an `a=Hc` measurement attack does not change the supplied traffic event list. This is not evidence that every network detector is blind to every coordinated attack.

## Unresolved

- The repository does not define an approved mapping from the requested 13 measurements to the current 15 RTU-reported measurements. P10 cannot claim acceptance for a 13-measurement frontier until that mapping is resolved.
- A production-relevant frontier needs the finalized P4 scenario library, independent runs, and the frozen P5 evaluation protocol; this fixed-feeder diagnostic is insufficient for those claims.
- The exact-versus-nominal distinction here uses the base-load Jacobian as the nominal reference against a 1.35 load-scaled point while keeping topology fixed. A true alternate-topology mismatch experiment requires an approved alternate topology source.

## Evidence paths

- Results: `C:\Users\K Srisai Kedar\OneDrive\Documents\Projects\GridSentinel - SIH\gridsentinel\backend\experiments\P10\frontier_results.json`
- Frontier CSV: `C:\Users\K Srisai Kedar\OneDrive\Documents\Projects\GridSentinel - SIH\gridsentinel\backend\reports\research\P10\frontier.csv`
- Frontier figure: `C:\Users\K Srisai Kedar\OneDrive\Documents\Projects\GridSentinel - SIH\gridsentinel\backend\reports\research\P10\frontier.png`
- Run manifest: `C:\Users\K Srisai Kedar\OneDrive\Documents\Projects\GridSentinel - SIH\gridsentinel\backend\experiments\P10\run_manifest.json`
- Source Jacobian implementation: `C:\Users\K Srisai Kedar\OneDrive\Documents\Projects\GridSentinel - SIH\gridsentinel\backend\.venv\Lib\site-packages\pandapower\estimation\algorithm\matrix_base.py`

## Reproduction

`backend/.venv/Scripts/python.exe backend/scripts/expo/p10_frontier.py --out-dir backend/experiments/P10 --report-dir backend/reports/research/P10 --seed 1010`
