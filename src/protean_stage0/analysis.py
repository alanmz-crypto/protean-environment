"""Frozen Stage 0 ROC-AUC, DeLong confidence bound, and PASS/STOP gate."""

from __future__ import annotations

import math
from dataclasses import dataclass

from .results import ParseStatus, RawResult, Stage0Decision

ONE_SIDED_95_Z = 1.6448536269514722


@dataclass(frozen=True, slots=True)
class AnalysisResult:
    decision: Stage0Decision
    roc_auc: float | None
    delong_variance: float | None
    one_sided_95_lower_bound: float | None
    reason: str


def _kernel(positive_score: float, negative_score: float) -> float:
    if positive_score > negative_score:
        return 1.0
    if positive_score == negative_score:
        return 0.5
    return 0.0


def _sample_variance(values: list[float]) -> float:
    if len(values) < 2:
        raise ValueError("DeLong variance requires at least two values per class")
    mean = sum(values) / len(values)
    return sum((value - mean) ** 2 for value in values) / (len(values) - 1)


def delong_auc_variance(
    positive_scores: list[float], negative_scores: list[float]
) -> tuple[float, float]:
    """Compute empirical AUC and single-classifier DeLong variance, ties = 0.5."""

    if len(positive_scores) < 2 or len(negative_scores) < 2:
        raise ValueError("DeLong requires at least two positive and two negative scores")
    for score in (*positive_scores, *negative_scores):
        if not math.isfinite(score) or not 0.0 <= score <= 1.0:
            raise ValueError("scores must be finite values in [0, 1]")

    positive_placements = [
        sum(_kernel(positive, negative) for negative in negative_scores) / len(negative_scores)
        for positive in positive_scores
    ]
    negative_placements = [
        sum(_kernel(positive, negative) for positive in positive_scores) / len(positive_scores)
        for negative in negative_scores
    ]
    auc = sum(positive_placements) / len(positive_placements)
    variance = _sample_variance(positive_placements) / len(positive_scores) + _sample_variance(
        negative_placements
    ) / len(negative_scores)
    return auc, max(0.0, variance)


def one_sided_95_lower_bound(auc: float, variance: float) -> float:
    return max(0.0, auc - ONE_SIDED_95_Z * math.sqrt(variance))


def apply_stage0_gate(auc: float, lower_bound: float) -> Stage0Decision:
    return Stage0Decision.PASS if auc >= 0.60 and lower_bound > 0.50 else Stage0Decision.STOP


def analyze_stage0(raw_results: tuple[RawResult, ...]) -> AnalysisResult:
    if len(raw_results) != 80:
        return AnalysisResult(Stage0Decision.STOP, None, None, None, "requires 80 usable cases")
    if any(result.mechanical_error_status is not None for result in raw_results):
        raise ValueError("mechanically defective run must be invalidated, not analyzed")
    if any(
        result.parse_status is not ParseStatus.VALID_SCORE or result.returned_score is None
        for result in raw_results
    ):
        return AnalysisResult(Stage0Decision.STOP, None, None, None, "requires 80 usable cases")
    labels = [result.truth_label for result in raw_results]
    if sum(labels) != 40:
        raise ValueError("analysis requires exact 40/40 truth balance")

    scored = []
    for result in raw_results:
        assert result.returned_score is not None
        scored.append((result.truth_label, float(result.returned_score)))
    positive_scores = [score for label, score in scored if label]
    negative_scores = [score for label, score in scored if not label]
    auc, variance = delong_auc_variance(positive_scores, negative_scores)
    lower = one_sided_95_lower_bound(auc, variance)
    decision = apply_stage0_gate(auc, lower)
    reason = "both preregistered gates pass" if decision is Stage0Decision.PASS else "gate failure"
    return AnalysisResult(decision, auc, variance, lower, reason)
