from __future__ import annotations

from dataclasses import dataclass

from .schemas import PromotionPolicy


@dataclass(frozen=True)
class PolicyEvaluation:
    decision: str
    reasons: list[str]
    primary_relative_improvement: float | None


def _relative_improvement(candidate: float, champion: float, direction: str) -> float:
    denominator = abs(champion) if champion != 0 else 1.0
    if direction == "min":
        return (champion - candidate) / denominator
    return (candidate - champion) / denominator


def evaluate_promotion(
    candidate_metrics: dict[str, float],
    candidate_samples: int,
    policy: PromotionPolicy,
    champion_metrics: dict[str, float] | None,
) -> PolicyEvaluation:
    reasons: list[str] = []
    if candidate_samples < policy.min_eval_samples:
        reasons.append(
            f"eval_samples {candidate_samples} < required {policy.min_eval_samples}"
        )

    for metric, floor in policy.minimum_metrics.items():
        value = candidate_metrics.get(metric)
        if value is None:
            reasons.append(f"missing required metric {metric}")
        elif value < floor:
            reasons.append(f"{metric} {value:.6g} < minimum {floor:.6g}")

    for metric, ceiling in policy.maximum_metrics.items():
        value = candidate_metrics.get(metric)
        if value is None:
            reasons.append(f"missing required metric {metric}")
        elif value > ceiling:
            reasons.append(f"{metric} {value:.6g} > maximum {ceiling:.6g}")

    primary = candidate_metrics.get(policy.primary_metric)
    if primary is None:
        reasons.append(f"missing primary metric {policy.primary_metric}")
        return PolicyEvaluation("REJECT", reasons, None)

    if champion_metrics is None:
        if not policy.allow_bootstrap:
            reasons.append("no production champion and bootstrap is disabled")
        return PolicyEvaluation("PROMOTE" if not reasons else "REJECT", reasons, None)

    champion_primary = champion_metrics.get(policy.primary_metric)
    if champion_primary is None:
        reasons.append(f"champion missing primary metric {policy.primary_metric}")
        return PolicyEvaluation("REJECT", reasons, None)

    improvement = _relative_improvement(primary, champion_primary, policy.direction)
    if improvement < policy.min_relative_improvement:
        reasons.append(
            f"primary relative improvement {improvement:.4f} < required "
            f"{policy.min_relative_improvement:.4f}"
        )

    for metric, allowed_regression in policy.max_secondary_regression.items():
        candidate_value = candidate_metrics.get(metric)
        champion_value = champion_metrics.get(metric)
        if candidate_value is None or champion_value is None:
            reasons.append(f"secondary guard metric {metric} missing")
            continue
        if policy.direction == "min":
            ceiling = champion_value * (1 + allowed_regression)
            if candidate_value > ceiling:
                reasons.append(
                    f"{metric} {candidate_value:.6g} > guarded ceiling {ceiling:.6g}"
                )
        else:
            floor = champion_value * (1 - allowed_regression)
            if candidate_value < floor:
                reasons.append(f"{metric} {candidate_value:.6g} < guarded floor {floor:.6g}")

    return PolicyEvaluation(
        decision="PROMOTE" if not reasons else "REJECT",
        reasons=reasons,
        primary_relative_improvement=improvement,
    )
