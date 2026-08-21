"""Hermetic Stage-1A real-origin tests (no provider calls)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from protean_stage0.artifacts import sha256_bytes
from protean_stage0.grammar import FROZEN_STRUCTURES, StructureId
from protean_stage0.harness import ModelResponse
from protean_stage0.stage1a_cases import build_stage1a_cases
from protean_stage0.stage1a_driver import (
    Stage1APreparedRun,
    require_real_origin_coverage,
)
from protean_stage0.stage1a_origin import (
    ORIGIN_PROMPT,
    ORIGIN_PROMPT_SHA256,
    ORIGIN_RESPONSE_CONTRACT_SHA256,
    ORIGIN_RESPONSE_CONTRACT_SPEC,
    OriginResponseContractFailure,
    OriginSessionArtifact,
    build_origin_request_bytes,
    canonical_commitment_records,
    commitments_hash,
    verify_origin_artifact,
)
from protean_stage0.textualize import TemplateBank

REPO = Path(__file__).resolve().parents[1]
_FAKE_LUNA_CONFIG_SHA = "5" * 64


def _dummy_prompt() -> Any:
    from protean_stage0.artifacts import FrozenArtifact

    return FrozenArtifact.from_bytes("s1a-prompt", b"x")


def _dummy_config() -> Any:
    from protean_stage0.manifest import ModelConfiguration

    return ModelConfiguration(
        provider="test",
        model_id="test-model",
        version_or_snapshot=None,
        reasoning_settings={},
        temperature=0.1,
        seed=None,
        max_output_length=64,
        api_parameters={},
    )


def _cases() -> tuple[Any, ...]:
    bank = TemplateBank.from_bytes((REPO / "stage0/template-bank-v1.json").read_bytes())
    return build_stage1a_cases(template_bank=bank)


def _group_by_structure(cases: tuple[Any, ...]) -> dict[str, list[Any]]:
    out: dict[str, list[Any]] = {s.value: [] for s in FROZEN_STRUCTURES}
    for c in cases:
        out[c.generated.spec.structure_id.value].append(c)
    return out


def _case_to_structure(cases: tuple[Any, ...]) -> dict[str, Any]:
    return {c.generated.spec.case_id: c.generated.spec.structure_id for c in cases}


def _records_for(cases: list[Any]) -> list[tuple[str, bytes]]:
    return [(c.generated.spec.case_id, c.textualized.commitment.encode()) for c in cases]


def _origin_artifact(
    structure: str,
    cases: list[Any],
    *,
    origin_run_id: str,
    adopt_all: bool = True,
    override_records: list[tuple[str, bytes]] | None = None,
    response_text: str | None = None,
) -> OriginSessionArtifact:
    records = canonical_commitment_records(
        override_records if override_records is not None else _records_for(cases)
    )
    case_ids = tuple(e for e, _ in records)
    adoption = {cid: adopt_all for cid in case_ids}
    # Provider response = one ADOPT line per case (the frozen contract).
    if response_text is None:
        response_text = "\n".join(f"ADOPT {cid}" for cid in case_ids)
    provider_bytes = response_text.encode()
    request_sha = sha256_bytes(build_origin_request_bytes(ORIGIN_PROMPT, list(records)))
    return OriginSessionArtifact(
        origin_run_id=origin_run_id,
        structure=StructureId(structure),
        commitment_records=records,
        commitment_sha256=commitments_hash(records),
        model_configuration_sha256=_FAKE_LUNA_CONFIG_SHA,
        request_sha256=request_sha,
        provider_response_sha256=sha256_bytes(provider_bytes),
        provider_response_bytes=provider_bytes,
        adoption=adoption,
        timestamp="2026-08-21T00:00:00Z",
        provider_metadata={"model": "gpt-5.6-luna", "status": "completed"},
    )


def _all_origins(
    cases: tuple[Any, ...], run_base: str = "origin-"
) -> tuple[OriginSessionArtifact, ...]:
    grouped = _group_by_structure(cases)
    return tuple(
        _origin_artifact(s.value, grouped[s.value], origin_run_id=run_base + s.value)
        for s in FROZEN_STRUCTURES
    )


# ---- 1. origin mandatory (including zero artifacts) ----
def test_origin_mandatory_zero_artifacts_no_client_no_calls() -> None:
    cases = _cases()
    constructed: list[str] = []
    calls: list[str] = []

    def factory() -> Any:
        constructed.append("client")
        raise AssertionError("must not construct the calibration client")

    prepared = Stage1APreparedRun(
        cases=cases,
        scoring_prompt=_dummy_prompt(),
        model_configuration=_dummy_config(),
        seal=lambda: None,
        client_factory=factory,
        origin_artifacts=(),  # zero artifacts
    )
    with pytest.raises(ValueError, match="origin sessions"):
        prepared.run()
    assert constructed == []  # 0 client constructions
    assert calls == []  # 0 scoring calls


# ---- 2. exact five-structure allocation ----
def test_exact_five_structure_allocation() -> None:
    cases = _cases()
    grouped = _group_by_structure(cases)
    assert len(grouped) == 5
    for s in FROZEN_STRUCTURES:
        assert len(grouped[s.value]) == 12
    all_ids = [c.generated.spec.case_id for c in cases]
    assert len(set(all_ids)) == 60
    require_real_origin_coverage(_all_origins(cases), frozenset(all_ids), _case_to_structure(cases))


def test_duplicate_structure_fails() -> None:
    cases = _cases()
    artifacts = _all_origins(cases)
    # Replace the last artifact's structure with a duplicate of the first.
    dup = list(artifacts)
    wrong = _origin_artifact("P", _group_by_structure(cases)["P AND Q"], origin_run_id="dup")
    dup[-1] = wrong  # now two "P" artifacts
    with pytest.raises(ValueError, match="duplicate origin structure"):
        require_real_origin_coverage(tuple(dup), frozenset(c.generated.spec.case_id for c in cases))


def test_missing_structure_fails() -> None:
    cases = _cases()
    grouped = _group_by_structure(cases)
    artifacts = [
        _origin_artifact(s.value, grouped[s.value], origin_run_id=s.value)
        for s in FROZEN_STRUCTURES
        if s.value != "P"  # drop P
    ]
    with pytest.raises(ValueError, match="origin sessions"):
        require_real_origin_coverage(
            tuple(artifacts), frozenset(c.generated.spec.case_id for c in cases)
        )


def test_12_valid_ids_assigned_to_wrong_structure_fails() -> None:
    cases = _cases()
    grouped = _group_by_structure(cases)
    # An artifact declares structure P but covers the 12 P AND Q case IDs, placed
    # FIRST so the migration check (not a duplicate-structure check) fires.
    bad = _origin_artifact("P", grouped["P AND Q"], origin_run_id="migration")
    artifacts = list(_all_origins(cases))
    artifacts[0] = bad  # replace P's artifact with a P-declaring one covering P AND Q cases
    with pytest.raises(ValueError, match="migrated"):
        require_real_origin_coverage(
            tuple(artifacts),
            frozenset(c.generated.spec.case_id for c in cases),
            _case_to_structure(cases),
        )


# ---- 4. unambiguous ordered request records ----
def test_request_records_are_ordered_binary_mapping() -> None:
    cases = _cases()
    grouped = _group_by_structure(cases)
    records = _records_for(grouped["P"])
    req = build_origin_request_bytes(ORIGIN_PROMPT, records)
    # The request embeds the SAME case IDs the response contract references and the
    # exact commitment text per case, as an ordered list.
    for cid, cbytes in records:
        assert cid.encode() in req
        assert cbytes in req
    # no truth / future-state info present (the frozen prompt text may legitimately
    # mention 'calibration' in its isolation clause; that is not leakage)
    assert b"truth_label" not in req
    assert b"observed_event" not in req


def test_request_sha_reproducible() -> None:
    cases = _cases()
    grouped = _group_by_structure(cases)
    records = _records_for(grouped["P"])
    r1 = build_origin_request_bytes(ORIGIN_PROMPT, records)
    r2 = build_origin_request_bytes(ORIGIN_PROMPT, list(records))
    assert r1 == r2
    assert sha256_bytes(r1) == sha256_bytes(r2)


# ---- origin prompt + response contract frozen ----
def test_origin_prompt_and_contract_frozen() -> None:
    assert len(ORIGIN_PROMPT) > 0
    assert sha256_bytes(ORIGIN_PROMPT) == ORIGIN_PROMPT_SHA256
    assert sha256_bytes(ORIGIN_RESPONSE_CONTRACT_SPEC) == ORIGIN_RESPONSE_CONTRACT_SHA256


# ---- 5. real origin-artifact seal verification ----
def test_verify_origin_artifact_passes() -> None:
    cases = _cases()
    grouped = _group_by_structure(cases)
    art = _origin_artifact("P", grouped["P"], origin_run_id="o-P")
    expected_ids = tuple(c.generated.spec.case_id for c in grouped["P"])
    verify_origin_artifact(
        art,
        origin_prompt=ORIGIN_PROMPT,
        expected_structure=StructureId("P"),
        expected_case_ids=expected_ids,
        authoritative_luna_config_sha256=_FAKE_LUNA_CONFIG_SHA,
        expected_provider_model="gpt-5.6-luna",
        expected_provider_status="completed",
    )


def test_verify_origin_artifact_wrong_structure_fails() -> None:
    cases = _cases()
    grouped = _group_by_structure(cases)
    art = _origin_artifact("P", grouped["P"], origin_run_id="o-P")
    with pytest.raises(OriginResponseContractFailure, match="wrong structure"):
        verify_origin_artifact(
            art,
            origin_prompt=ORIGIN_PROMPT,
            expected_structure=StructureId("P AND Q"),
            expected_case_ids=tuple(c.generated.spec.case_id for c in grouped["P"]),
            authoritative_luna_config_sha256=_FAKE_LUNA_CONFIG_SHA,
        )


def test_verify_origin_artifact_tampered_provider_bytes_fails() -> None:
    cases = _cases()
    grouped = _group_by_structure(cases)
    case_ids = tuple(c.generated.spec.case_id for c in grouped["P"])
    # Build an artifact with a genuinely malformed provider response (bytes and SHA
    # consistent, so it constructs) that still fails the frozen-contract reparse.
    bad_art = _origin_artifact(
        "P",
        grouped["P"],
        origin_run_id="o-P",
        response_text="\n".join(f"ADOPT {cid}" for cid in case_ids[:11]),  # only 11 adopted
    )
    with pytest.raises(OriginResponseContractFailure, match="Adopt|origin|commitment|adopt"):
        verify_origin_artifact(
            bad_art,
            origin_prompt=ORIGIN_PROMPT,
            expected_structure=StructureId("P"),
            expected_case_ids=case_ids,
            authoritative_luna_config_sha256=_FAKE_LUNA_CONFIG_SHA,
        )


def test_verify_origin_artifact_manual_boolean_not_proof() -> None:
    # A manually populated adoption dict is NOT proof; the verifier reparses the
    # provider response under the frozen contract. If the response only adopts 11
    # commitments, verification fails even if the artifact's stored adoption says 12.
    cases = _cases()
    grouped = _group_by_structure(cases)
    records = _records_for(grouped["P"])
    case_ids = tuple(e for e, _ in records)
    # provider response adopts only the first 11 -> contract failure
    provider_bytes = ("\n".join(f"ADOPT {cid}" for cid in case_ids[:-1])).encode()
    request_sha = sha256_bytes(build_origin_request_bytes(ORIGIN_PROMPT, list(records)))
    art = OriginSessionArtifact(
        origin_run_id="o-P",
        structure=StructureId("P"),
        commitment_records=tuple(records),
        commitment_sha256=commitments_hash(tuple(records)),
        model_configuration_sha256=_FAKE_LUNA_CONFIG_SHA,
        request_sha256=request_sha,
        provider_response_sha256=sha256_bytes(provider_bytes),
        provider_response_bytes=provider_bytes,
        adoption={cid: True for cid in case_ids},  # manually claims all 12
        timestamp="2026-08-21T00:00:00Z",
        provider_metadata={"model": "gpt-5.6-luna", "status": "completed"},
    )
    with pytest.raises((OriginResponseContractFailure, ValueError)):
        verify_origin_artifact(
            art,
            origin_prompt=ORIGIN_PROMPT,
            expected_structure=StructureId("P"),
            expected_case_ids=case_ids,
            authoritative_luna_config_sha256=_FAKE_LUNA_CONFIG_SHA,
        )


# ---- 5/5 unlock vs <5 gates ----
def test_5_of_5_unlock_calibration_preflight() -> None:
    cases = _cases()
    artifacts = _all_origins(cases)
    require_real_origin_coverage(artifacts, frozenset(c.generated.spec.case_id for c in cases))


def test_fewer_than_5_never_construct_scoring_client() -> None:
    cases = _cases()
    constructed: list[str] = []

    def factory() -> Any:
        constructed.append("client")
        raise AssertionError("must not construct the client")

    prepared = Stage1APreparedRun(
        cases=cases,
        scoring_prompt=_dummy_prompt(),
        model_configuration=_dummy_config(),
        seal=lambda: None,
        client_factory=factory,
        origin_artifacts=_all_origins(cases)[:4],
    )
    with pytest.raises(ValueError):
        prepared.run()
    assert constructed == []


# ---- scoring-context isolation ----
def test_scoring_context_only_authorized_persisted_case_record() -> None:
    cases = _cases()
    allowed = {
        "commitment",
        "trigger_condition",
        "prior_state",
        "observed_event",
        "lifecycle_state",
    }
    for c in cases[:5]:
        ctx = dict(c.cross_session.judgment_context)
        assert set(ctx) <= allowed
        for bad in ("conversation", "raw_response", "origin", "truth", "calibration"):
            assert bad not in ctx


def test_no_cross_case_data_from_shared_origin_reaches_scoring() -> None:
    cases = _cases()
    grouped = _group_by_structure(cases)
    for c in grouped["P"]:
        ctx = dict(c.cross_session.judgment_context)
        joined = " ".join(ctx.values()) + " " + json.dumps(ctx)
        other_ids = [
            x.generated.spec.case_id
            for x in grouped["P"]
            if x.generated.spec.case_id != c.generated.spec.case_id
        ]
        for oid in other_ids:
            assert oid not in joined, f"cross-case leakage of {oid} into scoring context"


# ---- integrated preflight ordering (seal -> origin -> client -> scoring) ----
def test_preflight_ordering_seal_then_client_then_scoring() -> None:
    from protean_stage0.artifacts import FrozenArtifact
    from protean_stage0.stage1a_driver import Stage1APreparedRun

    constructed: list[str] = []
    calls: list[str] = []

    class _Client:
        def make_single_decision(self, request: Any) -> Any:
            calls.append("call")
            return ModelResponse(b"0.73", {})

    def factory() -> Any:
        constructed.append("client")
        return _Client()

    cases = _cases()
    prepared = Stage1APreparedRun(
        cases=cases,
        scoring_prompt=FrozenArtifact.from_bytes("p", b"x"),
        model_configuration=_dummy_config(),
        seal=lambda: None,
        client_factory=factory,
        origin_artifacts=_all_origins(cases),
    )
    prepared.run()
    assert constructed == ["client"]
    assert len(calls) == len(cases)  # one call per case, after a single client


def test_seal_mismatch_yields_zero_clients_and_zero_calls() -> None:
    from protean_stage0.artifacts import FrozenArtifact
    from protean_stage0.stage1a_driver import Stage1APreparedRun

    constructed: list[str] = []
    calls: list[str] = []

    def _client_factory() -> object:
        constructed.append("client")
        return object()

    def _seal_boom() -> None:
        raise ValueError("Stage-1A seal mismatch: harness revision")

    prepared = Stage1APreparedRun(
        cases=_cases(),
        scoring_prompt=FrozenArtifact.from_bytes("p", b"x"),
        model_configuration=_dummy_config(),
        seal=_seal_boom,
        client_factory=_client_factory,
    )
    with pytest.raises(ValueError, match="seal mismatch"):
        prepared.run()
    assert constructed == []  # no client built
    assert calls == []
