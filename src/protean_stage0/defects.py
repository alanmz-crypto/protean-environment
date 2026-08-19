"""Performance-blind mechanical-defect and single-restart controls."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class MechanicalDefectKind(StrEnum):
    WRONG_PROMPT_ASSEMBLY = "wrong_prompt_assembly"
    WRONG_FROZEN_PROMPT = "wrong_frozen_prompt"
    WRONG_MODEL_CONFIGURATION = "wrong_model_configuration"
    PARSER_SPECIFICATION_DEVIATION = "parser_specification_deviation"
    CORRUPTED_CASE_PAYLOAD = "corrupted_case_payload"
    HARNESS_IMPLEMENTATION_DEFECT = "harness_implementation_defect"
    WRONG_GROUND_TRUTH = "wrong_ground_truth"


@dataclass(frozen=True, slots=True)
class MechanicalDefectEvidence:
    """Evidence about frozen machinery; performance fields are impossible by design."""

    kind: MechanicalDefectKind
    description: str
    expected_fingerprint: str
    observed_fingerprint: str

    def __post_init__(self) -> None:
        if not self.description:
            raise ValueError("mechanical defect evidence requires a description")
        if self.expected_fingerprint == self.observed_fingerprint:
            raise ValueError("mechanical defect requires an observed deviation")


class MechanicalDefect(RuntimeError):
    def __init__(self, evidence: MechanicalDefectEvidence):
        super().__init__(evidence.description)
        self.evidence = evidence


@dataclass(slots=True)
class RestartController:
    restarts_used: int = 0

    def authorize_restart(
        self,
        evidence: MechanicalDefectEvidence,
        *,
        invalidated_case_set_hash: str,
        fresh_case_set_hash: str,
    ) -> None:
        if self.restarts_used >= 1:
            raise RuntimeError("Protocol v1.0 permits only one Stage 0 restart")
        if invalidated_case_set_hash == fresh_case_set_hash:
            raise ValueError("a mechanical-defect restart requires a fresh case set")
        if not evidence.description:
            raise ValueError("documented mechanical defect evidence is required")
        self.restarts_used += 1
