"""
tests/test_ml_taxonomy_regression.py
------------------------------------
Regression tests for ML taxonomy consistency, 3-class primary triage preservation,
dynamic integer-label encoding/decoding, and separate sensor-drift evaluation.

Validates:
1. Dynamic XGBoost integer-encoded predictions safely decode back to class label strings
   and NEVER silently map unexpected indices (or Sensor Malfunction) to 'Normal'.
2. Dataset partitioning cleanly isolates Sensor Malfunction rows from the 3-class
   primary triage training and testing sets.
3. Candidate models (RandomForest and XGBoost) train strictly on the 3 primary classes:
   "Cyber Intrusion", "Natural Fault", "Normal".
4. Sensor drift scenarios are evaluated separately without distorting 3-class model-comparison
   accuracy or F2 metrics.
5. The dedicated physics-based sensor-drift detection pathway correctly intercepts localized
   sensor-drift telemetry without confusing it with Cyber Intrusion or Natural Fault.
6. The deployed model bundle (models/fusion_classifier.joblib) remains completely unchanged.
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict
import joblib
import numpy as np
import pandas as pd
import pytest
from sklearn.ensemble import RandomForestClassifier

try:
    from xgboost import XGBClassifier
    _HAS_XGB = True
except ImportError:
    _HAS_XGB = False

from app.ml.classifier_service import (
    ClassifierService,
    VerdictLabel,
    detect_sensor_drift_signature,
)
from app.ml.feature_engineering import FEATURE_SCHEMA
from app.ml.train_classifier import (
    PRIMARY_CLASSES,
    SENSOR_MALFUNCTION_LABEL,
    decode_xgb_predictions,
    evaluate_sensor_drift_scenarios,
    partition_primary_and_drift,
    tune_threshold,
)


# ---------------------------------------------------------------------------
# Test Helpers
# ---------------------------------------------------------------------------

def _make_dummy_dataset(n_samples: int = 120, seed: int = 42) -> pd.DataFrame:
    """Generate a small synthetic DataFrame with all 4 classes for taxonomy tests."""
    rng = np.random.default_rng(seed)
    data = {f: rng.normal(0.0, 1.0, size=n_samples) for f in FEATURE_SCHEMA}

    n_each = n_samples // 4
    remainder = n_samples % 4
    labels = (
        ["Normal"] * (n_each + remainder)
        + ["Natural Fault"] * n_each
        + ["Cyber Intrusion"] * n_each
        + ["Sensor Malfunction"] * n_each
    )
    subtypes = (
        ["normal"] * (n_each + remainder)
        + ["line_trip"] * n_each
        + ["data_injection"] * n_each
        + ["sensor_drift"] * n_each
    )
    data["top_level_label"] = labels
    data["subtype_label"] = subtypes
    df = pd.DataFrame(data)

    # Configure realistic sensor drift features on the Sensor Malfunction rows
    drift_mask = df["top_level_label"] == "Sensor Malfunction"
    df.loc[drift_mask, "pcd_resid_breadth_count"] = 1.0
    df.loc[drift_mask, "pcd_resid_concentration"] = 0.90
    df.loc[drift_mask, "pcd_voltage_deviation_pu"] = 0.04
    df.loc[drift_mask, "pcd_voltage_dev_nominal"] = 0.04
    df.loc[drift_mask, "pcd_target_rtu_is_flagged"] = 1.0
    df.loc[drift_mask, "pcd_max_lnr"] = 3.5
    df.loc[drift_mask, "nbd_unexpected_write_count"] = 0.0
    df.loc[drift_mask, "nbd_modbus_anomaly_rate"] = 0.0

    return df


# ---------------------------------------------------------------------------
# Suite 1: Label Mapping and Safe Decoding
# ---------------------------------------------------------------------------

class TestClassLabelMapping:
    """Tests that label encodings and decodings are strictly injective and never silently map."""

    def test_decode_xgb_predictions_standard_mapping(self):
        label_map_inv = {0: "Cyber Intrusion", 1: "Natural Fault", 2: "Normal"}
        encoded = np.array([0, 1, 2, 1, 0])
        decoded = decode_xgb_predictions(encoded, label_map_inv)

        expected = np.array([
            "Cyber Intrusion",
            "Natural Fault",
            "Normal",
            "Natural Fault",
            "Cyber Intrusion",
        ])
        np.testing.assert_array_equal(decoded, expected)

    def test_decode_xgb_predictions_never_maps_sensor_malfunction_to_normal(self):
        """Regression test: class index 3 must NEVER silently default to 'Normal'."""
        label_map_inv = {0: "Cyber Intrusion", 1: "Natural Fault", 2: "Normal"}
        encoded = np.array([3])

        with pytest.raises(KeyError) as exc_info:
            decode_xgb_predictions(encoded, label_map_inv)

        assert "3" in str(exc_info.value)
        assert "not in label map" in str(exc_info.value)

    def test_decode_xgb_predictions_with_4class_mapping(self):
        """When 4 classes are explicitly mapped, index 3 resolves to Sensor Malfunction."""
        label_map_inv = {
            0: "Cyber Intrusion",
            1: "Natural Fault",
            2: "Normal",
            3: "Sensor Malfunction",
        }
        encoded = np.array([0, 1, 2, 3])
        decoded = decode_xgb_predictions(encoded, label_map_inv)
        expected = np.array([
            "Cyber Intrusion",
            "Natural Fault",
            "Normal",
            "Sensor Malfunction",
        ])
        np.testing.assert_array_equal(decoded, expected)


# ---------------------------------------------------------------------------
# Suite 2: Dataset Partitioning
# ---------------------------------------------------------------------------

class TestDatasetPartitioning:
    """Tests partition_primary_and_drift separating 3-class triage from drift scenarios."""

    def test_partition_with_sensor_malfunction(self):
        df = _make_dummy_dataset(120)
        X = df[FEATURE_SCHEMA]
        y_top = df["top_level_label"]
        y_sub = df["subtype_label"]

        (
            X_prim,
            y_prim,
            y_sub_prim,
            X_drift,
            y_drift,
            y_sub_drift,
        ) = partition_primary_and_drift(X, y_top, y_sub)

        # Primary set must contain exactly 90 rows with strictly 3 primary classes
        assert len(X_prim) == 90
        assert len(y_prim) == 90
        assert set(y_prim.unique()) == {"Cyber Intrusion", "Natural Fault", "Normal"}
        assert SENSOR_MALFUNCTION_LABEL not in y_prim.unique()

        # Drift set must contain exactly 30 rows of Sensor Malfunction
        assert len(X_drift) == 30
        assert len(y_drift) == 30
        assert set(y_drift.unique()) == {SENSOR_MALFUNCTION_LABEL}
        assert set(y_sub_drift.unique()) == {"sensor_drift"}

        # Total sample preservation
        assert len(X_prim) + len(X_drift) == len(df)

    def test_partition_pure_3class_dataset(self):
        df = _make_dummy_dataset(90)
        df = df[df["top_level_label"] != "Sensor Malfunction"]
        X = df[FEATURE_SCHEMA]
        y_top = df["top_level_label"]
        y_sub = df["subtype_label"]

        (
            X_prim,
            y_prim,
            _,
            X_drift,
            y_drift,
            _,
        ) = partition_primary_and_drift(X, y_top, y_sub)

        assert len(X_prim) == len(df)
        assert len(X_drift) == 0
        assert len(y_drift) == 0


# ---------------------------------------------------------------------------
# Suite 3: Model Training (RandomForest and XGBoost on 3 Primary Classes)
# ---------------------------------------------------------------------------

class TestCandidateModelTraining:
    """Validates that candidate models train strictly on 3 primary classes."""

    def test_random_forest_trains_on_3_primary_classes(self):
        df = _make_dummy_dataset(120)
        X = df[FEATURE_SCHEMA]
        y_top = df["top_level_label"]
        y_sub = df["subtype_label"]

        X_prim, y_prim, _, _, _, _ = partition_primary_and_drift(X, y_top, y_sub)

        rf = RandomForestClassifier(n_estimators=10, random_state=42)
        rf.fit(X_prim, y_prim)

        assert set(rf.classes_) == {"Cyber Intrusion", "Natural Fault", "Normal"}
        assert SENSOR_MALFUNCTION_LABEL not in rf.classes_
        assert len(rf.classes_) == 3

    @pytest.mark.skipif(not _HAS_XGB, reason="XGBoost not installed in environment")
    def test_xgboost_trains_on_3_primary_classes_and_decodes(self):
        df = _make_dummy_dataset(120)
        X = df[FEATURE_SCHEMA]
        y_top = df["top_level_label"]
        y_sub = df["subtype_label"]

        X_prim, y_prim, _, _, _, _ = partition_primary_and_drift(X, y_top, y_sub)

        unique_labels = sorted(list(y_prim.unique()))
        label_map = {lbl: idx for idx, lbl in enumerate(unique_labels)}
        label_map_inv = {idx: lbl for lbl, idx in label_map.items()}

        y_enc = y_prim.map(label_map)
        xgb = XGBClassifier(n_estimators=10, max_depth=3, random_state=42, verbosity=0)
        xgb.fit(X_prim, y_enc)

        raw_pred = xgb.predict(X_prim)
        decoded_pred = decode_xgb_predictions(raw_pred, label_map_inv)

        assert set(decoded_pred).issubset({"Cyber Intrusion", "Natural Fault", "Normal"})
        assert SENSOR_MALFUNCTION_LABEL not in decoded_pred

    @pytest.mark.skipif(not _HAS_XGB, reason="XGBoost not installed in environment")
    def test_xgboost_threshold_tuning_with_dynamic_mapping(self):
        df = _make_dummy_dataset(120)
        X = df[FEATURE_SCHEMA]
        y_top = df["top_level_label"]
        y_sub = df["subtype_label"]

        X_prim, y_prim, _, _, _, _ = partition_primary_and_drift(X, y_top, y_sub)
        unique_labels = sorted(list(y_prim.unique()))
        label_map = {lbl: idx for idx, lbl in enumerate(unique_labels)}
        label_map_inv = {idx: lbl for lbl, idx in label_map.items()}

        y_enc = y_prim.map(label_map)
        xgb = XGBClassifier(n_estimators=10, max_depth=3, random_state=42, verbosity=0)
        xgb.fit(X_prim, y_enc)

        xgb_classes_named = [label_map_inv[int(c)] for c in xgb.classes_]
        best_thr, best_f2 = tune_threshold(xgb, X_prim, y_prim, xgb_classes_named)

        assert 0.10 <= best_thr <= 0.60
        assert 0.0 <= best_f2 <= 1.0


# ---------------------------------------------------------------------------
# Suite 4: Evaluation Metrics & Separate Sensor Drift Evaluation
# ---------------------------------------------------------------------------

class TestEvaluationAndSensorDriftMetrics:
    """Verifies sensor drift scenarios are evaluated separately without distorting 3-class metrics."""

    def test_separate_sensor_drift_evaluation(self):
        df = _make_dummy_dataset(120)
        X = df[FEATURE_SCHEMA]
        y_top = df["top_level_label"]
        y_sub = df["subtype_label"]

        X_prim, y_prim, _, X_drift, y_drift, _ = partition_primary_and_drift(X, y_top, y_sub)

        # Train 3-class model
        rf = RandomForestClassifier(n_estimators=15, random_state=42)
        rf.fit(X_prim, y_prim)

        # Evaluate drift scenarios separately
        drift_metrics = evaluate_sensor_drift_scenarios(
            model=rf,
            X_drift=X_drift,
            model_name="RandomForest",
            threshold=0.50,
            classes=list(rf.classes_),
        )

        assert drift_metrics["n_samples"] == 30
        assert "primary_model_verdicts" in drift_metrics
        assert "primary_model_cyber_fp_count" in drift_metrics
        assert "primary_model_cyber_fpr" in drift_metrics
        assert "dedicated_pathway_intercepted" in drift_metrics
        assert "dedicated_pathway_recall" in drift_metrics

        # Since dummy drift features were given valid drift signatures, pathway should intercept them
        assert drift_metrics["dedicated_pathway_intercepted"] == 30
        assert drift_metrics["dedicated_pathway_recall"] == 1.0

    def test_evaluate_sensor_drift_empty_dataframe(self):
        empty_df = pd.DataFrame(columns=FEATURE_SCHEMA)
        res = evaluate_sensor_drift_scenarios(
            model=None,
            X_drift=empty_df,
            model_name="Model",
        )
        assert res["n_samples"] == 0
        assert res["status"] == "no_drift_samples"
        assert res["dedicated_pathway_intercepted"] == 0


# ---------------------------------------------------------------------------
# Suite 5: Dedicated Sensor Drift Detection Pathway
# ---------------------------------------------------------------------------

class TestDedicatedSensorDriftPathway:
    """Validates the physics-network signature check in detect_sensor_drift_signature."""

    def test_sensor_drift_signature_positive(self):
        feats: Dict[str, float] = {k: 0.0 for k in FEATURE_SCHEMA}
        feats["pcd_resid_breadth_count"] = 1.0
        feats["pcd_resid_concentration"] = 0.85
        feats["pcd_voltage_deviation_pu"] = 0.03
        feats["pcd_voltage_dev_nominal"] = 0.03
        feats["pcd_target_rtu_is_flagged"] = 1.0
        feats["pcd_max_lnr"] = 3.2
        feats["nbd_unexpected_write_count"] = 0.0
        feats["nbd_modbus_anomaly_rate"] = 0.0

        assert detect_sensor_drift_signature(feats) is True

    def test_sensor_drift_signature_broad_fault_rejected(self):
        """Widespread multi-sensor residual (breadth >= 2) must NOT trigger sensor drift."""
        feats: Dict[str, float] = {k: 0.0 for k in FEATURE_SCHEMA}
        feats["pcd_resid_breadth_count"] = 3.0
        feats["pcd_resid_concentration"] = 0.35
        feats["pcd_voltage_deviation_pu"] = 0.05
        feats["pcd_target_rtu_is_flagged"] = 1.0
        feats["pcd_max_lnr"] = 4.0

        assert detect_sensor_drift_signature(feats) is False

    def test_sensor_drift_signature_cyber_network_anomaly_rejected(self):
        """Network rogue writes must NOT trigger sensor drift."""
        feats: Dict[str, float] = {k: 0.0 for k in FEATURE_SCHEMA}
        feats["pcd_resid_breadth_count"] = 1.0
        feats["pcd_resid_concentration"] = 0.85
        feats["pcd_voltage_deviation_pu"] = 0.03
        feats["pcd_target_rtu_is_flagged"] = 1.0
        feats["pcd_max_lnr"] = 3.2
        feats["nbd_unexpected_write_count"] = 4.0  # Cyber signal

        assert detect_sensor_drift_signature(feats) is False

    def test_sensor_drift_signature_extreme_voltage_rejected(self):
        """Severe voltage fabrication (> 0.10 pu) must NOT trigger sensor drift."""
        feats: Dict[str, float] = {k: 0.0 for k in FEATURE_SCHEMA}
        feats["pcd_resid_breadth_count"] = 1.0
        feats["pcd_resid_concentration"] = 0.85
        feats["pcd_voltage_deviation_pu"] = 0.22  # Extreme voltage
        feats["pcd_target_rtu_is_flagged"] = 1.0
        feats["pcd_max_lnr"] = 3.2

        assert detect_sensor_drift_signature(feats) is False


# ---------------------------------------------------------------------------
# Suite 6: Deployed Model Immutability & Classifier Service Integrity
# ---------------------------------------------------------------------------

class TestDeployedModelAndClassifierService:
    """Validates that the deployed model artifact has NOT been modified and service functions correctly."""

    def test_deployed_model_bundle_integrity(self):
        backend_dir = Path(__file__).resolve().parent.parent
        model_path = backend_dir / "models" / "fusion_classifier.joblib"
        assert model_path.exists(), f"Missing deployed model artifact at {model_path}"

        bundle = joblib.load(model_path)
        assert bundle["model_name"] == "XGBoost"
        assert bundle["classes"] == ["Cyber Intrusion", "Natural Fault", "Normal"]
        assert len(bundle["classes"]) == 3
        assert bundle["decision_threshold"] == pytest.approx(0.58, rel=1e-2)

    def test_classifier_service_with_sensor_drift(self):
        svc = ClassifierService()
        feats: Dict[str, float] = {k: 0.0 for k in FEATURE_SCHEMA}
        feats["pcd_resid_breadth_count"] = 1.0
        feats["pcd_resid_concentration"] = 0.95
        feats["pcd_voltage_deviation_pu"] = 0.02
        feats["pcd_voltage_dev_nominal"] = 0.02
        feats["pcd_target_rtu_is_flagged"] = 1.0
        feats["pcd_max_lnr"] = 3.2
        feats["nbd_unexpected_write_count"] = 0.0
        feats["nbd_modbus_anomaly_rate"] = 0.0

        res = svc.predict(feats)
        assert res["verdict"] == VerdictLabel("Sensor Malfunction")
        assert res["subtype"] == "sensor_drift"
        assert "Sensor Malfunction" in res["probabilities"]
        assert res["probabilities"]["Sensor Malfunction"] >= 0.80
