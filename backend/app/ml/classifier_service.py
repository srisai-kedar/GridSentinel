"""
classifier_service.py
---------------------
Real-time Cyber-Physical Fusion Classifier Service for GridSentinel.

Loads the trained model bundle on startup and evaluates live telemetry:
  - Takes raw feature dictionary (from feature_engineering.py)
  - Applies the tuned decision threshold stored in the model bundle
  - Outputs a structured verdict with a 3-line explainable evidence panel:
      * network_evidence  – what the Network / Modbus layer observed
      * physics_evidence  – what the Physical / power-flow layer observed
      * conclusion        – the combined decision reason
  - Supports hot-reloading via POST /classifier/reload

This component acts as a decision-support layer; final operational
decisions rest with qualified grid operators.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

import joblib
import numpy as np

from app.ml.feature_engineering import FEATURE_SCHEMA, extract_features

logger = logging.getLogger("GridSentinel.ClassifierService")

# ─────────────────────────────────────────────────────────────────────────────
# Evidence panel builder
# ─────────────────────────────────────────────────────────────────────────────

# Thresholds used to generate human-readable evidence lines from raw features.
_ANOMALY_RATE_HI = 0.15   # nbd_modbus_anomaly_rate
_LNR_HI = 2.5             # pcd_max_lnr
_VOLTAGE_DIV_HI = 0.03    # pcd_cross_rtu_voltage_divergence
_PHYS_NET_HI = 0.5        # pcd_physics_network_disagreement_index


def _build_evidence(
    features: Dict[str, float],
    verdict: str,
    subtype: Optional[str],
    proba_dict: Dict[str, float],
) -> Dict[str, str]:
    """
    Produce a structured 3-line evidence panel for human-readable display.
    Each line is a single, concise factual statement grounded in feature values.
    """
    # ── Network layer observations ──────────────────────────────────────────
    unexpected_writes = features.get("nbd_unexpected_write_count", 0.0)
    anomaly_rate = features.get("nbd_modbus_anomaly_rate", 0.0)
    # These legacy keys were removed from FEATURE_SCHEMA v2.0.0. Derive the
    # write ratio from the live schema instead of silently reading fields that
    # can never be populated by the current telemetry pipeline.
    traffic_volume = features.get("nbd_traffic_volume", 0.0)
    write_count = features.get("nbd_fc6_write_count", 0.0) + features.get("nbd_fc16_write_count", 0.0)
    write_ratio = write_count / traffic_volume if traffic_volume > 0 else 0.0

    if unexpected_writes > 0:
        net_evidence = (
            f"Network: {int(unexpected_writes)} unexpected Modbus write(s) to monitored RTU "
            f"(anomaly rate {anomaly_rate * 100:.1f}%)."
        )
    elif anomaly_rate > _ANOMALY_RATE_HI:
        net_evidence = (
            f"Network: Elevated Modbus anomaly rate ({anomaly_rate * 100:.1f}%) "
            f"on target RTU traffic."
        )
    else:
        net_evidence = (
            f"Network: Nominal Modbus traffic pattern "
            f"(anomaly rate {anomaly_rate * 100:.1f}%, write ratio {write_ratio * 100:.1f}%)."
        )

    # ── Physics layer observations ──────────────────────────────────────────
    max_lnr = features.get("pcd_max_lnr", 0.0)
    chi2_failed = features.get("pcd_chi2_failed", 0.0)
    status_code = features.get("pcd_status_code", 1.0)
    target_flagged = features.get("pcd_target_rtu_is_flagged", 0.0)
    voltage_div = features.get("pcd_cross_rtu_voltage_divergence", 0.0)
    phys_net_idx = features.get("pcd_physics_network_disagreement_index", 0.0)

    if max_lnr > _LNR_HI and target_flagged > 0:
        phys_evidence = (
            f"Physics: State estimator flagged target RTU (LNR={max_lnr:.2f}); "
            f"reported voltage deviates from power-flow solution."
        )
    elif chi2_failed > 0 and status_code == 3:
        phys_evidence = (
            f"Physics: χ² bad-data test failed and line-trip status detected "
            f"(LNR={max_lnr:.2f}); consistent with an Impedance-Depression Fault stand-in."
        )
    elif voltage_div > _VOLTAGE_DIV_HI:
        phys_evidence = (
            f"Physics: Cross-RTU voltage divergence {voltage_div:.4f} pu exceeds "
            f"neighbourhood threshold; topology change likely."
        )
    elif phys_net_idx > _PHYS_NET_HI:
        phys_evidence = (
            f"Physics: Physics-network disagreement index {phys_net_idx:.3f} "
            f"suggests inconsistency between reported and estimated values."
        )
    else:
        phys_evidence = (
            f"Physics: Power-flow residuals within normal bounds "
            f"(LNR={max_lnr:.2f}, χ²-fail={int(chi2_failed)})."
        )

    # ── Conclusion ──────────────────────────────────────────────────────────
    cyber_p = proba_dict.get("Cyber Intrusion", 0.0)
    fault_p = proba_dict.get("Natural Fault", 0.0)

    if verdict == "Cyber Intrusion":
        subtype_label = {
            "data_injection": "Data-Injection attack",
            "command_injection": "Command-Injection attack",
            "replay": "Replay attack",
        }.get(subtype or "", "Cyber Intrusion")
        conclusion = (
            f"Conclusion: Classifier assigns {cyber_p * 100:.1f}% Cyber probability; "
            f"pattern consistent with a {subtype_label}. "
            "Recommend operator review before any automated control action."
        )
    elif verdict == "Natural Fault":
        conclusion = (
            f"Conclusion: Classifier assigns {fault_p * 100:.1f}% Natural-Fault probability; "
            "physics residuals indicate a genuine line or equipment anomaly, "
            "not a manipulation pattern."
        )
    else:
        conclusion = (
            f"Conclusion: All indicators nominal; classifier confidence "
            f"{proba_dict.get('Normal', 0.0) * 100:.1f}% Normal. No action required."
        )

    return {
        "network_evidence": net_evidence,
        "physics_evidence": phys_evidence,
        "conclusion": conclusion,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Classifier Service
# ─────────────────────────────────────────────────────────────────────────────

class ClassifierService:
    """
    Singleton service managing model lifecycle and real-time inference.

    The service applies the decision threshold that was tuned on the
    validation set (stored inside the model bundle) and produces a
    structured evidence panel alongside every verdict.
    """

    def __init__(self, model_path: str = "models/fusion_classifier.joblib"):
        self.model_path = Path(model_path)
        self.bundle: Optional[Dict[str, Any]] = None
        self.top_model: Any = None
        self.subtype_model: Any = None
        self.is_loaded: bool = False
        self.classes: List[str] = ["Normal", "Natural Fault", "Cyber Intrusion"]
        self.subtype_classes: List[str] = ["data_injection", "command_injection", "replay"]
        # Tuned Cyber Intrusion decision threshold (overridden from bundle at load time)
        self.decision_threshold: float = 0.5

        # Cache of latest verdicts per RTU
        self.latest_verdicts: Dict[int, Dict[str, Any]] = {}

        # Attempt initial load
        self.load_model()

    def load_model(self, path_override: Optional[str] = None) -> bool:
        """Load or reload model bundle from disk."""
        target_path = Path(path_override) if path_override else self.model_path

        if not target_path.exists():
            logger.warning(
                f"[ClassifierService] Model file '{target_path}' not found. "
                "Running in heuristic baseline mode until model is trained."
            )
            self.is_loaded = False
            return False

        try:
            bundle = joblib.load(target_path)
            self.bundle = bundle
            self.top_model = bundle.get("top_level_model")
            self.subtype_model = bundle.get("subtype_model")
            raw_classes = bundle.get("classes", self.classes)
            label_map = {0: "Cyber Intrusion", 1: "Natural Fault", 2: "Normal"}
            self.classes = [
                label_map[int(c)] if isinstance(c, (int, np.integer)) and int(c) in label_map else str(c)
                for c in raw_classes
            ]
            self.subtype_classes = [str(c) for c in bundle.get("subtype_classes", self.subtype_classes)]
            # Load tuned threshold from bundle (default 0.5 if older bundle)
            self.decision_threshold = float(bundle.get("decision_threshold", 0.5))
            self.is_loaded = True
            logger.info(
                f"[ClassifierService] Loaded Fusion Classifier v{bundle.get('version', '?')} "
                f"from '{target_path}' (model={bundle.get('model_name', 'RF')}, "
                f"threshold={self.decision_threshold:.2f})."
            )
            return True
        except Exception as exc:
            logger.error(f"[ClassifierService] Failed to load model from '{target_path}': {exc}")
            self.is_loaded = False
            return False

    def clear_cache(self) -> None:
        """Discard verdicts from a prior simulation/session lifecycle."""
        self.latest_verdicts = {}
        logger.info("[ClassifierService] Cleared cached RTU verdicts.")

    def predict(self, features: Dict[str, float]) -> Dict[str, Any]:
        """
        Run inference on a single feature dictionary.

        Parameters
        ----------
        features : dict
            Feature dictionary containing keys from FEATURE_SCHEMA

        Returns
        -------
        dict with keys:
            verdict            – "Normal" | "Natural Fault" | "Cyber Intrusion"
            subtype            – specific attack/fault subtype or None
            confidence         – float [0,1] probability of the decided class
            probabilities      – {class_name: probability} for all classes
            decision_threshold – the Cyber threshold applied
            network_evidence   – single-line human-readable network finding
            physics_evidence   – single-line human-readable physics finding
            conclusion         – single-line combined decision rationale
            model_status       – "loaded" | "heuristic_fallback"
        """
        if not self.is_loaded or self.top_model is None:
            return self._heuristic_fallback(features)

        try:
            # Build strictly ordered feature vector
            vector = np.array([[float(features.get(k, 0.0)) for k in FEATURE_SCHEMA]])

            # Stage 1: Primary Triage (with tuned threshold)
            proba = self.top_model.predict_proba(vector)[0]
            raw_top_classes = list(self.top_model.classes_)
            # Ensure top_classes are string names
            label_map = {0: "Cyber Intrusion", 1: "Natural Fault", 2: "Normal"}
            top_classes = [
                label_map[int(c)] if isinstance(c, (int, np.integer)) and int(c) in label_map else str(c)
                for c in raw_top_classes
            ]
            prob_dict = {cls_name: round(float(p), 4) for cls_name, p in zip(top_classes, proba)}

            # Apply tuned threshold for Cyber Intrusion class
            if "Cyber Intrusion" in top_classes:
                cyber_idx = top_classes.index("Cyber Intrusion")
                if proba[cyber_idx] >= self.decision_threshold:
                    verdict = "Cyber Intrusion"
                    confidence = round(float(proba[cyber_idx]), 4)
                else:
                    # Argmax excluding Cyber Intrusion
                    masked = proba.copy()
                    masked[cyber_idx] = 0.0
                    pred_idx = int(np.argmax(masked))
                    verdict = top_classes[pred_idx]
                    confidence = round(float(proba[pred_idx]), 4)
            else:
                pred_idx = int(np.argmax(proba))
                verdict = top_classes[pred_idx]
                confidence = round(float(proba[pred_idx]), 4)

            # Stage 2: Forensic Subtyping if Cyber Intrusion
            subtype: Optional[str] = None
            if verdict == "Cyber Intrusion" and self.subtype_model is not None:
                sub_proba = self.subtype_model.predict_proba(vector)[0]
                sub_classes = list(self.subtype_model.classes_)
                sub_idx = int(np.argmax(sub_proba))
                subtype = sub_classes[sub_idx]
            elif verdict == "Natural Fault":
                subtype = "physical_fault"
            else:
                subtype = "normal"

            # Step 7: Build 3-line evidence panel
            evidence = _build_evidence(features, verdict, subtype, prob_dict)

            return {
                "verdict": verdict,
                "subtype": subtype,
                "confidence": confidence,
                "probabilities": prob_dict,
                "decision_threshold": self.decision_threshold,
                "network_evidence": evidence["network_evidence"],
                "physics_evidence": evidence["physics_evidence"],
                "conclusion": evidence["conclusion"],
                "model_status": "loaded",
            }

        except Exception as exc:
            logger.error(f"[ClassifierService] Prediction failed: {exc}", exc_info=True)
            return self._heuristic_fallback(features)

    def _heuristic_fallback(self, features: Dict[str, float]) -> Dict[str, Any]:
        """
        Physics/Network rule-based heuristic when ML model is not yet available.
        This is a decision-support layer only — operators must confirm any actions.
        """
        unexpected_writes = features.get("nbd_unexpected_write_count", 0.0)
        target_flagged = features.get("pcd_target_rtu_is_flagged", 0.0)
        chi2_failed = features.get("pcd_chi2_failed", 0.0)
        status_code = features.get("pcd_status_code", 1.0)
        max_lnr = features.get("pcd_max_lnr", 0.0)

        if unexpected_writes > 0:
            verdict, subtype = "Cyber Intrusion", "command_injection"
            prob_dict = {"Normal": 0.01, "Natural Fault": 0.04, "Cyber Intrusion": 0.95}
        elif target_flagged > 0 or max_lnr > 3.0:
            verdict, subtype = "Cyber Intrusion", "data_injection"
            prob_dict = {"Normal": 0.02, "Natural Fault": 0.10, "Cyber Intrusion": 0.88}
        elif status_code == 3 or (chi2_failed > 0 and target_flagged == 0):
            verdict, subtype = "Natural Fault", "line_trip"
            prob_dict = {"Normal": 0.08, "Natural Fault": 0.82, "Cyber Intrusion": 0.10}
        else:
            verdict, subtype = "Normal", "normal"
            prob_dict = {"Normal": 0.96, "Natural Fault": 0.03, "Cyber Intrusion": 0.01}

        confidence = prob_dict[verdict]
        evidence = _build_evidence(features, verdict, subtype, prob_dict)

        return {
            "verdict": verdict,
            "subtype": subtype,
            "confidence": confidence,
            "probabilities": prob_dict,
            "decision_threshold": 0.5,
            "network_evidence": evidence["network_evidence"],
            "physics_evidence": evidence["physics_evidence"],
            "conclusion": evidence["conclusion"],
            "model_status": "heuristic_fallback",
        }

    def evaluate_all_rtus(
        self,
        traffic_events: List[Dict[str, Any]],
        state_estimation_result: Dict[str, Any],
        polled_telemetry: Optional[Dict[int, Dict[str, Any]]] = None,
    ) -> Dict[int, Dict[str, Any]]:
        """Extract features and run classification for all 5 monitored RTUs."""
        results = {}
        for rtu_id in range(1, 6):
            feats = extract_features(
                traffic_events=traffic_events,
                state_estimation_result=state_estimation_result,
                target_rtu_id=rtu_id,
                polled_telemetry=polled_telemetry,
            )
            res = self.predict(feats)
            results[rtu_id] = res

        self.latest_verdicts = results
        return results


# Global singleton instance
classifier_service = ClassifierService()
