"""Late-bound experimental inputs and frozen Stage 0 run manifest."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any

from .artifacts import FrozenArtifact, FrozenCaseSet, canonical_json_bytes, sha256_bytes
from .schema import EvaluatorProvenance


@dataclass(frozen=True, slots=True)
class ModelConfiguration:
    provider: str
    model_id: str
    version_or_snapshot: str | None
    reasoning_settings: Mapping[str, Any]
    temperature: float | None
    seed: int | None
    max_output_length: int
    api_parameters: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.provider or not self.model_id:
            raise ValueError("provider and exact model ID must be frozen")
        if self.max_output_length <= 0:
            raise ValueError("max output length must be positive")
        object.__setattr__(
            self, "reasoning_settings", MappingProxyType(dict(self.reasoning_settings))
        )
        object.__setattr__(
            self,
            "api_parameters",
            MappingProxyType(dict(self.api_parameters)),
        )

    def canonical_record(self) -> dict[str, Any]:
        return {
            "api_parameters": dict(self.api_parameters),
            "max_output_length": self.max_output_length,
            "model_id": self.model_id,
            "provider": self.provider,
            "reasoning_settings": dict(self.reasoning_settings),
            "seed": self.seed,
            "temperature": self.temperature,
            "version_or_snapshot": self.version_or_snapshot,
        }

    @property
    def sha256(self) -> str:
        return sha256_bytes(canonical_json_bytes(self.canonical_record()))


class UnresolvedExperimentalInputs(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class ExperimentalBindings:
    """Inputs that must remain absent until Ryan freezes Decisions 1 and 3."""

    prompt: FrozenArtifact | None = None
    model_configuration: ModelConfiguration | None = None

    def require_frozen(self) -> tuple[FrozenArtifact, ModelConfiguration]:
        missing = []
        if self.prompt is None:
            missing.append("final scoring prompt")
        if self.model_configuration is None:
            missing.append("experimental model/configuration")
        if missing:
            raise UnresolvedExperimentalInputs(
                "unresolved late-bound inputs: " + ", ".join(missing)
            )
        assert self.prompt is not None
        assert self.model_configuration is not None
        self.prompt.verify()
        return self.prompt, self.model_configuration


@dataclass(frozen=True, slots=True)
class RunManifest:
    protocol_version: str
    protocol_sha256: str
    execution_plan_version: str
    execution_plan_sha256: str
    case_set_sha256: str
    scoring_prompt_sha256: str
    parse_contract_sha256: str
    case_count: int
    positive_count: int
    negative_count: int
    model_configuration: Mapping[str, Any]
    model_configuration_sha256: str
    primary_evaluator: EvaluatorProvenance
    reference_evaluator: EvaluatorProvenance
    harness_revision: str
    timestamp: str
    run_id: str

    @classmethod
    def create(
        cls,
        *,
        protocol: FrozenArtifact,
        execution_plan: FrozenArtifact,
        case_set: FrozenCaseSet,
        bindings: ExperimentalBindings,
        parse_contract_sha256: str,
        primary_evaluator: EvaluatorProvenance,
        reference_evaluator: EvaluatorProvenance,
        harness_revision: str,
        timestamp: str,
        run_id: str,
    ) -> RunManifest:
        prompt, model = bindings.require_frozen()
        labels = [case.truth_label for case in case_set.cases]
        return cls(
            protocol_version="v1.0",
            protocol_sha256=protocol.sha256,
            execution_plan_version="stage0-merged-v1",
            execution_plan_sha256=execution_plan.sha256,
            case_set_sha256=case_set.sha256,
            scoring_prompt_sha256=prompt.sha256,
            parse_contract_sha256=parse_contract_sha256,
            case_count=len(case_set.cases),
            positive_count=sum(labels),
            negative_count=len(labels) - sum(labels),
            model_configuration=MappingProxyType(model.canonical_record()),
            model_configuration_sha256=model.sha256,
            primary_evaluator=primary_evaluator,
            reference_evaluator=reference_evaluator,
            harness_revision=harness_revision,
            timestamp=timestamp,
            run_id=run_id,
        )

    def validate_completeness(self) -> None:
        required_strings = (
            self.protocol_version,
            self.protocol_sha256,
            self.execution_plan_version,
            self.execution_plan_sha256,
            self.case_set_sha256,
            self.scoring_prompt_sha256,
            self.parse_contract_sha256,
            self.model_configuration_sha256,
            self.harness_revision,
            self.timestamp,
            self.run_id,
        )
        if not all(required_strings):
            raise ValueError("manifest contains an empty required field")
        if (self.case_count, self.positive_count, self.negative_count) != (80, 40, 40):
            raise ValueError("manifest must record exactly 80 cases with 40/40 balance")

    def canonical_record(self) -> dict[str, Any]:
        def provenance(value: EvaluatorProvenance) -> dict[str, Any]:
            return {
                "authored_at": value.authored_at,
                "author": value.author,
                "evaluator_name": value.evaluator_name,
                "grammar_sha256": value.grammar_sha256,
                "grammar_version": value.grammar_version,
                "implementation_sha256": value.implementation_sha256,
                "independently_derived": value.independently_derived,
            }

        return {
            "case_count": self.case_count,
            "case_set_sha256": self.case_set_sha256,
            "execution_plan_sha256": self.execution_plan_sha256,
            "execution_plan_version": self.execution_plan_version,
            "harness_revision": self.harness_revision,
            "model_configuration": dict(self.model_configuration),
            "model_configuration_sha256": self.model_configuration_sha256,
            "negative_count": self.negative_count,
            "parse_contract_sha256": self.parse_contract_sha256,
            "positive_count": self.positive_count,
            "primary_evaluator": provenance(self.primary_evaluator),
            "protocol_sha256": self.protocol_sha256,
            "protocol_version": self.protocol_version,
            "reference_evaluator": provenance(self.reference_evaluator),
            "run_id": self.run_id,
            "scoring_prompt_sha256": self.scoring_prompt_sha256,
            "timestamp": self.timestamp,
        }

    def to_exact_bytes(self) -> bytes:
        return canonical_json_bytes(self.canonical_record())

    @property
    def sha256(self) -> str:
        return sha256_bytes(self.to_exact_bytes())
