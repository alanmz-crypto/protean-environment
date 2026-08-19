"""Truth-table tests derived directly from the frozen Stage 0 grammar."""

from __future__ import annotations

import pytest

from protean_stage0.grammar import StructureId
from protean_stage0.reference_truth import evaluate_reference_truth
from protean_stage0.schema import LifecycleState, StructuredCaseSpec


@pytest.mark.parametrize("p_now", [False, True])
def test_p_is_true_exactly_when_p_is_true_now(p_now: bool) -> None:
    case_spec = StructuredCaseSpec(
        case_id=f"reference-p-{p_now}",
        structure_id=StructureId.P,
        p_now=p_now,
    )

    assert evaluate_reference_truth(case_spec) is p_now


@pytest.mark.parametrize("p_now", [False, True])
@pytest.mark.parametrize("q_now", [False, True])
def test_p_and_q_is_true_exactly_when_both_are_true(p_now: bool, q_now: bool) -> None:
    case_spec = StructuredCaseSpec(
        case_id=f"reference-p-and-q-{p_now}-{q_now}",
        structure_id=StructureId.P_AND_Q,
        p_now=p_now,
        q_now=q_now,
    )

    assert evaluate_reference_truth(case_spec) is (p_now and q_now)


@pytest.mark.parametrize("p_now", [False, True])
@pytest.mark.parametrize("q_now", [False, True])
def test_p_and_not_q_is_true_exactly_when_p_is_true_and_q_is_false(
    p_now: bool, q_now: bool
) -> None:
    case_spec = StructuredCaseSpec(
        case_id=f"reference-p-and-not-q-{p_now}-{q_now}",
        structure_id=StructureId.P_AND_NOT_Q,
        p_now=p_now,
        q_now=q_now,
    )

    assert evaluate_reference_truth(case_spec) is (p_now and not q_now)


@pytest.mark.parametrize("p_previous", [False, True])
@pytest.mark.parametrize("p_now", [False, True])
def test_t2_p_is_true_exactly_when_p_is_true_in_both_observations(
    p_previous: bool, p_now: bool
) -> None:
    case_spec = StructuredCaseSpec(
        case_id=f"reference-t2-p-{p_previous}-{p_now}",
        structure_id=StructureId.T2_P,
        p_now=p_now,
        p_previous=p_previous,
    )

    assert evaluate_reference_truth(case_spec) is (p_previous and p_now)


@pytest.mark.parametrize("lifecycle_state", list(LifecycleState))
@pytest.mark.parametrize("p_now", [False, True])
def test_active_and_p_is_true_exactly_when_state_is_active_and_p_is_true(
    lifecycle_state: LifecycleState, p_now: bool
) -> None:
    case_spec = StructuredCaseSpec(
        case_id=f"reference-active-and-p-{lifecycle_state.value}-{p_now}",
        structure_id=StructureId.ACTIVE_AND_P,
        p_now=p_now,
        lifecycle_state=lifecycle_state,
    )

    expected = lifecycle_state is LifecycleState.ACTIVE and p_now
    assert evaluate_reference_truth(case_spec) is expected


def test_evaluation_is_deterministic_and_does_not_mutate_the_case_spec() -> None:
    case_spec = StructuredCaseSpec(
        case_id="reference-purity",
        structure_id=StructureId.T2_P,
        p_now=True,
        p_previous=True,
        ordinal=7,
    )

    before = repr(case_spec)
    first_result = evaluate_reference_truth(case_spec)
    second_result = evaluate_reference_truth(case_spec)

    assert first_result is True
    assert second_result is first_result
    assert repr(case_spec) == before
