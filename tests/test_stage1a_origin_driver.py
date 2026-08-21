"""Hermetic tests for the hardening of the Stage-1A live-origin driver."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from protean_stage0.artifacts import FrozenArtifact
from protean_stage0.direct_config import (
    MODEL,
    REASONING_CONTEXT,
    REASONING_EFFORT,
    direct_model_configuration,
)
from protean_stage0.grammar import FROZEN_STRUCTURES
from protean_stage0.stage1a_authority import load_authority_artifacts
from protean_stage0.stage1a_origin_driver import (
    AtomicEvidenceSink,
    OriginFailureCategory,
    OriginRunStatus,
    OriginRunUnresolved,
    build_origin_run_manifest,
    execute_origin_run,
    validate_origin_run_manifest_seal,
)
from protean_stage0.textualize import TemplateBank

REPO = Path(__file__).resolve().parents[1]


def _auth() -> Any:
    return load_authority_artifacts(verify_expected=True)


def _luna_ok(structure_case_ids: list[str]) -> bytes:
    adopt = "\n".join(f"ADOPT {cid}" for cid in structure_case_ids)
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
                "content": [{"type": "output_text", "text": adopt}],
            },
        ],
        "usage": {"input_tokens": 10, "output_tokens": 20, "total_tokens": 30},
    }
    return json.dumps(obj).encode()


def _specs(auth: Any) -> Any:
    return build_origin_run_manifest(auth=auth, harness_revision="HARNESS", batch_run_id="batch-1")


def _plan(auth: Any, batch: str = "batch-1") -> Any:
    manifest, specs = build_origin_run_manifest(
        auth=auth, harness_revision="HARNESS", batch_run_id=batch
    )
    return manifest, specs


def _ok_transport(auth: Any, specs: Any) -> tuple[Any, dict[str, int]]:
    calls = {"n": 0}

    def transport(
        *, payload: bytes
    ) -> tuple[int | None, bytes | None, bytes | None, dict[Any, Any]]:
        calls["n"] += 1
        idx = calls["n"]
        structure = FROZEN_STRUCTURES[idx - 1]
        cids = [
            c.case_id for c in auth.case_set.cases if c.structured_spec.structure_id == structure
        ]
        return (200, None, _luna_ok(cids), {"model": MODEL, "status": "completed"})

    return transport, calls


# 1. placeholder/empty-authority manifest cannot execute
def test_placeholder_empty_authority_manifest_cannot_be_built() -> None:
    # The authoritative builder must never leave authority fields empty.
    auth = _auth()
    manifest, specs = build_origin_run_manifest(auth=auth, harness_revision="H", batch_run_id="b")
    assert manifest.protocol_sha256
    assert manifest.real_origin_amendment_sha256
    assert manifest.case_set_sha256
    assert manifest.origin_prompt_sha256
    assert manifest.origin_response_contract_sha256
    assert manifest.direct_luna_config_sha256
    assert manifest.expected_requests == 5
    assert len(specs) == 5


# 3. adoption contract enforced in live loop
def test_non_adopt_text_is_adoption_contract_failure() -> None:
    auth = _auth()
    manifest, specs = _plan(auth)
    raw = json.dumps(
        {
            "id": "r",
            "object": "response",
            "created_at": 0,
            "status": "completed",
            "model": MODEL,
            "reasoning": {"effort": REASONING_EFFORT, "context": REASONING_CONTEXT},
            "output": [
                {
                    "type": "message",
                    "role": "assistant",
                    "status": "completed",
                    "content": [{"type": "output_text", "text": "I refuse."}],
                }
            ],
            "usage": None,
        }
    ).encode()

    def transport(
        *, payload: bytes
    ) -> tuple[int | None, bytes | None, bytes | None, dict[Any, Any]]:
        return (200, None, raw, {"model": MODEL})

    result = execute_origin_run(
        manifest_bytes=manifest.to_exact_bytes(),
        expected_manifest_sha256=manifest.sha256,
        actual_harness_revision="HARNESS",
        auth=auth,
        batch_run_id="batch-1",
        transport=transport,
    )
    assert result.status is OriginRunStatus.FAILED
    assert result.evidence[0].failure_category is OriginFailureCategory.ADOPTION_CONTRACT


def test_malformed_responses_is_responses_contract_failure() -> None:
    auth = _auth()
    manifest, specs = _plan(auth)

    def transport(
        *, payload: bytes
    ) -> tuple[int | None, bytes | None, bytes | None, dict[Any, Any]]:
        return (200, None, b"{bad json", {"model": MODEL})

    result = execute_origin_run(
        manifest_bytes=manifest.to_exact_bytes(),
        expected_manifest_sha256=manifest.sha256,
        actual_harness_revision="HARNESS",
        auth=auth,
        batch_run_id="batch-1",
        transport=transport,
    )
    assert result.status is OriginRunStatus.FAILED
    assert result.evidence[0].failure_category is OriginFailureCategory.RESPONSES_CONTRACT


# 2/4. execution consumes sealed manifest + actual harness; stale/manipulated stops pre-transport
def test_wrong_expected_manifest_sha_stops_zero_transport() -> None:
    auth = _auth()
    manifest, specs = _plan(auth)
    t, calls = _ok_transport(auth, specs)
    with pytest.raises(ValueError, match="expected value"):
        execute_origin_run(
            manifest_bytes=manifest.to_exact_bytes(),
            expected_manifest_sha256="0" * 64,
            actual_harness_revision="HARNESS",
            auth=auth,
            batch_run_id="batch-1",
            transport=t,
        )
    assert calls["n"] == 0


def test_stale_harness_stops_zero_transport() -> None:
    auth = _auth()
    manifest, specs = _plan(auth)
    t, calls = _ok_transport(auth, specs)
    with pytest.raises(ValueError, match="harness revision"):
        execute_origin_run(
            manifest_bytes=manifest.to_exact_bytes(),
            expected_manifest_sha256=manifest.sha256,
            actual_harness_revision="STALE",
            auth=auth,
            batch_run_id="batch-1",
            transport=t,
        )
    assert calls["n"] == 0


def test_mutated_case_set_binding_stops_zero_transport() -> None:
    auth = _auth()
    manifest, specs = _plan(auth)
    # Tamper the manifest's case-set SHA (a mutated binding).
    from dataclasses import replace

    tampered = replace(manifest, case_set_sha256="0" * 64)
    t, calls = _ok_transport(auth, specs)
    with pytest.raises(ValueError, match="case set"):
        execute_origin_run(
            manifest_bytes=tampered.to_exact_bytes(),
            expected_manifest_sha256=tampered.sha256,
            actual_harness_revision="HARNESS",
            auth=auth,
            batch_run_id="batch-1",
            transport=t,
        )
    assert calls["n"] == 0


def test_five_success_gives_completed_binding_five_artifact_shas() -> None:
    auth = _auth()
    manifest, specs = _plan(auth)
    t, calls = _ok_transport(auth, specs)
    result = execute_origin_run(
        manifest_bytes=manifest.to_exact_bytes(),
        expected_manifest_sha256=manifest.sha256,
        actual_harness_revision="HARNESS",
        auth=auth,
        batch_run_id="batch-1",
        transport=t,
    )
    assert result.status is OriginRunStatus.COMPLETED
    assert calls["n"] == 5
    assert len(result.artifacts) == 5
    assert result.completed is not None
    assert result.completed.successes == 5
    assert len(result.completed.artifact_shas) == 5
    assert result.completed.artifact_shas == tuple(a.sha256 for a in result.artifacts)


# 6. evidence written after each attempt; mechanical failure at N keeps earlier evidence
def test_evidence_sink_preserves_prior_attempts_on_mechanical_failure(tmp_path: Path) -> None:
    auth = _auth()
    manifest, specs = _plan(auth)
    calls = {"n": 0}

    def transport(
        *, payload: bytes
    ) -> tuple[int | None, bytes | None, bytes | None, dict[Any, Any]]:
        calls["n"] += 1
        idx = calls["n"]
        if idx == 3:
            raise RuntimeError("boom")
        structure = FROZEN_STRUCTURES[idx - 1]
        cids = [
            c.case_id for c in auth.case_set.cases if c.structured_spec.structure_id == structure
        ]
        return (200, None, _luna_ok(cids), {"model": MODEL})

    with pytest.raises(OriginRunUnresolved):
        execute_origin_run(
            manifest_bytes=manifest.to_exact_bytes(),
            expected_manifest_sha256=manifest.sha256,
            actual_harness_revision="HARNESS",
            auth=auth,
            batch_run_id="batch-1",
            transport=transport,
            evidence_sink=AtomicEvidenceSink(tmp_path),
        )
    files = sorted(tmp_path.glob("*.json"))
    # Evidence for requests 1 and 2 must be durably written before the mechanical error at 3.
    assert len(files) >= 2
    first = json.loads(files[0].read_text())
    assert first["request_index"] == 1
    assert first["request_bytes_base64"]  # durable, lossless


# 5/7. evidence + artifact round-trip lossless
def test_evidence_round_trips_exact_request_and_raw_body(tmp_path: Path) -> None:
    auth = _auth()
    manifest, specs = _plan(auth)
    sink = AtomicEvidenceSink(tmp_path)
    cids = specs[0].case_ids

    def transport(
        *, payload: bytes
    ) -> tuple[int | None, bytes | None, bytes | None, dict[Any, Any]]:
        return (200, None, _luna_ok(list(cids)), {"model": MODEL})

    execute_origin_run(
        manifest_bytes=manifest.to_exact_bytes(),
        expected_manifest_sha256=manifest.sha256,
        actual_harness_revision="HARNESS",
        auth=auth,
        batch_run_id="batch-1",
        transport=transport,
        evidence_sink=sink,
    )
    import base64

    first = json.loads((tmp_path / "origin-evidence-batch-1-r01.json").read_text())
    assert base64.b64decode(first["request_bytes_base64"]) == specs[0].request_bytes
    assert first["request_sha256"] == specs[0].request_sha256
    assert first["case_ids"] == list(cids)


# 8. cross-batch / no-completed must fail in Stage1APreparedRun (calibration)
def test_stage1a_prepared_run_requires_completed_batch() -> None:
    from protean_stage0.stage1a_cases import build_stage1a_cases
    from protean_stage0.stage1a_driver import Stage1APreparedRun

    cases = build_stage1a_cases(
        template_bank=TemplateBank.from_bytes((REPO / "stage0/template-bank-v1.json").read_bytes())
    )
    constructed: list[str] = []

    def factory() -> Any:
        constructed.append("client")
        raise AssertionError("must not construct")

    prepared = Stage1APreparedRun(
        cases=cases,
        scoring_prompt=FrozenArtifact.from_bytes("p", b"x"),
        model_configuration=direct_model_configuration(),
        seal=lambda: None,
        client_factory=factory,
        origin_artifacts=(),
    )
    with pytest.raises(ValueError):
        prepared.run()
    assert constructed == []


# 4. typed failure categories stay distinct
def test_transport_http_and_adoption_categories_distinct() -> None:
    auth = _auth()
    cases_fn: list[tuple[str, Any]] = [
        ("transport", lambda: (None, None, None, {})),
        ("http", lambda: (503, b"err", None, {})),
        ("adoption", lambda: (200, None, _luna_ok(["S1A-01"]), {})),  # wrong 1-ID adoption
    ]
    for kind, fn in cases_fn:
        batch = f"batch-{kind}"
        manifest, specs = build_origin_run_manifest(
            auth=auth, harness_revision="HARNESS", batch_run_id=batch
        )
        result = execute_origin_run(
            manifest_bytes=manifest.to_exact_bytes(),
            expected_manifest_sha256=manifest.sha256,
            actual_harness_revision="HARNESS",
            auth=auth,
            batch_run_id=batch,
            transport=lambda payload, f=fn: f(),
        )
        assert result.status is OriginRunStatus.FAILED
        if kind == "transport":
            assert result.evidence[0].failure_category is OriginFailureCategory.TRANSPORT
        elif kind == "http":
            assert result.evidence[0].failure_category is OriginFailureCategory.HTTP
        else:
            assert result.evidence[0].failure_category is OriginFailureCategory.ADOPTION_CONTRACT


def test_seal_validate_checks_request_binding() -> None:
    auth = _auth()
    manifest, specs = _plan(auth)
    # A manifest with a tampered per-request SHA must fail the seal.
    from dataclasses import replace

    tampered = replace(
        manifest, per_request_request_sha={k: "0" * 64 for k in manifest.per_request_request_sha}
    )
    with pytest.raises(ValueError, match="request SHA"):
        validate_origin_run_manifest_seal(
            manifest=tampered,
            manifest_sha256=tampered.sha256,
            actual_harness_revision="HARNESS",
            auth=auth,
        )
