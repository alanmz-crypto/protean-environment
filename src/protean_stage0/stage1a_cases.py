"""Deterministic Stage-1A calibration case generation and validation.

Generates the frozen 60-case Stage-1A calibration set (12 per familiar structure,
6 positive / 6 negative = 30/30) from the frozen familiar grammar, textualizes it
deterministically with the already-authorized template bank, builds the minimal
cross-session representation per case, and verifies primary/reference truth
agreement.

This is calibration textualization reusing the frozen familiar-structure
semantics; it is NOT the independently-authored Stage-1B holdout (a separate,
information-isolated process). It contains no live-call code.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, replace

from .artifacts import FrozenCaseSet
from .generator import GeneratedCaseSpec, _stable_key
from .generator import _candidate_space as _candidate_specs
from .grammar import FROZEN_STRUCTURES
from .primary_truth import evaluate_truth
from .reference_truth import evaluate_reference_truth
from .schema import Stage0Case
from .stage1a_config import (
    STAGE1A_PER_CLASS_PER_STRUCTURE,
    STAGE1A_PER_STRUCTURE,
    STAGE1A_SEED,
    STAGE1A_TOTAL,
)
from .stage1a_session import CrossSessionRepresentation
from .textualize import TemplateBank, textualize_case

# Re-export the candidate-space helper under a local alias for clarity.
_candidate_space = _candidate_specs


@dataclass(frozen=True, slots=True)
class Stage1ACase:
    generated: GeneratedCaseSpec
    textualized: Stage0Case
    cross_session: CrossSessionRepresentation


def generate_stage1a_structured(seed: str = STAGE1A_SEED) -> tuple[GeneratedCaseSpec, ...]:
    """Deterministic 60-case structured allocation: 12/structure, 6/6 each."""
    items: list[GeneratedCaseSpec] = []
    for structure in FROZEN_STRUCTURES:
        candidates = tuple(_candidate_space(structure))
        by_label = {
            label: tuple(c for c in candidates if evaluate_truth(c) is label)
            for label in (False, True)
        }
        structure_items: list[GeneratedCaseSpec] = []
        for label in (False, True):
            pool = sorted(
                by_label[label], key=lambda c: _stable_key(seed, structure.value, repr(c))
            )
            for i in range(STAGE1A_PER_CLASS_PER_STRUCTURE):
                structure_items.append(
                    GeneratedCaseSpec(
                        replace(pool[i % len(pool)], ordinal=len(structure_items)), label
                    )
                )
        structure_items.sort(
            key=lambda it: _stable_key(
                seed, f"{structure.value}/stage1a", f"{repr(it.spec)}/{it.truth_label}"
            )
        )
        items += structure_items
    items.sort(
        key=lambda it: _stable_key(
            seed, "stage1a-global", f"{it.spec.structure_id.value}/{it.spec.ordinal}"
        )
    )
    result = tuple(
        GeneratedCaseSpec(replace(item.spec, case_id=f"S1A-{index:02d}"), item.truth_label)
        for index, item in enumerate(items, start=1)
    )
    validate_stage1a_allocation(result)
    return result


def validate_stage1a_allocation(cases: tuple[GeneratedCaseSpec, ...]) -> None:
    if len(cases) != STAGE1A_TOTAL:
        raise ValueError(f"expected {STAGE1A_TOTAL} Stage-1A cases, got {len(cases)}")
    if sum(it.truth_label for it in cases) != STAGE1A_TOTAL // 2:
        raise ValueError("Stage-1A must have exact 30/30 truth balance")
    if len({it.spec.case_id for it in cases}) != STAGE1A_TOTAL:
        raise ValueError("Stage-1A case IDs must be unique")
    for structure in FROZEN_STRUCTURES:
        subset = [it for it in cases if it.spec.structure_id is structure]
        if len(subset) != STAGE1A_PER_STRUCTURE:
            raise ValueError(f"{structure} must have exactly 12 Stage-1A cases")
        if sum(it.truth_label for it in subset) != STAGE1A_PER_CLASS_PER_STRUCTURE:
            raise ValueError(f"{structure} must have exact 6/6 Stage-1A balance")


def build_stage1a_cases(
    seed: str = STAGE1A_SEED,
    *,
    template_bank: TemplateBank,
    session_base: str = "stage1a-session-0",
) -> tuple[Stage1ACase, ...]:
    structured = generate_stage1a_structured(seed)
    text_seed = f"{seed}/text"
    out: list[Stage1ACase] = []
    for index, item in enumerate(structured, start=1):
        text = textualize_case(item, seed=text_seed, bank=template_bank)
        # Cross-session boundary: only the authorized persisted fields cross. The
        # original earlier-session conversation is never carried forward.
        persisted = dict(text.model_visible_payload())
        rep = CrossSessionRepresentation(
            session_id=f"{session_base}-{index:02d}", persisted_state=persisted
        )
        out.append(Stage1ACase(generated=item, textualized=text, cross_session=rep))
    return tuple(out)


def verify_stage1a_truth_agreement(cases: tuple[GeneratedCaseSpec, ...]) -> int:
    """Recompute primary + reference truth for all cases; must agree on all 60."""
    for item in cases:
        primary = evaluate_truth(item.spec)
        reference = evaluate_reference_truth(item.spec)
        if primary is not reference:
            raise ValueError(f"Stage-1A truth evaluators disagree for {item.spec.case_id}")
        if primary is not item.truth_label:
            raise ValueError(f"Stage-1A generated label mismatch for {item.spec.case_id}")
    return len(cases)


def freeze_stage1a_case_set(
    cases: Iterable[Stage1ACase],
) -> FrozenCaseSet:
    """Build the immutable 60-case Stage-1A artifact (with case_set_hash injected)."""
    staged = tuple(c.textualized for c in cases)
    return FrozenCaseSet.from_cases(staged)
