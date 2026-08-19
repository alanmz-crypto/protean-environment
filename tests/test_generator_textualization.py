from __future__ import annotations

from collections import Counter
from dataclasses import replace

import pytest

from protean_stage0.artifacts import FrozenCaseSet
from protean_stage0.generator import generate_structured_cases
from protean_stage0.grammar import FROZEN_STRUCTURES, StructureId
from protean_stage0.schema import StructuredCaseSpec
from protean_stage0.textualize import TextTemplate, assignment_for

from .helpers import TEST_SEED, frozen_test_case_set, make_test_template_bank


def test_exact_structural_and_class_allocation() -> None:
    cases = generate_structured_cases(TEST_SEED)
    assert len(cases) == 80
    assert len({item.spec.case_id for item in cases}) == 80
    assert Counter(item.truth_label for item in cases) == {False: 40, True: 40}
    for structure in FROZEN_STRUCTURES:
        subset = [item for item in cases if item.spec.structure_id is structure]
        assert len(subset) == 16
        assert Counter(item.truth_label for item in subset) == {False: 8, True: 8}


def test_seed_is_deterministic_and_material() -> None:
    first = generate_structured_cases(TEST_SEED)
    assert first == generate_structured_cases(TEST_SEED)
    assert first != generate_structured_cases(TEST_SEED + "-different")


def test_assignment_cannot_depend_on_truth_bearing_state() -> None:
    bank = make_test_template_bank()
    negative = StructuredCaseSpec("same-id", StructureId.P, False, ordinal=4)
    positive = replace(negative, p_now=True)
    assert assignment_for("test-seed", negative, bank) == assignment_for(
        "test-seed", positive, bank
    )


def test_model_visible_payload_excludes_all_hidden_metadata() -> None:
    case = frozen_test_case_set().cases[0]
    payload = dict(case.model_visible_payload())
    assert set(payload) <= {
        "commitment",
        "trigger_condition",
        "prior_state",
        "observed_event",
        "lifecycle_state",
    }
    serialized = repr(payload)
    assert "truth_label" not in serialized
    assert "structure_id" not in serialized
    assert case.case_id not in serialized
    assert case.case_set_hash is not None
    assert case.case_set_hash not in serialized


def test_template_rejects_hidden_metadata_placeholders() -> None:
    template = TextTemplate(
        commitment="{truth_label}",
        trigger_condition="test",
        prior_state="test",
        observed_event="test",
    )
    with pytest.raises(ValueError, match="hidden"):
        template.validate()


def test_case_set_hash_is_exact_and_tamper_evident() -> None:
    frozen = frozen_test_case_set()
    frozen.verify()
    assert all(case.case_set_hash == frozen.sha256 for case in frozen.cases)
    tampered = FrozenCaseSet(frozen.cases, frozen.artifact_bytes + b"x", frozen.sha256)
    with pytest.raises(ValueError, match="frozen artifact bytes"):
        tampered.verify()
    changed_case = replace(frozen.cases[0], observed_event="tampered")
    mismatched_objects = FrozenCaseSet(
        (changed_case, *frozen.cases[1:]), frozen.artifact_bytes, frozen.sha256
    )
    with pytest.raises(ValueError, match="do not match"):
        mismatched_objects.verify()


def test_no_experimental_case_artifact_is_present() -> None:
    assert not list((__import__("pathlib").Path("cases")).glob("*.json"))
