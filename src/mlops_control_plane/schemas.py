from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator

MetricDirection = Literal["min", "max"]
ModelStage = Literal[
    "REGISTERED",
    "VALIDATED",
    "PRODUCTION",
    "REJECTED",
    "ARCHIVED",
]
DeploymentState = Literal["CANARY", "ACTIVE", "SUPERSEDED", "ROLLED_BACK", "FAILED"]


class ModelRegistration(BaseModel):
    model_name: str = Field(min_length=1, max_length=120)
    version: str = Field(min_length=1, max_length=80)
    artifact_uri: str = Field(min_length=1, max_length=500)
    artifact_sha256: str
    dataset_sha256: str
    code_sha: str = Field(min_length=7, max_length=64)
    eval_samples: int = Field(ge=1)
    metrics: dict[str, float]

    @field_validator("artifact_sha256", "dataset_sha256")
    @classmethod
    def validate_sha256(cls, value: str) -> str:
        normalized = value.lower()
        if len(normalized) != 64 or any(ch not in "0123456789abcdef" for ch in normalized):
            raise ValueError("must be a 64-character lowercase-compatible SHA256")
        return normalized


class PromotionPolicy(BaseModel):
    primary_metric: str = Field(min_length=1)
    direction: MetricDirection = "min"
    min_relative_improvement: float = Field(default=0.02, ge=0, lt=1)
    max_secondary_regression: dict[str, float] = Field(default_factory=dict)
    minimum_metrics: dict[str, float] = Field(default_factory=dict)
    maximum_metrics: dict[str, float] = Field(default_factory=dict)
    min_eval_samples: int = Field(default=1000, ge=1)
    allow_bootstrap: bool = False


class PromotionResult(BaseModel):
    decision: Literal["PROMOTE", "REJECT"]
    reasons: list[str]
    candidate_stage: ModelStage
    champion_version: str | None
    primary_relative_improvement: float | None


class CanaryRequest(BaseModel):
    model_name: str
    version: str
    environment: str = "production"
    traffic_pct: float = Field(default=10.0, gt=0, lt=100)


class DriftRequest(BaseModel):
    reference: list[float] = Field(min_length=20)
    current: list[float] = Field(min_length=20)


class DriftThresholds(BaseModel):
    warning_psi: float = 0.10
    critical_psi: float = 0.25
    warning_ks: float = 0.10
    critical_ks: float = 0.20
    warning_mean_shift_sigma: float = 0.50
    critical_mean_shift_sigma: float = 1.00
