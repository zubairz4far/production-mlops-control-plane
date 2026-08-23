import hashlib
import math
import sqlite3

import pytest

from mlops_control_plane.control_plane import ControlPlane
from mlops_control_plane.schemas import ModelRegistration, PromotionPolicy
from mlops_control_plane.store import Store


def digest(label: str) -> str:
    return hashlib.sha256(label.encode()).hexdigest()


def registration(version: str, mae: float, p95: float = 200.0) -> ModelRegistration:
    return ModelRegistration(
        model_name="forecast",
        version=version,
        artifact_uri=f"s3://registry/forecast/{version}",
        artifact_sha256=digest(f"artifact-{version}"),
        dataset_sha256=digest(f"dataset-{version}"),
        code_sha=digest(f"code-{version}")[:12],
        eval_samples=2000,
        metrics={"mae": mae, "p95_error": p95, "schema_validity": 0.999},
    )


def bootstrap_policy() -> PromotionPolicy:
    return PromotionPolicy(
        primary_metric="mae",
        max_secondary_regression={"p95_error": 0.02},
        minimum_metrics={"schema_validity": 0.99},
        min_eval_samples=1000,
        allow_bootstrap=True,
        min_relative_improvement=0.0,
    )


def candidate_policy() -> PromotionPolicy:
    return PromotionPolicy(
        primary_metric="mae",
        max_secondary_regression={"p95_error": 0.02},
        minimum_metrics={"schema_validity": 0.99},
        min_eval_samples=1000,
        min_relative_improvement=0.05,
    )


def prepared_canary() -> tuple[ControlPlane, dict[str, object], dict[str, object]]:
    control = ControlPlane(Store(":memory:"))
    control.register_model(registration("v1", 100.0))
    assert control.evaluate_model("forecast", "v1", bootstrap_policy()).decision == "PROMOTE"
    first = control.bootstrap_deployment("forecast", "v1")
    control.register_model(registration("v2", 90.0, 198.0))
    assert control.evaluate_model("forecast", "v2", candidate_policy()).decision == "PROMOTE"
    canary = control.create_canary("forecast", "v2", traffic_pct=10.0)
    return control, first, canary


def test_canary_promotion_and_drift_rollback() -> None:
    control, first, canary = prepared_canary()
    assert control.get_deployment(int(first["id"]))["traffic_pct"] == 90.0

    reference = [math.sin(i * 0.1) for i in range(250)]
    safe = [value + 0.01 * math.cos(i * 0.07) for i, value in enumerate(reference)]
    canary_report = control.record_drift(int(canary["id"]), reference, safe)
    assert canary_report["decision"] == "ALLOW"

    active = control.promote_canary(int(canary["id"]))
    assert active["state"] == "ACTIVE"

    shifted = [value + 1.4 for value in reference]
    report = control.record_drift(int(active["id"]), reference, shifted)
    assert report["decision"] == "BLOCK"
    restored = control.rollback(int(active["id"]))
    assert restored["version"] == "v1"
    assert restored["traffic_pct"] == 100.0


def test_canary_cannot_promote_without_allow_drift() -> None:
    control, _, canary = prepared_canary()
    with pytest.raises(ValueError, match="ALLOW drift decision"):
        control.promote_canary(int(canary["id"]))


def test_rejected_model_cannot_be_deployed() -> None:
    control = ControlPlane(Store(":memory:"))
    control.register_model(registration("v1", 100.0))
    control.evaluate_model("forecast", "v1", bootstrap_policy())
    control.bootstrap_deployment("forecast", "v1")
    control.register_model(registration("bad", 110.0))
    result = control.evaluate_model("forecast", "bad", candidate_policy())
    assert result.decision == "REJECT"
    with pytest.raises(ValueError):
        control.create_canary("forecast", "bad")


def test_audit_events_are_database_immutable() -> None:
    store = Store(":memory:")
    control = ControlPlane(store)
    control.register_model(registration("v1", 100.0))
    with pytest.raises(sqlite3.IntegrityError, match="audit events are immutable"):
        with store.transaction() as connection:
            connection.execute("UPDATE audit_events SET event_type = 'TAMPERED' WHERE id = 1")
    with pytest.raises(sqlite3.IntegrityError, match="audit events are immutable"):
        with store.transaction() as connection:
            connection.execute("DELETE FROM audit_events WHERE id = 1")
