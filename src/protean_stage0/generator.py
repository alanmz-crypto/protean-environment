"""Deterministic structured Stage 0 case generation capability.

Calling this module returns in-memory specifications. It never writes or freezes
an experimental case artifact.
"""

from __future__ import annotations

import hashlib
import itertools
from collections.abc import Iterable
from dataclasses import dataclass, replace

from .grammar import FROZEN_STRUCTURES, StructureId
from .primary_truth import evaluate_truth
from .schema import LifecycleState, StructuredCaseSpec

CASES_PER_STRUCTURE = 16
CASES_PER_CLASS_PER_STRUCTURE = 8
TOTAL_CASES = 80


@dataclass(frozen=True, slots=True)
class GeneratedCaseSpec:
    spec: StructuredCaseSpec
    truth_label: bool


def _stable_key(seed: str, namespace: str, value: str) -> bytes:
    return hashlib.sha256(f"{seed}\x00{namespace}\x00{value}".encode()).digest()


def _candidate_space(structure: StructureId) -> Iterable[StructuredCaseSpec]:
    placeholder = "unassigned"
    if structure is StructureId.P:
        for p_now in (False, True):
            yield StructuredCaseSpec(placeholder, structure, p_now)
        return
    if structure in {StructureId.P_AND_Q, StructureId.P_AND_NOT_Q}:
        for p_now, q_now in itertools.product((False, True), repeat=2):
            yield StructuredCaseSpec(placeholder, structure, p_now, q_now=q_now)
        return
    if structure is StructureId.T2_P:
        for p_previous, p_now in itertools.product((False, True), repeat=2):
            yield StructuredCaseSpec(
                placeholder,
                structure,
                p_now,
                p_previous=p_previous,
            )
        return
    if structure is StructureId.ACTIVE_AND_P:
        for lifecycle_state in LifecycleState:
            for p_now in (False, True):
                yield StructuredCaseSpec(
                    placeholder,
                    structure,
                    p_now,
                    lifecycle_state=lifecycle_state,
                )
        return
    raise ValueError(f"unsupported frozen structure: {structure}")


def _balanced_structure_cases(seed: str, structure: StructureId) -> list[GeneratedCaseSpec]:
    candidates = tuple(_candidate_space(structure))
    by_label = {
        label: tuple(case for case in candidates if evaluate_truth(case) is label)
        for label in (False, True)
    }
    if not all(by_label.values()):
        raise AssertionError(f"grammar structure lacks both truth classes: {structure}")

    generated: list[GeneratedCaseSpec] = []
    for label in (False, True):
        pool = sorted(
            by_label[label],
            key=lambda case: _stable_key(seed, structure.value, repr(case)),
        )
        for repetition in range(CASES_PER_CLASS_PER_STRUCTURE):
            source = pool[repetition % len(pool)]
            generated.append(GeneratedCaseSpec(source, label))

    decorated = list(enumerate(generated))
    decorated.sort(
        key=lambda indexed: _stable_key(
            seed,
            f"{structure.value}/balanced",
            f"{indexed[1].truth_label}/{repr(indexed[1].spec)}/{indexed[0]}",
        )
    )
    generated = [item for _, item in decorated]
    return [
        GeneratedCaseSpec(replace(item.spec, ordinal=ordinal), item.truth_label)
        for ordinal, item in enumerate(generated)
    ]


def generate_structured_cases(seed: str) -> tuple[GeneratedCaseSpec, ...]:
    """Generate the authorized allocation in memory from a non-empty seed."""

    if not seed:
        raise ValueError("a non-empty frozen seed is required")
    generated = [
        item
        for structure in FROZEN_STRUCTURES
        for item in _balanced_structure_cases(seed, structure)
    ]
    generated.sort(
        key=lambda item: _stable_key(
            seed,
            "global-order",
            f"{item.spec.structure_id.value}/{item.spec.ordinal}",
        )
    )
    result = tuple(
        GeneratedCaseSpec(
            replace(item.spec, case_id=f"S0-{index:03d}"),
            item.truth_label,
        )
        for index, item in enumerate(generated, start=1)
    )
    validate_allocation(result)
    return result


def validate_allocation(cases: tuple[GeneratedCaseSpec, ...]) -> None:
    if len(cases) != TOTAL_CASES:
        raise ValueError(f"expected {TOTAL_CASES} cases, got {len(cases)}")
    if len({item.spec.case_id for item in cases}) != TOTAL_CASES:
        raise ValueError("case IDs must be unique")
    if sum(item.truth_label for item in cases) != TOTAL_CASES // 2:
        raise ValueError("case set must have exact 40/40 truth balance")
    for structure in FROZEN_STRUCTURES:
        subset = [item for item in cases if item.spec.structure_id is structure]
        if len(subset) != CASES_PER_STRUCTURE:
            raise ValueError(f"{structure} must have exactly 16 cases")
        if sum(item.truth_label for item in subset) != CASES_PER_CLASS_PER_STRUCTURE:
            raise ValueError(f"{structure} must have exact 8/8 truth balance")
        if any(evaluate_truth(item.spec) is not item.truth_label for item in subset):
            raise ValueError(f"primary truth mismatch in {structure}")
