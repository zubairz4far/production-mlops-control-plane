from mlops_control_plane.policy import evaluate_promotion
from mlops_control_plane.schemas import PromotionPolicy


def policy() -> PromotionPolicy:
    return PromotionPolicy(
        primary_metric="mae",
        direction="min",
        min_relative_improvement=0.05,
        max_secondary_regression={"p95_error": 0.02},
        minimum_metrics={"schema_validity": 0.99},
        min_eval_samples=1000,
    )


def test_promotion_accepts_material_improvement() -> None:
    result = evaluate_promotion(
        {"mae": 90.0, "p95_error": 198.0, "schema_validity": 0.999},
        2000,
        policy(),
        {"mae": 100.0, "p95_error": 200.0, "schema_validity": 0.999},
    )
    assert result.decision == "PROMOTE"
    assert result.primary_relative_improvement == 0.1


def test_promotion_rejects_regression() -> None:
    result = evaluate_promotion(
        {"mae": 99.0, "p95_error": 210.0, "schema_validity": 0.98},
        500,
        policy(),
        {"mae": 100.0, "p95_error": 200.0, "schema_validity": 0.999},
    )
    assert result.decision == "REJECT"
    assert len(result.reasons) >= 3
