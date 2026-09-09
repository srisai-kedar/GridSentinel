"""Out-of-band in-memory storage for frontend-created incident audit records."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from app.replay_capture import replay_capture_store


class IncidentRecord(BaseModel):
    """The fields already present in the frontend audit incident record."""

    id: str = Field(min_length=1)
    timestamp: Optional[str] = None
    sim_time: Optional[str] = None
    rtu_id: Optional[int] = None
    asset_name: Optional[str] = None
    verdict: Optional[str] = None
    subtype: Optional[str] = None
    confidence: Optional[float] = None
    network_evidence: Optional[str] = None
    physics_evidence: Optional[str] = None
    conclusion: Optional[str] = None
    recommended_action: Optional[str] = None
    formatted_alert: Optional[str] = None
    trigger_tick: Optional[int] = None
    replay_window: List[Dict[str, Any]] = Field(default_factory=list)


_records: Dict[str, IncidentRecord] = {}


def store_incident(record: IncidentRecord) -> IncidentRecord:
    record.replay_window = replay_capture_store.get_window(record.rtu_id, record.trigger_tick)
    _records[record.id] = record
    return record


def get_incident(incident_id: str) -> Optional[IncidentRecord]:
    record = _records.get(incident_id)
    if record is not None:
        # A registration can arrive before the five post-trigger ticks have
        # completed. Refresh on reads so the attached record becomes complete.
        record.replay_window = replay_capture_store.get_window(record.rtu_id, record.trigger_tick)
    return record


def clear_incidents() -> None:
    """Reset the test/session registry without touching simulation state."""
    _records.clear()
