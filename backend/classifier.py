"""
classifier.py
-------------
Root-level wrapper and re-export for GridSentinel ClassifierService.
Ensures direct imports like `import backend.classifier` or `from backend.classifier import ...`
resolve seamlessly.
"""

from app.ml.classifier_service import (
    ClassifierService,
    VerdictLabel,
    evaluate_residual_disagreement,
    classifier_service,
)

__all__ = [
    "ClassifierService",
    "VerdictLabel",
    "evaluate_residual_disagreement",
    "classifier_service",
]
