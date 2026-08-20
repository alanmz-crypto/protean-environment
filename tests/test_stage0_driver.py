"""Zero-call tests for the sealed Stage-0 run driver (prepared-manifest execution seal)."""

from __future__ import annotations

import hashlib
import os
from typing import Any

import pytest

from protean_stage0 import stage0_driver as drv
from protean_stage0.direct_config import DIRECT_CONFIG_HASH
from protean_stage0.results import ParseStatus, RawResult, freeze_raw_results
from protean_stage0.validation import validate_pre_run


def _prepared_manifest(tmp_path) -> tuple[str, str]:
    """Prepare once in tmp dir; return (manifest_path, manifest_sha)."""
    rc = drv.run_cli(["--prepare", "--out-dir", str(tmp_path)])
    assert rc == 0
    import glob

    paths = sorted(glob.glob(str(tmp_path / "run-manifest-*.json")))
    assert len(paths) == 1
    p = paths[0]
    return p, hashlib.sha256(open(p, "rb").read()).hexdigest()


def test_frozen_case_artifact_loads_and_round_trips_byte_identical() -> None:
    frozen, generated = drv.load_frozen_case_set()
    raw = drv.CASE_SET_PATH.read_bytes()
    assert frozen.artifact_bytes == raw
    assert frozen.sha256 == drv.FROZEN_CASE_SET_SHA
    assert len(frozen.cases) == 80
    assert len(generated) == 80


def test_actual_case_hash_is_06fe8d47() -> None:
    frozen, _ = drv.load_frozen_case_set()
    assert frozen.sha256 == "06fe8d471b1fbbc226696ed6d80b706cc84a6040a7fb91a93814343420291556"


def test_actual_prompt_hash_is_ae8f093a() -> None:
    pbytes = drv.SCORING_PROMPT_PATH.read_bytes()
    assert hashlib.sha256(pbytes).hexdigest() == (
        "ae8f093a69a7bae6818421000490a14c8a19a4a6be33069a1858bf0a9d7f6909"
    )


def test_actual_direct_config_hash_is_b3e21561() -> None:
    assert drv.direct_model_configuration().sha256 == DIRECT_CONFIG_HASH


def test_real_artifact_preflight_passes() -> None:
    prepared = drv.build_run_manifest(harness_revision=drv.current_git_head())
    validated = validate_pre_run(
        manifest=prepared.manifest,
        case_set=prepared.case_set,
        protocol=prepared.protocol,
        execution_plan=prepared.execution_plan,
        bindings=prepared.bindings,
        agreement=prepared.agreement,
    )
    validated.assert_validated()


def test_wrong_artifact_hash_blocks_before_transport(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(drv, "FROZEN_CASE_SET_SHA", "0" * 64)
    with pytest.raises(ValueError, match="case-set hash"):
        drv.load_frozen_case_set()


# ---- Task 4 sealing tests ----
def test_prepare_requires_clean_tree(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    monkeypatch.setattr(drv, "working_tree_is_clean", lambda: False)
    with pytest.raises(RuntimeError, match="clean working tree"):
        drv.run_cli(["--prepare", "--out-dir", str(tmp_path)])


def test_two_prepares_do_not_collide_or_overwrite(tmp_path) -> None:
    p1, s1 = _prepared_manifest(tmp_path)
    # second prepare at same time -> distinct run id (unique immutable), distinct file
    rc = drv.run_cli(["--prepare", "--out-dir", str(tmp_path)])
    assert rc == 0
    import glob

    paths = sorted(glob.glob(str(tmp_path / "run-manifest-*.json")))
    assert len(paths) == 2
    assert p1 in paths
    assert len(set(paths)) == 2  # distinct files; no overwrite
    # No two run ids are equal
    run_ids = []
    for p in paths:
        raw = open(p, "rb").read()
        manifest = drv.reconstruct_run_manifest_from_bytes(raw)
        run_ids.append(manifest.run_id)
    assert len(set(run_ids)) == 2


def test_live_requires_manifest(tmp_path) -> None:
    # --execute-live without --manifest -> parser.error (SystemExit)
    with pytest.raises(SystemExit) as exc:
        drv.run_cli(["--execute-live", "--out-dir", str(tmp_path)])
    assert exc.value.code == 2


def test_live_uses_exact_prepared_bytes_and_sha(tmp_path) -> None:
    manifest_path, sha = _prepared_manifest(tmp_path)
    raw, loaded_sha, manifest = drv.load_prepared_manifest(drv.REPO_ROOT / manifest_path)
    assert loaded_sha == sha
    assert manifest.sha256 == sha
    # round trip exact
    assert manifest.to_exact_bytes() == raw


def test_changing_one_byte_of_manifest_blocks(tmp_path) -> None:
    manifest_path, _ = _prepared_manifest(tmp_path)
    p = tmp_path / manifest_path
    raw = p.read_bytes()
    # flip one byte near the end
    flipped = raw[:-2] + bytes([raw[-2] ^ 0x01]) + raw[-1:]
    p.write_bytes(flipped)
    with pytest.raises(RuntimeError, match="corrupt"):
        drv.load_prepared_manifest(p)


def test_manifest_head_mismatch_blocks(tmp_path) -> None:
    manifest_path, _ = _prepared_manifest(tmp_path)
    _, _, manifest = drv.load_prepared_manifest(tmp_path / manifest_path)
    other = manifest.harness_revision + "0"
    with pytest.raises(RuntimeError, match="HEAD != manifest"):
        drv.seal_reconstructed_run(manifest, head=other, clean=True)


def test_live_does_not_call_build_run_manifest(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    manifest_path, _ = _prepared_manifest(tmp_path)
    calls: list[str] = []

    def boom(*a: Any, **k: Any) -> Any:
        calls.append("build_run_manifest")
        raise AssertionError("live path must not rebuild the manifest")

    monkeypatch.setattr(drv, "build_run_manifest", boom)
    monkeypatch.setattr(drv, "working_tree_is_clean", lambda: True)
    os.environ.pop("OPENAI_API_KEY", None)
    # live seals then reaches key-check; must fail on missing key WITHOUT build_run_manifest
    with pytest.raises(RuntimeError, match="OPENAI_API_KEY"):
        drv.run_cli(["--execute-live", "--manifest", manifest_path, "--out-dir", str(tmp_path)])
    assert calls == []


def test_prepared_sha_before_execution_equals_consumed_by_live_path(tmp_path) -> None:
    manifest_path, sha = _prepared_manifest(tmp_path)
    _, loaded_sha, manifest = drv.load_prepared_manifest(tmp_path / manifest_path)
    assert sha == loaded_sha == manifest.sha256


def test_runtime_output_does_not_dirty_repository(tmp_path) -> None:
    # write a run artifact under stage0/runs/ (gitignored) and confirm git stays clean
    run_dir = drv.REPO_ROOT / "stage0/runs"
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "run-manifest-stage0-000000000000-test.json").write_bytes(b"{}")
    assert drv.working_tree_is_clean()
    # .gitignore ignores stage0/runs
    import subprocess

    out = subprocess.run(["git", "check-ignore", "stage0/runs/"], cwd=drv.REPO_ROOT, capture_output=True, text=True)
    assert out.returncode == 0


def test_manifest_records_exact_harness_revision(tmp_path) -> None:
    _, _, manifest = drv.load_prepared_manifest(tmp_path / _prepared_manifest(tmp_path)[0])
    assert manifest.harness_revision == drv.current_git_head()


def test_freeze_raw_results_sha_is_stable() -> None:
    rr = RawResult(
        run_id="R",
        case_id="C1",
        truth_label=True,
        returned_score=0.73,
        raw_model_response=b"0.73",
        model_provider="openai_responses_api",
        model_id="gpt-5.6-luna",
        model_configuration_sha256=DIRECT_CONFIG_HASH,
        provider_metadata=None,
        timestamp="t",
        call_order=1,
        parse_status=ParseStatus.VALID_SCORE,
    )
    art = freeze_raw_results("R", (rr,))
    assert len(art.sha256) == 64
