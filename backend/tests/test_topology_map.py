from pathlib import Path

import pandapower as pp
import pytest

from app.core.feeder import build_feeder
from app.core.state_estimation import add_measurements, detect_bad_data
from app.core.topology_map import (
    RTU_IDS,
    TRUSTED_PSEUDO_SENSORS,
    bindings_for_rtu,
    measurement_matches_rtu,
    rtu_for_measurement,
)


@pytest.mark.parametrize("rtu_id", RTU_IDS)
def test_each_rtu_has_unique_bus_and_attackable_power_binding(rtu_id):
    bindings = bindings_for_rtu(rtu_id)
    assert any(binding.element_type == "bus" and binding.measurement_types == ("v",) for binding in bindings)
    assert any(binding.element_type in {"line", "trafo"} and set(binding.measurement_types) == {"p", "q"} for binding in bindings)
    assert all(rtu_for_measurement(binding.element_type, binding.element) == rtu_id for binding in bindings)


def _perturbed_result(rtu_id: int, measurement_type: str):
    net = build_feeder()
    pp.runpp(net, algorithm="nr", calculate_voltage_angles=True, numba=False)
    add_measurements(net)
    binding = next(binding for binding in bindings_for_rtu(rtu_id) if measurement_type in binding.measurement_types)
    rows = net.measurement[
        (net.measurement["element_type"] == binding.element_type)
        & (net.measurement["element"] == binding.element)
        & (net.measurement["measurement_type"] == measurement_type)
    ]
    assert len(rows) == 1
    index = rows.index[0]
    net.measurement.at[index, "value"] += 10.0 * float(net.measurement.at[index, "std_dev"])
    result = detect_bad_data(net)
    residual = next(item for item in result["all_residuals"] if item["measurement_index"] == index)
    return binding, residual


@pytest.mark.parametrize("rtu_id", RTU_IDS)
@pytest.mark.parametrize("measurement_type", ["v", "p", "q"])
def test_ten_sigma_perturbation_retains_expected_rtu_owner(rtu_id, measurement_type):
    """Run WLS after a fixed +10σ perturbation and verify owner attribution."""
    binding, residual = _perturbed_result(rtu_id, measurement_type)
    assert measurement_matches_rtu(residual["element_type"], residual["element"], rtu_id)
    assert rtu_for_measurement(residual["element_type"], residual["element"]) == rtu_id
    assert residual["normalised_residual"] >= 0.0


def test_element_type_is_part_of_max_residual_attribution():
    residuals = [
        {"element_type": "bus", "element": 1, "normalised_residual": 4.0},
        {"element_type": "line", "element": 0, "normalised_residual": 9.0},
    ]
    max_residual = max(residuals, key=lambda item: item["normalised_residual"])
    assert rtu_for_measurement(max_residual["element_type"], max_residual["element"]) == 2
    assert rtu_for_measurement(max_residual["element_type"], max_residual["element"]) != 1


def test_trusted_pseudo_sensors_are_not_attackable_rtu_measurements():
    assert len(TRUSTED_PSEUDO_SENSORS) == 2
    for binding in TRUSTED_PSEUDO_SENSORS:
        assert rtu_for_measurement(binding.element_type, binding.element) is None


def test_mapping_lint_has_no_legacy_index_arithmetic():
    root = Path(__file__).parents[1] / "app"
    source = "\n".join(path.read_text(encoding="utf-8") for path in root.rglob("*.py"))
    assert "rid - 1" not in source
    assert "dev_idx" not in source
