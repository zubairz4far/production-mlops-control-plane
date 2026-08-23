import hashlib

from fastapi.testclient import TestClient

from mlops_control_plane.api import create_app
from mlops_control_plane.control_plane import ControlPlane
from mlops_control_plane.store import Store


def sha(label: str) -> str:
    return hashlib.sha256(label.encode()).hexdigest()


def test_health_registration_and_metrics() -> None:
    app = create_app(ControlPlane(Store(":memory:")))
    client = TestClient(app)
    assert client.get("/health").json() == {"status": "ok"}

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
    response = client.post("/models", json=payload)
    assert response.status_code == 201
    assert client.get("/models").json()[0]["version"] == "v1"
    metrics = client.get("/metrics").text
    assert "mlops_model_registrations_total 1.0" in metrics
