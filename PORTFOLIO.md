# AI / ML Engineering Portfolio

A consolidated index of evaluated AI, ML, LLM, RAG, and MLOps systems by **Zubair Zafar**.

The portfolio emphasizes reproducibility, leakage-safe evaluation, failure analysis, promotion/rejection gates, source integrity, serving, monitoring, and explicit production boundaries.

## Portfolio matrix

| Project | Domain | Core technical work | Evaluation evidence | Decision / result |
|---|---|---|---|---|
| [`qwen3-tool-calling-qlora`](https://github.com/zubairz4far/qwen3-tool-calling-qlora) | LLM / tool calling | Qwen3-1.7B, 4-bit QLoRA, structured calls, adversarial prompts | 150-case locked final benchmark | **94.44% strict exact-call**, V2 rejected |
| [`production-rag-engine`](https://github.com/zubairz4far/production-rag-engine) | RAG | Dense + BM25 + RRF, Qdrant, reranking, grounded generation | hard retrieval + adversarial generation suites | evaluated retrieval / grounding / refusal behavior |
| [`production-mlops-control-plane`](https://github.com/zubairz4far/production-mlops-control-plane) | MLOps | registry, lineage, policy engine, canary, drift, rollback, audit, API | frozen deterministic lifecycle + container smoke CI | lifecycle release gate **PASS** |
| [`industrial-predictive-maintenance-platform`](https://github.com/zubairz4far/industrial-predictive-maintenance-platform) | Predictive maintenance | calibration, cost-sensitive classification, thresholding | UCI Scania APS official 16k final test | challenge cost **-31.9%**, promote |
| [`energy-grid-intelligence-platform`](https://github.com/zubairz4far/energy-grid-intelligence-platform) | Energy forecasting | residual correction, uncertainty, reserve/ramp diagnostics | DE-LU final 60-day untouched test | MAE/WAPE **-7.33%**, promote |
| [`smart-warehouse-intelligence-platform`](https://github.com/zubairz4far/smart-warehouse-intelligence-platform) | Warehouse optimization | temporal demand forecast, ABC, assignment-based slotting | UCI Online Retail later held-out invoices | ML forecast **reject**; route proxy **-10.26%** |
| [`production-fleet-intelligence-platform`](https://github.com/zubairz4far/production-fleet-intelligence-platform) | Fleet platform | failure risk, anomaly detection, ETA, routing, MLflow, Kafka, IaC | CI integration chain | production-integration evidence; synthetic headline benchmark |

## 1. LLM fine-tuning and tool reliability

### `qwen3-tool-calling-qlora`

Fine-tuned Qwen3-1.7B for seven structured operations tools using 4-bit NF4 QLoRA.

**Controlled held-out benchmark**
- Tool selection: 85.00% -> **100.00%**
- Exact function-call accuracy: 74.17% -> **95.00%**
- Argument KV accuracy: 80.49% -> **98.33%**

**Locked 150-case final benchmark**
- Tool selection: 85.56% -> **98.89%**
- Strict exact-call: 73.33% -> **94.44%**
- Prompt-injection exact accuracy: 55.00% -> **95.00%**

The release retains V1 because a corrective V2 became too conservative. Clarification weakness and hallucinated-tool behavior remain documented.

## 2. Retrieval-Augmented Generation

### `production-rag-engine`

Production-oriented RAG architecture:

```text
documents
 -> page-aware chunking
 -> dense + BM25 retrieval
 -> reciprocal-rank fusion
 -> optional CrossEncoder reranking
 -> evidence builder
 -> grounded generation + citations
 -> retrieval / grounding / refusal / injection evaluation
 -> FastAPI + Prometheus + Docker
```

Evaluation includes:
- 20-query retrieval smoke benchmark
- 120-query hard retrieval benchmark
- 12-case Generation Reliability V1
- 40-case adversarial Generation Reliability V2
- prompt-injection leakage tests
- unsupported-question refusal contracts

## 3. Model lifecycle and MLOps

### `production-mlops-control-plane`

A deterministic, evaluated control plane around model versions.

```text
REGISTERED
  -> VALIDATED
  -> CANARY
  -> ALLOW drift
  -> ACTIVE
  -> BLOCK on critical drift
  -> ROLLBACK
```

Implemented:
- model/version registry
- SHA-based artifact/dataset/code lineage
- declarative champion/candidate policies
- rejection reasons
- canary traffic state
- PSI / KS / standardized mean-shift monitoring
- rollback to last-known-good revision
- immutable audit events
- FastAPI + API-key protection
- Prometheus
- Docker / Kubernetes
- exact frozen-evidence CI

Frozen scenario:
- 3 registered models
- bad candidate rejected
- good candidate primary MAE improvement: **11.67%**
- healthy canary: `ALLOW`
- shifted production: `BLOCK`
- rollback restores previous model at **100%**
- all lifecycle invariants pass

## 4. Predictive maintenance

### `industrial-predictive-maintenance-platform`

Dataset: UCI APS Failure at Scania Trucks.

Evaluation contract:
- official 60,000-row training set split into fit / calibration / development
- official 16,000-row test set untouched until final scoring
- probability calibration and threshold selection occur before final evaluation

| Model | PR-AUC | Recall | Challenge cost |
|---|---:|---:|---:|
| Logistic Regression | 0.794 | 0.880 | 25,170 |
| HistGradientBoosting | **0.871** | **0.925** | **17,140** |

**Cost reduction: 31.9%.**

## 5. Energy-grid forecasting

### `energy-grid-intelligence-platform`

Dataset: OPSD / ENTSO-E DE-LU hourly load + published day-ahead forecast.

| Forecast | MAE MW | WAPE | p95 abs error MW |
|---|---:|---:|---:|
| ENTSO-E day-ahead | 1,127.0 | 2.159% | 2,650.0 |
| Residual HGB | **1,044.4** | **2.000%** | **2,616.7** |

**MAE/WAPE improvement: 7.33%.**

The project also measures interval coverage, reserve-risk exceedances, and high-ramp events. It explicitly records that nominal 90% intervals under-cover on the shifted final period.

## 6. Warehouse intelligence

### `smart-warehouse-intelligence-platform`

Dataset: UCI Online Retail.

Scale:
- 541,909 raw transactions
- 527,794 positive shipment lines
- 19,778 invoices
- 3,806 physical SKUs

Forecasting result:
- four-week moving average test WAPE: **0.5647**
- HistGradientBoosting test WAPE: **0.5981**
- candidate decision: **REJECT**

Slotting result:
- baseline held-out route proxy: 800,664
- optimized: **718,514**
- reduction: **10.26%**

The project deliberately preserves a rejected ML candidate because the simpler model generalized better.

## 7. Fleet ML platform

### `production-fleet-intelligence-platform`

Five release layers:
1. failure-risk baseline
2. calibrated promotion comparison
3. telemetry anomaly / drift detection
4. ETA + constrained routing
5. production MLOps integration

Infrastructure includes FastAPI, Prometheus, MLflow registry, Kafka ingestion, Docker, Kubernetes, Terraform, and CI validation.

The repository correctly labels its headline mobility benchmark as deterministic synthetic evidence rather than real fleet savings.

## Evaluation philosophy

The projects use a common engineering standard:

1. Define the data and decision contract.
2. Separate training, development/calibration, and final evaluation.
3. Freeze promotion criteria before final test scoring.
4. Preserve source and artifact hashes.
5. Emit machine-readable evidence.
6. Reproduce evidence in CI.
7. Reject models when a baseline wins.
8. Document limitations and failure modes.
9. Avoid converting offline proxy improvements into unsupported business claims.

## Recommended six GitHub pins

1. `qwen3-tool-calling-qlora`
2. `production-rag-engine`
3. `production-mlops-control-plane`
4. `industrial-predictive-maintenance-platform`
5. `energy-grid-intelligence-platform`
6. `smart-warehouse-intelligence-platform`

This gives a recruiter an immediate progression from **LLM fine-tuning -> RAG -> MLOps -> real-data applied ML**.

## Positioning

Target roles: **AI Engineer, Machine Learning Engineer, Applied AI Engineer, LLM / Agent Engineer, MLOps Engineer**.

Primary strengths: evaluated LLM/tool-calling behavior, RAG retrieval and grounding, production ML architecture, leakage controls, benchmark design, model promotion/rejection, drift/rollback, APIs, containers, observability, and CI.
