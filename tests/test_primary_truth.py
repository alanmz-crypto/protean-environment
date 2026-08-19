"""Primary evaluator tests derived directly from the frozen grammar."""

from __future__ import annotations

import unittest
from typing import Any

from protean_stage0.grammar import StructureId
from protean_stage0.primary_truth import evaluate_truth
from protean_stage0.schema import LifecycleState, StructuredCaseSpec


class PrimaryTruthTests(unittest.TestCase):
    def case(self, structure: StructureId, p_now: bool, **kwargs: Any) -> StructuredCaseSpec:
        return StructuredCaseSpec("primary-test", structure, p_now, **kwargs)

    def test_p(self) -> None:
        for value in (False, True):
            with self.subTest(value=value):
                self.assertIs(evaluate_truth(self.case(StructureId.P, value)), value)

    def test_p_and_q(self) -> None:
        for p_now, q_now, expected in (
            (False, False, False),
            (False, True, False),
            (True, False, False),
            (True, True, True),
        ):
            with self.subTest(p_now=p_now, q_now=q_now):
                self.assertIs(
                    evaluate_truth(self.case(StructureId.P_AND_Q, p_now, q_now=q_now)),
                    expected,
                )

    def test_p_and_not_q(self) -> None:
        for p_now, q_now, expected in (
            (False, False, False),
            (False, True, False),
            (True, False, True),
            (True, True, False),
        ):
            with self.subTest(p_now=p_now, q_now=q_now):
                self.assertIs(
                    evaluate_truth(self.case(StructureId.P_AND_NOT_Q, p_now, q_now=q_now)),
                    expected,
                )

    def test_t2_p(self) -> None:
        for p_previous, p_now, expected in (
            (False, False, False),
            (False, True, False),
            (True, False, False),
            (True, True, True),
        ):
            with self.subTest(p_previous=p_previous, p_now=p_now):
                self.assertIs(
                    evaluate_truth(self.case(StructureId.T2_P, p_now, p_previous=p_previous)),
                    expected,
                )

    def test_active_and_p(self) -> None:
        for lifecycle in LifecycleState:
            for p_now in (False, True):
                expected = lifecycle is LifecycleState.ACTIVE and p_now
                with self.subTest(lifecycle=lifecycle, p_now=p_now):
                    self.assertIs(
                        evaluate_truth(
                            self.case(
                                StructureId.ACTIVE_AND_P,
                                p_now,
                                lifecycle_state=lifecycle,
                            )
                        ),
                        expected,
                    )


if __name__ == "__main__":
    unittest.main()
