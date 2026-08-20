"""Zero-call tests for the sealed Stage-0 run driver.

Loads the REAL frozen artifacts (immutable repo bytes) and exercises the PREPARE
path only. NO live OpenAI request is possible or made. Live (--execute-live)
sealing is tested with patched dirty-tree / HEAD mismatch so the transport is
never reached.
"""

from __future__ import annotations

import hashlib
import os
from typing import Any

import pytest

from protean_stage0 import stage0_driver as drv
from protean_stage0.direct_config import DIRECT_CONFIG_HASH, direct_model_configuration
from protean_stage0.results import ParseStatus, RawResult, freeze_raw_results
from protean_stage0.validation import validate_pre_run


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
    assert direct_model_configuration().sha256 == DIRECT_CONFIG_HASH


def test_real_artifact_preflight_passes(monkeypatch: pytest.MonkeyPatch) -> None:
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


def test_dirty_working_tree_blocks_live_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(drv, "working_tree_is_clean", lambda: False)
    monkeypatch.setattr(drv, "current_git_head", lambda: "0f89c9ccd9d694699284be3c400a11654e2a9a96")
    with pytest.raises(Exception) as exc:
        drv.run_cli(["--execute-live", "--out-dir", "/tmp/live-block"])
    assert "dirty" in str(exc.value)


def test_head_mismatch_blocks_live_mode() -> None:
    prepared = drv.build_run_manifest(harness_revision=drv.current_git_head())
    other = prepared.manifest.harness_revision + "0"
    with pytest.raises(RuntimeError, match="HEAD != manifest"):
        drv.seal_checks(prepared, head=other, clean=True)


def test_default_invocation_cannot_make_live_call(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[int] = []

    class Boom:
        def __init__(self, *a: Any, **k: Any) -> None:
            calls.append(1)
            raise AssertionError("live client must not be constructed in default mode")

    monkeypatch.setattr(drv, "DirectResponsesClient", Boom)
    rc = drv.run_cli(["--out-dir", "/tmp/prep-default"])
    assert rc == 0
    assert calls == []


def test_prepare_performs_zero_calls(monkeypatch: pytest.MonkeyPatch) -> None:
    os.environ["OPENAI_API_KEY"] = "sk-test-do-not-use"
    calls: list[int] = []

    class Boom:
        def __init__(self, *a: Any, **k: Any) -> None:
            calls.append(1)
            raise AssertionError("prepare must not construct a live client")

    monkeypatch.setattr(drv, "DirectResponsesClient", Boom)
    try:
        rc = drv.run_cli(["--prepare", "--out-dir", "/tmp/prep-zero"])
    finally:
        del os.environ["OPENAI_API_KEY"]
    assert rc == 0
    assert calls == []


def test_live_mode_requires_explicit_execute_live(monkeypatch: pytest.MonkeyPatch) -> None:
    os.environ.pop("OPENAI_API_KEY", None)
    constructed: list[int] = []

    class FakeBoom:
        def __init__(self, *a: Any, **k: Any) -> None:
            constructed.append(1)
            raise AssertionError("live transport must not be constructed without a key")

    monkeypatch.setattr(drv, "DirectResponsesClient", FakeBoom)
    monkeypatch.setattr(drv, "working_tree_is_clean", lambda: True)
    with pytest.raises(Exception, match="OPENAI_API_KEY"):
        drv.run_cli(["--execute-live", "--out-dir", "/tmp/live-key"])
    assert constructed == []


def test_manifest_records_exact_harness_revision() -> None:
    head = drv.current_git_head()
    prepared = drv.build_run_manifest(harness_revision=head)
    assert prepared.manifest.harness_revision == head


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
