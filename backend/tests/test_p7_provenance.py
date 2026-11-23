from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.ml.dataset_generator import add_run_provenance


def test_run_provenance_is_derived_from_generator_invocation():
    row = add_run_provenance({}, run_id="run-500", total_ticks=3600, sim_seconds_per_tick=1.0, mode="clean", regime="clean")
    assert row == {"run_id": "run-500", "capture_id": "run-500", "duration_hours": 1.0, "is_clean_run": True}
