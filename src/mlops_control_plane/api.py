from __future__ import annotations

import os
import secrets
from typing import Annotated

from fastapi import Depends, FastAPI, Header, HTTPException, Response

from .control_plane import ControlPlane
from .schemas import CanaryRequest, DriftRequest, ModelRegistration, PromotionPolicy
from .store import Store


def create_app(
    control_plane: ControlPlane | None = None,
    *,
    api_key: str | None = None,
) -> FastAPI:
    if control_plane is None:
        database_path = os.getenv("CONTROL_PLANE_DB", "/tmp/control-plane.db")
        control_plane = ControlPlane(Store(database_path))
    configured_api_key = api_key if api_key is not None else os.getenv("CONTROL_PLANE_API_KEY")

    app = FastAPI(title="Production MLOps Control Plane", version="0.1.0")
    app.state.control_plane = control_plane

    def require_api_key(
        supplied_key: Annotated[str | None, Header(alias="X-API-Key")] = None,
    ) -> None:
        if not configured_api_key:
            raise HTTPException(status_code=503, detail="control-plane API key is not configured")
        if supplied_key is None or not secrets.compare_digest(supplied_key, configured_api_key):
            raise HTTPException(status_code=401, detail="invalid API key")

    protected = [Depends(require_api_key)]

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/models", dependencies=protected)
    def models() -> list[dict[str, object]]:
        return control_plane.list_models()

    @app.post("/models", status_code=201, dependencies=protected)
    def register_model(payload: ModelRegistration) -> dict[str, object]:
        try:
            return control_plane.register_model(payload)
        except Exception as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @app.post("/models/{model_name}/{version}/evaluate", dependencies=protected)
    def evaluate(model_name: str, version: str, policy: PromotionPolicy) -> dict[str, object]:
        try:
            return control_plane.evaluate_model(model_name, version, policy).model_dump()
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @app.post("/deployments/bootstrap", dependencies=protected)
    def bootstrap(request: CanaryRequest) -> dict[str, object]:
        try:
            return control_plane.bootstrap_deployment(
                request.model_name,
                request.version,
                request.environment,
            )
        except (KeyError, ValueError) as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @app.post("/deployments/canary", status_code=201, dependencies=protected)
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

    @app.post("/deployments/{deployment_id}/promote", dependencies=protected)
    def promote(deployment_id: int) -> dict[str, object]:
        try:
            return control_plane.promote_canary(deployment_id)
        except (KeyError, ValueError) as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @app.post("/deployments/{deployment_id}/drift", dependencies=protected)
    def drift(deployment_id: int, request: DriftRequest) -> dict[str, object]:
        try:
            return control_plane.record_drift(deployment_id, request.reference, request.current)
        except (KeyError, ValueError) as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @app.post("/deployments/{deployment_id}/rollback", dependencies=protected)
    def rollback(deployment_id: int) -> dict[str, object]:
        try:
            return control_plane.rollback(deployment_id)
        except (KeyError, ValueError) as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @app.get("/deployments", dependencies=protected)
    def deployments() -> list[dict[str, object]]:
        return control_plane.list_deployments()

    @app.get("/audit", dependencies=protected)
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
