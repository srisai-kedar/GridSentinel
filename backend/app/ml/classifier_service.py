"""
classifier_service.py
---------------------
Real-time Cyber-Physical Fusion Classifier Service for GridSentinel.

Loads the trained Random Forest model bundle on startup and evaluates live telemetry:
  - Takes raw feature dictionary (from feature_engineering.py)
  - Outputs {"verdict": str, "subtype": Optional[str], "confidence": float, "probabilities": dict}
  - Supports hot-reloading via POST /classifier/reload
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional
import joblib
import numpy as np

from app.ml.feature_engineering import FEATURE_SCHEMA, extract_features

logger = logging.getLogger("GridSentinel.ClassifierService")


class ClassifierService:
    """
    Singleton service managing model lifecycle and real-time inference.
    """

    def __init__(self, model_path: str = "models/fusion_classifier.joblib"):
        self.model_path = Path(model_path)
        self.bundle: Optional[Dict[str, Any]] = None
        self.top_model: Any = None
        self.subtype_model: Any = None
        self.is_loaded: bool = False
        self.classes: List[str] = ["Normal", "Natural Fault", "Cyber Intrusion"]
        self.subtype_classes: List[str] = ["data_injection", "command_injection", "replay"]

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
            self.classes = bundle.get("classes", self.classes)
            self.subtype_classes = bundle.get("subtype_classes", self.subtype_classes)
            self.is_loaded = True
            logger.info(f"[ClassifierService] Successfully loaded Fusion Classifier from '{target_path}'.")
            return True
        except Exception as exc:
            logger.error(f"[ClassifierService] Failed to load model from '{target_path}': {exc}")
            self.is_loaded = False
            return False

    def predict(self, features: Dict[str, float]) -> Dict[str, Any]:
        """
        Run inference on a single feature dictionary.

        Parameters
        ----------
        features : dict
            Feature dictionary containing keys from FEATURE_SCHEMA

        Returns
        -------
        dict
            {"verdict": str, "subtype": Optional[str], "confidence": float, "probabilities": dict}
        """
        if not self.is_loaded or self.top_model is None:
            return self._heuristic_fallback(features)

        try:
            # Build strictly ordered feature vector
            vector = np.array([[float(features.get(k, 0.0)) for k in FEATURE_SCHEMA]])

            # Stage 1: Primary Triage
            proba = self.top_model.predict_proba(vector)[0]
            top_classes = list(self.top_model.classes_)
            prob_dict = {cls_name: round(float(p), 4) for cls_name, p in zip(top_classes, proba)}

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

            return {
                "verdict": verdict,
                "subtype": subtype,
                "confidence": confidence,
                "probabilities": prob_dict,
                "model_status": "loaded",
            }

        except Exception as exc:
            logger.error(f"[ClassifierService] Prediction failed: {exc}", exc_info=True)
            return self._heuristic_fallback(features)

    def _heuristic_fallback(self, features: Dict[str, float]) -> Dict[str, Any]:
        """Physics/Network rule-based heuristic when ML model is not yet compiled."""
        unexpected_writes = features.get("nbd_unexpected_write_count", 0.0)
        target_flagged = features.get("pcd_target_rtu_is_flagged", 0.0)
        chi2_failed = features.get("pcd_chi2_failed", 0.0)
        status_code = features.get("pcd_status_code", 1.0)
        max_lnr = features.get("pcd_max_lnr", 0.0)

        if unexpected_writes > 0:
            return {
                "verdict": "Cyber Intrusion",
                "subtype": "command_injection",
                "confidence": 0.95,
                "probabilities": {"Normal": 0.01, "Natural Fault": 0.04, "Cyber Intrusion": 0.95},
                "model_status": "heuristic_fallback",
            }
        elif target_flagged > 0 or max_lnr > 3.0:
            return {
                "verdict": "Cyber Intrusion",
                "subtype": "data_injection",
                "confidence": 0.88,
                "probabilities": {"Normal": 0.02, "Natural Fault": 0.10, "Cyber Intrusion": 0.88},
                "model_status": "heuristic_fallback",
            }
        elif status_code == 3 or (chi2_failed > 0 and target_flagged == 0):
            return {
                "verdict": "Natural Fault",
                "subtype": "line_trip",
                "confidence": 0.82,
                "probabilities": {"Normal": 0.08, "Natural Fault": 0.82, "Cyber Intrusion": 0.10},
                "model_status": "heuristic_fallback",
            }
        else:
            return {
                "verdict": "Normal",
                "subtype": "normal",
                "confidence": 0.96,
                "probabilities": {"Normal": 0.96, "Natural Fault": 0.03, "Cyber Intrusion": 0.01},
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
