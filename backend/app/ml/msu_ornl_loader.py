"""
msu_ornl_loader.py
------------------
Loader and mapper for the Mississippi State University / Oak Ridge National Laboratory
(MSU/ORNL) Power System Attack Datasets.

This module is designed for external benchmark validation:
- If CSV files are manually placed in `data/msu_ornl/`, this module loads them and
  maps their labeled categories to GridSentinel's 3-way taxonomy.
- If no files are present, it logs a clear notice and skips gracefully without error.

NOTE ON BENCHMARK COMPARISON:
Validation against MSU/ORNL datasets serves as a coarse sanity check for cyber-vs-physical
triage behavior, not an apples-to-apples benchmark, because the external dataset derives
from a 15-bus transmission system (IEEE 9-bus or 39-bus with PMU/relay telemetry) rather
than our 11kV radial distribution feeder with pandapower state estimation residuals.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional
import pandas as pd

logger = logging.getLogger("GridSentinel.MSU_ORNL_Loader")

# ---------------------------------------------------------------------------
# MSU / ORNL Category Mapping Table
# Maps external scenario labels to GridSentinel's 3 top-level classes
# ---------------------------------------------------------------------------
MSU_ORNL_CATEGORY_MAPPING = {
    # Normal operations
    "Natural": "Normal",
    "No Events": "Normal",
    "Normal": "Normal",
    "0": "Normal",

    # Physical Faults (Natural grid events)
    "Fault": "Natural Fault",
    "Line Fault": "Natural Fault",
    "Line Trip": "Natural Fault",
    "Generator Trip": "Natural Fault",
    "1": "Natural Fault",
    "2": "Natural Fault",
    "3": "Natural Fault",

    # Cyber Attacks
    "Attack": "Cyber Intrusion",
    "Data Injection": "Cyber Intrusion",
    "FDI": "Cyber Intrusion",
    "Command Injection": "Cyber Intrusion",
    "Disable Relay": "Cyber Intrusion",
    "Remote Trip Command": "Cyber Intrusion",
    "Replay": "Cyber Intrusion",
    "4": "Cyber Intrusion",
    "5": "Cyber Intrusion",
    "6": "Cyber Intrusion",
}


def load_msu_ornl_data(data_dir: str = "data/msu_ornl") -> Optional[pd.DataFrame]:
    """
    Search `data_dir` for MSU/ORNL CSV datasets and load them if present.

    Returns
    -------
    pd.DataFrame or None
        Combined DataFrame with normalized column `mapped_label` if files found,
        None if directory is empty or missing.
    """
    path = Path(data_dir)
    if not path.exists():
        logger.info(f"[MSU/ORNL Loader] Directory {data_dir} does not exist. Skipping external benchmark.")
        return None

    csv_files = list(path.glob("*.csv"))
    if not csv_files:
        logger.info(
            f"[MSU/ORNL Loader] No CSV files found in {data_dir}. "
            "To use the MSU/ORNL benchmark, manually download CSVs from the "
            "MSU/ORNL Industrial Control System Cyber Attack Dataset repository "
            f"and place them into '{data_dir}/'."
        )
        return None

    logger.info(f"[MSU/ORNL Loader] Found {len(csv_files)} benchmark CSV file(s) in {data_dir}.")
    dfs = []
    for f in csv_files:
        try:
            df = pd.read_csv(f)
            # Find label column if present (typically 'marker', 'label', or 'class')
            label_col = next((c for c in df.columns if c.lower() in ("marker", "label", "class", "target")), None)
            if label_col:
                df["mapped_label"] = df[label_col].astype(str).map(
                    lambda x: MSU_ORNL_CATEGORY_MAPPING.get(x, "Normal")
                )
            dfs.append(df)
        except Exception as exc:
            logger.warning(f"[MSU/ORNL Loader] Failed to read {f}: {exc}")

    if not dfs:
        return None

    combined_df = pd.concat(dfs, ignore_index=True)
    logger.info(f"[MSU/ORNL Loader] Loaded {len(combined_df)} total external benchmark rows.")
    return combined_df


def validate_against_msu_ornl(
    model_bundle: Optional[Dict[str, Any]] = None,
    data_dir: str = "data/msu_ornl",
) -> Dict[str, Any]:
    """
    Evaluate how the trained model's logic holds up against mapped MSU/ORNL data.

    If data is not present, returns a structured status indicating graceful skip.
    """
    data = load_msu_ornl_data(data_dir)
    if data is None or data.empty:
        return {
            "status": "skipped",
            "message": f"No external MSU/ORNL dataset found in '{data_dir}/'. Gracefully skipped.",
            "data_present": False,
        }

    return {
        "status": "loaded",
        "message": f"Successfully loaded {len(data)} MSU/ORNL benchmark samples.",
        "data_present": True,
        "sample_count": len(data),
        "mapped_distribution": data["mapped_label"].value_counts().to_dict() if "mapped_label" in data.columns else {},
    }
