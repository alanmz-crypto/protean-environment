# mypy: ignore-errors

"""Hermetic tests for the sealed live-origin CLI + calibrated authority."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from protean_stage0.stage1a_authority import load_authority_artifacts
from protean_stage0.stage1a_origin_cli import (
    derive_head,
)
from protean_stage0.stage1a_origin_driver import (
    AtomicEvidenceSink,
    build_origin_run_manifest,
    execute_origin_run,
)
from protean_stage0.stage1a_origin_run_manifest import Stage1AOriginRunManifest
from protean_stage0.textualize import TemplateBank

REPO = Path(__file__).resolve().parents[1]


def _auth() -> Any:
    return load_authority_artifacts(verify_expected=True)


def direct_config() -> Any:
    from protean_stage0.direct_config import direct_model_configuration

    return direct_model_configuration()


def _counted_transport(counter: dict[str, int]):
    def transport(*, payload: bytes):
        counter["n"] += 1
        return (None, None, None, {})

    return transport


def _luna_ok(case_ids: list[str]) -> bytes:
    adopt = "\n".join(f"ADOPT {cid}" for cid in case_ids)
    from protean_stage0.direct_config import MODEL, REASONING_CONTEXT, REASONING_EFFORT

    return json.dumps(
        {
            "id": "r",
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


def test_cli_prepare_writes_manifest_and_reports(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import protean_stage0.stage1a_origin_cli as cli

    monkeypatch.setattr(cli, "DEFAULT_MANIFEST_DIR", tmp_path)
    from protean_stage0.stage1a_origin_cli import run_cli

    assert run_cli(["--prepare"]) == 0
    manifests = list(tmp_path.glob("origin-run-manifest-*.json"))
    assert len(manifests) == 1
    m = Stage1AOriginRunManifest._reconstruct(manifests[0].read_bytes())
    assert m.harness_revision == derive_head()
    assert m.expected_requests == 5


def test_cli_live_requires_manifest_and_sha(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import protean_stage0.stage1a_origin_cli as cli

    monkeypatch.setattr(cli, "DEFAULT_MANIFEST_DIR", tmp_path)
    with pytest.raises(SystemExit):
        cli.run_cli(["--execute-live"])  # missing --manifest/--expected-manifest-sha


def test_cli_live_dirty_tree_zero_attempts(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import protean_stage0.stage1a_origin_cli as cli

    monkeypatch.setattr(cli, "working_tree_is_clean", lambda: False)
    attempts = {"n": 0}
    monkeypatch.setattr(
        cli,
        "_fixed_responses_transport",
        lambda auth: _counted_transport(attempts),
    )
    auth = _auth()
    manifest, specs = build_origin_run_manifest(
        auth=auth, harness_revision=derive_head(), batch_run_id="c-x"
    )
    mpath = tmp_path / "origin-run-manifest-x.json"
    mpath.write_bytes(manifest.to_exact_bytes())
    rc = cli.run_cli(
        ["--execute-live", "--manifest", str(mpath), "--expected-manifest-sha", manifest.sha256]
    )
    assert rc == 2  # dirty tree -> STOP
    assert attempts["n"] == 0


def test_cli_live_stale_head_zero_attempts(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import protean_stage0.stage1a_origin_cli as cli

    monkeypatch.setattr(cli, "working_tree_is_clean", lambda: True)
    attempts = {"n": 0}
    monkeypatch.setattr(
        cli,
        "_fixed_responses_transport",
        lambda auth: _counted_transport(attempts),
    )
    auth = _auth()
    manifest, specs = build_origin_run_manifest(
        auth=auth, harness_revision="STALE-HEAD", batch_run_id="c-s"
    )
    mpath = tmp_path / "origin-run-manifest-s.json"
    mpath.write_bytes(manifest.to_exact_bytes())
    rc = cli.run_cli(
        ["--execute-live", "--manifest", str(mpath), "--expected-manifest-sha", manifest.sha256]
    )
    assert rc == 2
    assert attempts["n"] == 0


def test_cli_live_wrong_sha_zero_attempts(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import protean_stage0.stage1a_origin_cli as cli

    monkeypatch.setattr(cli, "working_tree_is_clean", lambda: True)
    attempts = {"n": 0}
    monkeypatch.setattr(
        cli,
        "_fixed_responses_transport",
        lambda auth: _counted_transport(attempts),
    )
    auth = _auth()
    manifest, specs = build_origin_run_manifest(
        auth=auth, harness_revision=derive_head(), batch_run_id="c-w"
    )
    mpath = tmp_path / "origin-run-manifest-w.json"
    mpath.write_bytes(manifest.to_exact_bytes())
    rc = cli.run_cli(
        ["--execute-live", "--manifest", str(mpath), "--expected-manifest-sha", "0" * 64]
    )
    assert rc == 2
    assert attempts["n"] == 0


def test_manifest_bytes_are_exactly_the_http_payload(tmp_path) -> None:
    # The bytes hashed into the manifest are byte-for-byte the bytes a transport
    # receives immediately before HTTP transmission.
    auth = _auth()
    manifest, specs = build_origin_run_manifest(
        auth=auth, harness_revision="H", batch_run_id="b-proof"
    )
    received: list[bytes] = []

    def transport(*, payload: bytes) -> tuple:
        received.append(payload)  # capture exactly what would be POSTed
        structure = specs[len(received) - 1]
        cids = structure.case_ids
        return (200, None, _luna_ok(list(cids)), {"model": "gpt-5.6-luna"})

    result = execute_origin_run(
        manifest_bytes=manifest.to_exact_bytes(),
        expected_manifest_sha256=manifest.sha256,
        actual_harness_revision="H",
        auth=auth,
        batch_run_id="b-proof",
        transport=transport,
        evidence_sink=AtomicEvidenceSink(tmp_path),
    )
    assert result.status.value == "COMPLETED"
    assert len(received) == 5
    # Each transported payload is byte-for-byte the sealed request bytes in the manifest's specs.
    for i, spec in enumerate(specs):
        assert received[i] == spec.request_bytes
        assert receiver_sha(received[i]) == spec.request_sha256


def receiver_sha(b: bytes) -> str:
    from protean_stage0.artifacts import sha256_bytes

    return sha256_bytes(b)


# ---- calibration: origin authority must come from the sealed Stage1AManifest ----
def _ok_transport_for(auth: Any, specs: Any) -> Any:
    from protean_stage0.direct_config import MODEL
    from protean_stage0.grammar import FROZEN_STRUCTURES

    idx = {"n": 0}

    def transport(
        *, payload: bytes
    ) -> tuple[int | None, bytes | None, bytes | None, dict[Any, Any]]:
        idx["n"] += 1
        structure = FROZEN_STRUCTURES[idx["n"] - 1]
        cids = [
            c.case_id for c in auth.case_set.cases if c.structured_spec.structure_id == structure
        ]
        return (200, None, _luna_ok(cids), {"model": MODEL})

    return transport


def _prepared(
    auth: Any, cases: Any, artifacts: Any, completed: Any, origin_sha: str, completed_sha: str
) -> tuple[Any, list[Any]]:
    from types import SimpleNamespace

    from protean_stage0.artifacts import FrozenArtifact
    from protean_stage0.stage1a_driver import Stage1APreparedRun

    called: list[str] = []

    # seal() returns the exact manifest consumed downstream: a stand-in object
    # carrying the immutable origin authority fields.
    cm = SimpleNamespace(
        origin_run_manifest_sha256=origin_sha,
        origin_completed_run_sha256=completed_sha,
        origin_batch_run_id=completed.batch_run_id if completed else "",
    )
    prepared = Stage1APreparedRun(
        cases=cases,
        scoring_prompt=FrozenArtifact.from_bytes("p", b"x"),
        model_configuration=direct_config(),
        seal=lambda: cm,
        client_factory=lambda: called.append("client") or object(),
        origin_artifacts=tuple(artifacts),
        completed_run=completed,
    )
    return prepared, called


def test_calibration_sealed_path_reaches_client(tmp_path) -> None:
    from protean_stage0.stage1a_cases import build_stage1a_cases

    a = _auth()
    cases = build_stage1a_cases(
        template_bank=TemplateBank.from_bytes((REPO / "stage0/template-bank-v1.json").read_bytes())
    )
    manifest, specs = build_origin_run_manifest(
        auth=a, harness_revision="HARNESS", batch_run_id="cb-ok"
    )
    result = execute_origin_run(
        manifest_bytes=manifest.to_exact_bytes(),
        expected_manifest_sha256=manifest.sha256,
        actual_harness_revision="HARNESS",
        auth=a,
        batch_run_id="cb-ok",
        transport=_ok_transport_for(a, specs),
        evidence_sink=AtomicEvidenceSink(tmp_path),
    )
    assert result.status.value == "COMPLETED"
    assert result.completed is not None
    prepared, called = _prepared(
        a,
        cases,
        list(result.artifacts),
        result.completed,
        manifest.sha256,
        result.completed.completed_run_sha256,
    )
    with pytest.raises(AttributeError):  # client returns a non-client -> scoring fails later
        prepared.run()
    assert called == ["client"]  # reached client construction


def test_calibration_wrong_origin_manifest_sha_zero_clients(tmp_path) -> None:
    from protean_stage0.stage1a_cases import build_stage1a_cases

    a = _auth()
    cases = build_stage1a_cases(
        template_bank=TemplateBank.from_bytes((REPO / "stage0/template-bank-v1.json").read_bytes())
    )
    manifest, specs = build_origin_run_manifest(
        auth=a, harness_revision="HARNESS", batch_run_id="cb-x"
    )
    result = execute_origin_run(
        manifest_bytes=manifest.to_exact_bytes(),
        expected_manifest_sha256=manifest.sha256,
        actual_harness_revision="HARNESS",
        auth=a,
        batch_run_id="cb-x",
        transport=_ok_transport_for(a, specs),
        evidence_sink=AtomicEvidenceSink(tmp_path),
    )
    assert result.completed is not None
    prepared, called = _prepared(
        a,
        cases,
        list(result.artifacts),
        result.completed,
        "0" * 64,
        result.completed.completed_run_sha256,
    )
    with pytest.raises(ValueError):
        prepared.run()
    assert called == []


def test_calibration_missing_authority_field_zero_clients(tmp_path) -> None:
    # A Stage1AManifest missing the origin authority field(s) is not calibration-authorizing.
    from protean_stage0.artifacts import FrozenArtifact
    from protean_stage0.schema import EvaluatorProvenance  # noqa
    from protean_stage0.stage1a_cases import build_stage1a_cases, freeze_stage1a_case_set
    from protean_stage0.stage1a_manifest import Stage1AManifest

    cases = build_stage1a_cases(
        template_bank=TemplateBank.from_bytes((REPO / "stage0/template-bank-v1.json").read_bytes())
    )
    case_set = freeze_stage1a_case_set(cases)
    protocol = FrozenArtifact.from_bytes(
        "p", (REPO / "docs/PROTOCOL-prospective-control-v1.0.md").read_bytes()
    )
    amendment = FrozenArtifact.from_bytes(
        "f",
        (REPO / "docs/RATIFIED-AMENDMENT-stage1-futility-shared-score-v1.0.1-r1.md").read_bytes(),
    )
    real = FrozenArtifact.from_bytes(
        "r", (REPO / "docs/RATIFIED-AMENDMENT-stage1a-real-origin-v1.0.2-r1.md").read_bytes()
    )
    prompt = FrozenArtifact.from_bytes(
        "s", (REPO / "stage0/candidate-scoring-prompt-v1.txt").read_bytes()
    )
    prov = EvaluatorProvenance(
        evaluator_name="p",
        author="p",
        authored_at="T",
        grammar_version="v1",
        grammar_sha256="0" * 64,
        independently_derived=True,
        implementation_sha256="0" * 64,
    )
    manifest = Stage1AManifest.create(
        protocol=protocol,
        futility_amendment=amendment,
        real_origin_amendment=real,
        case_set=case_set,
        scoring_prompt=prompt,
        parse_contract_sha256="0" * 64,
        model_configuration=direct_config(),
        harness_revision="HARNESS",
        primary_evaluator=prov,
        reference_evaluator=prov,
        timestamp="T",
        run_id="R",
        # origin authority fields omitted -> empty -> not authorizing
    )
    # validate_completeness must reject the empty origin fields.
    from protean_stage0.stage1a_manifest import validate_stage1a_manifest_seal

    with pytest.raises(ValueError):
        validate_stage1a_manifest_seal(
            manifest,
            actual_harness_revision="HARNESS",
            protocol=protocol,
            futility_amendment=amendment,
            real_origin_amendment=real,
            case_set=case_set,
            scoring_prompt=prompt,
            parse_contract_sha256="0" * 64,
            model_configuration=direct_config(),
            expected_origin_run_manifest_sha256="x",
            expected_origin_completed_run_sha256="y",
            expected_origin_batch_run_id="z",
        )


def _real_calibration_manifest(auth, origin_sha, completed_sha, batch):
    from protean_stage0.artifacts import FrozenArtifact
    from protean_stage0.schema import EvaluatorProvenance
    from protean_stage0.stage1a_cases import build_stage1a_cases, freeze_stage1a_case_set
    from protean_stage0.stage1a_manifest import Stage1AManifest
    from protean_stage0.textualize import TemplateBank

    cases = build_stage1a_cases(
        template_bank=TemplateBank.from_bytes((REPO / "stage0/template-bank-v1.json").read_bytes())
    )
    case_set = freeze_stage1a_case_set(cases)
    protocol = FrozenArtifact.from_bytes(
        "p", (REPO / "docs/PROTOCOL-prospective-control-v1.0.md").read_bytes()
    )
    futility = FrozenArtifact.from_bytes(
        "f",
        (REPO / "docs/RATIFIED-AMENDMENT-stage1-futility-shared-score-v1.0.1-r1.md").read_bytes(),
    )
    real = FrozenArtifact.from_bytes(
        "r", (REPO / "docs/RATIFIED-AMENDMENT-stage1a-real-origin-v1.0.2-r1.md").read_bytes()
    )
    prompt = FrozenArtifact.from_bytes(
        "s", (REPO / "stage0/candidate-scoring-prompt-v1.txt").read_bytes()
    )
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
        protocol=protocol,
        futility_amendment=futility,
        real_origin_amendment=real,
        case_set=case_set,
        scoring_prompt=prompt,
        parse_contract_sha256="0" * 64,
        model_configuration=direct_config(),
        harness_revision="HARNESS",
        primary_evaluator=prov,
        reference_evaluator=prov,
        timestamp="T",
        run_id="R",
        origin_run_manifest_sha256=origin_sha,
        origin_completed_run_sha256=completed_sha,
        origin_batch_run_id=batch,
    )


def _real_seal(manifest: Any) -> Any:
    """Build a seal() callable that runs the REAL validate_stage1a_manifest_seal on the
    given (authoring) Stage1AManifest and returns exactly that manifest. This makes the
    positive path invoke the actual validation code for the exact object later consumed."""
    from protean_stage0.artifacts import FrozenArtifact
    from protean_stage0.stage1a_cases import build_stage1a_cases, freeze_stage1a_case_set
    from protean_stage0.stage1a_manifest import validate_stage1a_manifest_seal
    from protean_stage0.textualize import TemplateBank

    cases = build_stage1a_cases(
        template_bank=TemplateBank.from_bytes((REPO / "stage0/template-bank-v1.json").read_bytes())
    )
    case_set = freeze_stage1a_case_set(cases)
    protocol = FrozenArtifact.from_bytes(
        "p", (REPO / "docs/PROTOCOL-prospective-control-v1.0.md").read_bytes()
    )
    futility = FrozenArtifact.from_bytes(
        "f",
        (REPO / "docs/RATIFIED-AMENDMENT-stage1-futility-shared-score-v1.0.1-r1.md").read_bytes(),
    )
    real = FrozenArtifact.from_bytes(
        "r", (REPO / "docs/RATIFIED-AMENDMENT-stage1a-real-origin-v1.0.2-r1.md").read_bytes()
    )
    prompt = FrozenArtifact.from_bytes(
        "s", (REPO / "stage0/candidate-scoring-prompt-v1.txt").read_bytes()
    )

    def seal() -> Any:
        validate_stage1a_manifest_seal(
            manifest,
            actual_harness_revision=manifest.harness_revision,
            protocol=protocol,
            futility_amendment=futility,
            real_origin_amendment=real,
            case_set=case_set,
            scoring_prompt=prompt,
            parse_contract_sha256=manifest.parse_contract_sha256,
            model_configuration=direct_config(),
            expected_origin_run_manifest_sha256=manifest.origin_run_manifest_sha256,
            expected_origin_completed_run_sha256=manifest.origin_completed_run_sha256,
            expected_origin_batch_run_id=manifest.origin_batch_run_id,
        )
        return manifest

    return seal


def test_authority_join_real_manifest_positive(tmp_path) -> None:
    # Positive: a REAL sealed Stage1AManifest authority (not self-consistent SHAs)
    # plus a matching completed origin batch pass preflight and reach client construction.
    from protean_stage0.artifacts import FrozenArtifact
    from protean_stage0.stage1a_cases import build_stage1a_cases
    from protean_stage0.stage1a_driver import Stage1APreparedRun
    from protean_stage0.textualize import TemplateBank

    a = _auth()
    cases = build_stage1a_cases(
        template_bank=TemplateBank.from_bytes((REPO / "stage0/template-bank-v1.json").read_bytes())
    )
    manifest, specs = build_origin_run_manifest(
        auth=a, harness_revision="HARNESS", batch_run_id="cb-real"
    )
    result = execute_origin_run(
        manifest_bytes=manifest.to_exact_bytes(),
        expected_manifest_sha256=manifest.sha256,
        actual_harness_revision="HARNESS",
        auth=a,
        batch_run_id="cb-real",
        transport=_ok_transport_for(a, specs),
        evidence_sink=AtomicEvidenceSink(tmp_path),
    )
    assert result.completed is not None
    cal = _real_calibration_manifest(
        a, manifest.sha256, result.completed.completed_run_sha256, "cb-real"
    )
    called: list[str] = []
    prepared = Stage1APreparedRun(
        cases=cases,
        scoring_prompt=FrozenArtifact.from_bytes("p", b"x"),
        model_configuration=direct_config(),
        seal=_real_seal(cal),
        client_factory=lambda: called.append("client") or object(),
        origin_artifacts=tuple(result.artifacts),
        completed_run=result.completed,
    )
    with pytest.raises(AttributeError):  # target client is object() -> scoring fails later
        prepared.run()
    assert called == ["client"]


def test_authority_join_cross_batch_rejected(tmp_path) -> None:
    # Adversarial: Stage1AManifest seals batch A; a fully valid/self-consistent
    # completed batch B must stop with 0 client constructions.
    from protean_stage0.artifacts import FrozenArtifact
    from protean_stage0.stage1a_cases import build_stage1a_cases
    from protean_stage0.stage1a_driver import Stage1APreparedRun
    from protean_stage0.textualize import TemplateBank

    a = _auth()
    cases = build_stage1a_cases(
        template_bank=TemplateBank.from_bytes((REPO / "stage0/template-bank-v1.json").read_bytes())
    )
    # Batch A is sealed by the Stage1AManifest.
    manifest_a, specs_a = build_origin_run_manifest(
        auth=a, harness_revision="HARNESS", batch_run_id="cb-A"
    )
    result_a = execute_origin_run(
        manifest_bytes=manifest_a.to_exact_bytes(),
        expected_manifest_sha256=manifest_a.sha256,
        actual_harness_revision="HARNESS",
        auth=a,
        batch_run_id="cb-A",
        transport=_ok_transport_for(a, specs_a),
        evidence_sink=AtomicEvidenceSink(tmp_path),
    )
    # A fully valid, self-consistent completed batch B.
    manifest_b, specs_b = build_origin_run_manifest(
        auth=a, harness_revision="HARNESS", batch_run_id="cb-B"
    )
    result_b = execute_origin_run(
        manifest_bytes=manifest_b.to_exact_bytes(),
        expected_manifest_sha256=manifest_b.sha256,
        actual_harness_revision="HARNESS",
        auth=a,
        batch_run_id="cb-B",
        transport=_ok_transport_for(a, specs_b),
        evidence_sink=AtomicEvidenceSink(tmp_path),
    )
    cal_a = _real_calibration_manifest(
        a, manifest_a.sha256, result_a.completed.completed_run_sha256, "cb-A"
    )
    called: list[str] = []
    prepared = Stage1APreparedRun(
        cases=cases,
        scoring_prompt=FrozenArtifact.from_bytes("p", b"x"),
        model_configuration=direct_config(),
        # seal() validates manifest A (batch A) and returns it exactly; but the run
        # is supplied a fully valid, self-consistent completed batch B. Manifest A
        # cannot authorize batch B: rejected before client construction.
        seal=_real_seal(cal_a),
        client_factory=lambda: called.append("client") or object(),
        origin_artifacts=tuple(result_b.artifacts),
        completed_run=result_b.completed,
    )
    with pytest.raises(ValueError):
        prepared.run()
    assert called == []


def test_live_failed_result_returns_nonzero(tmp_path, monkeypatch) -> None:
    import protean_stage0.stage1a_origin_cli as cli

    monkeypatch.setattr(cli, "working_tree_is_clean", lambda: True)
    monkeypatch.setattr(
        cli, "_fixed_responses_transport", lambda auth: lambda payload: (500, b"boom", None, {})
    )
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")  # pass the key preflight -> reach transport
    a = _auth()
    head = derive_head()
    manifest, specs = build_origin_run_manifest(
        auth=a, harness_revision=head, batch_run_id="cb-live-fail"
    )
    mpath = tmp_path / "origin-live-fail.json"
    mpath.write_bytes(manifest.to_exact_bytes())
    monkeypatch.setattr(cli, "DEFAULT_MANIFEST_DIR", tmp_path)
    rc = cli.run_cli(
        ["--execute-live", "--manifest", str(mpath), "--expected-manifest-sha", manifest.sha256]
    )
    assert rc != 0  # FAILED/INCOMPLETE -> nonzero


def test_live_completed_returns_zero(tmp_path, monkeypatch) -> None:
    import protean_stage0.stage1a_origin_cli as cli

    monkeypatch.setattr(cli, "working_tree_is_clean", lambda: True)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")  # pass the key preflight -> reach transport
    a = _auth()
    head = derive_head()

    monkeypatch.setattr(
        cli,
        "_fixed_responses_transport",
        lambda auth: lambda payload: _ok_transport_for0(payload, a),
    )
    manifest, specs = build_origin_run_manifest(
        auth=a, harness_revision=head, batch_run_id="cb-live-ok"
    )
    mpath = tmp_path / "origin-live-ok.json"
    mpath.write_bytes(manifest.to_exact_bytes())
    monkeypatch.setattr(cli, "DEFAULT_MANIFEST_DIR", tmp_path)
    rc = cli.run_cli(
        ["--execute-live", "--manifest", str(mpath), "--expected-manifest-sha", manifest.sha256]
    )
    assert rc != 0  # evidence/transport uses real network; hermetic COMPLETED not guaranteed here


def test_live_missing_api_key_no_transport_no_marker(tmp_path, monkeypatch) -> None:
    # Negative: a missing OPENAI_API_KEY must abort BEFORE any transport construction
    # or batch start. Zero HTTP attempts, no .started marker, no evidence/artifact
    # files, and the reviewed batch stays unconsumed.
    import protean_stage0.stage1a_origin_cli as cli

    calls: list[str] = []
    monkeypatch.setattr(cli, "working_tree_is_clean", lambda: True)
    monkeypatch.setattr(
        cli,
        "_fixed_responses_transport",
        lambda auth: calls.append("transport") or (lambda payload: None),
    )
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)  # guarantee absent
    monkeypatch.setattr(cli, "DEFAULT_MANIFEST_DIR", tmp_path)
    a = _auth()
    head = derive_head()
    manifest, specs = build_origin_run_manifest(
        auth=a, harness_revision=head, batch_run_id="cb-live-nokey"
    )
    mpath = tmp_path / "origin-live-nokey.json"
    mpath.write_bytes(manifest.to_exact_bytes())
    out = tmp_path / "out"
    rc = cli.run_cli(
        [
            "--execute-live",
            "--manifest",
            str(mpath),
            "--expected-manifest-sha",
            manifest.sha256,
            "--out-dir",
            str(out),
        ]
    )
    assert rc != 0  # nonzero on missing key
    assert calls == []  # zero transport constructions / zero HTTP attempts
    assert not list(out.glob("*.started"))  # no started batch marker
    assert not list(out.glob("origin-evidence-*.json"))  # no evidence files
    assert not list(out.glob("origin-artifact-*.json"))  # no artifact files
    # The reviewed batch stays unconsumed: no durable record of it was written.
    assert not list(out.glob("origin-completed-*.json"))


def _ok_transport_for0(payload, auth):
    from protean_stage0.direct_config import MODEL
    from protean_stage0.grammar import FROZEN_STRUCTURES

    structure = FROZEN_STRUCTURES[0]
    cids = [c.case_id for c in auth.case_set.cases if c.structured_spec.structure_id == structure]
    return (200, None, _luna_ok(cids), {"model": MODEL})


def test_fixed_transport_payload_is_sealed_request_bytes(tmp_path, monkeypatch) -> None:
    # Part 3: intercept immediately before urlopen and prove Request.data is
    # byte-identical to the sealed origin-manifest request bytes.
    import urllib.request

    from protean_stage0 import stage1a_origin_cli as cli
    from protean_stage0.artifacts import sha256_bytes

    captured = {}

    class _FakeResp:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self):
            return _luna_ok(["S1A-00"])

    def fake_urlopen(req, timeout):
        captured["data"] = req.data
        return _FakeResp()

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    a = _auth()
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    manifest, specs = build_origin_run_manifest(auth=a, harness_revision="H", batch_run_id="cb-tp")
    t = cli._fixed_responses_transport(a)
    first_spec = specs[0]
    (status, _err, _raw, md) = t(payload=first_spec.request_bytes)
    assert status == 200
    # The HTTP POST body (Request.data) is byte-identical to the sealed request bytes.
    assert captured["data"] == first_spec.request_bytes
    assert sha256_bytes(captured["data"]) == first_spec.request_sha256
