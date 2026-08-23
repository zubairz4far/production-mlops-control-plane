from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime

from .drift import evaluate_drift
from .metrics import ControlPlaneMetrics
from .policy import evaluate_promotion
from .schemas import DriftThresholds, ModelRegistration, PromotionPolicy, PromotionResult
from .store import Store

Clock = Callable[[], str]


def utc_clock() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


class ControlPlane:
    def __init__(
        self,
        store: Store | None = None,
        *,
        clock: Clock = utc_clock,
        metrics: ControlPlaneMetrics | None = None,
    ) -> None:
        self.store = store or Store()
        self.clock = clock
        self.metrics = metrics or ControlPlaneMetrics()

    def _audit(
        self,
        connection,
        event_type: str,
        entity_type: str,
        entity_id: int | None,
        payload: dict[str, object],
        now: str,
    ) -> None:
        connection.execute(
            (
                "INSERT INTO audit_events("
                "event_type, entity_type, entity_id, payload_json, created_at"
                ") VALUES (?, ?, ?, ?, ?)"
            ),
            (event_type, entity_type, entity_id, self.store.dumps(payload), now),
        )

    def register_model(self, registration: ModelRegistration) -> dict[str, object]:
        now = self.clock()
        with self.store.transaction() as connection:
            cursor = connection.execute(
                """
                INSERT INTO models(
                    model_name, version, artifact_uri, artifact_sha256, dataset_sha256,
                    code_sha, eval_samples, metrics_json, stage, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'REGISTERED', ?)
                """,
                (
                    registration.model_name,
                    registration.version,
                    registration.artifact_uri,
                    registration.artifact_sha256,
                    registration.dataset_sha256,
                    registration.code_sha,
                    registration.eval_samples,
                    self.store.dumps(registration.metrics),
                    now,
                ),
            )
            model_id = int(cursor.lastrowid)
            self._audit(
                connection,
                "MODEL_REGISTERED",
                "model",
                model_id,
                {
                    "model_name": registration.model_name,
                    "version": registration.version,
                    "artifact_sha256": registration.artifact_sha256,
                    "dataset_sha256": registration.dataset_sha256,
                    "code_sha": registration.code_sha,
                },
                now,
            )
        self.metrics.model_registrations.inc()
        return self.get_model(registration.model_name, registration.version)

    def get_model(self, model_name: str, version: str) -> dict[str, object]:
        row = self.store.fetchone(
            "SELECT * FROM models WHERE model_name = ? AND version = ?",
            (model_name, version),
        )
        if row is None:
            raise KeyError(f"model {model_name}:{version} not found")
        row["metrics"] = self.store.loads(str(row.pop("metrics_json")))
        return row

    def list_models(self) -> list[dict[str, object]]:
        rows = self.store.fetchall("SELECT * FROM models ORDER BY id")
        for row in rows:
            row["metrics"] = self.store.loads(str(row.pop("metrics_json")))
        return rows

    def _production_champion(self, model_name: str) -> dict[str, object] | None:
        row = self.store.fetchone(
            """
            SELECT m.* FROM models m
            JOIN deployments d ON d.model_id = m.id
            WHERE m.model_name = ? AND d.environment = 'production'
              AND d.state = 'ACTIVE' AND d.traffic_pct = 100
            ORDER BY d.revision DESC LIMIT 1
            """,
            (model_name,),
        )
        if row is not None:
            row["metrics"] = self.store.loads(str(row.pop("metrics_json")))
        return row

    def evaluate_model(
        self,
        model_name: str,
        version: str,
        policy: PromotionPolicy,
    ) -> PromotionResult:
        candidate = self.get_model(model_name, version)
        champion = self._production_champion(model_name)
        champion_metrics = champion["metrics"] if champion is not None else None
        evaluation = evaluate_promotion(
            candidate["metrics"],
            int(candidate["eval_samples"]),
            policy,
            champion_metrics,
        )
        stage = "VALIDATED" if evaluation.decision == "PROMOTE" else "REJECTED"
        now = self.clock()
        with self.store.transaction() as connection:
            connection.execute("UPDATE models SET stage = ? WHERE id = ?", (stage, candidate["id"]))
            connection.execute(
                """
                INSERT INTO promotion_events(
                    model_id, champion_model_id, decision, reasons_json, policy_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    candidate["id"],
                    champion["id"] if champion is not None else None,
                    evaluation.decision,
                    self.store.dumps(evaluation.reasons),
                    self.store.dumps(policy.model_dump()),
                    now,
                ),
            )
            self._audit(
                connection,
                "PROMOTION_EVALUATED",
                "model",
                int(candidate["id"]),
                {
                    "decision": evaluation.decision,
                    "reasons": evaluation.reasons,
                    "champion_version": champion["version"] if champion is not None else None,
                    "primary_relative_improvement": evaluation.primary_relative_improvement,
                },
                now,
            )
        self.metrics.promotion_decisions.labels(decision=evaluation.decision).inc()
        return PromotionResult(
            decision=evaluation.decision,
            reasons=evaluation.reasons,
            candidate_stage=stage,
            champion_version=str(champion["version"]) if champion is not None else None,
            primary_relative_improvement=evaluation.primary_relative_improvement,
        )

    def _next_revision(self, environment: str, connection) -> int:
        row = connection.execute(
            "SELECT COALESCE(MAX(revision), 0) AS revision FROM deployments WHERE environment = ?",
            (environment,),
        ).fetchone()
        return int(row["revision"]) + 1

    def bootstrap_deployment(
        self, model_name: str, version: str, environment: str = "production"
    ) -> dict[str, object]:
        model = self.get_model(model_name, version)
        if model["stage"] != "VALIDATED":
            raise ValueError("bootstrap deployment requires a VALIDATED model")
        now = self.clock()
        with self.store.transaction() as connection:
            existing = connection.execute(
                "SELECT id FROM deployments WHERE environment = ? AND state = 'ACTIVE'",
                (environment,),
            ).fetchone()
            if existing is not None:
                raise ValueError(f"{environment} already has an active deployment")
            revision = self._next_revision(environment, connection)
            cursor = connection.execute(
                """
                INSERT INTO deployments(
                    environment, revision, model_id, state, traffic_pct,
                    previous_deployment_id, created_at, updated_at
                ) VALUES (?, ?, ?, 'ACTIVE', 100, NULL, ?, ?)
                """,
                (environment, revision, model["id"], now, now),
            )
            deployment_id = int(cursor.lastrowid)
            if environment == "production":
                connection.execute(
                    "UPDATE models SET stage = 'PRODUCTION' WHERE id = ?",
                    (model["id"],),
                )
            self._audit(
                connection,
                "DEPLOYMENT_BOOTSTRAPPED",
                "deployment",
                deployment_id,
                {"environment": environment, "revision": revision, "version": version},
                now,
            )
        self.metrics.deployment_transitions.labels(transition="bootstrap").inc()
        if environment == "production":
            self.metrics.active_production_revision.set(revision)
        return self.get_deployment(deployment_id)

    def create_canary(
        self,
        model_name: str,
        version: str,
        *,
        environment: str = "production",
        traffic_pct: float = 10.0,
    ) -> dict[str, object]:
        model = self.get_model(model_name, version)
        if model["stage"] != "VALIDATED":
            raise ValueError("canary deployment requires a VALIDATED model")
        now = self.clock()
        with self.store.transaction() as connection:
            active = connection.execute(
                """
                SELECT * FROM deployments
                WHERE environment = ? AND state = 'ACTIVE' AND traffic_pct = 100
                ORDER BY revision DESC LIMIT 1
                """,
                (environment,),
            ).fetchone()
            if active is None:
                raise ValueError(f"{environment} has no 100% active deployment")
            revision = self._next_revision(environment, connection)
            connection.execute(
                "UPDATE deployments SET traffic_pct = ?, updated_at = ? WHERE id = ?",
                (100.0 - traffic_pct, now, active["id"]),
            )
            cursor = connection.execute(
                """
                INSERT INTO deployments(
                    environment, revision, model_id, state, traffic_pct,
                    previous_deployment_id, created_at, updated_at
                ) VALUES (?, ?, ?, 'CANARY', ?, ?, ?, ?)
                """,
                (environment, revision, model["id"], traffic_pct, active["id"], now, now),
            )
            deployment_id = int(cursor.lastrowid)
            self._audit(
                connection,
                "CANARY_STARTED",
                "deployment",
                deployment_id,
                {
                    "environment": environment,
                    "revision": revision,
                    "traffic_pct": traffic_pct,
                    "previous_deployment_id": int(active["id"]),
                },
                now,
            )
        self.metrics.deployment_transitions.labels(transition="canary_started").inc()
        return self.get_deployment(deployment_id)

    def promote_canary(self, deployment_id: int) -> dict[str, object]:
        deployment = self.get_deployment(deployment_id)
        if deployment["state"] != "CANARY":
            raise ValueError("only a CANARY deployment can be promoted")
        latest_drift = self.store.fetchone(
            """
            SELECT decision FROM drift_reports
            WHERE deployment_id = ?
            ORDER BY id DESC LIMIT 1
            """,
            (deployment_id,),
        )
        if latest_drift is None:
            raise ValueError("canary promotion requires an ALLOW drift decision")
        if latest_drift["decision"] != "ALLOW":
            raise ValueError(
                f"canary promotion blocked by drift decision {latest_drift['decision']}"
            )
        now = self.clock()
        previous_id = deployment["previous_deployment_id"]
        with self.store.transaction() as connection:
            connection.execute(
                (
                    "UPDATE deployments SET state = 'ACTIVE', traffic_pct = 100, "
                    "updated_at = ? WHERE id = ?"
                ),
                (now, deployment_id),
            )
            connection.execute(
                (
                    "UPDATE deployments SET state = 'SUPERSEDED', traffic_pct = 0, "
                    "updated_at = ? WHERE id = ?"
                ),
                (now, previous_id),
            )
            model_id = int(deployment["model_id"])
            connection.execute("UPDATE models SET stage = 'PRODUCTION' WHERE id = ?", (model_id,))
            previous_model = connection.execute(
                "SELECT model_id FROM deployments WHERE id = ?", (previous_id,)
            ).fetchone()
            if previous_model is not None and int(previous_model["model_id"]) != model_id:
                connection.execute(
                    "UPDATE models SET stage = 'ARCHIVED' WHERE id = ?",
                    (previous_model["model_id"],),
                )
            self._audit(
                connection,
                "CANARY_PROMOTED",
                "deployment",
                deployment_id,
                {"previous_deployment_id": previous_id},
                now,
            )
        self.metrics.deployment_transitions.labels(transition="canary_promoted").inc()
        if deployment["environment"] == "production":
            self.metrics.active_production_revision.set(int(deployment["revision"]))
        return self.get_deployment(deployment_id)

    def record_drift(
        self,
        deployment_id: int,
        reference: list[float],
        current: list[float],
        thresholds: DriftThresholds | None = None,
    ) -> dict[str, object]:
        deployment = self.get_deployment(deployment_id)
        if deployment["state"] not in {"CANARY", "ACTIVE"}:
            raise ValueError("drift can only be evaluated for CANARY or ACTIVE deployments")
        metrics = evaluate_drift(reference, current, thresholds)
        now = self.clock()
        with self.store.transaction() as connection:
            cursor = connection.execute(
                """
                INSERT INTO drift_reports(
                    deployment_id, psi, ks_stat, mean_shift_sigma, sample_size,
                    severity, decision, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    deployment_id,
                    metrics.psi,
                    metrics.ks_stat,
                    metrics.mean_shift_sigma,
                    metrics.sample_size,
                    metrics.severity,
                    metrics.decision,
                    now,
                ),
            )
            report_id = int(cursor.lastrowid)
            self._audit(
                connection,
                "DRIFT_EVALUATED",
                "deployment",
                deployment_id,
                {
                    "report_id": report_id,
                    "decision": metrics.decision,
                    "severity": metrics.severity,
                    "psi": metrics.psi,
                    "ks_stat": metrics.ks_stat,
                    "mean_shift_sigma": metrics.mean_shift_sigma,
                },
                now,
            )
        self.metrics.drift_decisions.labels(decision=metrics.decision).inc()
        return {
            "id": report_id,
            "deployment_id": deployment_id,
            **metrics.__dict__,
            "created_at": now,
        }

    def rollback(
        self, deployment_id: int, *, require_blocked_drift: bool = True
    ) -> dict[str, object]:
        deployment = self.get_deployment(deployment_id)
        if deployment["state"] != "ACTIVE":
            raise ValueError("rollback requires the current ACTIVE deployment")
        previous_id = deployment["previous_deployment_id"]
        if previous_id is None:
            raise ValueError("deployment has no rollback target")
        if require_blocked_drift:
            blocked = self.store.fetchone(
                """
                SELECT id FROM drift_reports
                WHERE deployment_id = ? AND decision = 'BLOCK'
                ORDER BY id DESC LIMIT 1
                """,
                (deployment_id,),
            )
            if blocked is None:
                raise ValueError("rollback requires a BLOCK drift decision")
        now = self.clock()
        with self.store.transaction() as connection:
            previous = connection.execute(
                "SELECT * FROM deployments WHERE id = ?", (previous_id,)
            ).fetchone()
            if previous is None:
                raise ValueError("rollback target no longer exists")
            connection.execute(
                (
                    "UPDATE deployments SET state = 'ROLLED_BACK', traffic_pct = 0, "
                    "updated_at = ? WHERE id = ?"
                ),
                (now, deployment_id),
            )
            connection.execute(
                (
                    "UPDATE deployments SET state = 'ACTIVE', traffic_pct = 100, "
                    "updated_at = ? WHERE id = ?"
                ),
                (now, previous_id),
            )
            connection.execute(
                "UPDATE models SET stage = 'ARCHIVED' WHERE id = ?",
                (deployment["model_id"],),
            )
            connection.execute(
                "UPDATE models SET stage = 'PRODUCTION' WHERE id = ?",
                (previous["model_id"],),
            )
            self._audit(
                connection,
                "DEPLOYMENT_ROLLED_BACK",
                "deployment",
                deployment_id,
                {"restored_deployment_id": previous_id},
                now,
            )
        self.metrics.deployment_transitions.labels(transition="rollback").inc()
        if deployment["environment"] == "production":
            self.metrics.active_production_revision.set(int(previous["revision"]))
        return self.get_deployment(int(previous_id))

    def get_deployment(self, deployment_id: int) -> dict[str, object]:
        row = self.store.fetchone(
            """
            SELECT d.*, m.model_name, m.version
            FROM deployments d JOIN models m ON m.id = d.model_id
            WHERE d.id = ?
            """,
            (deployment_id,),
        )
        if row is None:
            raise KeyError(f"deployment {deployment_id} not found")
        return row

    def list_deployments(self) -> list[dict[str, object]]:
        return self.store.fetchall(
            """
            SELECT d.*, m.model_name, m.version
            FROM deployments d JOIN models m ON m.id = d.model_id
            ORDER BY d.environment, d.revision
            """
        )

    def audit_events(self) -> list[dict[str, object]]:
        rows = self.store.fetchall("SELECT * FROM audit_events ORDER BY id")
        for row in rows:
            row["payload"] = self.store.loads(str(row.pop("payload_json")))
        return rows
