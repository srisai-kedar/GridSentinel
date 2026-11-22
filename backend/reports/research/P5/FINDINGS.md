# P5 Findings

## Supported

- Pre-registration protocol was committed before evaluation code execution; SHA-256: `143572cd4a232e14a90bb21cfc95f0208174cd93819731ae32c1fc44a782b8eb`.
- `eval/metrics.py` reports reading, evidence-visible, system-tick, episode, per-type recall, delay, alert-event, and clean-run false-alarm metrics from one in-memory call.
- `eval/bootstrap.py` implements two-level run/episode resampling and Holm adjustment.
- Focused synthetic suite: `6 passed`.

## Not supported

- No production model, candidate model, threshold, or test dataset was evaluated in this task.
- Synthetic coverage tests validate implementation behavior only; they are not detector-performance evidence.
- No final evaluation result is reported because no authorized P5 final-evaluation dataset was supplied or read.

## Unresolved

- Final evaluation still requires labelled validation/test runs with run duration, clean-run identity, scenario episode metadata, and model scores.
- The existing repository citation-lint baseline remains separate from P5 and is not modified.

## Test result

- Full backend suite: `1 failed, 371 passed, 522 warnings`.
