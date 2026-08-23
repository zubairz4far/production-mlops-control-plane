from __future__ import annotations

from prometheus_client import CollectorRegistry, Counter, Gauge, generate_latest


class ControlPlaneMetrics:
    def __init__(self) -> None:
        self.registry = CollectorRegistry()
        self.model_registrations = Counter(
            "mlops_model_registrations_total",
            "Registered model versions",
            registry=self.registry,
        )
        self.promotion_decisions = Counter(
            "mlops_promotion_decisions_total",
            "Promotion decisions",
            ["decision"],
            registry=self.registry,
        )
        self.deployment_transitions = Counter(
            "mlops_deployment_transitions_total",
            "Deployment lifecycle transitions",
            ["transition"],
            registry=self.registry,
        )
        self.drift_decisions = Counter(
            "mlops_drift_decisions_total",
            "Drift decisions",
            ["decision"],
            registry=self.registry,
        )
        self.active_production_revision = Gauge(
            "mlops_active_production_revision",
            "Current active production deployment revision",
            registry=self.registry,
        )

    def render(self) -> bytes:
        return generate_latest(self.registry)
