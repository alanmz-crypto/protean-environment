"""Truth-agreement and pre-run protocol validation gates."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from .artifacts import FrozenArtifact, FrozenCaseSet, canonical_json_bytes, sha256_bytes
from .defects import MechanicalDefect, MechanicalDefectEvidence, MechanicalDefectKind
from .generator import GeneratedCaseSpec
from .grammar import FROZEN_STRUCTURES, GRAMMAR_SHA256, GRAMMAR_VERSION
from .manifest import ExperimentalBindings, RunManifest
from .parse_contract import PLAIN_DECIMAL_V1_SHA256
from .primary_truth import evaluate_truth
from .reference_truth import evaluate_reference_truth
from .schema import EvaluatorProvenance


class TruthDisagreement(RuntimeError):
    pass


_VALIDATION_TOKEN = object()


@dataclass(frozen=True, slots=True)
class ValidatedRun:
    manifest: RunManifest
    case_set: FrozenCaseSet
    bindings: ExperimentalBindings
    _token: object

    def assert_validated(self) -> None:
        if self._token is not _VALIDATION_TOKEN:
            raise ValueError("model calls require the complete pre-run validation gate")


@dataclass(frozen=True, slots=True)
class TruthAgreementReport:
    case_count: int
    agreement_sha256: str
    primary_evaluator_sha256: str
    reference_evaluator_sha256: str


def load_evaluator_provenance(
    provenance_path: Path, implementation_path: Path
) -> EvaluatorProvenance:
    raw = json.loads(provenance_path.read_bytes())
    actual_implementation_hash = sha256_bytes(implementation_path.read_bytes())
    if raw["implementation_sha256"] != actual_implementation_hash:
        raise ValueError(f"evaluator source hash mismatch: {implementation_path}")
    if raw["grammar_version"] != GRAMMAR_VERSION or raw["grammar_sha256"] != GRAMMAR_SHA256:
        raise ValueError("evaluator provenance does not match frozen grammar")
    return EvaluatorProvenance(
        evaluator_name=raw["evaluator_name"],
        author=raw["author"],
        authored_at=raw["authored_at"],
        grammar_version=raw["grammar_version"],
        grammar_sha256=raw["grammar_sha256"],
        independently_derived=raw["independently_derived"],
        implementation_sha256=raw["implementation_sha256"],
    )


def verify_truth_agreement(
    cases: tuple[GeneratedCaseSpec, ...],
    *,
    primary_provenance: EvaluatorProvenance,
    reference_provenance: EvaluatorProvenance,
) -> TruthAgreementReport:
    if primary_provenance.author == reference_provenance.author:
        raise ValueError("primary and reference evaluators require distinct authorship provenance")
    if primary_provenance.implementation_sha256 == reference_provenance.implementation_sha256:
        raise ValueError("primary and reference evaluator sources must be distinct")
    if primary_provenance.grammar_sha256 != reference_provenance.grammar_sha256:
        raise ValueError("evaluators did not use the same frozen grammar")

    records = []
    for generated in cases:
        primary = evaluate_truth(generated.spec)
        reference = evaluate_reference_truth(generated.spec)
        if primary is not reference:
            raise TruthDisagreement(f"truth evaluators disagree for {generated.spec.case_id}")
        if primary is not generated.truth_label:
            raise TruthDisagreement(f"generated truth label mismatch for {generated.spec.case_id}")
        records.append(
            {
                "structured_spec": generated.spec.canonical_record(),
                "truth_label": primary,
            }
        )
    return TruthAgreementReport(
        case_count=len(records),
        agreement_sha256=sha256_bytes(canonical_json_bytes(records)),
        primary_evaluator_sha256=primary_provenance.implementation_sha256,
        reference_evaluator_sha256=reference_provenance.implementation_sha256,
    )


def validate_pre_run(
    *,
    manifest: RunManifest,
    case_set: FrozenCaseSet,
    protocol: FrozenArtifact,
    execution_plan: FrozenArtifact,
    bindings: ExperimentalBindings,
    agreement: TruthAgreementReport,
) -> ValidatedRun:
    """Block every scored call unless all frozen mechanical checks pass."""

    manifest.validate_completeness()
    protocol.verify()
    execution_plan.verify()
    case_set.verify()
    prompt, model = bindings.require_frozen()

    expected_hashes = {
        "protocol": (
            manifest.protocol_sha256,
            protocol.sha256,
            MechanicalDefectKind.HARNESS_IMPLEMENTATION_DEFECT,
        ),
        "execution plan": (
            manifest.execution_plan_sha256,
            execution_plan.sha256,
            MechanicalDefectKind.HARNESS_IMPLEMENTATION_DEFECT,
        ),
        "case set": (
            manifest.case_set_sha256,
            case_set.sha256,
            MechanicalDefectKind.CORRUPTED_CASE_PAYLOAD,
        ),
        "prompt": (
            manifest.scoring_prompt_sha256,
            prompt.sha256,
            MechanicalDefectKind.WRONG_FROZEN_PROMPT,
        ),
        "model configuration": (
            manifest.model_configuration_sha256,
            model.sha256,
            MechanicalDefectKind.WRONG_MODEL_CONFIGURATION,
        ),
        "parse contract": (
            manifest.parse_contract_sha256,
            PLAIN_DECIMAL_V1_SHA256,
            MechanicalDefectKind.PARSER_SPECIFICATION_DEVIATION,
        ),
    }
    for name, (recorded, actual, defect_kind) in expected_hashes.items():
        if recorded != actual:
            raise MechanicalDefect(
                MechanicalDefectEvidence(
                    kind=defect_kind,
                    description=f"{name} hash mismatch blocks the run",
                    expected_fingerprint=recorded,
                    observed_fingerprint=actual,
                )
            )

    if agreement.case_count != 80:
        raise ValueError("truth agreement must cover all 80 cases")
    if agreement.primary_evaluator_sha256 != manifest.primary_evaluator.implementation_sha256:
        raise ValueError("primary evaluator provenance mismatch")
    if agreement.reference_evaluator_sha256 != manifest.reference_evaluator.implementation_sha256:
        raise ValueError("reference evaluator provenance mismatch")

    if manifest.primary_evaluator.author == manifest.reference_evaluator.author:
        raise ValueError("manifest evaluator authorship is not independent")
    if (
        manifest.primary_evaluator.grammar_version != GRAMMAR_VERSION
        or manifest.reference_evaluator.grammar_version != GRAMMAR_VERSION
        or manifest.primary_evaluator.grammar_sha256 != GRAMMAR_SHA256
        or manifest.reference_evaluator.grammar_sha256 != GRAMMAR_SHA256
    ):
        raise ValueError("manifest evaluators do not match the frozen grammar")
    recorded_model_hash = sha256_bytes(canonical_json_bytes(dict(manifest.model_configuration)))
    if recorded_model_hash != manifest.model_configuration_sha256:
        raise ValueError("manifest model configuration record/hash mismatch")

    if len(case_set.cases) != 80 or sum(case.truth_label for case in case_set.cases) != 40:
        raise ValueError("case set must contain exactly 80 cases with 40/40 truth balance")
    if len({case.case_id for case in case_set.cases}) != 80:
        raise ValueError("case IDs must be unique")
    expected_agreement_hash = sha256_bytes(
        canonical_json_bytes(
            [
                {
                    "structured_spec": case.structured_spec.canonical_record(),
                    "truth_label": case.truth_label,
                }
                for case in case_set.cases
            ]
        )
    )
    if expected_agreement_hash != agreement.agreement_sha256:
        raise ValueError("truth agreement report does not cover the frozen case set")

    for structure in FROZEN_STRUCTURES:
        subset = [case for case in case_set.cases if case.structure_id is structure]
        if len(subset) != 16 or sum(case.truth_label for case in subset) != 8:
            raise ValueError(f"frozen allocation mismatch for {structure}")
    visible_keys = {
        "commitment",
        "trigger_condition",
        "prior_state",
        "observed_event",
        "lifecycle_state",
    }
    for case in case_set.cases:
        if not all(
            (
                case.case_id,
                case.commitment,
                case.trigger_condition,
                case.prior_state,
                case.observed_event,
                case.authorship_source,
                case.version_id,
                case.case_set_hash,
            )
        ):
            raise ValueError(f"case has incomplete required fields: {case.case_id}")
        if case.structured_spec.case_id != case.case_id:
            raise ValueError("structured specification/case ID mismatch")
        if case.structured_spec.structure_id is not case.structure_id:
            raise ValueError("structured specification/structure metadata mismatch")
        primary_truth = evaluate_truth(case.structured_spec)
        reference_truth = evaluate_reference_truth(case.structured_spec)
        if primary_truth is not reference_truth or primary_truth is not case.truth_label:
            raise TruthDisagreement(f"frozen truth mismatch for {case.case_id}")
        payload_keys = set(case.model_visible_payload())
        if not payload_keys <= visible_keys:
            raise ValueError("hidden metadata entered model-visible payload")
        if any("truth" in key or "structure" in key for key in payload_keys):
            raise ValueError("truth-revealing metadata entered model-visible payload")
    return ValidatedRun(manifest, case_set, bindings, _VALIDATION_TOKEN)
