# P2 Findings

## Supported

- Static provenance audit passed = `True`; violations = `0`.
- Blind re-extraction passed = `True`; differing features = `0`.
- Test-only leak canary detected the injected feature mismatch = `True`.
- Label shuffle used `7500` training rows and `3500` validation rows; accuracy `0.6857142857142857`, majority rate `0.6854285714285714`, absolute gap `0.00028571428571433355`.
- Matched generator diagnostic rows: leaky `600`, repaired `600`; each used a 70/30 tick split recorded by the script.
- Diagnostic command-injection recall: leaky `0.06666666666666667`, repaired `0.2`; precision: leaky `1.0`, repaired `1.0`.

## Not supported

- The matched generator comparison is diagnostic only: it is one seed, one short run, uses a time split rather than independent capture groups, and does not establish production improvement.
- The blind audit validates the extractor boundary over serialized traffic and telemetry; it does not prove that every estimator/PCD path is independently replayable from those two logs.

## Unresolved

- Generator timing is not bitwise reproducible: repeated same-seed runs can produce different timing-dependent samples and therefore different diagnostic metrics. This is recorded in the generated run manifests and is a P0 issue.
- The pre-PR16 scratch comparison does not isolate only the historical label leak; generator and runtime differences remain possible confounders.

## Test result

- Full backend suite: `354` passed, `1` failed, `522` warnings; source summary: `1 failed, 354 passed, 522 warnings`.
- The single failure is the pre-existing repository citation-lint baseline failure; no citation report or lint rule was changed by P2.
