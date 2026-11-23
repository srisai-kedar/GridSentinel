# P8 Findings

## Supported

- Validation-only alert analysis executed `41` candidates with budgets 1, 5, and 20 events/hour. Machine results remain in `backend\experiments\P8-completion\alert_validation\validation_alert_layers.json`.
- The benign pilot completed `4` runs and `2000` rows; its observed subtype counts are machine-generated in `completion_results.json`.

## Not supported

- The required 24 real-clock clean validation hours were not completed.
- No independent clean held-out dataset was evaluated through `scripts/eval_final.py`.
- The benign pilot observed zero requested benign-event subtypes, so no benign-event robustness claim is supported.
- The 0.125 false-alarm/hour target is not established; the existing short-exposure Poisson intervals remain too wide.

## Unresolved

- Human/runtime action: run `--ticks 86400 --sim-seconds-per-tick 1.0` with unique ports, then generate a disjoint held-out clean run and pass it once to `scripts/eval_final.py`.
- Generate targeted or sufficiently long benign-event runs until each requested benign subtype is observed, preserving manifests and hashes.
