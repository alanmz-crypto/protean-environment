from __future__ import annotations

from dataclasses import replace

import pytest

from protean_stage0.defects import MechanicalDefect, MechanicalDefectKind
from protean_stage0.manifest import (
    ExperimentalBindings,
    RunManifest,
    UnresolvedExperimentalInputs,
)
from protean_stage0.validation import TruthDisagreement, validate_pre_run

from .helpers import evaluator_materials, generated_test_cases, manifest_materials


def test_independent_evaluators_agree_on_all_80_generated_specs() -> None:
    primary, reference, report = evaluator_materials()
    assert primary.author != reference.author  # type: ignore[attr-defined]
    assert primary.implementation_sha256 != reference.implementation_sha256  # type: ignore[attr-defined]
    assert report.case_count == 80


def test_truth_disagreement_blocks_scoring(monkeypatch: pytest.MonkeyPatch) -> None:
    primary, reference, _ = evaluator_materials()
    monkeypatch.setattr("protean_stage0.validation.evaluate_reference_truth", lambda case: False)
    from protean_stage0.validation import verify_truth_agreement

    with pytest.raises(TruthDisagreement):
        verify_truth_agreement(
            generated_test_cases(),
            primary_provenance=primary,  # type: ignore[arg-type]
            reference_provenance=reference,  # type: ignore[arg-type]
        )


def test_unresolved_prompt_and_model_block_manifest_construction() -> None:
    manifest, case_set, protocol, plan, _, _ = manifest_materials()
    with pytest.raises(UnresolvedExperimentalInputs):
        RunManifest.create(
            protocol=protocol,
            execution_plan=plan,
            case_set=case_set,
            bindings=ExperimentalBindings(),
            parse_contract_sha256=manifest.parse_contract_sha256,
            primary_evaluator=manifest.primary_evaluator,
            reference_evaluator=manifest.reference_evaluator,
            harness_revision="TEST",
            timestamp="TEST",
            run_id="TEST",
        )


def test_manifest_hash_mismatch_blocks_pre_run() -> None:
    manifest, case_set, protocol, plan, bindings, agreement = manifest_materials()
    bad_manifest = replace(manifest, scoring_prompt_sha256="0" * 64)
    with pytest.raises(MechanicalDefect, match="prompt") as captured:
        validate_pre_run(
            manifest=bad_manifest,
            case_set=case_set,
            protocol=protocol,
            execution_plan=plan,
            bindings=bindings,
            agreement=agreement,
        )
    assert captured.value.evidence.kind is MechanicalDefectKind.WRONG_FROZEN_PROMPT


def test_complete_synthetic_manifest_passes_pre_run() -> None:
    manifest, case_set, protocol, plan, bindings, agreement = manifest_materials()
    validated = validate_pre_run(
        manifest=manifest,
        case_set=case_set,
        protocol=protocol,
        execution_plan=plan,
        bindings=bindings,
        agreement=agreement,
    )
    validated.assert_validated()
    assert len(manifest.to_exact_bytes()) > 0
    assert len(manifest.sha256) == 64


def test_agreement_report_from_another_case_set_is_rejected() -> None:
    manifest, case_set, protocol, plan, bindings, agreement = manifest_materials()
    unrelated = replace(agreement, agreement_sha256="0" * 64)
    with pytest.raises(ValueError, match="does not cover"):
        validate_pre_run(
            manifest=manifest,
            case_set=case_set,
            protocol=protocol,
            execution_plan=plan,
            bindings=bindings,
            agreement=unrelated,
        )
