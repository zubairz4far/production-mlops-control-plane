"""Frozen evidence verification is strict except for Python patch releases."""

import importlib.util
from pathlib import Path

MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "verify_frozen_lifecycle.py"
spec = importlib.util.spec_from_file_location("verify_frozen_lifecycle", MODULE_PATH)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def example():
    return {
        "runtime": {"python": "3.12.14", "fastapi": "0.141.1"},
        "promotion": {"decision": "PROMOTE", "accuracy": 0.91},
        "rollbacks": 1,
        "lineage": {"sha256": "123abc"},
    }


def test_python_patch_version_drift_is_allowed():
    actual = example()
    actual["runtime"]["python"] = "3.12.15"
    assert module.verify(example(), actual)[0]


def test_different_python_minor_is_not_accepted():
    actual = example()
    actual["runtime"]["python"] = "3.13.0"
    assert not module.verify(example(), actual)[0]


def test_release_decision_metrics_and_lineage_must_match():
    for path, changed in (
        ("promotion", {"decision": "REJECT", "accuracy": 0.91}),
        ("promotion", {"decision": "PROMOTE", "accuracy": 0.90}),
        ("lineage", {"sha256": "tampered"}),
    ):
        actual = example()
        actual[path] = changed
        assert not module.verify(example(), actual)[0]


def test_dependency_version_and_missing_fields_cause_failure():
    actual = example()
    actual["runtime"]["fastapi"] = "0.999.0"
    assert not module.verify(example(), actual)[0]
    actual = example()
    del actual["runtime"]["python"]
    assert not module.verify(example(), actual)[0]
