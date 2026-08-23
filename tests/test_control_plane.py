import hashlib
import math

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


def test_canary_promotion_and_drift_rollback() -> None:
    control = ControlPlane(Store(":memory:"))
    control.register_model(registration("v1", 100.0))
    assert control.evaluate_model("forecast", "v1", bootstrap_policy()).decision == "PROMOTE"
    first = control.bootstrap_deployment("forecast", "v1")

    control.register_model(registration("v2", 90.0, 198.0))
    assert control.evaluate_model("forecast", "v2", candidate_policy()).decision == "PROMOTE"
    canary = control.create_canary("forecast", "v2", traffic_pct=10.0)
    assert control.get_deployment(int(first["id"]))["traffic_pct"] == 90.0
    active = control.promote_canary(int(canary["id"]))
    assert active["state"] == "ACTIVE"

    reference = [math.sin(i * 0.1) for i in range(250)]
    shifted = [value + 1.4 for value in reference]
    report = control.record_drift(int(active["id"]), reference, shifted)
    assert report["decision"] == "BLOCK"
    restored = control.rollback(int(active["id"]))
    assert restored["version"] == "v1"
    assert restored["traffic_pct"] == 100.0


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
