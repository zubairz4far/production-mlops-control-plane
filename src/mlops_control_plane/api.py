from __future__ import annotations

import os

from fastapi import FastAPI, HTTPException, Response

from .control_plane import ControlPlane
from .schemas import CanaryRequest, DriftRequest, ModelRegistration, PromotionPolicy
from .store import Store


def create_app(control_plane: ControlPlane | None = None) -> FastAPI:
    if control_plane is None:
        database_path = os.getenv("CONTROL_PLANE_DB", "/tmp/control-plane.db")
        control_plane = ControlPlane(Store(database_path))

    app = FastAPI(title="Production MLOps Control Plane", version="0.1.0")
    app.state.control_plane = control_plane

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/models")
    def models() -> list[dict[str, object]]:
        return control_plane.list_models()

    @app.post("/models", status_code=201)
    def register_model(payload: ModelRegistration) -> dict[str, object]:
        try:
            return control_plane.register_model(payload)
        except Exception as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @app.post("/models/{model_name}/{version}/evaluate")
    def evaluate(model_name: str, version: str, policy: PromotionPolicy) -> dict[str, object]:
        try:
            return control_plane.evaluate_model(model_name, version, policy).model_dump()
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @app.post("/deployments/bootstrap")
    def bootstrap(request: CanaryRequest) -> dict[str, object]:
        try:
            return control_plane.bootstrap_deployment(
                request.model_name,
                request.version,
                request.environment,
            )
        except (KeyError, ValueError) as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @app.post("/deployments/canary", status_code=201)
    def canary(request: CanaryRequest) -> dict[str, object]:
        try:
            return control_plane.create_canary(
                request.model_name,
                request.version,
                environment=request.environment,
                traffic_pct=request.traffic_pct,
            )
        except (KeyError, ValueError) as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @app.post("/deployments/{deployment_id}/promote")
    def promote(deployment_id: int) -> dict[str, object]:
        try:
            return control_plane.promote_canary(deployment_id)
        except (KeyError, ValueError) as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @app.post("/deployments/{deployment_id}/drift")
    def drift(deployment_id: int, request: DriftRequest) -> dict[str, object]:
        try:
            return control_plane.record_drift(deployment_id, request.reference, request.current)
        except (KeyError, ValueError) as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @app.post("/deployments/{deployment_id}/rollback")
    def rollback(deployment_id: int) -> dict[str, object]:
        try:
            return control_plane.rollback(deployment_id)
        except (KeyError, ValueError) as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @app.get("/deployments")
    def deployments() -> list[dict[str, object]]:
        return control_plane.list_deployments()

    @app.get("/audit")
    def audit() -> list[dict[str, object]]:
        return control_plane.audit_events()

    @app.get("/metrics")
    def metrics() -> Response:
        return Response(
            content=control_plane.metrics.render(),
            media_type="text/plain; version=0.0.4; charset=utf-8",
        )

    return app


app = create_app()
