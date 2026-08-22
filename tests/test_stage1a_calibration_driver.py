"""Adversarial tests for the sealed Stage-1A calibration live driver.

Proves the production fail-closed surface: zero provider calls on any mismatch,
exact request-byte sealing, no continuation, no truth in payload, no second B/C
call, durable per-request evidence, and a single 60/60/0 completed authority.
All tests are hermetic — no live provider call is made, and the origin chain is
built synthetically in a temporary directory (CI-safe, independent of any
gitignored local run artifacts).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from protean_stage0.artifacts import sha256_bytes
from protean_stage0.direct_config import MODEL, REASONING_CONTEXT, REASONING_EFFORT
from protean_stage0.grammar import FROZEN_STRUCTURES
from protean_stage0.stage1a_authority import load_authority_artifacts
from protean_stage0.stage1a_calibration_driver import (
    AtomicCalibrationSink,
    CalibrationCompletedRun,
    Stage1ACalibrationManifest,
    build_calibration_manifest,
    compute_calibration_report,
    execute_calibration_run,
    require_valid_completed_calibration,
    validate_calibration_manifest_seal_exact,
)
from protean_stage0.stage1a_origin_driver import (
    AtomicEvidenceSink,
    build_origin_run_manifest,
    execute_origin_run,
)

HEAD = "SYNTHETIC-HEAD"


def _auth() -> Any:
    return load_authority_artifacts(verify_expected=True)


def _scoring_ok(score: str = "0.73") -> bytes:
    return json.dumps(
        {
            "id": "resp_cal",
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
                    "content": [{"type": "output_text", "text": score}],
                },
            ],
            "usage": {"input_tokens": 10, "output_tokens": 20, "total_tokens": 30},
        }
    ).encode()


def _origin_luna_ok(structure_case_ids: list[str]) -> bytes:
    adopt = "\n".join(f"ADOPT {cid}" for cid in structure_case_ids)
    return json.dumps(
        {
            "id": "resp_origin",
            "object": "response",
            "created_at": 0,
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
            "usage": None,
        }
    ).encode()


def _origin_transport(auth: Any, specs: Any) -> Any:
    calls = {"n": 0}

    def transport(*, payload: bytes) -> Any:
        calls["n"] += 1
        idx = calls["n"]
        structure = FROZEN_STRUCTURES[idx - 1]
        cids = [
            c.case_id for c in auth.case_set.cases if c.structured_spec.structure_id == structure
        ]
        return (200, None, _origin_luna_ok(cids), {"model": MODEL, "status": "completed"})

    return transport


_ORIGIN_SEQ = {"n": 0}


def _origin_chain(tmp_path: Path) -> dict[str, Any]:
    """Build a hermetic 5/5/0 origin chain (manifest + completed + five artifacts)
    in a temp dir and return the inputs ``build_calibration_manifest`` requires."""
    auth = _auth()
    origin_dir = Path(tmp_path) / "origin"
    origin_dir.mkdir(parents=True, exist_ok=True)
    _ORIGIN_SEQ["n"] += 1
    batch = f"hermetic-origin-{_ORIGIN_SEQ['n']}"
    manifest, specs = build_origin_run_manifest(
        auth=auth, harness_revision=HEAD, batch_run_id=batch
    )
    sink = AtomicEvidenceSink(origin_dir)
    result = execute_origin_run(
        manifest_bytes=manifest.to_exact_bytes(),
        expected_manifest_sha256=manifest.sha256,
        actual_harness_revision=HEAD,
        auth=auth,
        batch_run_id=batch,
        transport=_origin_transport(auth, specs),
        evidence_sink=sink,
    )
    assert result.completed is not None
    om_path = origin_dir / f"origin-run-manifest-{batch}.json"
    oc_path = origin_dir / f"origin-completed-{batch}.json"
    om_path.write_bytes(manifest.to_exact_bytes())
    oc_path.write_bytes(result.completed.to_exact_bytes())
    return {
        "origin_manifest_path": om_path,
        "origin_manifest_sha256": manifest.sha256,
        "origin_completed_path": oc_path,
        "origin_completed_sha256": result.completed.completed_run_sha256,
        "origin_artifacts_dir": origin_dir,
        "origin_batch_run_id": batch,
    }


def _ok_transport(score: str = "0.73", *, count: dict[str, int] | None = None) -> Any:
    if count is None:
        count = {"n": 0}

    def transport(*, payload: bytes) -> Any:
        count["n"] += 1
        return (200, None, _scoring_ok(score), {"model": MODEL})

    return transport, count


def _prepared_manifest(tmp_path: Path) -> tuple[Stage1ACalibrationManifest, bytes, Any]:
    chain = _origin_chain(tmp_path)
    manifest, specs = build_calibration_manifest(harness_revision=HEAD, **chain)
    return manifest, manifest.to_exact_bytes(), specs


def _run_success(tmp_path: Path, *, count: dict[str, int] | None = None) -> Any:
    manifest, manifest_bytes, _ = _prepared_manifest(tmp_path)
    transport, count = _ok_transport(count=count)
    sink = AtomicCalibrationSink(tmp_path / "cal")
    status, evidence, completed = execute_calibration_run(
        manifest_bytes=manifest_bytes,
        expected_manifest_sha256=manifest.sha256,
        actual_harness_revision=HEAD,
        auth=_auth(),
        batch_run_id=manifest.batch_run_id,
        transport=transport,
        evidence_sink=sink,
    )
    return manifest, status, evidence, completed, count


# ---------------------------------------------------------------------------
# Prepare mode = zero provider calls
# ---------------------------------------------------------------------------
def test_prepare_mode_zero_provider_calls(tmp_path: Path) -> None:
    chain = _origin_chain(tmp_path)
    manifest, specs = build_calibration_manifest(harness_revision=HEAD, **chain)
    assert len(specs) == 60
    assert manifest.expected_requests == 60


# ---------------------------------------------------------------------------
# Liveness: 60/60/0 success, single completed authority, byte-exact
# ---------------------------------------------------------------------------
def test_60_60_completed_single_authority(tmp_path: Path) -> None:
    manifest, status, evidence, completed, count = _run_success(tmp_path)
    assert status.value == "COMPLETED"
    assert count["n"] == 60
    assert len(evidence) == 60
    assert all(e.success for e in evidence)
    assert completed is not None
    assert len(completed.evidence_shas) == 60
    assert len(completed.scores) == 60
    cal_dir = Path(tmp_path) / "cal"
    completed_files = list(cal_dir.glob("calibration-completed-*.json"))
    evidence_files = list(cal_dir.glob("calibration-evidence-*.json"))
    assert len(completed_files) == 1
    assert len(evidence_files) == 60
    raw = completed_files[0].read_bytes()
    rebuilt = CalibrationCompletedRun._reconstruct(raw)
    assert rebuilt.to_exact_bytes() == raw
    assert rebuilt.sha256 == completed.sha256


def test_failure_at_n_persists_evidence_no_nplus1(tmp_path: Path) -> None:
    manifest, manifest_bytes, _ = _prepared_manifest(tmp_path)
    calls: list[int] = []

    def transport(*, payload: bytes) -> Any:
        n = len(calls) + 1
        calls.append(n)
        if n == 3:
            return (500, b"boom", None, {})
        return (200, None, _scoring_ok(), {"model": MODEL})

    sink = AtomicCalibrationSink(tmp_path / "cal")
    status, evidence, completed = execute_calibration_run(
        manifest_bytes=manifest_bytes,
        expected_manifest_sha256=manifest.sha256,
        actual_harness_revision=HEAD,
        auth=_auth(),
        batch_run_id=manifest.batch_run_id,
        transport=transport,
        evidence_sink=sink,
    )
    assert status.value == "FAILED"
    assert len(calls) == 3
    assert len(evidence) == 3
    assert completed is None
    cal_dir = Path(tmp_path) / "cal"
    assert len(list(cal_dir.glob("calibration-evidence-*.json"))) == 3
    assert not list(cal_dir.glob("calibration-completed-*.json"))


def test_malformed_decimal_stops(tmp_path: Path) -> None:
    manifest, manifest_bytes, _ = _prepared_manifest(tmp_path)
    transport, _ = _ok_transport(score="0.5")
    sink = AtomicCalibrationSink(tmp_path / "cal")
    status, _evidence, completed = execute_calibration_run(
        manifest_bytes=manifest_bytes,
        expected_manifest_sha256=manifest.sha256,
        actual_harness_revision=HEAD,
        auth=_auth(),
        batch_run_id=manifest.batch_run_id,
        transport=transport,
        evidence_sink=sink,
    )
    assert status.value == "FAILED"
    assert completed is None


def test_59_of_60_cannot_complete(tmp_path: Path) -> None:
    manifest, manifest_bytes, _ = _prepared_manifest(tmp_path)
    calls: list[int] = []

    def transport(*, payload: bytes) -> Any:
        n = len(calls) + 1
        calls.append(n)
        if n == 59:
            return (503, b"err", None, {})
        return (200, None, _scoring_ok(), {"model": MODEL})

    sink = AtomicCalibrationSink(tmp_path / "cal")
    status, evidence, completed = execute_calibration_run(
        manifest_bytes=manifest_bytes,
        expected_manifest_sha256=manifest.sha256,
        actual_harness_revision=HEAD,
        auth=_auth(),
        batch_run_id=manifest.batch_run_id,
        transport=transport,
        evidence_sink=sink,
    )
    assert status.value == "FAILED"
    assert len(calls) == 59
    assert completed is None
    assert not list((Path(tmp_path) / "cal").glob("calibration-completed-*.json"))


def test_one_case_exactly_one_call_not_two(tmp_path: Path) -> None:
    manifest, manifest_bytes, _ = _prepared_manifest(tmp_path)
    transport, count = _ok_transport()
    sink = AtomicCalibrationSink(tmp_path / "cal")
    _, _evidence, completed = execute_calibration_run(
        manifest_bytes=manifest_bytes,
        expected_manifest_sha256=manifest.sha256,
        actual_harness_revision=HEAD,
        auth=_auth(),
        batch_run_id=manifest.batch_run_id,
        transport=transport,
        evidence_sink=sink,
    )
    assert count["n"] == 60
    assert completed is not None


# ---------------------------------------------------------------------------
# Stale HEAD / wrong origin chain -> zero client construction
# ---------------------------------------------------------------------------
def test_stale_head_zero_calls(tmp_path: Path) -> None:
    manifest, manifest_bytes, _ = _prepared_manifest(tmp_path)
    transport, count = _ok_transport()
    sink = AtomicCalibrationSink(tmp_path / "cal")
    with pytest.raises(ValueError, match="harness revision"):
        execute_calibration_run(
            manifest_bytes=manifest_bytes,
            expected_manifest_sha256=manifest.sha256,
            actual_harness_revision="deadbeef" * 8,
            auth=_auth(),
            batch_run_id=manifest.batch_run_id,
            transport=transport,
            evidence_sink=sink,
        )
    assert count["n"] == 0
    assert not list((Path(tmp_path) / "cal").glob("calibration-batch-*.started"))


def test_wrong_origin_manifest_sha_zero_calls(tmp_path: Path) -> None:
    chain = _origin_chain(tmp_path)
    with pytest.raises(ValueError, match="origin manifest"):
        build_calibration_manifest(
            harness_revision=HEAD,
            **{**chain, "origin_manifest_sha256": "0" * 64},
        )


def test_wrong_completed_run_sha_zero_calls(tmp_path: Path) -> None:
    chain = _origin_chain(tmp_path)
    with pytest.raises(ValueError, match="origin completed"):
        build_calibration_manifest(
            harness_revision=HEAD,
            **{**chain, "origin_completed_sha256": "0" * 64},
        )


def test_cross_batch_origin_substitution_zero_calls(tmp_path: Path) -> None:
    chain = _origin_chain(tmp_path)
    with pytest.raises(ValueError, match="batch"):
        build_calibration_manifest(
            harness_revision=HEAD,
            **{**chain, "origin_batch_run_id": "origin-some-other-batch"},
        )


def test_4_of_5_origin_artifacts_zero_calls(tmp_path: Path) -> None:
    chain = _origin_chain(tmp_path)
    artifact_files = sorted((Path(tmp_path) / "origin").glob("origin-artifact-*.json"))
    assert len(artifact_files) == 5
    artifact_files[0].unlink()
    with pytest.raises(ValueError, match="artifact"):
        build_calibration_manifest(harness_revision=HEAD, **chain)


# ---------------------------------------------------------------------------
# Calibration manifest byte/SHA mutation -> zero calls
# ---------------------------------------------------------------------------
def test_calibration_manifest_byte_mutation_zero_calls(tmp_path: Path) -> None:
    manifest, manifest_bytes, _ = _prepared_manifest(tmp_path)
    transport, count = _ok_transport()
    sink = AtomicCalibrationSink(tmp_path / "cal")
    tampered = bytearray(manifest_bytes)
    tampered[10] ^= 0xFF
    with pytest.raises(ValueError, match="hash"):
        execute_calibration_run(
            manifest_bytes=bytes(tampered),
            expected_manifest_sha256=manifest.sha256,
            actual_harness_revision=HEAD,
            auth=_auth(),
            batch_run_id=manifest.batch_run_id,
            transport=transport,
            evidence_sink=sink,
        )
    assert count["n"] == 0


def test_calibration_manifest_sha_mutation_zero_calls(tmp_path: Path) -> None:
    manifest, manifest_bytes, _ = _prepared_manifest(tmp_path)
    transport, count = _ok_transport()
    sink = AtomicCalibrationSink(tmp_path / "cal")
    with pytest.raises(ValueError, match="hash"):
        execute_calibration_run(
            manifest_bytes=manifest_bytes,
            expected_manifest_sha256="0" * 64,
            actual_harness_revision=HEAD,
            auth=_auth(),
            batch_run_id=manifest.batch_run_id,
            transport=transport,
            evidence_sink=sink,
        )
    assert count["n"] == 0


# ---------------------------------------------------------------------------
# Seal-A/use-B substitution impossible (N3)
# ---------------------------------------------------------------------------
def test_seal_a_use_b_substitution_impossible(tmp_path: Path) -> None:
    manifest_a, _manifest_a_bytes, _ = _prepared_manifest(tmp_path)
    manifest_b, _, _ = _prepared_manifest(tmp_path)
    assert manifest_a.sha256 != manifest_b.sha256
    transport, count = _ok_transport()
    sink = AtomicCalibrationSink(tmp_path / "cal")
    with pytest.raises(ValueError, match="hash"):
        execute_calibration_run(
            manifest_bytes=manifest_b.to_exact_bytes(),
            expected_manifest_sha256=manifest_a.sha256,
            actual_harness_revision=HEAD,
            auth=_auth(),
            batch_run_id=manifest_a.batch_run_id,
            transport=transport,
            evidence_sink=sink,
        )
    assert count["n"] == 0


def test_validate_seal_exact_returns_same_object(tmp_path: Path) -> None:
    manifest_a, _bytes_a, _ = _prepared_manifest(tmp_path)
    returned = validate_calibration_manifest_seal_exact(
        manifest=manifest_a,
        manifest_sha256=manifest_a.sha256,
        auth=_auth(),
        actual_harness_revision=HEAD,
    )
    assert returned is manifest_a


# ---------------------------------------------------------------------------
# Request-byte contract: exact sealed bytes = HTTP Request.data (no continuation)
# ---------------------------------------------------------------------------
def test_exact_sealed_request_bytes_equal_http_data(tmp_path: Path) -> None:
    manifest, manifest_bytes, specs = _prepared_manifest(tmp_path)
    got: list[bytes] = []

    def transport(*, payload: bytes) -> Any:
        got.append(payload)
        return (200, None, _scoring_ok(), {"model": MODEL})

    sink = AtomicCalibrationSink(tmp_path / "cal")
    execute_calibration_run(
        manifest_bytes=manifest_bytes,
        expected_manifest_sha256=manifest.sha256,
        actual_harness_revision=HEAD,
        auth=_auth(),
        batch_run_id=manifest.batch_run_id,
        transport=transport,
        evidence_sink=sink,
    )
    assert len(got) == 60
    for spec in specs:
        idx = spec.request_index - 1
        assert got[idx] == spec.request_bytes
        assert sha256_bytes(got[idx]) == spec.request_sha256
        body = json.loads(got[idx].decode("utf-8"))
        assert "previous_response_id" not in body or body["previous_response_id"] is None
        assert "conversation" not in body


def test_scoring_payload_no_transcript_truth(tmp_path: Path) -> None:
    manifest, manifest_bytes, specs = _prepared_manifest(tmp_path)
    seen: list[bytes] = []

    def transport(*, payload: bytes) -> Any:
        seen.append(payload)
        return (200, None, _scoring_ok(), {"model": MODEL})

    sink = AtomicCalibrationSink(tmp_path / "cal")
    execute_calibration_run(
        manifest_bytes=manifest_bytes,
        expected_manifest_sha256=manifest.sha256,
        actual_harness_revision=HEAD,
        auth=_auth(),
        batch_run_id=manifest.batch_run_id,
        transport=transport,
        evidence_sink=sink,
    )
    assert len(seen) == 60
    for spec in specs:
        body = json.loads(seen[spec.request_index - 1].decode("utf-8"))
        # The request body exposes only the frozen Response fields, never a truth
        # label or any conversation/history/transcript continuation payload.
        assert set(body) == {"input", "max_output_tokens", "model", "reasoning", "store"}
        text = body["input"]
        assert isinstance(text, str)
        assert text.startswith("You maintain a record")
        assert "truth" not in text.lower()
        assert "truth_label" not in text.lower()
        for forbidden in ("transcript", "conversation", "history", "session_log"):
            assert forbidden not in text.lower()


# ---------------------------------------------------------------------------
# Missing API key -> no .started marker + zero transport (CLI live guard)
# ---------------------------------------------------------------------------
def test_missing_api_key_no_started_marker_zero_transport(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import protean_stage0.stage1a_calibration_cli as cli

    manifest, manifest_bytes, _ = _prepared_manifest(tmp_path)
    # Point the CLI at the synthetic origin chain, not any local gitignored files.
    c = _origin_chain(tmp_path)
    mpath = tmp_path / "cal.json"
    mpath.write_bytes(manifest_bytes)
    out = tmp_path / "out"
    calls: list[str] = []
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setattr(cli, "working_tree_is_clean", lambda: True)
    monkeypatch.setattr(cli, "derive_head", lambda: HEAD)
    monkeypatch.setattr(cli, "_fixed_calibration_transport", lambda: calls.append("transport"))
    rc = cli.run_cli(
        [
            "--execute-live",
            "--manifest",
            str(mpath),
            "--expected-manifest-sha",
            manifest.sha256,
            "--origin-manifest",
            str(c["origin_manifest_path"]),
            "--origin-manifest-sha",
            c["origin_manifest_sha256"],
            "--origin-completed",
            str(c["origin_completed_path"]),
            "--origin-completed-sha",
            c["origin_completed_sha256"],
            "--origin-artifacts-dir",
            str(c["origin_artifacts_dir"]),
            "--origin-batch",
            c["origin_batch_run_id"],
            "--out-dir",
            str(out),
        ]
    )
    assert rc != 0
    assert calls == []
    assert not list(out.glob("calibration-batch-*.started"))


# ---------------------------------------------------------------------------
# Authority mutation -> zero client/calls
# ---------------------------------------------------------------------------
def test_authority_mutation_zero_calls(tmp_path: Path) -> None:
    chain = _origin_chain(tmp_path)
    oc_path = Path(chain["origin_completed_path"])
    raw = json.loads(oc_path.read_text())
    raw["batch_run_id"] = "tampered"
    oc_path.write_bytes(json.dumps(raw).encode("utf-8"))
    with pytest.raises(ValueError):
        build_calibration_manifest(harness_revision=HEAD, **chain)


# ---------------------------------------------------------------------------
# Deterministic analysis gating (threshold report; C=.50 futility stop)
# ---------------------------------------------------------------------------
def test_threshold_analysis_refuses_incomplete_run(tmp_path: Path) -> None:
    manifest, _bytes, _ = _prepared_manifest(tmp_path)
    with pytest.raises(ValueError, match="completed"):
        require_valid_completed_calibration(
            None,
            expected_manifest_sha256=manifest.sha256,
            expected_batch_run_id=manifest.batch_run_id,
        )


def test_threshold_c_equals_50_yields_deterministic_futility_stop(tmp_path: Path) -> None:
    manifest, manifest_bytes, _ = _prepared_manifest(tmp_path)
    transport, _ = _ok_transport(score="0.50")
    sink = AtomicCalibrationSink(tmp_path / "cal")
    _, _, completed = execute_calibration_run(
        manifest_bytes=manifest_bytes,
        expected_manifest_sha256=manifest.sha256,
        actual_harness_revision=HEAD,
        auth=_auth(),
        batch_run_id=manifest.batch_run_id,
        transport=transport,
        evidence_sink=sink,
    )
    assert completed is not None
    report = compute_calibration_report(
        completed,
        expected_manifest_sha256=manifest.sha256,
        expected_batch_run_id=manifest.batch_run_id,
        truth_map=manifest.truth_map,
    )
    assert report["stage1b_projection"] == "DETERMINISTIC_FUTILITY_STOP"


# ---------------------------------------------------------------------------
# N3 close at the Stage1AManifest layer
# ---------------------------------------------------------------------------
def test_stage1a_manifest_exact_byte_reconstruction(tmp_path: Path) -> None:
    from protean_stage0.stage1a_manifest import Stage1AManifest

    m = _real_stage1a_manifest()
    raw = m.to_exact_bytes()
    rebuilt = Stage1AManifest._reconstruct(raw)
    assert rebuilt.to_exact_bytes() == raw
    assert rebuilt.sha256 == m.sha256


def test_stage1a_manifest_seal_exact_returns_same_object(tmp_path: Path) -> None:
    from protean_stage0.direct_config import direct_model_configuration
    from protean_stage0.stage1a_cases import build_stage1a_cases, freeze_stage1a_case_set
    from protean_stage0.stage1a_config import STAGE1A_SEED
    from protean_stage0.stage1a_manifest import validate_stage1a_manifest_seal_exact
    from protean_stage0.textualize import TemplateBank

    m = _real_stage1a_manifest()
    auth = _auth()
    cases = build_stage1a_cases(
        seed=STAGE1A_SEED, template_bank=TemplateBank.from_bytes(auth.template_bank.content)
    )
    case_set = freeze_stage1a_case_set(cases)
    returned = validate_stage1a_manifest_seal_exact(
        m,
        actual_harness_revision=HEAD,
        protocol=auth.protocol,
        futility_amendment=auth.futility_amendment,
        real_origin_amendment=auth.real_origin_amendment,
        case_set=case_set,
        scoring_prompt=auth.scoring_prompt,
        parse_contract_sha256="0" * 64,
        model_configuration=direct_model_configuration(),
        expected_origin_run_manifest_sha256="0" * 64,
        expected_origin_completed_run_sha256="0" * 64,
        expected_origin_batch_run_id="b",
    )
    assert returned is m


def _real_stage1a_manifest() -> Any:
    from protean_stage0.direct_config import direct_model_configuration
    from protean_stage0.schema import EvaluatorProvenance
    from protean_stage0.stage1a_cases import build_stage1a_cases, freeze_stage1a_case_set
    from protean_stage0.stage1a_config import STAGE1A_SEED
    from protean_stage0.stage1a_manifest import Stage1AManifest
    from protean_stage0.textualize import TemplateBank

    auth = _auth()
    cases = build_stage1a_cases(
        seed=STAGE1A_SEED, template_bank=TemplateBank.from_bytes(auth.template_bank.content)
    )
    case_set = freeze_stage1a_case_set(cases)
    prov = EvaluatorProvenance(
        evaluator_name="p",
        author="p",
        authored_at="T",
        grammar_version="v1",
        grammar_sha256="0" * 64,
        independently_derived=True,
        implementation_sha256="0" * 64,
    )
    return Stage1AManifest.create(
        protocol=auth.protocol,
        futility_amendment=auth.futility_amendment,
        real_origin_amendment=auth.real_origin_amendment,
        case_set=case_set,
        scoring_prompt=auth.scoring_prompt,
        parse_contract_sha256="0" * 64,
        model_configuration=direct_model_configuration(),
        harness_revision=HEAD,
        primary_evaluator=prov,
        reference_evaluator=prov,
        timestamp="T",
        run_id="R",
        origin_run_manifest_sha256="0" * 64,
        origin_completed_run_sha256="0" * 64,
        origin_batch_run_id="b",
    )


# ---------------------------------------------------------------------------
# Correction 1 regression: duplicated/substituted origin artifact cannot pass the
# canonical prepare-path verifier (Claude-proven gap).
# ---------------------------------------------------------------------------
def test_duplicated_artifact_slot_attack_rejected(tmp_path: Path) -> None:
    chain = _origin_chain(tmp_path)
    art_dir = Path(tmp_path) / "origin"
    # Duplicate slot-1 content into slot-2's file (superficially matching batch/manifest).
    slot1 = next(art_dir.glob("origin-artifact-*-01.json"))
    slot2 = next(art_dir.glob("origin-artifact-*-02.json"))
    slot2.write_bytes(slot1.read_bytes())
    assert slot1.read_bytes() == slot2.read_bytes()
    with pytest.raises(ValueError, match="request index"):
        build_calibration_manifest(harness_revision=HEAD, **chain)


def test_swapped_valid_artifacts_rejected(tmp_path: Path) -> None:
    chain = _origin_chain(tmp_path)
    art_dir = Path(tmp_path) / "origin"
    slot1 = next(art_dir.glob("origin-artifact-*-01.json"))
    slot2 = next(art_dir.glob("origin-artifact-*-02.json"))
    c1, c2 = slot1.read_bytes(), slot2.read_bytes()
    slot1.write_bytes(c2)
    slot2.write_bytes(c1)  # swap the two valid artifacts
    with pytest.raises(ValueError):
        build_calibration_manifest(harness_revision=HEAD, **chain)


# ---------------------------------------------------------------------------
# Correction 2: the REAL production CLI --execute-live success path (60/60/0),
# through a payload-aware fake at the network boundary (no transport injection).
# ---------------------------------------------------------------------------
def test_cli_execute_live_completed_60_60(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import protean_stage0.direct_responses as dr
    import protean_stage0.stage1a_calibration_cli as cli
    from protean_stage0.stage1a_calibration_driver import _build_calibration_specs

    manifest, manifest_bytes, _ = _prepared_manifest(tmp_path)
    mpath = tmp_path / "cal.json"
    mpath.write_bytes(manifest_bytes)
    origin = _origin_chain(tmp_path)
    out = tmp_path / "out"

    # Deterministic expected request bytes, in manifest order.
    specs = _build_calibration_specs(
        auth=_auth(), harness_revision=HEAD, batch_run_id=manifest.batch_run_id
    )
    expected_by_index = {s.request_index: s.request_bytes for s in specs}

    transmitted: list[bytes] = []
    calls = {"n": 0}

    def fake_default_transport(*, payload: bytes, api_key: str, timeout_seconds: int) -> Any:
        # Payload-aware: only accept exactly one of the sealed request bytes; reject if a
        # payload is not one of the 60 sealed requests or repeats an index out of order.
        calls["n"] += 1
        n = calls["n"]
        if n > 60:
            return dr.TransportResult(400, b"too many requests")
        expected = expected_by_index[n]
        if payload != expected:
            return dr.TransportResult(400, b"payload does not match sealed request")
        transmitted.append(payload)
        return dr.TransportResult(200, _scoring_ok("0.60"))

    # Network boundary: the CLI's fixed transport homes in on its module-level
    # default_transport binding. Patch exactly that (no transport-injection param).
    monkeypatch.setattr(cli, "default_transport", fake_default_transport)
    monkeypatch.setattr(cli, "working_tree_is_clean", lambda: True)
    monkeypatch.setattr(cli, "derive_head", lambda: HEAD)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-dummy")

    # Capture stdout on the single invocation to assert the COMPLETED status line.
    import io
    from contextlib import redirect_stdout

    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = cli.run_cli(
            [
                "--execute-live",
                "--manifest",
                str(mpath),
                "--expected-manifest-sha",
                manifest.sha256,
                "--origin-manifest",
                str(origin["origin_manifest_path"]),
                "--origin-manifest-sha",
                origin["origin_manifest_sha256"],
                "--origin-completed",
                str(origin["origin_completed_path"]),
                "--origin-completed-sha",
                origin["origin_completed_sha256"],
                "--origin-artifacts-dir",
                str(origin["origin_artifacts_dir"]),
                "--origin-batch",
                origin["origin_batch_run_id"],
                "--out-dir",
                str(out),
            ],
        )
    assert rc == 0
    assert "calibration_status=COMPLETED" in buf.getvalue()
    # exactly 60 transport calls and the payload bytes equal the sealed request bytes.
    assert calls["n"] == 60
    assert transmitted == [expected_by_index[i] for i in range(1, 61)]
    # evidence + one completed authority, byte-exact reconstruction, order matches manifest.
    ev_files = sorted(out.glob("calibration-evidence-*.json"))
    comp_files = list(out.glob("calibration-completed-*.json"))
    assert len(ev_files) == 60
    assert len(comp_files) == 1
    completed = CalibrationCompletedRun._reconstruct(comp_files[0].read_bytes())
    assert completed.to_exact_bytes() == comp_files[0].read_bytes()
    assert completed.ordered_case_ids == manifest.ordered_case_ids


# ---------------------------------------------------------------------------
# Correction 3: analysis gating NON-OPTIONAL inside compute_calibration_report.
# ---------------------------------------------------------------------------
def test_report_allowed_with_correct_manifest_batch(tmp_path: Path) -> None:
    manifest, manifest_bytes, _ = _prepared_manifest(tmp_path)
    transport, _ = _ok_transport(score="0.60")
    sink = AtomicCalibrationSink(tmp_path / "cal")
    _, _, completed = execute_calibration_run(
        manifest_bytes=manifest_bytes,
        expected_manifest_sha256=manifest.sha256,
        actual_harness_revision=HEAD,
        auth=_auth(),
        batch_run_id=manifest.batch_run_id,
        transport=transport,
        evidence_sink=sink,
    )
    assert completed is not None
    report = compute_calibration_report(
        completed,
        expected_manifest_sha256=manifest.sha256,
        expected_batch_run_id=manifest.batch_run_id,
        truth_map=manifest.truth_map,
    )
    assert report["manifest_sha256"] == manifest.sha256


def test_report_rejects_wrong_manifest_sha(tmp_path: Path) -> None:
    manifest, manifest_bytes, _ = _prepared_manifest(tmp_path)
    transport, _ = _ok_transport(score="0.60")
    sink = AtomicCalibrationSink(tmp_path / "cal")
    _, _, completed = execute_calibration_run(
        manifest_bytes=manifest_bytes,
        expected_manifest_sha256=manifest.sha256,
        actual_harness_revision=HEAD,
        auth=_auth(),
        batch_run_id=manifest.batch_run_id,
        transport=transport,
        evidence_sink=sink,
    )
    assert completed is not None
    with pytest.raises(ValueError, match="manifest SHA"):
        compute_calibration_report(
            completed,
            expected_manifest_sha256="0" * 64,
            expected_batch_run_id=manifest.batch_run_id,
            truth_map=manifest.truth_map,
        )


def test_report_rejects_wrong_batch(tmp_path: Path) -> None:
    manifest, manifest_bytes, _ = _prepared_manifest(tmp_path)
    transport, _ = _ok_transport(score="0.60")
    sink = AtomicCalibrationSink(tmp_path / "cal")
    _, _, completed = execute_calibration_run(
        manifest_bytes=manifest_bytes,
        expected_manifest_sha256=manifest.sha256,
        actual_harness_revision=HEAD,
        auth=_auth(),
        batch_run_id=manifest.batch_run_id,
        transport=transport,
        evidence_sink=sink,
    )
    assert completed is not None
    with pytest.raises(ValueError, match="batch"):
        compute_calibration_report(
            completed,
            expected_manifest_sha256=manifest.sha256,
            expected_batch_run_id="wrong-batch",
            truth_map=manifest.truth_map,
        )


def test_report_rejects_59_of_60(tmp_path: Path) -> None:
    manifest, manifest_bytes, _ = _prepared_manifest(tmp_path)
    calls: list[int] = []

    def transport(*, payload: bytes) -> Any:
        n = len(calls) + 1
        calls.append(n)
        if n == 59:
            return (503, b"err", None, {})
        return (200, None, _scoring_ok(), {"model": MODEL})

    sink = AtomicCalibrationSink(tmp_path / "cal")
    _, _, completed = execute_calibration_run(
        manifest_bytes=manifest_bytes,
        expected_manifest_sha256=manifest.sha256,
        actual_harness_revision=HEAD,
        auth=_auth(),
        batch_run_id=manifest.batch_run_id,
        transport=transport,
        evidence_sink=sink,
    )
    assert completed is None
    with pytest.raises(ValueError, match="completed"):
        compute_calibration_report(
            None,
            expected_manifest_sha256=manifest.sha256,
            expected_batch_run_id=manifest.batch_run_id,
            truth_map=manifest.truth_map,
        )


def test_report_rejects_fabricated_self_consistent_object() -> None:
    # A length-60 self-consistent object cannot bypass the outer manifest/batch binding.
    fake = CalibrationCompletedRun(
        manifest_sha256="cafebabe" * 8,
        batch_run_id="fabricated",
        ordered_case_ids=tuple(f"S1A-{i:02d}" for i in range(1, 61)),
        evidence_shas=tuple(("aa" * 32) for _ in range(60)),
        scores=(0.5,) * 60,
    )
    with pytest.raises(ValueError, match="manifest SHA"):
        compute_calibration_report(
            fake,
            expected_manifest_sha256="0" * 64,
            expected_batch_run_id="expected-batch",
            truth_map={f"S1A-{i:02d}": (i % 2 == 0) for i in range(1, 61)},
        )
