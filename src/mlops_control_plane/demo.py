from __future__ import annotations

import hashlib
import json
import math
import platform
from collections.abc import Callable
from importlib.metadata import version as package_version
from pathlib import Path

import fastapi
import pydantic
import uvicorn

from .control_plane import ControlPlane
from .schemas import ModelRegistration, PromotionPolicy
from .store import Store


def _hash(label: str) -> str:
    return hashlib.sha256(label.encode()).hexdigest()


def _clock() -> Callable[[], str]:
    counter = 0

    def now() -> str:
        nonlocal counter
        counter += 1
        return f"2026-08-23T00:00:{counter:02d}+00:00"

    return now


def _registration(
    version: str, mae: float, p95: float, schema_validity: float
) -> ModelRegistration:
    return ModelRegistration(
        model_name="portfolio-demand-forecast",
        version=version,
        artifact_uri=f"s3://model-registry/portfolio-demand-forecast/{version}/model.bin",
        artifact_sha256=_hash(f"artifact-{version}"),
        dataset_sha256=_hash(f"dataset-{version}"),
        code_sha=_hash(f"code-{version}")[:12],
        eval_samples=5000,
        metrics={"mae": mae, "p95_error": p95, "schema_validity": schema_validity},
    )


def run_demo() -> dict[str, object]:
    control = ControlPlane(Store(":memory:"), clock=_clock())
    bootstrap_policy = PromotionPolicy(
        primary_metric="mae",
        direction="min",
        min_relative_improvement=0.0,
        maximum_metrics={"mae": 130.0, "p95_error": 300.0},
        minimum_metrics={"schema_validity": 0.99},
        min_eval_samples=1000,
        allow_bootstrap=True,
    )
    candidate_policy = PromotionPolicy(
        primary_metric="mae",
        direction="min",
        min_relative_improvement=0.05,
        max_secondary_regression={"p95_error": 0.02},
        minimum_metrics={"schema_validity": 0.99},
        min_eval_samples=1000,
        allow_bootstrap=False,
    )

    control.register_model(_registration("v1", mae=120.0, p95=260.0, schema_validity=0.999))
    v1_eval = control.evaluate_model("portfolio-demand-forecast", "v1", bootstrap_policy)
    control.bootstrap_deployment("portfolio-demand-forecast", "v1")

    control.register_model(_registration("v2-bad", mae=124.0, p95=275.0, schema_validity=0.998))
    bad_eval = control.evaluate_model("portfolio-demand-forecast", "v2-bad", candidate_policy)

    control.register_model(_registration("v3", mae=106.0, p95=252.0, schema_validity=0.9995))
    good_eval = control.evaluate_model("portfolio-demand-forecast", "v3", candidate_policy)
    canary = control.create_canary("portfolio-demand-forecast", "v3", traffic_pct=10.0)

    reference = [math.sin(i * 0.17) + 0.3 * math.cos(i * 0.031) for i in range(500)]
    safe_current = [value + 0.02 * math.sin(i * 0.11) for i, value in enumerate(reference)]
    canary_drift = control.record_drift(int(canary["id"]), reference, safe_current)
    promoted = control.promote_canary(int(canary["id"]))

    shifted_current = [value + 1.4 for value in reference]
    production_drift = control.record_drift(int(promoted["id"]), reference, shifted_current)
    restored = control.rollback(int(promoted["id"]))

    models = control.list_models()
    deployments = control.list_deployments()
    audit = control.audit_events()
    active_prod = [
        row
        for row in deployments
        if row["environment"] == "production"
        and row["state"] == "ACTIVE"
        and float(row["traffic_pct"]) == 100.0
    ]
    rejected_ids = {row["id"] for row in models if row["stage"] == "REJECTED"}
    deployed_model_ids = {row["model_id"] for row in deployments}
    invariants = {
        "exactly_one_active_production": len(active_prod) == 1,
        "bad_candidate_never_deployed": rejected_ids.isdisjoint(deployed_model_ids),
        "rollback_restored_v1": restored["version"] == "v1" and restored["state"] == "ACTIVE",
        "all_models_have_lineage_hashes": all(
            len(str(row["artifact_sha256"])) == 64 and len(str(row["dataset_sha256"])) == 64
            for row in models
        ),
        "critical_drift_blocks": production_drift["decision"] == "BLOCK",
        "safe_canary_allowed": canary_drift["decision"] == "ALLOW",
    }
    release_pass = (
        v1_eval.decision == "PROMOTE"
        and bad_eval.decision == "REJECT"
        and good_eval.decision == "PROMOTE"
        and all(invariants.values())
    )
    return {
        "release": "v0.1",
        "scenario": {
            "registered_models": len(models),
            "audit_events": len(audit),
            "production_revisions": len(
                [row for row in deployments if row["environment"] == "production"]
            ),
        },
        "promotion_policy": candidate_policy.model_dump(),
        "decisions": {
            "bootstrap_v1": v1_eval.model_dump(),
            "bad_candidate_v2": bad_eval.model_dump(),
            "good_candidate_v3": good_eval.model_dump(),
        },
        "drift": {
            "canary": {
                key: canary_drift[key]
                for key in ["psi", "ks_stat", "mean_shift_sigma", "severity", "decision"]
            },
            "production_shift": {
                key: production_drift[key]
                for key in ["psi", "ks_stat", "mean_shift_sigma", "severity", "decision"]
            },
        },
        "deployment_lifecycle": [
            {
                "revision": row["revision"],
                "version": row["version"],
                "state": row["state"],
                "traffic_pct": row["traffic_pct"],
                "previous_deployment_id": row["previous_deployment_id"],
            }
            for row in deployments
        ],
        "final_production": {
            "version": active_prod[0]["version"],
            "revision": active_prod[0]["revision"],
            "traffic_pct": active_prod[0]["traffic_pct"],
        },
        "invariants": invariants,
        "release_gate": {
            "decision": "PASS" if release_pass else "FAIL",
            "rule": (
                "bootstrap/promotion/rejection, safe canary, critical drift block, rollback, "
                "lineage, and single-active-production invariants must all hold"
            ),
        },
        "runtime": {
            "python": platform.python_version(),
            "fastapi": fastapi.__version__,
            "pydantic": pydantic.__version__,
            "prometheus_client": package_version("prometheus-client"),
            "uvicorn": uvicorn.__version__,
        },
    }


def write_demo(path: str | Path) -> dict[str, object]:
    report = run_demo()
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return report
