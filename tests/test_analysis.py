from __future__ import annotations

from protean_stage0.analysis import (
    analyze_stage0,
    apply_stage0_gate,
    delong_auc_variance,
    one_sided_95_lower_bound,
)
from protean_stage0.results import ParseStatus, RawResult, Stage0Decision


def raw_results(
    positive_scores: list[float], negative_scores: list[float]
) -> tuple[RawResult, ...]:
    scores = [(True, score) for score in positive_scores] + [
        (False, score) for score in negative_scores
    ]
    return tuple(
        RawResult(
            run_id="TEST-ONLY-RUN",
            case_id=f"TEST-{index:03d}",
            truth_label=label,
            returned_score=score,
            raw_model_response=f"{score:.2f}".encode(),
            model_provider="test-fake-provider",
            model_id="test-fake-model",
            model_configuration_sha256="test",
            provider_metadata={"fake": True},
            timestamp="test",
            call_order=index,
            parse_status=ParseStatus.VALID_SCORE,
        )
        for index, (label, score) in enumerate(scores, start=1)
    )


def test_delong_matches_trusted_r_proc_reference() -> None:
    # Independently generated with R pROC 1.18.5:
    # roc(c(1,1,1,1,0,0,0,0), c(.9,.8,.4,.3,.7,.6,.5,.2), direction="<")
    # var(..., method="delong") and ci.auc(..., conf.level=.90, method="delong").
    positives = [0.9, 0.8, 0.4, 0.3]
    negatives = [0.7, 0.6, 0.5, 0.2]
    auc, variance = delong_auc_variance(positives, negatives)
    lower = one_sided_95_lower_bound(auc, variance)
    assert auc == 0.625
    assert variance == 0.0625
    assert abs(lower - 0.213786593262132) < 1e-15


def test_delong_ties_are_half_credit_and_deterministic() -> None:
    first = delong_auc_variance([0.5] * 4, [0.5] * 4)
    second = delong_auc_variance([0.5] * 4, [0.5] * 4)
    assert first == second == (0.5, 0.0)


def test_gate_boundaries_are_exact() -> None:
    assert apply_stage0_gate(0.60, 0.5000000001) is Stage0Decision.PASS
    assert apply_stage0_gate(0.5999999999, 0.9) is Stage0Decision.STOP
    assert apply_stage0_gate(0.9, 0.50) is Stage0Decision.STOP


def test_perfect_80_case_signal_passes() -> None:
    result = analyze_stage0(raw_results([0.9] * 40, [0.1] * 40))
    assert result.decision is Stage0Decision.PASS
    assert result.roc_auc == 1.0
    assert result.one_sided_95_lower_bound == 1.0


def test_non_discriminative_80_case_signal_stops() -> None:
    result = analyze_stage0(raw_results([0.5] * 40, [0.5] * 40))
    assert result.decision is Stage0Decision.STOP
    assert result.roc_auc == 0.5
    assert result.one_sided_95_lower_bound == 0.5


def test_79_usable_cases_cannot_pass() -> None:
    result = analyze_stage0(raw_results([0.9] * 40, [0.1] * 39))
    assert result.decision is Stage0Decision.STOP
    assert result.roc_auc is None
