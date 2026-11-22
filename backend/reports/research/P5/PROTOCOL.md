# P5 Evaluation Protocol

Status: pre-registered before any final evaluation.

## Units and labels

The primary units are RTU-tick readings, evidence-visible readings, system ticks, and labelled scenario episodes. A system tick is alarmed when any RTU is alarmed. An episode is detected when the first alert occurs in `[onset_tick, end_tick + g]`, where `g` is fixed before evaluation. Delay is the first-alert tick minus onset tick.

The evaluator preserves `run_id`, `tick`, `rtu_id`, `episode_id`, `scenario_type`, `attack_active`, and `evidence_visible`. It does not infer labels from scores, filenames, or feature values.

## Alert-event definition

Consecutive alarmed system ticks separated by at most `gap` ticks are merged into one alert event. An event is true when it overlaps a labelled scenario interval extended by `tail` ticks; otherwise it is a false alarm. Results report sensitivity to the configured gap and tail.

False alarms per hour are computed from clean runs only. Each clean run supplies an explicit duration in hours. Exact Poisson intervals and a run-level bootstrap are reported; correlated readings are not treated as independent observations.

## Uncertainty

The default interval is a two-level cluster bootstrap: resample runs with replacement, then episodes within each selected run with replacement. The default number of replicates is `B=10000`; tests may use a smaller explicit `B` for speed. Percentile intervals use the 2.5th and 97.5th percentiles. Reading-level Wilson intervals, if emitted for continuity, are labelled lower bounds on uncertainty and are not primary intervals.

## Comparisons

Primary paired comparisons are per-episode detection differences and AUC differences. At most six pre-registered comparisons are allowed. Holm correction is applied to the resulting p-values.

## Threshold selection

Threshold `tau` is selected using validation runs only. For each false-alarm budget in `{1, 5, 20}` alert events/hour on validation clean runs, choose the threshold maximizing episode recall subject to that budget. Ties choose the higher threshold. The final evaluator reads test data only after threshold selection and records that access in `backend/reports/research/test_access_log.jsonl`.

## Reproducibility and lock

Every run writes `run_manifest.json` containing git SHA, Python/package versions, CPU, CLI arguments, seeds, timestamps, and SHA-256 values for every input and output dataset. No training, tuning, or selection script may read a path whose filename matches `*test*`; only `scripts/eval_final.py` may do so.
