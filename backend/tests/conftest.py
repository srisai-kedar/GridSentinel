"""
Shared test configuration.

The shipped model artifact (models/fusion_classifier.joblib) was trained on
feature schema 2.0.0. The extractor is now schema 3.0.0 (observed-traffic NBD
features). Until a schema-3 model is trained, the pre-existing tests that load
the shipped artifact must opt in to the legacy compatibility mode explicitly.

tests/test_nbd_no_label_leak.py verifies the guard itself with this variable
cleared, so strict behaviour is still tested.
"""
import os

os.environ.setdefault("GRIDSENTINEL_ALLOW_LEGACY_SCHEMA", "1")
