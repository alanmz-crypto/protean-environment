"""Stage-1A 17-threshold selection, futility determination, and shared-score arms.

The core deterministic machinery of Stage 1A. It is pure; it makes no provider
calls and does not know about the model. B and C consume the SAME per-case raw
score (shared-score authority). B applies a permanently-fixed 0.50 threshold; C
evaluates the frozen 17-threshold grid and selects one per the preregistered rule.
If C selects exactly 0.50 the run is a DETERMINISTIC FUTILITY STOP and Stage 1B
is not reachable.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from .stage1a_config import B_THRESHOLD, FUTILITY_THRESHOLD, THRESHOLD_GRID


class Stage1BProjection(StrEnum):
    CONTINUE = "CONTINUE_TO_STAGE_1B"
    DETERMINISTIC_FUTILITY_STOP = "DETERMINISTIC_FUTILITY_STOP"


@dataclass(frozen=True, slots=True)
class ScoredCase:
    """One case carrying its SINGLE shared raw applicability score + truth label."""

    case_id: str
    score: float
    truth_label: bool

    def __post_init__(self) -> None:
        if not 0.0 <= self.score <= 1.0:
            raise ValueError("score must be in [0,1]")
        if not self.case_id:
            raise ValueError("case_id required")


def arm_decision(score: float, threshold: float) -> bool:
    """B or C decision: predicted eligible iff score >= threshold."""
    return score >= threshold


def evaluate_threshold(
    cases: tuple[ScoredCase, ...], threshold: float
) -> tuple[float, float, float]:
    """Return (balanced_accuracy, fp_rate, fn_rate) for one threshold.

    fp_rate = FP / (predicted-positive ground-truth-negative count denominator)
             = FP / total negatives.
    fn_rate = FN / total positives.
    balanced_accuracy = (TP/positives + TN/negatives) / 2.
    """
    if not cases:
        raise ValueError("no cases")
    positives = sum(1 for c in cases if c.truth_label)
    negatives = len(cases) - positives
    if positives == 0 or negatives == 0:
        raise ValueError("both classes required for balanced accuracy")
    tp = fn = tn = fp = 0
    for c in cases:
        d = arm_decision(c.score, threshold)
        if c.truth_label:
            if d:
                tp += 1
            else:
                fn += 1
        else:
            if d:
                fp += 1
            else:
                tn += 1
    tpr = tp / positives
    tnr = tn / negatives
    balanced = (tpr + tnr) / 2.0
    fp_rate = fp / negatives if negatives else 0.0
    fn_rate = fn / positives if positives else 0.0
    return balanced, fp_rate, fn_rate


@dataclass(frozen=True, slots=True)
class ThresholdEval:
    threshold: float
    balanced_accuracy: float
    fp_rate: float
    fn_rate: float


def evaluate_all_thresholds(cases: tuple[ScoredCase, ...]) -> tuple[ThresholdEval, ...]:
    return tuple(
        ThresholdEval(
            threshold=t,
            balanced_accuracy=ba,
            fp_rate=fp,
            fn_rate=fn,
        )
        for t in THRESHOLD_GRID
        for (ba, fp, fn) in [evaluate_threshold(cases, t)]
    )


def select_c_threshold(evals: tuple[ThresholdEval, ...]) -> float:
    """Preregistered C selection: max balanced accuracy, then closest to 0.50, then higher."""
    if not evals:
        raise ValueError("empty threshold evals")
    max_ba = max(e.balanced_accuracy for e in evals)
    best = [e for e in evals if abs(e.balanced_accuracy - max_ba) < 1e-9]
    # Distances rounded to 6dp so the 0.05-grid closest-to-0.50 tie is exact.
    best.sort(key=lambda e: (round(abs(e.threshold - FUTILITY_THRESHOLD), 6), -e.threshold))
    return best[0].threshold


def within_1pp_of_max(evals: tuple[ThresholdEval, ...]) -> tuple[float, ...]:
    max_ba = max(e.balanced_accuracy for e in evals)
    return tuple(e.threshold for e in evals if max_ba - e.balanced_accuracy <= 0.01)


def determine_stage1b_fate(selected_c: float) -> Stage1BProjection:
    """Futurity rule (ratified): selected C == 0.50 -> DETERMINISTIC FUTILITY STOP."""
    if abs(selected_c - FUTILITY_THRESHOLD) < 1e-9:
        return Stage1BProjection.DETERMINISTIC_FUTILITY_STOP
    return Stage1BProjection.CONTINUE


@dataclass(frozen=True, slots=True)
class Stage1AThresholdReport:
    evaluations: tuple[ThresholdEval, ...]
    selected_threshold: float
    second_best_threshold: float | None
    within_1pp: tuple[float, ...]
    b_threshold: float
    stage1b_projection: Stage1BProjection

    def to_dict(self) -> dict[str, Any]:
        return {
            "thresholds": [
                {
                    "threshold": e.threshold,
                    "balanced_accuracy": round(e.balanced_accuracy, 4),
                    "fp_rate": round(e.fp_rate, 4),
                    "fn_rate": round(e.fn_rate, 4),
                }
                for e in self.evaluations
            ],
            "selected_threshold": self.selected_threshold,
            "second_best_threshold": self.second_best_threshold,
            "within_1pp_of_max": list(self.within_1pp),
            "b_threshold": self.b_threshold,
            "stage1b_projection": self.stage1b_projection.value,
        }


def compute_stage1a_report(
    scored_cases: tuple[ScoredCase, ...],
    *,
    b_threshold: float = B_THRESHOLD,
) -> Stage1AThresholdReport:
    """Full Stage-1A threshold report: B fixed, C over the frozen grid."""
    if not scored_cases or len(scored_cases) < 2:
        raise ValueError("Stage-1A requires scored calibration cases")
    evals = evaluate_all_thresholds(scored_cases)
    if len(evals) != 17:
        raise ValueError("Stage-1A report requires all 17 frozen thresholds to be evaluated")
    selected = select_c_threshold(evals)
    # Second-best: remove the selected threshold, then re-apply the SAME frozen
    # ranking rule over the remaining 16. Because 17 were evaluated, second-best
    # is always present.
    remaining = tuple(e for e in evals if e.threshold != selected)
    second_best = select_c_threshold(remaining)
    within = within_1pp_of_max(evals)
    projection = determine_stage1b_fate(selected)
    # B threshold is fixed and must equal the frozen constant.
    if abs(b_threshold - B_THRESHOLD) > 1e-9:
        raise ValueError("B threshold must remain exactly 0.50")
    return Stage1AThresholdReport(
        evaluations=evals,
        selected_threshold=selected,
        second_best_threshold=second_best,
        within_1pp=within,
        b_threshold=B_THRESHOLD,
        stage1b_projection=projection,
    )
