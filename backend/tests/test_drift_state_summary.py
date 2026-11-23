from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.ot.scenario_injector import scenario_injector


def teardown_function():
    scenario_injector.clear_all_scenarios()


def test_parameterized_drift_summary_uses_magnitude_field():
    scenario_injector.inject_drift(rtu_id=3, mode="ramp", target="Q", duration_ticks=4, magnitude=0.1)
    assert scenario_injector.get_active_scenarios()["sensor_drifts"] == {3: 0.1}
