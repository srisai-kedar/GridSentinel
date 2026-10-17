"""
mitre_ics.py
------------
MITRE ATT&CK for ICS mapping schema and technique tagging for GridSentinel.
Maps cyber-intrusion alerts, False Data Injection (FDI) events, command overrides,
and replay attacks to formal MITRE ATT&CK for Industrial Control Systems (ICS)
technique identifiers.
"""

from __future__ import annotations

from typing import Any, Dict, Optional
from pydantic import BaseModel, Field


class MitreIcsMapping(BaseModel):
    """Formal MITRE ATT&CK for ICS technique identifier and tactical metadata."""

    technique_id: str = Field(
        ...,
        description="MITRE ATT&CK for ICS technique identifier (e.g., T0856, T0855, T0831, T0814)",
    )
    technique_name: str = Field(
        ...,
        description="Official MITRE ATT&CK for ICS technique name (e.g., Spoof Reporting Message)",
    )
    tactic: str = Field(
        ...,
        description="Tactical phase in the ATT&CK for ICS matrix (e.g., Impact, Impair Process Control)",
    )
    tactical_phase: Optional[str] = Field(
        None,
        description="Alias for tactical phase to support diverse schema consumer conventions",
    )
    description: Optional[str] = Field(
        None,
        description="Human-readable description mapped directly to the detected anomaly type",
    )


# Official MITRE ATT&CK for ICS technique catalog referenced in industrial standards
MITRE_ICS_TECHNIQUES: Dict[str, Dict[str, str]] = {
    "T0856": {
        "technique_id": "T0856",
        "technique_name": "Spoof Reporting Message",
        "tactic": "Impact",
        "tactical_phase": "Impact",
        "description": "Adversary injects falsified telemetry readings (voltage, active/reactive power) to mask grid anomalies or bypass state estimation.",
    },
    "T0855": {
        "technique_id": "T0855",
        "technique_name": "Unauthorized Command Message",
        "tactic": "Impair Process Control",
        "tactical_phase": "Impair Process Control",
        "description": "Adversary transmits unauthorized Modbus write commands (FC 06/16) to force breaker operations or alter RTU register setpoints.",
    },
    "T0831": {
        "technique_id": "T0831",
        "technique_name": "Manipulation of Control",
        "tactic": "Impair Process Control",
        "tactical_phase": "Impair Process Control",
        "description": "Adversary manipulates physical control devices or parameters to disrupt normal grid operations.",
    },
    "T0814": {
        "technique_id": "T0814",
        "technique_name": "Denial of Control",
        "tactic": "Impair Process Control",
        "tactical_phase": "Impair Process Control",
        "description": "Adversary impairs the ability of operators or automated systems to execute control actions.",
    },
}

# Subtype lookup table mapping internal classifier / scenario identifiers to MITRE technique IDs
CYBER_SUBTYPE_TO_MITRE: Dict[str, str] = {
    "data_injection": "T0856",
    "silent_data_injection": "T0856",
    "fdi": "T0856",
    "false_data_injection": "T0856",
    "command_injection": "T0855",
    "unauthorized_command": "T0855",
    "replay": "T0856",
    "replay_attack": "T0856",
    "manipulation_of_control": "T0831",
    "control_manipulation": "T0831",
    "denial_of_control": "T0814",
}


def get_mitre_mapping(
    classification: Optional[str],
    subtype: Optional[str] = None,
) -> Optional[Dict[str, str]]:
    """
    Resolve a MITRE ATT&CK for ICS technique mapping.

    Mapping Logic:
      - Natural electrical faults and sensor anomalies map strictly to None.
      - Normal operations map to None.
      - Cyber intrusion/attacks map to valid MITRE ATT&CK for ICS codes
        (T0856 for FDI / Spoof Reporting, T0855 for Command Injection,
        T0831 for Manipulation of Control, T0814 for Denial of Control).

    Parameters
    ----------
    classification : Optional[str]
        Primary classification (e.g. "Cyber Intrusion", "CYBER_ATTACK", "Natural Fault", "Normal").
    subtype : Optional[str]
        Secondary anomaly subtype (e.g. "data_injection", "command_injection", "replay", "line_trip").

    Returns
    -------
    Optional[Dict[str, str]]
        Dictionary containing technique_id, technique_name, tactic, tactical_phase,
        and human-readable description; or None if not a cyber intrusion.
    """
    if not classification:
        return None

    cls_norm = str(classification).strip().upper().replace(" ", "_")
    if cls_norm not in ("CYBER_ATTACK", "CYBER_INTRUSION", "CYBER"):
        return None

    sub_key = str(subtype).strip().lower() if subtype else ""
    tech_id = CYBER_SUBTYPE_TO_MITRE.get(sub_key, "T0856")
    base = dict(MITRE_ICS_TECHNIQUES[tech_id])

    # Contextual descriptions for GridSentinel anomaly patterns
    if sub_key in ("data_injection", "silent_data_injection", "fdi", "false_data_injection"):
        base["description"] = (
            "Adversary injects falsified telemetry readings (voltage, active/reactive power) "
            "to mask grid anomalies or bypass state estimation."
        )
    elif sub_key in ("command_injection", "unauthorized_command"):
        base["description"] = (
            "Adversary transmits unauthorized Modbus write commands (FC 06/16) "
            "to force breaker operations or alter RTU register setpoints."
        )
    elif sub_key in ("replay", "replay_attack"):
        base["description"] = (
            "Adversary replays historical telemetry frames with static values "
            "to conceal active grid disturbances or breaker operations."
        )
    elif sub_key in ("manipulation_of_control", "control_manipulation"):
        base["description"] = (
            "Adversary manipulates physical control devices or parameters to disrupt normal grid operations."
        )

    return base


def build_alert_payload(
    event_id: str,
    timestamp: str,
    classification: str,
    subtype: Optional[str] = None,
    rtu_id: Optional[int] = None,
    mitre_ics: Optional[Dict[str, Any]] = None,
    **extra: Any,
) -> Dict[str, Any]:
    """
    Construct an alert payload with explicit MITRE ATT&CK for ICS tagging.

    Natural electrical faults and sensor anomalies map mitre_ics to None,
    while cyber intrusions map strictly to valid MITRE ATT&CK for ICS codes.
    """
    mapped_mitre = (
        mitre_ics
        if mitre_ics is not None
        else get_mitre_mapping(classification, subtype)
    )

    payload: Dict[str, Any] = {
        "event_id": event_id,
        "timestamp": timestamp,
        "classification": classification,
        "mitre_ics": mapped_mitre,
    }
    if subtype is not None:
        payload["subtype"] = subtype
    if rtu_id is not None:
        payload["rtu_id"] = rtu_id
    payload.update(extra)
    return payload
