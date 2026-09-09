"""Out-of-band in-memory storage for frontend-created incident audit records."""

from __future__ import annotations

from typing import Dict, Optional

from pydantic import BaseModel, Field


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


_records: Dict[str, IncidentRecord] = {}


def store_incident(record: IncidentRecord) -> IncidentRecord:
    _records[record.id] = record
    return record


def get_incident(incident_id: str) -> Optional[IncidentRecord]:
    return _records.get(incident_id)


def clear_incidents() -> None:
    """Reset the test/session registry without touching simulation state."""
    _records.clear()
