"""
alerts.py
---------
Alert router and metadata pipeline with strict MITRE ATT&CK for ICS tagging.
Ensures that all cyber-intrusion alerts, False Data Injection (FDI) events,
and command-override anomalies carry standardized industrial cybersecurity identifiers.
"""

from __future__ import annotations

import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from app.mitre_ics import (
    CYBER_SUBTYPE_TO_MITRE,
    MITRE_ICS_TECHNIQUES,
    MitreIcsMapping,
    build_alert_payload,
    get_mitre_mapping,
)


class CyberAlert(BaseModel):
    """Normalized cyber security alert payload with MITRE ATT&CK for ICS tagging."""

    event_id: str
    timestamp: str
    classification: str
    subtype: Optional[str] = None
    rtu_id: Optional[int] = None
    mitre_ics: Optional[MitreIcsMapping] = None
    details: Dict[str, Any] = Field(default_factory=dict)


def format_cyber_alert(
    event_id: str,
    classification: str,
    subtype: Optional[str] = None,
    rtu_id: Optional[int] = None,
    timestamp: Optional[str] = None,
    details: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Format an alert with strict MITRE ATT&CK for ICS metadata.

    Ensures that natural electrical faults and normal events produce null mitre_ics,
    while cyber events include valid technique ID, name, tactic, and description.
    """
    ts = timestamp or datetime.datetime.now(datetime.timezone.utc).isoformat()
    return build_alert_payload(
        event_id=event_id,
        timestamp=ts,
        classification=classification,
        subtype=subtype,
        rtu_id=rtu_id,
        details=details or {},
    )


__all__ = [
    "MitreIcsMapping",
    "MITRE_ICS_TECHNIQUES",
    "CYBER_SUBTYPE_TO_MITRE",
    "get_mitre_mapping",
    "build_alert_payload",
    "CyberAlert",
    "format_cyber_alert",
]
