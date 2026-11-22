# P1 Findings

All numbers below are generated from `diagnostic_results.json` and the recorded pytest output.

## Supported

- The shared topology map covers RTUs `1, 2, 3, 4, 5` and explicitly identifies trusted pseudo-sensors.
- The same diagnostic stream contained `600` rows; the same pre-existing model bundle and threshold `0.69` were used for both mappings.
- Changed features (3):

| Feature | Rows changed | Maximum absolute difference |
|---|---:|---:|
| `pcd_resid_jump` | 595 | 30.8776 |
| `pcd_resid_persist` | 99 | 1.0 |
| `pcd_resid_rtu_share` | 284 | 0.000300000000000078 |

| Mapping | Overall cyber recall |
|---|---:|
| Legacy diagnostic mapping | 0.6363636363636364 |
| Corrected topology mapping | 0.6363636363636364 |

| Mapping | Attack subtype | Support | Recall |
|---|---|---:|---:|
| corrected_mapping | data_injection | 10 | 0.7 |
| corrected_mapping | replay | 1 | 0.0 |
| legacy_mapping | data_injection | 10 | 0.7 |
| legacy_mapping | replay | 1 | 0.0 |

## Not supported

- This diagnostic does not establish an independent improvement or a production-model promotion decision.
- The full backend suite is not fully green: `347` passed and `1` failed; the failure classification is recorded in the raw output.
- The diagnostic stream is not a held-out final test set and contains no cyber rows if the recorded support table is empty for a subtype.

## Unresolved

- The WLS estimator can distribute a +10σ P/Q perturbation across measurements; the tests verify exact ownership and corrected element-type matching, not that every global WLS maximum must be the injected P/Q row.
- The selected experimental bundle was serialized under a different scikit-learn patch version; loading emitted an `InconsistentVersionWarning`.
- Timing and socket behavior remain environment-dependent.

## Evidence

- Diagnostic JSON: `C:\Users\K Srisai Kedar\OneDrive\Documents\Projects\GridSentinel - SIH\gridsentinel\backend\experiments\P1\attribution_diagnostic_seed42_120\diagnostic_results.json` (SHA-256 `9282b46b46dfcdcee1dad8e449d9b70ec28736c5b919b9c237c3885514b8b587`)
- Diagnostic run manifest: `C:\Users\K Srisai Kedar\OneDrive\Documents\Projects\GridSentinel - SIH\gridsentinel\backend\experiments\P1\attribution_diagnostic_seed42_120\run_manifest.json`
- Test output: `C:\Users\K Srisai Kedar\OneDrive\Documents\Projects\GridSentinel - SIH\gridsentinel\backend\reports\research\P1\final_pytest.txt` (SHA-256 `ccf0eb91957f9758aaff5e96f957fdea7b9d9680398fb76f0ba0c4d479b7ac40`)
- No production model or frozen metrics file was modified.
