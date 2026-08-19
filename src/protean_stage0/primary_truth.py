"""Primary deterministic evaluator for the frozen Stage 0 grammar."""

from __future__ import annotations

from .grammar import StructureId
from .schema import LifecycleState, StructuredCaseSpec


def evaluate_truth(case: StructuredCaseSpec) -> bool:
    """Evaluate trigger truth with the primary implementation."""

    match case.structure_id:
        case StructureId.P:
            return case.p_now
        case StructureId.P_AND_Q:
            return case.p_now and bool(case.q_now)
        case StructureId.P_AND_NOT_Q:
            return case.p_now and not bool(case.q_now)
        case StructureId.T2_P:
            return bool(case.p_previous) and case.p_now
        case StructureId.ACTIVE_AND_P:
            return case.lifecycle_state is LifecycleState.ACTIVE and case.p_now
    raise ValueError(f"unsupported frozen structure: {case.structure_id}")
