import hashlib

from fastapi.testclient import TestClient

from mlops_control_plane.api import create_app
from mlops_control_plane.control_plane import ControlPlane
from mlops_control_plane.store import Store


def sha(label: str) -> str:
    return hashlib.sha256(label.encode()).hexdigest()


def test_health_registration_auth_and_metrics() -> None:
    app = create_app(ControlPlane(Store(":memory:")), api_key="test-secret")
    client = TestClient(app)
    assert client.get("/health").json() == {"status": "ok"}
    assert client.get("/models").status_code == 401

    payload = {
        "model_name": "demo",
        "version": "v1",
        "artifact_uri": "s3://registry/demo/v1",
        "artifact_sha256": sha("artifact"),
        "dataset_sha256": sha("dataset"),
        "code_sha": "abcdef123456",
        "eval_samples": 2000,
        "metrics": {"mae": 1.0, "p95_error": 2.0, "schema_validity": 1.0},
    }
    headers = {"X-API-Key": "test-secret"}
    response = client.post("/models", json=payload, headers=headers)
    assert response.status_code == 201
    assert client.get("/models", headers=headers).json()[0]["version"] == "v1"
    metrics = client.get("/metrics").text
    assert "mlops_model_registrations_total 1.0" in metrics


def test_protected_api_fails_closed_without_configured_key() -> None:
    app = create_app(ControlPlane(Store(":memory:")), api_key=None)
    client = TestClient(app)
    assert client.get("/health").status_code == 200
    assert client.get("/models").status_code == 503


def test_duplicate_model_registration_returns_sanitized_conflict() -> None:
    app = create_app(ControlPlane(Store(":memory:")), api_key="test-secret")
    client = TestClient(app)
    payload = {
        "model_name": "demo",
        "version": "v1",
        "artifact_uri": "s3://registry/demo/v1",
        "artifact_sha256": sha("artifact"),
        "dataset_sha256": sha("dataset"),
        "code_sha": "abcdef123456",
        "eval_samples": 2000,
        "metrics": {"mae": 1.0, "p95_error": 2.0, "schema_validity": 1.0},
    }
    headers = {"X-API-Key": "test-secret"}
    assert client.post("/models", json=payload, headers=headers).status_code == 201
    second = client.post("/models", json=payload, headers=headers)
    assert second.status_code == 409
    assert second.json()["detail"] == "model version already registered"
    assert "UNIQUE constraint" not in second.text


def test_unexpected_registration_exception_is_not_disclosed(monkeypatch) -> None:
    control_plane = ControlPlane(Store(":memory:"))

    def broken_registration(_):
        raise RuntimeError("SENSITIVE_INTERNAL_CONNECTION_STRING")

    monkeypatch.setattr(control_plane, "register_model", broken_registration)
    app = create_app(control_plane, api_key="test-secret")
    client = TestClient(app, raise_server_exceptions=False)
    response = client.post(
        "/models",
        headers={"X-API-Key": "test-secret"},
        json={
            "model_name": "demo",
            "version": "v1",
            "artifact_uri": "s3://registry/demo/v1",
            "artifact_sha256": sha("artifact"),
            "dataset_sha256": sha("dataset"),
            "code_sha": "abcdef123456",
            "eval_samples": 2000,
            "metrics": {"mae": 1.0},
        },
    )
    assert response.status_code == 500
    assert "SENSITIVE_INTERNAL_CONNECTION_STRING" not in response.text
