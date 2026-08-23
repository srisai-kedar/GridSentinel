"""
schemas.py
----------
Pydantic v2 models for GridSentinel Phase 1 (Physics API) and Phase 2 (OT SCADA simulation).
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field, field_validator


# ---------------------------------------------------------------------------
# Phase 1 Sub-models & Responses
# ---------------------------------------------------------------------------

class BusVoltage(BaseModel):
    """Voltage state at a single bus from power flow."""
    bus_index: int
    name: str
    vm_pu: Optional[float] = Field(None, description="Voltage magnitude in per-unit")
    va_degree: Optional[float] = Field(None, description="Voltage angle in degrees")


class LineLoading(BaseModel):
    """Loading state of a single line from power flow."""
    line_index: int
    name: str
    loading_percent: Optional[float] = Field(None, description="Line loading as % of thermal limit")
    i_ka: Optional[float] = Field(None, description="Current in kA")


class BusTopology(BaseModel):
    """Bus descriptor for topology endpoint."""
    bus_index: int
    name: str
    vn_kv: float = Field(description="Nominal voltage in kV")
    x: float = Field(description="Layout x-coordinate for rendering")
    y: float = Field(description="Layout y-coordinate for rendering")
    in_service: bool


class LineTopology(BaseModel):
    """Line descriptor for topology endpoint."""
    line_index: int
    name: str
    from_bus: int
    to_bus: int
    length_km: float


class EstimatedVoltage(BaseModel):
    """WLS-estimated voltage at a single bus."""
    bus_index: int
    name: str
    vm_pu_est: Optional[float] = Field(None, description="WLS-estimated voltage magnitude in pu")
    va_degree_est: Optional[float] = Field(None, description="WLS-estimated voltage angle in degrees")


class FlaggedMeasurement(BaseModel):
    """A measurement identified as anomalous by the bad-data detector."""
    measurement_index: int
    name: str
    meas_type: str = Field(description="v | p | q")
    element_type: str = Field(description="bus | line | trafo")
    element: int
    value: float = Field(description="The (possibly corrupted) measurement value")
    std_dev: float
    normalised_residual: float = Field(description="Abs normalised residual (>3.0 = flagged)")


class HealthResponse(BaseModel):
    status: str = "ok"


class TopologyResponse(BaseModel):
    feeder_name: str
    buses: List[BusTopology]
    lines: List[LineTopology]
    total_buses: int
    total_lines: int


class TickResponse(BaseModel):
    """Full electrical state snapshot from one simulation tick."""
    power_flow_converged: bool
    bus_voltages: List[BusVoltage]
    line_loadings: List[LineLoading]
    total_load_mw: float
    total_loss_mw: float
    state_estimation_success: bool
    estimated_voltages: List[EstimatedVoltage]
    chi2_test_passed: bool
    chi2_statistic: float
    chi2_threshold: float
    error: Optional[str] = None


class InjectBadDataRequest(BaseModel):
    """Request body for POST /feeder/inject-bad-data."""
    measurement_index: int = Field(
        ...,
        description="Index of the measurement to corrupt",
        ge=0,
    )
    magnitude_multiplier: float = Field(
        ...,
        description="Multiply the measurement value by this factor",
        gt=0.0,
    )

    @field_validator("magnitude_multiplier")
    @classmethod
    def multiplier_not_identity(cls, v: float) -> float:
        if 0.95 <= v <= 1.05:
            raise ValueError("magnitude_multiplier too close to 1.0 — not a meaningful anomaly")
        return v


class BadDataResponse(BaseModel):
    """Result of bad-data injection and detection."""
    injected_measurement_index: int
    magnitude_multiplier: float
    bad_data_detected: bool
    flagged_measurements: List[FlaggedMeasurement]
    chi2_test_passed: bool
    chi2_statistic: float
    chi2_threshold: float
    lnr_threshold: float
    verdict: str = Field(
        description="Human-readable verdict: ANOMALY_DETECTED | CLEAN | ESTIMATION_FAILED"
    )
    error: Optional[str] = None


class ResetResponse(BaseModel):
    status: str
    message: str


# ---------------------------------------------------------------------------
# Phase 2 OT SCADA & Scenario Schemas
# ---------------------------------------------------------------------------

class RTUInfo(BaseModel):
    rtu_id: int
    name: str
    port: int
    host: str
    is_running: bool
    monitored_bus: int
    telemetry: Dict[str, Any]


class RTUListResponse(BaseModel):
    total_rtus: int
    rtus: List[RTUInfo]


class TrafficEvent(BaseModel):
    event_id: int
    timestamp: str
    source: str
    target_rtu: str
    function_code: int
    function_name: str
    response_time_ms: float
    is_unexpected_write: bool
    success: bool
    details: str


class TrafficLogResponse(BaseModel):
    total_events_captured: int
    returned_events_count: int
    events: List[TrafficEvent]


class OTStatusResponse(BaseModel):
    is_simulation_running: bool
    sim_time: str
    sim_hour: float
    diurnal_multiplier: float
    tick_count: int
    active_scenarios: Dict[str, Any]
    total_traffic_events: int


# Attack & Fault Request Models
class SilentDataInjectionRequest(BaseModel):
    rtu_id: int = Field(..., ge=1, le=5, description="Target RTU ID (1 to 5)")
    voltage_pu: Optional[float] = Field(None, description="Fabricated voltage in pu")
    p_mw: Optional[float] = Field(None, description="Fabricated active power in MW")
    q_mvar: Optional[float] = Field(None, description="Fabricated reactive power in MVAR")
    duration_ticks: int = Field(20, ge=1, le=500, description="Number of simulation ticks to override")


class CommandInjectionRequest(BaseModel):
    rtu_id: int = Field(..., ge=1, le=5, description="Target RTU ID (1 to 5)")
    register_address: int = Field(0, ge=0, le=3, description="Target 16-bit register address (0=V, 1=P, 2=Q, 3=Status)")
    value: int = Field(..., ge=0, le=65535, description="Raw 16-bit integer value to write")


class ReplayAttackRequest(BaseModel):
    rtu_id: int = Field(..., ge=1, le=5, description="Target RTU ID (1 to 5)")
    duration_ticks: int = Field(15, ge=1, le=500, description="Duration in ticks to replay frozen telemetry")


class LineTripRequest(BaseModel):
    line_index: int = Field(..., ge=0, le=4, description="Feeder line index (0 to 4)")


class ShortCircuitRequest(BaseModel):
    bus_index: int = Field(..., ge=1, le=6, description="Target 11kV bus index (1 to 6)")
    fault_load_mw: float = Field(6.0, gt=0.0, description="Simulated fault load active power (MW)")
    fault_load_mvar: float = Field(4.0, ge=0.0, description="Simulated fault load reactive power (MVAR)")
    duration_ticks: int = Field(4, ge=1, le=50, description="Duration in ticks before fault is cleared")


class ScenarioActionResponse(BaseModel):
    status: str
    message: str
    details: Dict[str, Any]


# ---------------------------------------------------------------------------
# Phase 3 ML Fusion Classifier Schemas
# ---------------------------------------------------------------------------

class VerdictRequest(BaseModel):
    """
    Optional request body for POST /classifier/verdict.
    If omitted, the endpoint samples the latest live simulation state.
    Callers can also POST a snapshot dict for offline/batch evaluation.
    """
    traffic_window: Optional[List[Dict[str, Any]]] = Field(
        None,
        description="Traffic events from the Modbus logger (last N events).  "
                    "If None, the endpoint uses the live traffic_logger buffer.",
    )
    state_estimation_result: Optional[Dict[str, Any]] = Field(
        None,
        description="State estimation result dict from the last SE run.  "
                    "If None, the endpoint uses the latest simulation tick.",
    )
    polled_telemetry: Optional[Dict[str, Any]] = Field(
        None,
        description="RTU telemetry snapshot keyed by RTU id (str).  "
                    "If None, the endpoint queries the live RTU pool.",
    )


class RTUVerdict(BaseModel):
    """ML verdict for a single RTU."""
    rtu_id: int
    verdict: str = Field(description="Normal | Natural Fault | Cyber Intrusion")
    subtype: Optional[str] = Field(None, description="normal | physical_fault | data_injection | command_injection | replay")
    confidence: float = Field(ge=0.0, le=1.0)
    probabilities: Dict[str, float]
    model_status: str = Field(description="loaded | heuristic_fallback")


class VerdictResponse(BaseModel):
    """Aggregated per-RTU ML verdicts for one evaluation tick."""
    tick_timestamp: str
    model_loaded: bool
    overall_status: str = Field(
        description="NORMAL | ANOMALY_DETECTED. ANOMALY if any RTU is flagged as "
                    "Natural Fault or Cyber Intrusion.",
    )
    rtu_verdicts: List[RTUVerdict]
    evaluation_latency_ms: float


class ClassifierReloadResponse(BaseModel):
    """Result of POST /classifier/reload."""
    success: bool
    message: str
    model_path: str


class ClassifierStatusResponse(BaseModel):
    """Result of GET /classifier/status."""
    is_loaded: bool
    model_path: str
    classes: List[str]
    subtype_classes: List[str]
    cached_rtu_count: int
