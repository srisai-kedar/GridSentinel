# P7 protocol

P7 follows `backend/reports/research/P5/PROTOCOL.md`: grouped units, clean-run
false-alarm budgets, validation-only threshold selection, cluster bootstrap, and
final held-out access only through `scripts/eval_final.py`.

The task is fail-closed when run/episode grouping or clean-run duration metadata
is absent. In that case no learned baseline is selected and no performance
matrix is reported.
