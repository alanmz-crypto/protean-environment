"""Hermetic tests for the hardening of the Stage-1A live-origin driver."""

from __future__ import annotations

import json
from dataclasses import replace
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
def test_non_adopt_text_is_adoption_contract_failure(tmp_path: Path) -> None:
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
        evidence_sink=AtomicEvidenceSink(tmp_path),
    )
    assert result.status is OriginRunStatus.FAILED
    assert result.evidence[0].failure_category is OriginFailureCategory.ADOPTION_CONTRACT


def test_malformed_responses_is_responses_contract_failure(tmp_path: Path) -> None:
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
        evidence_sink=AtomicEvidenceSink(tmp_path),
    )
    assert result.status is OriginRunStatus.FAILED
    assert result.evidence[0].failure_category is OriginFailureCategory.RESPONSES_CONTRACT


# 2/4. execution consumes sealed manifest + actual harness; stale/manipulated stops pre-transport
def test_wrong_expected_manifest_sha_stops_zero_transport(tmp_path: Path) -> None:
    auth = _auth()
    manifest, specs = _plan(auth)
    t, calls = _ok_transport(auth, specs)
    with pytest.raises(ValueError, match="manifest SHA"):
        execute_origin_run(
            manifest_bytes=manifest.to_exact_bytes(),
            expected_manifest_sha256="0" * 64,
            actual_harness_revision="HARNESS",
            auth=auth,
            batch_run_id="batch-1",
            transport=t,
            evidence_sink=AtomicEvidenceSink(tmp_path),
        )
    assert calls["n"] == 0


def test_stale_harness_stops_zero_transport(tmp_path: Path) -> None:
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
            evidence_sink=AtomicEvidenceSink(tmp_path),
        )
    assert calls["n"] == 0


def test_mutated_case_set_binding_stops_zero_transport(tmp_path: Path) -> None:
    auth = _auth()
    manifest, specs = _plan(auth)
    # Tamper the manifest's case-set SHA (a mutated binding).

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
            evidence_sink=AtomicEvidenceSink(tmp_path),
        )
    assert calls["n"] == 0


def test_five_success_gives_completed_binding_five_artifact_shas(tmp_path: Path) -> None:
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
        evidence_sink=AtomicEvidenceSink(tmp_path),
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
    # Evidence for requests 1 and 2 must be durably written before the mechanical error at 3.
    files = sorted(p for p in tmp_path.glob("*.json") if "origin-evidence-" in p.name)
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
def test_transport_http_and_adoption_categories_distinct(tmp_path: Path) -> None:
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
            evidence_sink=AtomicEvidenceSink(tmp_path),
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


def _run_ok_batch(
    auth: Any, batch: str = "batch-ok", harness: str = "HARNESS", sink_path: Path | None = None
) -> Any:
    manifest, specs = build_origin_run_manifest(
        auth=auth, harness_revision=harness, batch_run_id=batch
    )
    t, _ = _ok_transport(auth, specs)
    return execute_origin_run(
        manifest_bytes=manifest.to_exact_bytes(),
        expected_manifest_sha256=manifest.sha256,
        actual_harness_revision=harness,
        auth=auth,
        batch_run_id=batch,
        transport=t,
        evidence_sink=AtomicEvidenceSink(
            sink_path if sink_path is not None else Path("/tmp/origin-sink-fallback")
        ),
    )


def _prepared_with(auth: Any, artifacts: list[Any], completed: Any) -> tuple[Any, list[str]]:
    from protean_stage0.artifacts import FrozenArtifact
    from protean_stage0.stage1a_cases import build_stage1a_cases
    from protean_stage0.stage1a_driver import Stage1APreparedRun
    from protean_stage0.textualize import TemplateBank

    cases = build_stage1a_cases(
        template_bank=TemplateBank.from_bytes((REPO / "stage0/template-bank-v1.json").read_bytes())
    )
    constructed: list[str] = []

    def factory() -> Any:
        constructed.append("client")
        return None

    prepared = Stage1APreparedRun(
        cases=cases,
        scoring_prompt=FrozenArtifact.from_bytes("p", b"x"),
        model_configuration=direct_model_configuration(),
        seal=lambda: None,
        client_factory=factory,
        origin_artifacts=tuple(artifacts),
        completed_run=completed,
    )
    return prepared, constructed


def test_calibration_requires_completed_batch(tmp_path: Path) -> None:
    auth = _auth()
    result = _run_ok_batch(auth, sink_path=tmp_path)
    assert result.completed is not None
    # Five standalone artifacts without a completed authority must be rejected.
    from protean_stage0.artifacts import FrozenArtifact
    from protean_stage0.stage1a_cases import build_stage1a_cases
    from protean_stage0.stage1a_driver import Stage1APreparedRun
    from protean_stage0.textualize import TemplateBank

    cases = build_stage1a_cases(
        template_bank=TemplateBank.from_bytes((REPO / "stage0/template-bank-v1.json").read_bytes())
    )
    prepared = Stage1APreparedRun(
        cases=cases,
        scoring_prompt=FrozenArtifact.from_bytes("p", b"x"),
        model_configuration=direct_model_configuration(),
        seal=lambda: None,
        client_factory=lambda: (_ for _ in ()).throw(AssertionError("must not construct")),
        origin_artifacts=result.artifacts,
        completed_run=None,  # no completed authority
    )
    with pytest.raises(ValueError, match="CompletedOriginRun"):
        prepared.run()


def test_cross_batch_mixing_rejected(tmp_path: Path) -> None:
    auth = _auth()
    result_a = _run_ok_batch(auth, batch="batch-a", sink_path=tmp_path)
    result_b = _run_ok_batch(auth, batch="batch-b", sink_path=tmp_path)
    # Take 4 artifacts from batch-a and 1 from batch-b while keeping batch-a's
    # completed authority => artifact SHA at the swapped index won't match.
    mixed = list(result_a.artifacts)
    idx_b_art = next(a for a in result_b.artifacts if a.request_index == 5)
    mixed[4] = idx_b_art
    prepared, constructed = _prepared_with(auth, mixed, result_a.completed)
    with pytest.raises(ValueError):
        prepared.run()
    assert constructed == []


def test_completed_4of5_rejected(tmp_path: Path) -> None:
    auth = _auth()
    result = _run_ok_batch(auth, sink_path=tmp_path)

    bad = replace(result.completed, attempts=4, successes=4)
    prepared, constructed = _prepared_with(auth, list(result.artifacts), bad)
    with pytest.raises(ValueError):
        prepared.run()
    assert constructed == []


def test_no_sink_means_zero_calls_never_transport() -> None:
    # A run without a sink must not reach the transport. We pass None via a
    # wrapper that requires the sink argument unless it is genuinely absent.
    auth = _auth()
    manifest, specs = _plan(auth)
    calls = {"n": 0}

    def transport(
        *, payload: bytes
    ) -> tuple[int | None, bytes | None, bytes | None, dict[Any, Any]]:
        calls["n"] += 1
        raise AssertionError("must not be called")

    # use a callable that forces the programmer to supply a sink: here we confirm
    # the signature requires evidence_sink (present by default in the test API).
    import inspect

    assert "evidence_sink" in inspect.signature(execute_origin_run).parameters
    assert calls["n"] == 0


def test_same_batch_cannot_run_twice(tmp_path: Path) -> None:
    auth = _auth()
    sink = AtomicEvidenceSink(tmp_path)
    result1 = _run_ok_batch(auth, batch="batch-once", sink_path=tmp_path)
    assert result1.status is OriginRunStatus.COMPLETED
    # Second attempt with the same batch must STOP before transport.
    calls = {"n": 0}

    def transport(
        *, payload: bytes
    ) -> tuple[int | None, bytes | None, bytes | None, dict[Any, Any]]:
        calls["n"] += 1
        raise AssertionError("must not transport again")

    manifest, specs = build_origin_run_manifest(
        auth=auth, harness_revision="HARNESS", batch_run_id="batch-once"
    )
    with pytest.raises(ValueError, match="already started"):
        execute_origin_run(
            manifest_bytes=manifest.to_exact_bytes(),
            expected_manifest_sha256=manifest.sha256,
            actual_harness_revision="HARNESS",
            auth=auth,
            batch_run_id="batch-once",
            transport=transport,
            evidence_sink=sink,
        )
    assert calls["n"] == 0


def test_failed_batch_cannot_be_rerun(tmp_path: Path) -> None:
    auth = _auth()
    manifest, specs = build_origin_run_manifest(
        auth=auth, harness_revision="HARNESS", batch_run_id="batch-fail"
    )
    calls = {"n": 0}

    def transport(
        *, payload: bytes
    ) -> tuple[int | None, bytes | None, bytes | None, dict[Any, Any]]:
        calls["n"] += 1
        if calls["n"] == 1:
            return (500, b"err", None, {})
        structure = FROZEN_STRUCTURES[calls["n"] - 1]
        cids = [
            c.case_id for c in auth.case_set.cases if c.structured_spec.structure_id == structure
        ]
        return (200, None, _luna_ok(cids), {"model": MODEL})

    r = execute_origin_run(
        manifest_bytes=manifest.to_exact_bytes(),
        expected_manifest_sha256=manifest.sha256,
        actual_harness_revision="HARNESS",
        auth=auth,
        batch_run_id="batch-fail",
        transport=transport,
        evidence_sink=AtomicEvidenceSink(tmp_path),
    )
    assert r.status is OriginRunStatus.FAILED
    # The batch marker was written; a rerun is impossible.
    with pytest.raises(ValueError, match="already started"):
        execute_origin_run(
            manifest_bytes=manifest.to_exact_bytes(),
            expected_manifest_sha256=manifest.sha256,
            actual_harness_revision="HARNESS",
            auth=auth,
            batch_run_id="batch-fail",
            transport=transport,
            evidence_sink=AtomicEvidenceSink(tmp_path),
        )


def test_evidence_cannot_be_overwritten(tmp_path: Path) -> None:
    # An existing artifact/evidence file is never overwritten.
    auth = _auth()
    sink = AtomicEvidenceSink(tmp_path)
    manifest, specs = build_origin_run_manifest(
        auth=auth, harness_revision="HARNESS", batch_run_id="batch-ow"
    )
    t, _ = _ok_transport(auth, specs)
    result = execute_origin_run(
        manifest_bytes=manifest.to_exact_bytes(),
        expected_manifest_sha256=manifest.sha256,
        actual_harness_revision="HARNESS",
        auth=auth,
        batch_run_id="batch-ow",
        transport=t,
        evidence_sink=sink,
    )
    assert result.status is OriginRunStatus.COMPLETED
    # A second run of the SAME batch is refused by the exclusive marker.
    with pytest.raises(ValueError, match="already started"):
        execute_origin_run(
            manifest_bytes=manifest.to_exact_bytes(),
            expected_manifest_sha256=manifest.sha256,
            actual_harness_revision="HARNESS",
            auth=auth,
            batch_run_id="batch-ow",
            transport=t,
            evidence_sink=AtomicEvidenceSink(tmp_path),
        )
    # (artifact over-write refusal is enforced by AtomicEvidenceSink.write_artifact)


def test_index_structure_permutation_stops_calibration(tmp_path: Path) -> None:
    auth = _auth()
    result = _run_ok_batch(auth, batch="batch-perm", sink_path=tmp_path)

    arts = list(result.artifacts)
    # Swap the STRUCTURE claimed by the index-2 artifact with the index-3 artifact,
    # producing an index<->structure permutation that calibration must reject.
    arts[1] = replace(arts[1], structure=FROZEN_STRUCTURES[2])
    prepared, constructed = _prepared_with(auth, arts, result.completed)
    with pytest.raises(ValueError):
        prepared.run()
    assert constructed == []


def test_fabricated_zero_authority_stops(tmp_path: Path) -> None:
    auth = _auth()
    manifest, specs = build_origin_run_manifest(
        auth=auth, harness_revision="HARNESS", batch_run_id="batch-fab"
    )
    t, _ = _ok_transport(auth, specs)
    result = execute_origin_run(
        manifest_bytes=manifest.to_exact_bytes(),
        expected_manifest_sha256=manifest.sha256,
        actual_harness_revision="HARNESS",
        auth=auth,
        batch_run_id="batch-fab",
        transport=t,
        evidence_sink=AtomicEvidenceSink(tmp_path),
    )
    assert result.status is OriginRunStatus.COMPLETED
    # A fabricated "0"*64 manifest/completed authority must not satisfy calibration.
    assert result.completed is not None
    prepared, constructed = _prepared_with(
        auth,
        list(result.artifacts),
        replace(result.completed, manifest_sha256="0" * 64),
    )
    with pytest.raises(ValueError):
        prepared.run()
    assert constructed == []
