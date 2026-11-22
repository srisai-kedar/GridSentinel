from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parents[2] / "scripts"))
from leakage_audit import compare_feature_dicts, static_provenance_violations
from p2_report import parse_pytest_counts
from app.research.data_access_guard import assert_no_literal_test_reads, guard_dataset_path


def test_static_provenance_scan_rejects_scenario_import(tmp_path: Path):
    source = tmp_path / "feature.py"
    source.write_text("from app.ot import scenario_injector\n", encoding="utf-8")
    assert static_provenance_violations([source])


def test_static_provenance_scan_accepts_observation_module(tmp_path: Path):
    source = tmp_path / "feature.py"
    source.write_text("import numpy as np\n", encoding="utf-8")
    assert static_provenance_violations([source]) == []


def test_blind_comparison_tolerates_timing_only_difference():
    result = compare_feature_dicts({"nbd_mean_response_time_ms": 1.0, "x": 2.0}, {"nbd_mean_response_time_ms": 1.000001, "x": 2.0})
    assert result["passed"]


def test_blind_comparison_detects_extra_canary_feature():
    result = compare_feature_dicts({"x": 1.0, "leak_attack_active": 1.0}, {"x": 1.0})
    assert not result["passed"]


def test_runtime_test_set_guard_rejects_test_path(tmp_path: Path):
    test_path = tmp_path / "candidate_test.csv"
    test_path.write_text("x\n1\n", encoding="utf-8")
    try:
        guard_dataset_path(test_path, purpose="unit test")
    except PermissionError:
        pass
    else:
        raise AssertionError("test-set guard accepted a test path")


def test_static_test_set_guard_rejects_literal_test_read(tmp_path: Path):
    source = tmp_path / "reader.py"
    source.write_text("import pandas as pd\npd.read_csv('fixture_test.csv')\n", encoding="utf-8")
    try:
        assert_no_literal_test_reads([source])
    except AssertionError:
        pass
    else:
        raise AssertionError("static guard accepted a literal test read")


def test_pytest_summary_parser_reads_counts(tmp_path: Path):
    output = tmp_path / "pytest.txt"
    output.write_text("1 failed, 6 passed, 2 warnings in 1.2s\n", encoding="utf-8")
    assert parse_pytest_counts(output) == {
        "failed": 1,
        "passed": 6,
        "warnings": 2,
        "raw_summary": "1 failed, 6 passed, 2 warnings",
    }
