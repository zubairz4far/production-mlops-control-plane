# Production MLOps Control Plane

[![CI](https://github.com/zubairz4far/production-mlops-control-plane/actions/workflows/ci.yml/badge.svg)](https://github.com/zubairz4far/production-mlops-control-plane/actions/workflows/ci.yml)

Auditable model promotion, lineage, canary deployment, drift policy, rollback, API security, and observability in one small production-style control plane.

## Status

**v0.1 — evaluated deterministic control-plane lifecycle.**

The frozen benchmark registers three model versions, records 12 audit events, exercises two production revisions, rejects a regressing candidate, promotes an improving candidate, requires a clean canary drift decision, detects a critical production distribution shift, and verifies rollback to the previous production revision.

Machine-readable evidence: [`evals/results/v0.1_control_plane.json`](evals/results/v0.1_control_plane.json).

## Headline lifecycle result

| Step | Result |
|---|---|
| Bootstrap `v1` | **PROMOTE** and deploy at 100% production traffic |
| Candidate `v2-bad` | **REJECT**: MAE regresses 3.33% and p95 guard is breached |
| Candidate `v3` | **PROMOTE**: primary MAE improves **11.67%** vs champion |
| `v3` canary drift | **ALLOW**: PSI 0.00126, KS 0.0120, mean shift 0.00051σ |
| Shifted `v3` production drift | **BLOCK**: PSI 6.7865, KS 0.5640, mean shift 1.900σ |
| Rollback | restore `v1` revision 1 to **ACTIVE / 100%**; `v3` becomes `ROLLED_BACK / 0%` |

All frozen safety invariants pass:

- exactly one 100%-traffic active production revision;
- rejected models never deploy;
- canaries cannot promote without a latest `ALLOW` drift result;
- critical drift blocks the active revision;
- rollback restores the previous production revision;
- every registered model carries artifact and dataset SHA256 lineage;
- audit events are immutable at the SQLite layer through update/delete-blocking triggers.

## v0.1 scope

This project is deliberately infrastructure-heavy. It does **not** train another model. Instead it governs the lifecycle around models produced by ML systems:

- immutable artifact/dataset/code lineage fields;
- persisted model registry and stages;
- champion-versus-candidate promotion policies;
- explicit rejection reasons and evaluation sample guards;
- canary traffic split and promotion state machine;
- PSI, KS, and standardized-mean drift diagnostics;
- `ALLOW` / `WATCH` / `BLOCK` drift decisions;
- rollback to the previous production revision;
- database-enforced immutable audit events;
- FastAPI control-plane API protected by `X-API-Key`;
- Prometheus metrics endpoint;
- Docker Compose and single-writer Kubernetes examples;
- deterministic end-to-end lifecycle benchmark locked byte-for-byte in CI.

## Promotion policy in the frozen scenario

The production candidate must improve MAE by at least 5%, keep p95 error within a 2% regression guard, maintain schema validity of at least 99%, and have at least 1,000 evaluation samples. Bootstrap promotion is separately controlled and is disabled for normal candidates.

`v2-bad` is intentionally retained as a rejection example. `v3` clears the policy with an 11.67% relative MAE improvement.

## API

Protected endpoints require the `X-API-Key` header. If `CONTROL_PLANE_API_KEY` is absent, protected endpoints fail closed; only `/health` and `/metrics` remain available for probes and scraping.

```text
GET  /health                              public
GET  /metrics                             public
GET  /models                              protected
POST /models                              protected
POST /models/{model_name}/{version}/evaluate
POST /deployments/bootstrap
POST /deployments/canary
POST /deployments/{id}/promote
POST /deployments/{id}/drift
POST /deployments/{id}/rollback
GET  /deployments
GET  /audit
```

## Run locally

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\\Scripts\\activate
pip install -r requirements-ci.txt
pip install -e . --no-deps

ruff check .
pytest -q
mlops-control-plane demo --output /tmp/v0.1_control_plane.json
diff -u evals/results/v0.1_control_plane.json /tmp/v0.1_control_plane.json

export CONTROL_PLANE_API_KEY="replace-with-a-secret"
uvicorn mlops_control_plane.api:app --host 0.0.0.0 --port 8000
```

For an authenticated request:

```bash
curl -H "X-API-Key: $CONTROL_PLANE_API_KEY" http://127.0.0.1:8000/models
```

Or run the Compose stack after setting the key:

```bash
export CONTROL_PLANE_API_KEY="replace-with-a-secret"
docker compose up --build
```

The API is available on port `8000` and Prometheus on port `9090`.

For the Kubernetes example, build/tag the image and create the referenced secret before applying the manifest:

```bash
kubectl create secret generic mlops-control-plane-secrets \
  --from-literal=api-key='replace-with-a-secret'
kubectl apply -f k8s/deployment.yaml
```

## Persistence and security boundaries

SQLite keeps v0.1 self-contained and inspectable. Docker Compose mounts persistent storage. Kubernetes intentionally uses **one replica**, a `ReadWriteOnce` PVC, and `Recreate` rollout strategy so there is only one SQLite writer.

This is not an HA database design. A real multi-replica control plane needs an external transactional database plus distributed concurrency/leader controls. The shared API key is also a minimal service boundary, not enterprise identity: production deployment should add TLS, OIDC/service identity, RBAC, secret rotation, and network policy.

The lifecycle benchmark itself is deterministic synthetic control-plane traffic. It proves the state machine, policy enforcement, auditability, observability plumbing, and rollback invariants; it does not claim a live production incident or business outcome.

Full architecture and state-machine notes: [`docs/architecture.md`](docs/architecture.md).

## Reproducibility

CI uses a pinned Python 3.12 dependency graph. It runs Ruff, the complete pytest suite, the deterministic lifecycle benchmark, and an exact diff against the frozen JSON evidence. A changed policy, state transition, dependency behavior, or benchmark output therefore fails the release gate instead of silently replacing the evidence.

## License

MIT.
