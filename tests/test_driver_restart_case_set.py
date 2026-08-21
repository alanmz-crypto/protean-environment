"""Hermetic tests for the driver's --case-set restart binding.

These prove the sealed driver seals and scores the EXACT reconstructed case set
from a supplied artifact, and refuses every mismatch before any provider call.
NO live provider call is made; scoring is never reached.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from protean_stage0 import stage0_driver as drv
from protean_stage0.artifacts import FrozenArtifact, FrozenCaseSet
from protean_stage0.direct_config import direct_model_configuration
from protean_stage0.manifest import ExperimentalBindings, RunManifest
from protean_stage0.parse_contract import PLAIN_DECIMAL_V1_SHA256
from protean_stage0.validation import load_evaluator_provenance

RESTART_CASE_SHA = "7099a821c74397bff188a630ed9ca84c8aeed6185947ef99bda0c7a66ef1a03e"
ORIGINAL_CASE_SHA = "06fe8d471b1fbbc226696ed6d80b706cc84a6040a7fb91a93814343420291556"
RESTART_CASE_ARTIFACT = drv.REPO_ROOT / f"stage0/runs/restart-case-set-{RESTART_CASE_SHA}.json"


def _frozen_docs() -> tuple[FrozenArtifact, FrozenArtifact]:
    protocol = FrozenArtifact.from_bytes(
        "protocol", (drv.REPO_ROOT / "docs/PROTOCOL-prospective-control-v1.0.md").read_bytes()
    )
    plan = FrozenArtifact.from_bytes(
        "execution-plan", (drv.REPO_ROOT / "docs/EXECUTION-stage0.md").read_bytes()
    )
    return protocol, plan


def _manifest_for(
    case_set: FrozenCaseSet,
    generated: tuple[Any, ...],
    *,
    head: str,
    case_set_sha: str,
) -> RunManifest:
    protocol, plan = _frozen_docs()
    prompt = FrozenArtifact.from_bytes("scoring-prompt", drv.SCORING_PROMPT_PATH.read_bytes())
    primary = load_evaluator_provenance(drv.PRIMARY_PROV_PATH, drv.PRIMARY_IMPL_PATH)
    reference = load_evaluator_provenance(drv.REFERENCE_PROV_PATH, drv.REFERENCE_IMPL_PATH)
    binding = ExperimentalBindings(prompt=prompt, model_configuration=direct_model_configuration())
    # case-set must carry the expected hash for the manifest to match
    assert case_set.sha256 == case_set_sha
    return RunManifest.create(
        protocol=protocol,
        execution_plan=plan,
        case_set=case_set,
        bindings=binding,
        parse_contract_sha256=PLAIN_DECIMAL_V1_SHA256,
        primary_evaluator=primary,
        reference_evaluator=reference,
        harness_revision=head,
        timestamp="2026-08-21T00:00:00Z",
        run_id=f"TEST-RESTART-{case_set_sha[:8]}",
    )


@pytest.fixture()
def restart_materials() -> tuple[Any, ...]:
    head = drv.current_git_head()
    assert RESTART_CASE_ARTIFACT.exists(), "restart case-set artifact must exist"
    fresh_set, fresh_generated = drv.load_frozen_case_set(
        RESTART_CASE_ARTIFACT, expected_sha=RESTART_CASE_SHA
    )
    original_set, original_generated = drv.load_frozen_case_set()
    restart_manifest = _manifest_for(
        fresh_set, fresh_generated, head=head, case_set_sha=RESTART_CASE_SHA
    )
    return restart_manifest, fresh_set, fresh_generated, original_set, original_generated


def test_restart_manifest_with_fresh_artifact_seals(restart_materials: tuple[Any, ...]) -> None:
    restart_manifest, fresh_set, fresh_generated, _, _ = restart_materials
    # must NOT raise: the fresh set exactly matches the restart manifest
    drv.seal_reconstructed_run(
        restart_manifest,
        head=restart_manifest.harness_revision,
        clean=True,
        case_set=fresh_set,
        generated=fresh_generated,
    )


def test_restart_manifest_with_original_artifact_refuses(
    restart_materials: tuple[Any, ...],
) -> None:
    restart_manifest, fresh_set, _, original_set, original_generated = restart_materials
    with pytest.raises(RuntimeError, match="case-set hash != manifest"):
        drv.seal_reconstructed_run(
            restart_manifest,
            head=restart_manifest.harness_revision,
            clean=True,
            case_set=original_set,
            generated=original_generated,
        )


def test_original_manifest_with_restart_artifact_refuses(
    restart_materials: tuple[Any, ...],
) -> None:
    _, _, _, original_set, original_generated = restart_materials
    head = drv.current_git_head()
    protocol, plan = _frozen_docs()
    prompt = FrozenArtifact.from_bytes("scoring-prompt", drv.SCORING_PROMPT_PATH.read_bytes())
    primary = load_evaluator_provenance(drv.PRIMARY_PROV_PATH, drv.PRIMARY_IMPL_PATH)
    reference = load_evaluator_provenance(drv.REFERENCE_PROV_PATH, drv.REFERENCE_IMPL_PATH)
    binding = ExperimentalBindings(prompt=prompt, model_configuration=direct_model_configuration())
    # original manifest binds 06fe8d47... but supplied artifact is the restart one.
    fresh_set, fresh_generated = drv.load_frozen_case_set(
        RESTART_CASE_ARTIFACT, expected_sha=RESTART_CASE_SHA
    )
    original_manifest = RunManifest.create(
        protocol=protocol,
        execution_plan=plan,
        case_set=original_set,
        bindings=binding,
        parse_contract_sha256=PLAIN_DECIMAL_V1_SHA256,
        primary_evaluator=primary,
        reference_evaluator=reference,
        harness_revision=head,
        timestamp="2026-08-21T00:00:00Z",
        run_id="TEST-ORIGINAL",
    )
    with pytest.raises(RuntimeError, match="case-set hash != manifest"):
        drv.seal_reconstructed_run(
            original_manifest,
            head=head,
            clean=True,
            case_set=fresh_set,
            generated=fresh_generated,
        )


def test_tampered_case_set_bytes_refuse() -> None:
    import tempfile

    raw = RESTART_CASE_ARTIFACT.read_bytes()
    tampered = raw[:-2] + bytes([raw[-2] ^ 0x01]) + raw[-1:]
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "tampered-case-set.json"
        p.write_bytes(tampered)
        with pytest.raises(ValueError, match="case-set hash does not match"):
            drv.load_frozen_case_set(p, expected_sha=RESTART_CASE_SHA)


def test_same_reconstructed_set_reaches_scoring(
    restart_materials: tuple[Any, ...], monkeypatch: pytest.MonkeyPatch
) -> None:
    # The exact reconstructed set passed to the seal must be the SAME object that
    # reaches scoring; the driver must never validate one set and score another.
    restart_manifest, fresh_set, fresh_generated, _, _ = restart_materials
    seal_seen: dict[str, Any] = {}
    score_seen: dict[str, Any] = {}

    def fake_seal(manifest: Any, *, head: Any, clean: bool, case_set: Any, generated: Any) -> None:
        seal_seen["case_set"] = case_set
        seal_seen["generated"] = generated

    def fake_scoring(manifest: Any, api_key: str, *, case_set: Any, generated: Any) -> Any:
        score_seen["case_set"] = case_set
        score_seen["generated"] = generated
        assert case_set is seal_seen["case_set"]
        assert generated is seal_seen["generated"]
        raise RuntimeError("REACHED_SCORING_SAME_SET")

    monkeypatch.setattr(drv, "seal_reconstructed_run", fake_seal)
    monkeypatch.setattr(drv, "run_prepared_scoring", fake_scoring)
    monkeypatch.setattr(drv, "working_tree_is_clean", lambda: True)
    monkeypatch.setattr(drv, "load_prepared_manifest", lambda p: (b"x", "x", restart_manifest))
    # --execute-live with --case-set pointing at the fresh artifact reaches the
    # (stubbed) scoring with the identical set object.
    with pytest.raises(RuntimeError, match="REACHED_SCORING_SAME_SET"):
        drv.run_cli(
            [
                "--execute-live",
                "--manifest",
                "restart.json",
                "--case-set",
                str(RESTART_CASE_ARTIFACT),
                "--out-dir",
                str(drv.REPO_ROOT / "stage0/runs"),
            ]
        )


def test_wrong_case_set_stops_before_any_client_call(
    restart_materials: tuple[Any, ...], monkeypatch: pytest.MonkeyPatch
) -> None:
    # A restart manifest invoked with the ORIGINAL artifact must refuse before any
    # provider call is constructed.
    restart_manifest, _, _, _, _ = restart_materials
    client_called: list[str] = []

    class Boom:
        def __init__(self) -> None:
            client_called.append("DirectResponsesClient")

    monkeypatch.setattr(drv, "DirectResponsesClient", Boom)
    monkeypatch.setattr(drv, "working_tree_is_clean", lambda: True)
    monkeypatch.setattr(drv, "load_prepared_manifest", lambda p: (b"x", "x", restart_manifest))
    import os
    import tempfile

    with tempfile.NamedTemporaryFile("wb", suffix=".case") as tf:
        tf.write(drv.CASE_SET_PATH.read_bytes())  # the ORIGINAL artifact bytes
        tf.flush()
        os.environ.pop("OPENAI_API_KEY", None)
        with pytest.raises(ValueError, match="case-set hash does not match"):
            drv.run_cli(
                [
                    "--execute-live",
                    "--manifest",
                    "restart.json",
                    "--case-set",
                    tf.name,
                    "--out-dir",
                    str(drv.REPO_ROOT / "stage0/runs"),
                ]
            )
    assert client_called == []
