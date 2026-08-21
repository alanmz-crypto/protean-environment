"""Hermetic Stage-1A real-origin wire tests (no provider calls; fake transport)."""

from __future__ import annotations

import base64
import json
from pathlib import Path
from typing import Any

import pytest

from protean_stage0.artifacts import sha256_bytes
from protean_stage0.direct_config import (
    DIRECT_CONFIG_HASH,
    MODEL,
    REASONING_CONTEXT,
    REASONING_EFFORT,
)
from protean_stage0.grammar import FROZEN_STRUCTURES, StructureId
from protean_stage0.harness import ModelResponse
from protean_stage0.stage1a_cases import build_stage1a_cases
from protean_stage0.stage1a_driver import Stage1APreparedRun, require_real_origin_coverage
from protean_stage0.stage1a_origin import (
    ORIGIN_PROMPT,
    ORIGIN_PROMPT_SHA256,
    ORIGIN_RESPONSE_CONTRACT_SHA256,
    ORIGIN_RESPONSE_CONTRACT_SPEC,
    ORIGIN_RESPONSE_CONTRACT_VERSION,
    OriginResponseContractFailure,
    OriginSessionArtifact,
    _parse_origin_adoptions_exact,
    build_origin_request_bytes,
    canonical_commitment_records,
    commitments_hash,
    parse_raw_provider_response,
    verify_origin_artifact,
)
from protean_stage0.textualize import TemplateBank

REPO = Path(__file__).resolve().parents[1]


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


def _dummy_prompt() -> Any:
    from protean_stage0.artifacts import FrozenArtifact

    return FrozenArtifact.from_bytes("s1a-prompt", b"x")


def _dummy_config() -> Any:
    from protean_stage0.manifest import ModelConfiguration

    return ModelConfiguration(
        provider="openai_responses_api",
        model_id=MODEL,
        version_or_snapshot=None,
        reasoning_settings={"effort": REASONING_EFFORT, "context": REASONING_CONTEXT},
        temperature=None,
        seed=None,
        max_output_length=128_000,
        api_parameters={},
    )


def _records_for(cases: list[Any]) -> list[tuple[str, bytes]]:
    return [(c.generated.spec.case_id, c.textualized.commitment.encode()) for c in cases]


def _luna_responses_json(case_ids: list[str], *, adopt_text: str | None = None) -> bytes:
    """A valid GPT-5.6 Luna /v1/responses JSON whose final output_text is adopt_text."""
    if adopt_text is None:
        adopt_text = "\n".join(f"ADOPT {cid}" for cid in case_ids)
    obj = {
        "id": "resp_origin",
        "object": "response",
        "created_at": 1700000000,
        "status": "completed",
        "model": MODEL,
        "reasoning": {"effort": REASONING_EFFORT, "context": REASONING_CONTEXT},
        "output": [
            {"type": "reasoning", "summary": []},
            {
                "type": "message",
                "role": "assistant",
                "status": "completed",
                "content": [{"type": "output_text", "text": adopt_text}],
            },
        ],
        "usage": {"input_tokens": 10, "output_tokens": 20, "total_tokens": 30},
    }
    return json.dumps(obj).encode()


def _origin_artifact(
    structure: str,
    cases: list[Any],
    *,
    origin_run_id: str,
    adopt_text: str | None = None,
    raw_override: bytes | None = None,
) -> OriginSessionArtifact:
    """Build a valid artifact from real wire evidence (fake Luna Responses JSON)."""
    records = canonical_commitment_records(_records_for(cases))
    case_ids = tuple(e for e, _ in records)
    raw = (
        raw_override
        if raw_override is not None
        else _luna_responses_json(list(case_ids), adopt_text=adopt_text)
    )
    final_out = parse_raw_provider_response(raw).encode()
    request_sha = sha256_bytes(build_origin_request_bytes(ORIGIN_PROMPT, list(records)))
    return OriginSessionArtifact(
        origin_run_id=origin_run_id,
        structure=StructureId(structure),
        commitment_records=records,
        commitment_sha256=commitments_hash(records),
        model_configuration_sha256=DIRECT_CONFIG_HASH,
        request_sha256=request_sha,
        raw_provider_response_sha256=sha256_bytes(raw),
        raw_provider_response_bytes=raw,
        final_output_sha256=sha256_bytes(final_out),
        final_output_bytes=final_out,
        timestamp="2026-08-21T00:00:00Z",
        provider_metadata={"model": MODEL, "status": "completed"},
    )


def _all_origins(
    cases: tuple[Any, ...], run_base: str = "origin-"
) -> tuple[OriginSessionArtifact, ...]:
    grouped = _group_by_structure(cases)
    return tuple(
        _origin_artifact(s.value, grouped[s.value], origin_run_id=run_base + s.value)
        for s in FROZEN_STRUCTURES
    )


# ---- 1. full verifier integrated into mandatory preflight ----
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
        origin_artifacts=(),  # zero artifacts -> MUST fail before client
    )
    with pytest.raises(ValueError, match="origin sessions"):
        prepared.run()
    assert constructed == []
    assert calls == []


def test_correct_structure_ids_adoption_but_invalid_wire_evidence_blocks() -> None:
    # Correct structure, correct 12 IDs, adoption=True for all, but invalid raw
    # provider evidence (not a valid Luna Responses JSON) must not construct the
    # calibration client / make any scoring call.
    cases = _cases()
    grouped = _group_by_structure(cases)
    bad_raw = b'{"object":"not-a-response","status":"x"}'
    constructed: list[str] = []
    calls: list[str] = []

    def factory() -> Any:
        constructed.append("client")
        raise AssertionError("must not construct")

    # If the artifact is constructible, feed it to the prepared run; either way the
    # calibration client must never be constructed.
    try:
        bad_art = _origin_artifact("P", grouped["P"], origin_run_id="o-P", raw_override=bad_raw)
        prepared = Stage1APreparedRun(
            cases=cases,
            scoring_prompt=_dummy_prompt(),
            model_configuration=_dummy_config(),
            seal=lambda: None,
            client_factory=factory,
            origin_artifacts=(bad_art,),
        )
        with pytest.raises(RuntimeError):
            prepared.run()
    except RuntimeError:
        pass  # construction or the prepared run rejected the invalid wire evidence
    assert constructed == []
    assert calls == []


# ---- 2. exact five-structure allocation ----
def test_exact_five_structure_allocation() -> None:
    cases = _cases()
    grouped = _group_by_structure(cases)
    assert len(grouped) == 5
    for s in FROZEN_STRUCTURES:
        assert len(grouped[s.value]) == 12
    require_real_origin_coverage(
        _all_origins(cases),
        frozenset(c.generated.spec.case_id for c in cases),
        _case_to_structure(cases),
    )


def test_duplicate_structure_fails() -> None:
    cases = _cases()
    dup = list(_all_origins(cases))
    dup[-1] = _origin_artifact("P", _group_by_structure(cases)["P AND Q"], origin_run_id="dup")
    with pytest.raises(ValueError, match="duplicate origin structure"):
        require_real_origin_coverage(tuple(dup), frozenset(c.generated.spec.case_id for c in cases))


def test_missing_structure_fails() -> None:
    cases = _cases()
    grouped = _group_by_structure(cases)
    artifacts = [
        _origin_artifact(s.value, grouped[s.value], origin_run_id=s.value)
        for s in FROZEN_STRUCTURES
        if s.value != "P"
    ]
    with pytest.raises(ValueError, match="origin sessions"):
        require_real_origin_coverage(
            tuple(artifacts), frozenset(c.generated.spec.case_id for c in cases)
        )


def test_12_valid_ids_assigned_to_wrong_structure_fails() -> None:
    cases = _cases()
    grouped = _group_by_structure(cases)
    bad = _origin_artifact("P", grouped["P AND Q"], origin_run_id="migration")
    artifacts = list(_all_origins(cases))
    artifacts[0] = bad
    with pytest.raises(ValueError, match="migrated"):
        require_real_origin_coverage(
            tuple(artifacts),
            frozenset(c.generated.spec.case_id for c in cases),
            _case_to_structure(cases),
        )


# ---- contract: exact origin-adoption-v1 ----
def test_parse_exact_accepts_canonical() -> None:
    cids = tuple(f"S1A-{i:02d}" for i in range(1, 13))
    raw = b"\n".join(b"ADOPT " + c.encode() for c in cids)
    assert all(_parse_origin_adoptions_exact(raw, cids).values())
    assert all(_parse_origin_adoptions_exact(raw + b"\n", cids).values())


@pytest.mark.parametrize(
    "bad",
    ["json", "shuffled", "crlf", "leadspace", "trailspace", "blankline", "extratext"],
)
def test_parse_exact_rejects(bad: str) -> None:
    cids = tuple(f"S1A-{i:02d}" for i in range(1, 13))
    canonical = [f"ADOPT {c}" for c in cids]
    if bad == "json":
        raw = json.dumps({c: True for c in cids}).encode()
    elif bad == "shuffled":
        raw = ("\n".join(canonical[::-1])).encode()
    elif bad == "crlf":
        raw = ("\r\n".join(canonical)).encode()
    elif bad == "leadspace":
        raw = ("\n".join(" " + line for line in canonical)).encode()
    elif bad == "trailspace":
        raw = ("\n".join(line + " " for line in canonical)).encode()
    elif bad == "blankline":
        raw = ("\n".join(canonical[:6]) + "\n\n" + "\n".join(canonical[6:])).encode()
    else:  # extratext
        raw = ("\n".join(canonical) + "\nextra").encode()
    with pytest.raises(OriginResponseContractFailure):
        _parse_origin_adoptions_exact(raw, cids)


def test_contract_frozen() -> None:
    assert len(ORIGIN_PROMPT) > 0
    assert sha256_bytes(ORIGIN_PROMPT) == ORIGIN_PROMPT_SHA256
    assert sha256_bytes(ORIGIN_RESPONSE_CONTRACT_SPEC) == ORIGIN_RESPONSE_CONTRACT_SHA256
    assert ORIGIN_RESPONSE_CONTRACT_VERSION == "origin-adoption-v1"


# ---- request records ordered + binary ----
def test_request_records_are_ordered_binary_mapping() -> None:
    cases = _cases()
    grouped = _group_by_structure(cases)
    records = _records_for(grouped["P"])
    req = build_origin_request_bytes(ORIGIN_PROMPT, records)
    for cid, cbytes in records:
        assert cid.encode() in req
        assert cbytes in req
    assert b"truth_label" not in req


def test_request_sha_reproducible() -> None:
    cases = _cases()
    grouped = _group_by_structure(cases)
    records = _records_for(grouped["P"])
    assert build_origin_request_bytes(ORIGIN_PROMPT, records) == build_origin_request_bytes(
        ORIGIN_PROMPT, list(records)
    )


# ---- real wire verifier ----
def test_verify_origin_artifact_passes() -> None:
    cases = _cases()
    grouped = _group_by_structure(cases)
    art = _origin_artifact("P", grouped["P"], origin_run_id="o-P")
    verify_origin_artifact(
        art,
        origin_prompt=ORIGIN_PROMPT,
        expected_structure=StructureId("P"),
        expected_case_ids=tuple(c.generated.spec.case_id for c in grouped["P"]),
    )


def test_verify_missing_model_evidence_fails_closed() -> None:
    cases = _cases()
    grouped = _group_by_structure(cases)
    case_ids = list(x.generated.spec.case_id for x in grouped["P"])
    obj = json.loads(_luna_responses_json(case_ids).decode())
    del obj["model"]
    raw = json.dumps(obj).encode()
    with pytest.raises(RuntimeError):
        parse_raw_provider_response(raw)  # missing model fails closed


def test_durable_serialization_preserves_raw_provider_response() -> None:
    cases = _cases()
    grouped = _group_by_structure(cases)
    art = _origin_artifact("P", grouped["P"], origin_run_id="o-P")
    record = art.canonical_record()
    assert "raw_provider_response_base64" in record
    restored = base64.b64decode(record["raw_provider_response_base64"])
    assert restored == art.raw_provider_response_bytes
    assert sha256_bytes(restored) == art.raw_provider_response_sha256


def test_5_of_5_unlock_calibration_preflight() -> None:
    cases = _cases()
    artifacts = _all_origins(cases)
    require_real_origin_coverage(artifacts, frozenset(c.generated.spec.case_id for c in cases))


def test_fewer_than_5_never_construct_scoring_client() -> None:
    cases = _cases()
    constructed: list[str] = []

    def factory() -> Any:
        constructed.append("client")
        raise AssertionError("must not construct")

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


# ---- integrated preflight ordering ----
def test_preflight_ordering_seal_then_client_then_scoring() -> None:
    from protean_stage0.artifacts import FrozenArtifact

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
    assert len(calls) == len(cases)


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
    assert constructed == []
    assert calls == []
