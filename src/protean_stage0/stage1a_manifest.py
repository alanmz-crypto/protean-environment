"""Stage-1A manifest: binds every frozen authority; fails closed before any call.

Mirrors the Stage-0 RunManifest philosophy but for the Stage-1A calibration run.
A Stage-1A manifest is created ONCE and is immutable; any hash/field mismatch
must stop before any provider call. It is not a Stage-0 manifest and does not
reuse the Stage-0 case set.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any

from .artifacts import FrozenArtifact, FrozenCaseSet, canonical_json_bytes, sha256_bytes
from .manifest import ModelConfiguration
from .schema import EvaluatorProvenance
from .stage1a_config import (
    CROSS_SESSION_REP_VERSION,
    STAGE1A_NEGATIVE,
    STAGE1A_PER_CLASS_PER_STRUCTURE,
    STAGE1A_PER_STRUCTURE,
    STAGE1A_POSITIVE,
    STAGE1A_TOTAL,
)


@dataclass(frozen=True, slots=True)
class Stage1AManifest:
    protocol_sha256: str
    protocol_version: str
    futility_amendment_sha256: str
    futility_amendment_version: str
    case_set_sha256: str
    scoring_prompt_sha256: str
    parse_contract_sha256: str
    model_configuration_sha256: str
    model_configuration: Mapping[str, Any]
    harness_revision: str
    cross_session_rep_version: str
    total_cases: int
    positive_count: int
    negative_count: int
    per_structure: int
    per_class_per_structure: int
    primary_evaluator: EvaluatorProvenance
    reference_evaluator: EvaluatorProvenance
    timestamp: str
    run_id: str
    _seal: object = field(repr=False, compare=False, default=None)

    @classmethod
    def create(
        cls,
        *,
        protocol: FrozenArtifact,
        futility_amendment: FrozenArtifact,
        case_set: FrozenCaseSet,
        scoring_prompt: FrozenArtifact,
        parse_contract_sha256: str,
        model_configuration: ModelConfiguration,
        harness_revision: str,
        primary_evaluator: EvaluatorProvenance,
        reference_evaluator: EvaluatorProvenance,
        timestamp: str,
        run_id: str,
    ) -> Stage1AManifest:
        if len(case_set.cases) != STAGE1A_TOTAL:
            raise ValueError("Stage-1A manifest requires exactly 60 cases")
        from .generator import GeneratedCaseSpec
        from .stage1a_cases import validate_stage1a_allocation

        validate_stage1a_allocation(
            tuple(GeneratedCaseSpec(c.structured_spec, c.truth_label) for c in case_set.cases)
        )
        return cls(
            protocol_sha256=protocol.sha256,
            protocol_version="prospective-control-v1.0",
            futility_amendment_sha256=futility_amendment.sha256,
            futility_amendment_version="stage1-futility-shared-score-v1.0.1-r1",
            case_set_sha256=case_set.sha256,
            scoring_prompt_sha256=scoring_prompt.sha256,
            parse_contract_sha256=parse_contract_sha256,
            model_configuration_sha256=model_configuration.sha256,
            model_configuration=MappingProxyType(dict(model_configuration.canonical_record())),
            harness_revision=harness_revision,
            cross_session_rep_version=CROSS_SESSION_REP_VERSION,
            total_cases=STAGE1A_TOTAL,
            positive_count=STAGE1A_POSITIVE,
            negative_count=STAGE1A_NEGATIVE,
            per_structure=STAGE1A_PER_STRUCTURE,
            per_class_per_structure=STAGE1A_PER_CLASS_PER_STRUCTURE,
            primary_evaluator=primary_evaluator,
            reference_evaluator=reference_evaluator,
            timestamp=timestamp,
            run_id=run_id,
        )

    def canonical_record(self) -> dict[str, Any]:
        def prov(p: EvaluatorProvenance) -> dict[str, Any]:
            return {
                "authored_at": p.authored_at,
                "author": p.author,
                "evaluator_name": p.evaluator_name,
                "grammar_sha256": p.grammar_sha256,
                "grammar_version": p.grammar_version,
                "implementation_sha256": p.implementation_sha256,
                "independently_derived": p.independently_derived,
            }

        return {
            "protocol_sha256": self.protocol_sha256,
            "protocol_version": self.protocol_version,
            "futility_amendment_sha256": self.futility_amendment_sha256,
            "futility_amendment_version": self.futility_amendment_version,
            "case_set_sha256": self.case_set_sha256,
            "scoring_prompt_sha256": self.scoring_prompt_sha256,
            "parse_contract_sha256": self.parse_contract_sha256,
            "model_configuration_sha256": self.model_configuration_sha256,
            "model_configuration": dict(self.model_configuration),
            "harness_revision": self.harness_revision,
            "cross_session_rep_version": self.cross_session_rep_version,
            "total_cases": self.total_cases,
            "positive_count": self.positive_count,
            "negative_count": self.negative_count,
            "per_structure": self.per_structure,
            "per_class_per_structure": self.per_class_per_structure,
            "primary_evaluator": prov(self.primary_evaluator),
            "reference_evaluator": prov(self.reference_evaluator),
            "timestamp": self.timestamp,
            "run_id": self.run_id,
        }

    def to_exact_bytes(self) -> bytes:
        return canonical_json_bytes(self.canonical_record())

    @property
    def sha256(self) -> str:
        return sha256_bytes(self.to_exact_bytes())

    def validate_completeness(self) -> None:
        required = (
            self.protocol_sha256,
            self.protocol_version,
            self.futility_amendment_sha256,
            self.futility_amendment_version,
            self.case_set_sha256,
            self.scoring_prompt_sha256,
            self.parse_contract_sha256,
            self.model_configuration_sha256,
            self.harness_revision,
            self.cross_session_rep_version,
            self.run_id,
        )
        if not all(required):
            raise ValueError("Stage-1A manifest contains an empty required field")
        if (self.total_cases, self.positive_count, self.negative_count) != (60, 30, 30):
            raise ValueError("Stage-1A manifest must record 60/30/30")
        if (self.per_structure, self.per_class_per_structure) != (12, 6):
            raise ValueError("Stage-1A manifest must record 12-per-structure, 6/6 per structure")


def validate_stage1a_manifest_seal(
    manifest: Stage1AManifest,
    *,
    protocol: FrozenArtifact,
    futility_amendment: FrozenArtifact,
    case_set: FrozenCaseSet,
    scoring_prompt: FrozenArtifact,
    parse_contract_sha256: str,
    model_configuration: ModelConfiguration,
    cross_session_rep_version: str = CROSS_SESSION_REP_VERSION,
) -> None:
    """Fail closed (raise) before any provider call on any Stage-1A mismatch."""
    checks = {
        "protocol": (manifest.protocol_sha256, protocol.sha256),
        "futility amendment": (manifest.futility_amendment_sha256, futility_amendment.sha256),
        "case set": (manifest.case_set_sha256, case_set.sha256),
        "scoring prompt": (manifest.scoring_prompt_sha256, scoring_prompt.sha256),
        "parse contract": (manifest.parse_contract_sha256, parse_contract_sha256),
        "model configuration": (
            manifest.model_configuration_sha256,
            model_configuration.sha256,
        ),
    }
    for name, (recorded, actual) in checks.items():
        if recorded != actual:
            raise ValueError(f"Stage-1A seal mismatch: {name}")
    if manifest.cross_session_rep_version != cross_session_rep_version:
        raise ValueError("Stage-1A seal mismatch: cross-session representation version")
    manifest.validate_completeness()
