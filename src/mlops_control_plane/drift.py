from __future__ import annotations

import bisect
import math
from dataclasses import dataclass

from .schemas import DriftThresholds


@dataclass(frozen=True)
class DriftMetrics:
    psi: float
    ks_stat: float
    mean_shift_sigma: float
    sample_size: int
    severity: str
    decision: str


def _mean(values: list[float]) -> float:
    return sum(values) / len(values)


def _std(values: list[float], mean: float) -> float:
    variance = sum((value - mean) ** 2 for value in values) / len(values)
    return math.sqrt(variance)


def _quantile(sorted_values: list[float], q: float) -> float:
    if not sorted_values:
        raise ValueError("cannot compute quantile of empty data")
    position = (len(sorted_values) - 1) * q
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return sorted_values[lower]
    weight = position - lower
    return sorted_values[lower] * (1 - weight) + sorted_values[upper] * weight


def population_stability_index(
    reference: list[float], current: list[float], bins: int = 10
) -> float:
    ordered = sorted(reference)
    edges = [_quantile(ordered, index / bins) for index in range(1, bins)]
    edges = sorted(set(edges))
    ref_counts = [0] * (len(edges) + 1)
    cur_counts = [0] * (len(edges) + 1)
    for value in reference:
        ref_counts[bisect.bisect_right(edges, value)] += 1
    for value in current:
        cur_counts[bisect.bisect_right(edges, value)] += 1
    epsilon = 1e-6
    score = 0.0
    for ref_count, cur_count in zip(ref_counts, cur_counts, strict=True):
        ref_rate = max(ref_count / len(reference), epsilon)
        cur_rate = max(cur_count / len(current), epsilon)
        score += (cur_rate - ref_rate) * math.log(cur_rate / ref_rate)
    return score


def ks_statistic(reference: list[float], current: list[float]) -> float:
    ref = sorted(reference)
    cur = sorted(current)
    points = sorted(set(ref + cur))
    max_gap = 0.0
    for point in points:
        ref_cdf = bisect.bisect_right(ref, point) / len(ref)
        cur_cdf = bisect.bisect_right(cur, point) / len(cur)
        max_gap = max(max_gap, abs(ref_cdf - cur_cdf))
    return max_gap


def evaluate_drift(
    reference: list[float],
    current: list[float],
    thresholds: DriftThresholds | None = None,
) -> DriftMetrics:
    if min(len(reference), len(current)) < 20:
        raise ValueError("drift evaluation requires at least 20 values per sample")
    thresholds = thresholds or DriftThresholds()
    ref_mean = _mean(reference)
    cur_mean = _mean(current)
    ref_std = _std(reference, ref_mean)
    mean_shift = abs(cur_mean - ref_mean) / ref_std if ref_std > 0 else float("inf")
    psi = population_stability_index(reference, current)
    ks = ks_statistic(reference, current)

    critical = (
        psi >= thresholds.critical_psi
        or ks >= thresholds.critical_ks
        or mean_shift >= thresholds.critical_mean_shift_sigma
    )
    warning = (
        psi >= thresholds.warning_psi
        or ks >= thresholds.warning_ks
        or mean_shift >= thresholds.warning_mean_shift_sigma
    )
    if critical:
        severity, decision = "CRITICAL", "BLOCK"
    elif warning:
        severity, decision = "WARNING", "WATCH"
    else:
        severity, decision = "OK", "ALLOW"
    return DriftMetrics(
        psi=psi,
        ks_stat=ks,
        mean_shift_sigma=mean_shift,
        sample_size=len(current),
        severity=severity,
        decision=decision,
    )
