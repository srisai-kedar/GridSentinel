"""
feeder.py
---------
Builds a simplified Indian-style radial 11kV distribution feeder in pandapower.

Topology (radial, single source):
  EHV Grid (33kV) ──[33/11kV Tx]──► Bus 0 (11kV substation bus)
                                           │
                               ┌───────────┼───────────┐
                             Line 0      Line 1      Line 2
                               │           │           │
                            Bus 1        Bus 2        Bus 3
                          (Feeder A)   (Feeder B)   (Feeder C)
                               │           │
                             Line 3      Line 4
                               │           │
                            Bus 4        Bus 5
                          (Feeder A2)  (Feeder B2)

Loads: at Bus 1, Bus 2, Bus 3, Bus 4, Bus 5 — realistic small-town/semi-urban
distribution values (50-400 kW each, total ~1.2 MW @ 0.85 pf).

Assumptions:
- Conductor: typical ACSR "Dog" conductor used in Indian 11kV feeders
  r = 0.278 Ohm/km, x = 0.315 Ohm/km (overhead)
- Base voltage: 11kV (LV side), 33kV (HV side)
- Transformer: 33/11kV, 2 MVA, 6% impedance (typical ONAN distribution Tx)
- Coordinates: approximate layout positions for future map rendering (not GPS)
"""

import pandapower as pp
import numpy as np


# ---------------------------------------------------------------------------
# Conductor parameters -- ACSR "Dog" 11kV overhead line
# ---------------------------------------------------------------------------
_R_OHM_PER_KM = 0.278   # Ohm/km
_X_OHM_PER_KM = 0.315   # Ohm/km
_C_NF_PER_KM  = 8.0     # nF/km (typical for 11kV ACSR)
_MAX_I_KA     = 0.100    # 100 A thermal limit for "Dog" ACSR


def _add_line(
    net: pp.pandapowerNet,
    from_bus: int,
    to_bus: int,
    length_km: float,
    name: str,
) -> int:
    """Add a single ACSR overhead 11kV line and return its index."""
    return pp.create_line_from_parameters(
        net,
        from_bus=from_bus,
        to_bus=to_bus,
        length_km=length_km,
        r_ohm_per_km=_R_OHM_PER_KM,
        x_ohm_per_km=_X_OHM_PER_KM,
        c_nf_per_km=_C_NF_PER_KM,
        max_i_ka=_MAX_I_KA,
        name=name,
    )


def build_feeder() -> pp.pandapowerNet:
    """
    Construct and return the clean Indian-style radial distribution network.

    Returns
    -------
    net : pandapowerNet
        A fully parameterised pandapower network ready for power-flow /
        state-estimation runs.
    """
    net = pp.create_empty_network(name="GridSentinel-Feeder", f_hz=50.0, sn_mva=1.0)

    # ------------------------------------------------------------------
    # HV side: 33kV external grid bus
    # ------------------------------------------------------------------
    hv_bus = pp.create_bus(
        net, vn_kv=33.0, name="HV-Grid-33kV", geodata=(0.0, 2.0)
    )
    pp.create_ext_grid(net, bus=hv_bus, vm_pu=1.00, va_degree=0.0, name="33kV-Grid")

    # ------------------------------------------------------------------
    # 33/11kV transformer -- 2 MVA, Dyn11 vector group (standard in India)
    # LV side: 11kV substation bus
    # ------------------------------------------------------------------
    sub_bus = pp.create_bus(
        net, vn_kv=11.0, name="Substation-11kV", geodata=(0.0, 0.0)
    )
    pp.create_transformer_from_parameters(
        net,
        hv_bus=hv_bus,
        lv_bus=sub_bus,
        sn_mva=2.0,
        vn_hv_kv=33.0,
        vn_lv_kv=11.0,
        vkr_percent=0.5,   # Resistive component of short-circuit impedance
        vk_percent=6.0,    # Short-circuit impedance (%)
        pfe_kw=3.5,        # No-load losses (iron losses), typical for 2 MVA
        i0_percent=0.5,    # No-load current
        shift_degree=330,  # Dyn11 -> -30 deg shift (330 deg)
        name="33-11kV-Tx",
    )

    # ------------------------------------------------------------------
    # 11kV feeder buses
    # Layout coordinates (x, y) -- purely for diagram rendering, not GPS
    # ------------------------------------------------------------------
    bus1 = pp.create_bus(net, vn_kv=11.0, name="Bus-1-FeederA",  geodata=(-3.0, -2.0))
    bus2 = pp.create_bus(net, vn_kv=11.0, name="Bus-2-FeederB",  geodata=( 0.0, -2.0))
    bus3 = pp.create_bus(net, vn_kv=11.0, name="Bus-3-FeederC",  geodata=( 3.0, -2.0))
    bus4 = pp.create_bus(net, vn_kv=11.0, name="Bus-4-FeederA2", geodata=(-3.0, -4.0))
    bus5 = pp.create_bus(net, vn_kv=11.0, name="Bus-5-FeederB2", geodata=( 0.0, -4.0))

    # ------------------------------------------------------------------
    # 11kV feeder lines (radial topology)
    # ------------------------------------------------------------------
    _add_line(net, sub_bus, bus1, length_km=2.5, name="L0-Sub-A")
    _add_line(net, sub_bus, bus2, length_km=1.8, name="L1-Sub-B")
    _add_line(net, sub_bus, bus3, length_km=3.2, name="L2-Sub-C")
    _add_line(net, bus1,    bus4, length_km=2.0, name="L3-A-A2")
    _add_line(net, bus2,    bus5, length_km=1.5, name="L4-B-B2")

    # ------------------------------------------------------------------
    # Loads -- realistic semi-urban Indian distribution feeder
    # Total active power ~1.18 MW, pf ~0.85 lagging
    # ------------------------------------------------------------------
    pp.create_load(net, bus=bus1, p_mw=0.280, q_mvar=0.175, name="Load-A-Industrial")
    pp.create_load(net, bus=bus2, p_mw=0.320, q_mvar=0.200, name="Load-B-Residential")
    pp.create_load(net, bus=bus3, p_mw=0.180, q_mvar=0.110, name="Load-C-Agriculture")
    pp.create_load(net, bus=bus4, p_mw=0.220, q_mvar=0.138, name="Load-A2-Mixed")
    pp.create_load(net, bus=bus5, p_mw=0.180, q_mvar=0.113, name="Load-B2-Residential")

    return net


def run_power_flow(net: pp.pandapowerNet) -> dict:
    """
    Run Newton-Raphson power flow on the feeder.

    Returns
    -------
    dict with keys:
        converged       : bool
        bus_voltages    : list of {bus_index, name, vm_pu, va_degree}
        line_loadings   : list of {line_index, name, loading_percent, i_ka}
        total_load_mw   : float
        total_loss_mw   : float
    """
    try:
        pp.runpp(net, algorithm="nr", calculate_voltage_angles=True, numba=False)
        converged = bool(net.converged)
    except Exception as exc:
        return {"converged": False, "error": str(exc)}

    bus_voltages = []
    for idx, row in net.res_bus.iterrows():
        bus_voltages.append(
            {
                "bus_index": int(idx),
                "name": str(net.bus.at[idx, "name"]),
                "vm_pu": float(row["vm_pu"]) if not np.isnan(row["vm_pu"]) else None,
                "va_degree": float(row["va_degree"]) if not np.isnan(row["va_degree"]) else None,
            }
        )

    line_loadings = []
    for idx, row in net.res_line.iterrows():
        line_loadings.append(
            {
                "line_index": int(idx),
                "name": str(net.line.at[idx, "name"]),
                "loading_percent": float(row["loading_percent"]) if not np.isnan(row["loading_percent"]) else None,
                "i_ka": float(row["i_ka"]) if not np.isnan(row["i_ka"]) else None,
            }
        )

    total_load_mw = float(net.res_load["p_mw"].sum()) if not net.res_load.empty else 0.0
    total_loss_mw = float(net.res_line["pl_mw"].sum()) if not net.res_line.empty else 0.0

    return {
        "converged": converged,
        "bus_voltages": bus_voltages,
        "line_loadings": line_loadings,
        "total_load_mw": round(total_load_mw, 5),
        "total_loss_mw": round(total_loss_mw, 5),
    }
