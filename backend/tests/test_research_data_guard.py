from pathlib import Path

import pytest

from app.research.data_access_guard import assert_no_literal_test_reads, guard_dataset_path


def test_runtime_guard_rejects_test_dataset(tmp_path: Path):
    with pytest.raises(PermissionError, match="Test-set lock"):
        guard_dataset_path(tmp_path / "heldout_test.csv", purpose="training")


def test_runtime_guard_allows_non_test_dataset(tmp_path: Path):
    assert guard_dataset_path(tmp_path / "training_seed42.csv", purpose="generation").name == "training_seed42.csv"


def test_static_scan_rejects_literal_test_read(tmp_path: Path):
    source = tmp_path / "reader.py"
    source.write_text("import pandas as pd\npd.read_csv('final_test.csv')\n", encoding="utf-8")
    with pytest.raises(AssertionError, match="Static test-set read"):
        assert_no_literal_test_reads([source])


def test_static_scan_accepts_generation_reader(tmp_path: Path):
    source = tmp_path / "reader.py"
    source.write_text("import pandas as pd\npd.read_csv('training_seed42.csv')\n", encoding="utf-8")
    assert_no_literal_test_reads([source]) is None
