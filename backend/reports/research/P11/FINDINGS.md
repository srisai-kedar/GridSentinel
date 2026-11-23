# P11 findings

All numeric values below are generated from `p11_results.json` by the committed P11 script. No held-out file was read.

## Supported

- The available feeder redundancy/observability sweep contains 5 measured configurations.
- Latency is measured as complete per-cycle wall time, including state estimation, feature extraction, and read-only production-model inference; five warmups are excluded.
- The production model was loaded read-only. No production artifact was written.
- Full backend suite result: 396 passed, 1 failed (raw output: C:\Users\K Srisai Kedar\OneDrive\Documents\Projects\GridSentinel - SIH\gridsentinel\backend\experiments\P11\full_suite.txt).

### Measured redundancy and latency

| Measurements | States | Ratio | Observable | p50 ms | p95 ms | p99 ms | Samples | Successful cycles |
|---:|---:|---:|:---:|---:|---:|---:|---:|---:|
| 18 | 13 | 1.38462 | True | 99.0358 | 116.512 | 118.311 | 20 | 20 |
| 16 | 0 | unavailable | False | 55.4169 | 57.5039 | 58.1408 | 20 | 0 |
| 15 | 0 | unavailable | False | 71.6677 | 79.7095 | 98.4462 | 20 | 0 |
| 14 | 0 | unavailable | False | 53.6449 | 70.6776 | 71.9117 | 20 | 0 |
| 13 | 0 | unavailable | False | 52.8815 | 58.9291 | 61.9123 | 20 | 0 |

## Not supported

- Cross-condition train-on-default/evaluate-on-OOD results were not produced: the expected 400–409 files are absent, and this task cannot read held-out paths outside `scripts/eval_final.py`.
- Cross-topology train-A/test-B and retrain-on-B results were not produced: no second feeder or approved Baran–Wu implementation is available.
- No cross-condition or cross-topology cluster-bootstrap intervals were computed because the required independent episode units do not exist in the available inputs.
- No claim of improved recall, false-alarm reduction, or generalisation is supported by the available-feeder timing/observability diagnostic.

## Unresolved

- Generate and provenance-manifest OOD runs 400–409 under the P3/P4 pipeline, with independent operating-condition metadata, then use the authorized final evaluator to read them once.
- Provide or implement a second feeder with a documented RTU placement/topology map and an independent scenario schedule before cross-topology evaluation.
- Reconcile the source comment's stated 1.5 redundancy with the measured state dimension and record the approved measurement-retention policy for each sweep level.

## Evidence paths

- Results: `C:\Users\K Srisai Kedar\OneDrive\Documents\Projects\GridSentinel - SIH\gridsentinel\backend\experiments\P11\p11_results.json`
- Run manifest: `C:\Users\K Srisai Kedar\OneDrive\Documents\Projects\GridSentinel - SIH\gridsentinel\backend\experiments\P11\run_manifest.json`
- Redundancy/latency CSV: `C:\Users\K Srisai Kedar\OneDrive\Documents\Projects\GridSentinel - SIH\gridsentinel\backend\reports\research\P11\redundancy_latency.csv`
- Cross-condition status: `C:\Users\K Srisai Kedar\OneDrive\Documents\Projects\GridSentinel - SIH\gridsentinel\backend\reports\research\P11\cross_condition.csv`
- Cross-topology status: `C:\Users\K Srisai Kedar\OneDrive\Documents\Projects\GridSentinel - SIH\gridsentinel\backend\reports\research\P11\cross_topology.csv`

## Reproduction

`backend/.venv/Scripts/python.exe backend/scripts/expo/p11_generalisation.py --out-dir backend/experiments/P11 --report-dir backend/reports/research/P11 --samples 20 --seed 1111`
