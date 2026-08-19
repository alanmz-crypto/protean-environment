"""Independent reference truth evaluator for the frozen Stage 0 grammar."""

from __future__ import annotations

from typing import assert_never

from .grammar import StructureId
from .schema import LifecycleState, StructuredCaseSpec


def evaluate_reference_truth(case_spec: StructuredCaseSpec) -> bool:
    """Evaluate a structured case according to the frozen familiar grammar."""

    match case_spec.structure_id:
        case StructureId.P:
            return case_spec.p_now
        case StructureId.P_AND_Q:
            return case_spec.p_now and case_spec.q_now is True
        case StructureId.P_AND_NOT_Q:
            return case_spec.p_now and case_spec.q_now is False
        case StructureId.T2_P:
            return case_spec.p_previous is True and case_spec.p_now
        case StructureId.ACTIVE_AND_P:
            return case_spec.lifecycle_state is LifecycleState.ACTIVE and case_spec.p_now

    assert_never(case_spec.structure_id)
