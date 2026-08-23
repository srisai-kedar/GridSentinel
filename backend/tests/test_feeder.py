"""
test_feeder.py
--------------
Tests for the pandapower feeder model (build_feeder + run_power_flow).
"""

import pytest
import numpy as np
import pandapower as pp

from app.core.feeder import build_feeder, run_power_flow


@pytest.fixture(scope="module")
def net():
    """Build the feeder once for this test module."""
    return build_feeder()


@pytest.fixture(scope="module")
def net_with_pf(net):
    """Run power flow and return the solved network."""
    pp.runpp(net, algorithm="nr", calculate_voltage_angles=True, numba=False)
    return net


# ---------------------------------------------------------------------------
# Structural tests
# ---------------------------------------------------------------------------

class TestFeederStructure:
    def test_feeder_builds_without_error(self):
        """build_feeder() must not raise any exception."""
        n = build_feeder()
        assert n is not None

    def test_correct_bus_count(self, net):
        """Expect 7 buses total: 1 HV (33kV) + 1 substation + 5 feeder buses."""
        assert len(net.bus) == 7, f"Expected 7 buses, got {len(net.bus)}"

    def test_correct_line_count(self, net):
        """Expect 5 lines: 3 from substation, 2 downstream."""
        assert len(net.line) == 5, f"Expected 5 lines, got {len(net.line)}"

    def test_correct_load_count(self, net):
        """Expect 5 loads distributed across the feeder."""
        assert len(net.load) == 5, f"Expected 5 loads, got {len(net.load)}"

    def test_has_transformer(self, net):
        """Expect exactly 1 transformer (33/11kV)."""
        assert len(net.trafo) == 1

    def test_has_ext_grid(self, net):
        """Expect exactly 1 external grid (slack bus)."""
        assert len(net.ext_grid) == 1

    def test_all_11kv_buses_correct_nominal_voltage(self, net):
        """All LV-side buses should be 11 kV."""
        lv_buses = net.bus[net.bus.vn_kv == 11.0]
        assert len(lv_buses) == 6, f"Expected 6 x 11kV buses, got {len(lv_buses)}"

    def test_hv_bus_is_33kv(self, net):
        """HV bus should be 33 kV."""
        hv_buses = net.bus[net.bus.vn_kv == 33.0]
        assert len(hv_buses) == 1

    def test_total_load_reasonable(self, net):
        """Total active load should be between 1.0 and 1.5 MW."""
        total_p = net.load.p_mw.sum()
        assert 1.0 <= total_p <= 1.5, f"Total load {total_p} MW outside expected range"

    def test_geodata_present_for_all_buses(self, net):
        """All buses should have non-null geodata for rendering."""
        for idx, row in net.bus.iterrows():
            has_geo = ("geo" in row and row["geo"] is not None) or ("bus_geodata" in net and idx in net["bus_geodata"].index)
            assert has_geo, f"Bus {idx} has no geodata"

    def test_radial_topology(self, net):
        """Radial feeder: number of lines should equal number of buses - 2
        (transformer + 5 lines vs 7 buses; 5 = 7 - 2)."""
        assert len(net.line) == len(net.bus) - 2


# ---------------------------------------------------------------------------
# Power flow tests
# ---------------------------------------------------------------------------

class TestPowerFlow:
    def test_power_flow_converges(self, net):
        """run_power_flow() must report convergence on the clean feeder."""
        result = run_power_flow(net)
        assert result["converged"] is True, f"Power flow did not converge: {result.get('error')}"

    def test_no_nan_voltages(self, net_with_pf):
        """All bus voltage magnitudes in the PF result must be finite."""
        for vm in net_with_pf.res_bus.vm_pu:
            assert np.isfinite(vm), f"NaN/Inf voltage magnitude found: {vm}"

    def test_voltages_within_statutory_limits(self, net_with_pf):
        """11kV bus voltages should stay within ±10% (0.90–1.10 pu) per CEA standards."""
        lv_buses = net_with_pf.bus.index[net_with_pf.bus.vn_kv == 11.0]
        for bus_idx in lv_buses:
            vm = net_with_pf.res_bus.at[bus_idx, "vm_pu"]
            assert 0.90 <= vm <= 1.10, (
                f"Bus {bus_idx} voltage {vm:.4f} pu outside CEA statutory limits"
            )

    def test_no_overloaded_lines(self, net_with_pf):
        """All lines should be below thermal limit on base case loading."""
        for idx, row in net_with_pf.res_line.iterrows():
            loading = row["loading_percent"]
            assert loading < 100.0, (
                f"Line {idx} ({net_with_pf.line.at[idx, 'name']}) overloaded: "
                f"{loading:.1f}%"
            )

    def test_power_balance(self, net_with_pf):
        """Generation ≈ Load + Losses (within 1 kW tolerance)."""
        gen_mw  = float(net_with_pf.res_ext_grid.p_mw.sum())
        load_mw = float(net_with_pf.res_load.p_mw.sum())
        loss_mw = float(net_with_pf.res_line.pl_mw.sum()) + float(net_with_pf.res_trafo.pl_mw.sum())
        imbalance = abs(gen_mw - (load_mw + loss_mw))
        assert imbalance < 0.001, f"Power imbalance {imbalance*1000:.2f} kW exceeds 1 kW tolerance"

    def test_run_power_flow_dict_schema(self, net):
        """run_power_flow() return dict must have required keys."""
        result = run_power_flow(net)
        for key in ("converged", "bus_voltages", "line_loadings", "total_load_mw", "total_loss_mw"):
            assert key in result, f"Missing key '{key}' in run_power_flow() result"

    def test_bus_voltages_list_length(self, net):
        """bus_voltages list must have an entry per bus."""
        result = run_power_flow(net)
        assert len(result["bus_voltages"]) == len(net.bus)

    def test_line_loadings_list_length(self, net):
        """line_loadings list must have an entry per line."""
        result = run_power_flow(net)
        assert len(result["line_loadings"]) == len(net.line)
