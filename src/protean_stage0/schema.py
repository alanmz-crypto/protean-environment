"""Minimal machine-readable schemas for Stage 0 mechanics."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, replace
from enum import StrEnum
from types import MappingProxyType
from typing import Any

from .grammar import StructureId


class LifecycleState(StrEnum):
    ACTIVE = "ACTIVE"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"


@dataclass(frozen=True, slots=True)
class StructuredCaseSpec:
    """Structured, pre-textualization case input to both truth evaluators."""

    case_id: str
    structure_id: StructureId
    p_now: bool
    q_now: bool | None = None
    p_previous: bool | None = None
    lifecycle_state: LifecycleState | None = None
    ordinal: int = 0

    def __post_init__(self) -> None:
        if not self.case_id:
            raise ValueError("case_id must be non-empty")
        if self.ordinal < 0:
            raise ValueError("ordinal must be non-negative")
        if (
            self.structure_id in {StructureId.P_AND_Q, StructureId.P_AND_NOT_Q}
            and self.q_now is None
        ):
            raise ValueError(f"{self.structure_id} requires q_now")
        if self.structure_id is StructureId.T2_P and self.p_previous is None:
            raise ValueError("T2(P) requires p_previous")
        if self.structure_id is StructureId.ACTIVE_AND_P and self.lifecycle_state is None:
            raise ValueError("ACTIVE AND P requires lifecycle_state")

    def canonical_record(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "lifecycle_state": self.lifecycle_state.value if self.lifecycle_state else None,
            "ordinal": self.ordinal,
            "p_now": self.p_now,
            "p_previous": self.p_previous,
            "q_now": self.q_now,
            "structure_id": self.structure_id.value,
        }


@dataclass(frozen=True, slots=True)
class Stage0Case:
    """Textualized Stage 0 case with model-visible and hidden metadata."""

    case_id: str
    commitment: str
    trigger_condition: str
    prior_state: str
    observed_event: str
    lifecycle_state: str | None
    structured_spec: StructuredCaseSpec
    truth_label: bool
    structure_id: StructureId
    authorship_source: str
    version_id: str
    case_set_hash: str | None = None

    def model_visible_payload(self) -> Mapping[str, str]:
        """Return the only fields authorized for prompt assembly."""

        visible = {
            "commitment": self.commitment,
            "trigger_condition": self.trigger_condition,
            "prior_state": self.prior_state,
            "observed_event": self.observed_event,
        }
        if self.lifecycle_state is not None:
            visible["lifecycle_state"] = self.lifecycle_state
        return MappingProxyType(visible)

    def with_case_set_hash(self, case_set_hash: str) -> Stage0Case:
        if len(case_set_hash) != 64:
            raise ValueError("case_set_hash must be a SHA-256 hex digest")
        return replace(self, case_set_hash=case_set_hash)

    def canonical_record(self) -> dict[str, Any]:
        """Return the exact serializable record, including hidden metadata."""

        return {
            "authorship_source": self.authorship_source,
            "case_id": self.case_id,
            "case_set_hash": self.case_set_hash,
            "commitment": self.commitment,
            "lifecycle_state": self.lifecycle_state,
            "observed_event": self.observed_event,
            "prior_state": self.prior_state,
            "structure_id": self.structure_id.value,
            "structured_spec": self.structured_spec.canonical_record(),
            "trigger_condition": self.trigger_condition,
            "truth_label": self.truth_label,
            "version_id": self.version_id,
        }


@dataclass(frozen=True, slots=True)
class EvaluatorProvenance:
    evaluator_name: str
    author: str
    authored_at: str
    grammar_version: str
    grammar_sha256: str
    independently_derived: bool
    implementation_sha256: str

    def __post_init__(self) -> None:
        if not self.independently_derived:
            raise ValueError("evaluator provenance must affirm independent derivation")
        if len(self.grammar_sha256) != 64 or len(self.implementation_sha256) != 64:
            raise ValueError("provenance hashes must be SHA-256 hex digests")
