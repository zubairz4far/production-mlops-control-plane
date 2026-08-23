# Production MLOps Control Plane

[![CI](https://github.com/zubairz4far/production-mlops-control-plane/actions/workflows/ci.yml/badge.svg)](https://github.com/zubairz4far/production-mlops-control-plane/actions/workflows/ci.yml)

Auditable model promotion, lineage, canary deployment, drift policy, rollback, API, and observability in one small production-style control plane.

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
- append-only audit trail;
- FastAPI control-plane API;
- Prometheus metrics endpoint;
- Docker Compose and Kubernetes examples;
- deterministic end-to-end lifecycle benchmark locked in CI.

## Safety invariants

v0.1 tests and benchmarks these invariants:

1. a rejected candidate cannot be deployed;
2. a canary requires a fully active previous deployment;
3. canary promotion atomically supersedes the previous revision;
4. critical drift produces `BLOCK`;
5. rollback requires a blocked active deployment and an existing previous revision;
6. rollback restores exactly one 100%-traffic active production deployment;
7. each registered model carries artifact and dataset SHA256 lineage.

## API

```text
GET  /health
GET  /models
POST /models
POST /models/{model_name}/{version}/evaluate
POST /deployments/bootstrap
POST /deployments/canary
POST /deployments/{id}/promote
POST /deployments/{id}/drift
POST /deployments/{id}/rollback
GET  /deployments
GET  /audit
GET  /metrics
```

## Run locally

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\\Scripts\\activate
pip install -r requirements-ci.txt
pip install -e . --no-deps

ruff check .
pytest -q
mlops-control-plane demo --output evals/results/v0.1_control_plane.json
uvicorn mlops_control_plane.api:app --host 0.0.0.0 --port 8000
```

Or:

```bash
docker compose up --build
```

Then the API is available on port `8000` and Prometheus on port `9090`.

## Persistence note

The application uses SQLite to keep the implementation self-contained and auditable. Docker Compose mounts persistent storage. The Kubernetes manifest uses `emptyDir` only as a runnable deployment example; it is **not** a claim of highly available production persistence. A real multi-replica deployment needs an external transactional database plus distributed concurrency/leader controls.

Full architecture and state-machine notes: [`docs/architecture.md`](docs/architecture.md).

## Status

**v0.1 implementation complete; deterministic lifecycle evidence pending CI.** No release-pass claim is made until the final state machine, audit trail, and evidence equality checks succeed in GitHub Actions.

## License

MIT.
