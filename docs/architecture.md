# v0.1 architecture and safety contract

## Purpose

This repository is a control-plane benchmark, not another predictive model. It governs model-version evidence and deployment transitions through an auditable state machine.

## Persisted entities

- **models** — version, artifact URI, artifact SHA256, dataset SHA256, code SHA, evaluation sample count, metrics, stage;
- **promotion events** — candidate/champion comparison, full policy snapshot, decision and rejection reasons;
- **deployments** — environment revision, model version, lifecycle state, traffic percentage and previous revision;
- **drift reports** — PSI, KS statistic, standardized mean shift, severity and allow/watch/block decision;
- **audit events** — append-only control-plane transition evidence.

## Promotion contract

A policy declares:

- primary metric and minimize/maximize direction;
- minimum relative improvement over the current production champion;
- secondary regression guards;
- absolute metric floors/ceilings;
- minimum evaluation sample count;
- whether bootstrap promotion without an existing champion is permitted.

A rejected model is moved to `REJECTED` and is ineligible for canary deployment.

## Deployment state machine

```text
REGISTERED -> VALIDATED -> CANARY -> ACTIVE
     |                         |        |
     +------> REJECTED         |        +-> ROLLED_BACK
                               +-> unsafe drift -> BLOCK

previous ACTIVE -> 90% while canary receives 10%
canary promote  -> previous SUPERSEDED 0%, candidate ACTIVE 100%
critical drift  -> explicit rollback restores previous revision ACTIVE 100%
```

The exact traffic split is configurable for canaries. v0.1 rejects creating a canary when there is no fully active previous deployment.

## Drift policy

v0.1 evaluates three independent distribution-shift signals:

- population stability index (PSI);
- two-sample empirical KS statistic;
- absolute mean shift expressed in reference standard deviations.

Default thresholds are deliberately simple and transparent. Any critical threshold produces `BLOCK`; warning-only thresholds produce `WATCH`; otherwise the decision is `ALLOW`.

The drift monitor is offline evidence. It does not claim causal model degradation, automatic business impact, or universal threshold validity.

## Rollback safety

By default, rollback is refused unless the active deployment has a recorded `BLOCK` drift report and a previous deployment revision exists. The rollback transaction restores the previous revision to 100% traffic, marks the current revision `ROLLED_BACK`, archives its model stage, restores the previous model to `PRODUCTION`, and appends an audit event.

## Storage and deployment limitation

The service uses SQLite for a self-contained portfolio implementation. Docker Compose mounts a persistent volume. The Kubernetes manifest intentionally uses `emptyDir` only as a runnable example and **is not a production HA persistence design**; a real deployment should use an external transactional database and leader/concurrency controls before running multiple replicas.
