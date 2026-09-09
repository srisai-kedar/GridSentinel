"""HTTP routes for the out-of-band incident report feature."""

from __future__ import annotations

import re

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response

from app.audit_report import build_incident_report
from app.audit_store import IncidentRecord, get_incident, store_incident


router = APIRouter(prefix="/audit", tags=["Incident Audit"])


@router.post("/incidents", response_model=IncidentRecord, status_code=201)
def register_incident(record: IncidentRecord) -> IncidentRecord:
    """Store the already-created frontend audit record outside the telemetry hot path."""
    return store_incident(record)


@router.get("/{incident_id}/report.pdf", response_class=Response)
def get_incident_report(incident_id: str) -> Response:
    record = get_incident(incident_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Incident record not found")

    pdf = build_incident_report(record)
    safe_id = re.sub(r"[^A-Za-z0-9._-]", "-", incident_id)[:80] or "incident"
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="GridSentinel-incident-{safe_id}.pdf"'},
    )
