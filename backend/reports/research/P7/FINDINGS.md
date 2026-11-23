# P7 findings

## Supported

- The production artefact was loaded read-only to obtain its exact feature schema.
- The two supplied train/validation files were checked for schema, labels, and evaluation metadata.
- No held-out data was read and no model was trained or tuned by this run.

## Not supported

- Classical bad-data and NBD rule scores were not promoted to performance claims; their final thresholds require the P5 validation clean-run rule.
- Isolation Forest, logistic regression, depth-3 tree, NBD-only, PCD-only, and fusion comparisons were not selected or evaluated because the required grouped clean-run validation inputs are unavailable.
- ROC/PR curves and paired Holm-adjusted intervals were not produced because the authorized final reader has not run on a defensible held-out set.

## Unresolved

- run/episode/timing/clean-duration metadata required by P5 is missing
- no explicit clean runs are available for the P5 false-alarm budget
- The legacy split lacks capture/session grouping, so row-level results would not satisfy the P7 leakage requirement.
- A valid next input must provide run IDs, episode IDs, tick timing, explicit clean-run duration, and a separate held-out file consumed only by `scripts/eval_final.py`.

## Evidence

- Full backend suite command output: `reports\research\P7\full_pytest.txt`; summary: `6 errors in 25.48s`.
- Machine-readable audit: `experiments\P7\input_audit.json`
- P5 protocol: `backend/reports/research/P5/PROTOCOL.md`
