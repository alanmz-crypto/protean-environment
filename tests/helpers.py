"""Clearly synthetic, non-experimental test material builders."""

from __future__ import annotations

import json
from pathlib import Path

from protean_stage0.artifacts import FrozenArtifact, FrozenCaseSet
from protean_stage0.generator import GeneratedCaseSpec, generate_structured_cases
from protean_stage0.grammar import FROZEN_STRUCTURES
from protean_stage0.manifest import ExperimentalBindings, ModelConfiguration, RunManifest
from protean_stage0.parse_contract import PLAIN_DECIMAL_V1_SHA256
from protean_stage0.textualize import TemplateBank, textualize_case
from protean_stage0.validation import (
    TruthAgreementReport,
    ValidatedRun,
    load_evaluator_provenance,
    validate_pre_run,
    verify_truth_agreement,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
TEST_SEED = "TEST-ONLY-NOT-AN-EXPERIMENTAL-SEED"
TEST_PROMPT = b"TEST ONLY: return a synthetic fixture score; not an experimental scoring prompt."


def make_test_template_bank() -> TemplateBank:
    templates = {}
    for structure in FROZEN_STRUCTURES:
        template = {
            "commitment": "TEST ONLY: {subject} will {action} when {p_condition} applies.",
            "trigger_condition": "Evaluate {p_condition} with {q_condition} when relevant.",
            "prior_state": "Earlier {p_condition} was {p_previous}.",
            "observed_event": "Now {p_condition} is {p_now}; {q_condition} is {q_now}.",
            "lifecycle_state": "Lifecycle is {lifecycle}.",
        }
        templates[structure.value] = [template, dict(template)]
    raw = {
        "authorship_source": "synthetic-test-fixture-only",
        "slots": [
            {
                "action": "record a test marker",
                "subject": "the synthetic worker",
                "p_condition": "the amber test flag",
                "q_condition": "the blue test flag",
            },
            {
                "action": "emit a test token",
                "subject": "the fixture worker",
                "p_condition": "the square test signal",
                "q_condition": "the round test signal",
            },
        ],
        "templates": templates,
        "version_id": "synthetic-template-bank-v1-test-only",
    }
    return TemplateBank.from_bytes(json.dumps(raw, sort_keys=True).encode())


def generated_test_cases() -> tuple[GeneratedCaseSpec, ...]:
    return generate_structured_cases(TEST_SEED)


def frozen_test_case_set() -> FrozenCaseSet:
    bank = make_test_template_bank()
    cases = tuple(
        textualize_case(item, seed="TEST-ONLY-TEXT-SEED", bank=bank)
        for item in generated_test_cases()
    )
    return FrozenCaseSet.from_cases(cases)


def evaluator_materials() -> tuple[object, object, TruthAgreementReport]:
    primary = load_evaluator_provenance(
        REPO_ROOT / "docs/primary-evaluator-provenance.json",
        REPO_ROOT / "src/protean_stage0/primary_truth.py",
    )
    reference = load_evaluator_provenance(
        REPO_ROOT / "docs/reference-evaluator-provenance.json",
        REPO_ROOT / "src/protean_stage0/reference_truth.py",
    )
    agreement = verify_truth_agreement(
        generated_test_cases(),
        primary_provenance=primary,
        reference_provenance=reference,
    )
    return primary, reference, agreement


def synthetic_bindings() -> ExperimentalBindings:
    return ExperimentalBindings(
        prompt=FrozenArtifact.from_bytes("synthetic-test-prompt", TEST_PROMPT),
        model_configuration=ModelConfiguration(
            provider="test-fake-provider",
            model_id="test-fake-model",
            version_or_snapshot="test-snapshot",
            reasoning_settings={"mode": "fake"},
            temperature=0.0,
            seed=7,
            max_output_length=16,
            api_parameters={"transport": "in-memory-fake"},
        ),
    )


def manifest_materials() -> tuple[
    RunManifest,
    FrozenCaseSet,
    FrozenArtifact,
    FrozenArtifact,
    ExperimentalBindings,
    TruthAgreementReport,
]:
    case_set = frozen_test_case_set()
    protocol = FrozenArtifact.from_bytes(
        "protocol", (REPO_ROOT / "docs/PROTOCOL-prospective-control-v1.0.md").read_bytes()
    )
    plan = FrozenArtifact.from_bytes(
        "execution-plan", (REPO_ROOT / "docs/EXECUTION-stage0.md").read_bytes()
    )
    bindings = synthetic_bindings()
    primary, reference, agreement = evaluator_materials()
    manifest = RunManifest.create(
        protocol=protocol,
        execution_plan=plan,
        case_set=case_set,
        bindings=bindings,
        parse_contract_sha256=PLAIN_DECIMAL_V1_SHA256,
        primary_evaluator=primary,  # type: ignore[arg-type]
        reference_evaluator=reference,  # type: ignore[arg-type]
        harness_revision="TEST-ONLY-REVISION",
        timestamp="2026-08-19T00:00:00Z",
        run_id="TEST-ONLY-RUN",
    )
    return manifest, case_set, protocol, plan, bindings, agreement


def validated_test_run() -> ValidatedRun:
    manifest, case_set, protocol, plan, bindings, agreement = manifest_materials()
    return validate_pre_run(
        manifest=manifest,
        case_set=case_set,
        protocol=protocol,
        execution_plan=plan,
        bindings=bindings,
        agreement=agreement,
    )
