from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.expo.train_v2 import assert_training_path_allowed


def test_training_reader_rejects_held_out_named_path():
    with pytest.raises(ValueError):
        assert_training_path_allowed(Path("heldout_test.csv"))


def test_training_reader_accepts_train_and_validation_names():
    assert_training_path_allowed(Path("train_seed100.csv"))
    assert_training_path_allowed(Path("validation_seed200.csv"))


def test_training_script_has_no_held_out_reader_literal():
    source = Path(__file__).resolve().parents[1] / "scripts" / "expo" / "train_v2.py"
    assert "test" not in source.read_text(encoding="utf-8").lower()
