import math

from mlops_control_plane.drift import evaluate_drift


def test_small_shift_is_allowed() -> None:
    reference = [math.sin(i * 0.13) for i in range(300)]
    current = [value + 0.01 * math.cos(i * 0.07) for i, value in enumerate(reference)]
    result = evaluate_drift(reference, current)
    assert result.decision == "ALLOW"
    assert result.severity == "OK"


def test_large_shift_is_blocked() -> None:
    reference = [math.sin(i * 0.13) for i in range(300)]
    current = [value + 1.5 for value in reference]
    result = evaluate_drift(reference, current)
    assert result.decision == "BLOCK"
    assert result.severity == "CRITICAL"
