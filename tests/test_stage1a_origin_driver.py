"""Hermetic tests for the Stage-1A live-origin driver (no provider calls)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from protean_stage0.artifacts import sha256_bytes
from protean_stage0.direct_config import (
    MODEL,
    REASONING_CONTEXT,
    REASONING_EFFORT,
)
from protean_stage0.grammar import FROZEN_STRUCTURES
from protean_stage0.stage1a_authority import (
    EXPECTED_PROTOCOL_SHA,
    EXPECTED_REAL_ORIGIN_AMENDMENT_SHA,
    load_authority_artifacts,
)
from protean_stage0.stage1a_origin_driver import (
    OriginFailureCategory,
    OriginRunStatus,
    OriginRunUnresolved,
    execute_origin_run,
    plan_origin_run,
)

REPO = Path(__file__).resolve().parents[1]


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


def _authority() -> Any:
    return load_authority_artifacts(verify_expected=True)


def _ok_transport_per_structure(auth: Any) -> tuple[Any, dict[str, int]]:
    """Returns a callable transport that maps each structure's request to a valid
    Luna response adopting that structure's 12 case IDs."""
    specs: dict[str, list[str]] = {}
    for case in auth.case_set.cases:
        specs.setdefault(case.structured_spec.structure_id.value, []).append(case.case_id)
    attempts = {"n": 0}

    def transport(
        *, payload: bytes
    ) -> tuple[int | None, bytes | None, bytes | None, dict[Any, Any]]:
        attempts["n"] += 1
        seed = attempts["n"]
        structure = FROZEN_STRUCTURES[seed - 1].value
        return (200, None, _luna_ok(specs[structure]), {"model": MODEL, "status": "completed"})

    return transport, attempts


def _base_plan(auth: Any, batch: str = "batch-1") -> Any:
    return plan_origin_run(
        loaded_case_set=auth.case_set,
        harness_revision="HARNESS-REV",
        batch_run_id=batch,
    )


# ---- B3 authority loading ----
def test_authority_files_loaded_from_disk() -> None:
    auth = _authority()
    assert auth.protocol.sha256 == EXPECTED_PROTOCOL_SHA
    assert auth.real_origin_amendment.sha256 == EXPECTED_REAL_ORIGIN_AMENDMENT_SHA
    assert (
        auth.case_set_sha256 == "6851bf6f49f080ca3ede7938e207b835e5b3ac7cf531e3a460fb74393adecf41"
    )


def test_mutated_ratified_amendment_stops(monkeypatch: pytest.MonkeyPatch) -> None:
    from protean_stage0 import stage1a_authority as auth_mod

    monkeypatch.setattr(
        auth_mod,
        "REAL_ORIGIN_AMENDMENT_PATH",
        REPO / "docs/PROPOSED-AMENDMENT-stage1a-real-origin-v1.0.2-r1.md",  # DRAFT
    )
    # DRAFT substitute must fail the frozen-SHA guard before provider.
    with pytest.raises(ValueError, match="real-origin amendment"):
        auth_mod.load_authority_artifacts(verify_expected=True)


def test_mutated_protocol_stops(monkeypatch: pytest.MonkeyPatch) -> None:
    import tempfile

    from protean_stage0 import stage1a_authority as auth_mod

    # Mutate the protocol file by loading current bytes and flipping a byte.
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "PROTOCOL.md"
        original = (REPO / "docs/PROTOCOL-prospective-control-v1.0.md").read_bytes()
        p.write_bytes(original[:-1] + bytes([original[-1] ^ 0x01]))
        monkeypatch.setattr(auth_mod, "PROTOCOL_PATH", p)
        with pytest.raises(ValueError, match="protocol"):
            auth_mod.load_authority_artifacts(verify_expected=True)


# ---- prepared vs execute ----
def test_plan_recomputes_five_request_shas() -> None:
    auth = _authority()
    plan = _base_plan(auth)
    assert len(plan.request_specs) == 5
    assert plan.manifest.expected_requests == 5
    for structure, ids, req_bytes, req_sha in plan.request_specs:
        assert ids == tuple(
            c.case_id
            for c in auth.case_set.cases
            if c.structured_spec.structure_id.value == structure
        )
        assert req_sha == sha256_bytes(req_bytes)


def test_wrong_expected_manifest_sha_stops() -> None:
    auth = _authority()
    plan = _base_plan(auth)
    t, _ = _ok_transport_per_structure(auth)
    with pytest.raises(ValueError, match="manifest SHA"):
        execute_origin_run(plan=plan, transport=t, verify_manifest_sha256="0" * 64)


def test_five_requests_success_gives_completed_authority() -> None:
    auth = _authority()
    plan = _base_plan(auth)
    t, attempts = _ok_transport_per_structure(auth)
    result = execute_origin_run(plan=plan, transport=t, verify_manifest_sha256=plan.manifest_sha256)
    assert result.status is OriginRunStatus.COMPLETED
    assert attempts["n"] == 5  # exactly one transport call per request
    assert result.completed is not None
    assert result.completed.successes == 5
    assert result.completed.attempts == 5
    assert result.completed.failures == 0
    assert result.completed.batch_run_id == plan.manifest.batch_run_id
    assert result.completed.manifest_sha256 == plan.manifest_sha256


def test_failure_at_request_3_yields_exactly_3_attempts() -> None:
    auth = _authority()
    plan = _base_plan(auth)
    specs: dict[str, list[str]] = {}
    for case in auth.case_set.cases:
        specs.setdefault(case.structured_spec.structure_id.value, []).append(case.case_id)
    calls: dict[str, int] = {"n": 0}

    def transport(
        *, payload: bytes
    ) -> tuple[int | None, bytes | None, bytes | None, dict[Any, Any]]:
        calls["n"] += 1
        idx = calls["n"]
        structure = FROZEN_STRUCTURES[idx - 1].value
        if idx == 3:  # HTTP 500 on the third request -> fail here
            return (500, b'{"error":"boom"}', None, {})
        return (200, None, _luna_ok(specs[structure]), {})

    result = execute_origin_run(
        plan=plan, transport=transport, verify_manifest_sha256=plan.manifest_sha256
    )
    assert calls["n"] == 3  # no request 4 after failure at 3
    assert result.status is OriginRunStatus.FAILED
    assert result.completed is None  # partial batch cannot unlock calibration
    assert len(result.evidence) == 3
    assert result.evidence[2].failure_category is OriginFailureCategory.HTTP


def test_failure_categories_distinct() -> None:
    auth = _authority()
    specs: dict[str, list[str]] = {}
    for case in auth.case_set.cases:
        specs.setdefault(case.structured_spec.structure_id.value, []).append(case.case_id)
    cases: list[tuple[str, Any]] = [
        ("transport", lambda: (None, None, None, {})),
        ("http", lambda: (503, b"err", None, {})),
        ("responses", lambda: (200, None, b"{bad json", {})),
    ]
    for name, fn in cases:
        plan = _base_plan(auth, batch=f"batch-{name}")
        calls: dict[str, int] = {"n": 0}

        def transport(
            *, payload: bytes, calls: dict[str, int] = calls, fn: Any = fn
        ) -> tuple[int | None, bytes | None, bytes | None, dict[Any, Any]]:
            calls["n"] += 1
            idx = calls["n"]
            if idx == 1:
                return fn()  # type: ignore[no-any-return]
            structure = FROZEN_STRUCTURES[idx - 1].value
            return (200, None, _luna_ok(specs[structure]), {})

        result = execute_origin_run(
            plan=plan, transport=transport, verify_manifest_sha256=plan.manifest_sha256
        )
        assert result.status is OriginRunStatus.FAILED
        cat = result.evidence[0].failure_category
        if name == "transport":
            assert cat is OriginFailureCategory.TRANSPORT
        elif name == "http":
            assert cat is OriginFailureCategory.HTTP
        elif name == "responses":
            assert cat is OriginFailureCategory.RESPONSES_CONTRACT


def test_raw_error_evidence_preserved() -> None:
    auth = _authority()
    plan = _base_plan(auth, batch="batch-evidence")
    specs: dict[str, list[str]] = {}
    for case in auth.case_set.cases:
        specs.setdefault(case.structured_spec.structure_id.value, []).append(case.case_id)
    calls: dict[str, int] = {"n": 0}

    def transport(
        *, payload: bytes
    ) -> tuple[int | None, bytes | None, bytes | None, dict[Any, Any]]:
        calls["n"] += 1
        idx = calls["n"]
        if idx == 1:
            return (429, b"raw error body", None, {"http": True})
        structure = FROZEN_STRUCTURES[idx - 1].value
        return (200, None, _luna_ok(specs[structure]), {})

    result = execute_origin_run(
        plan=plan, transport=transport, verify_manifest_sha256=plan.manifest_sha256
    )
    ev = result.evidence[0]
    assert ev.http_status == 429
    assert ev.raw_error_body == b"raw error body"
    assert result.status is OriginRunStatus.FAILED


def test_unexpected_exception_propagates_as_mechanical() -> None:
    auth = _authority()
    plan = _base_plan(auth)

    def transport(
        *, payload: bytes
    ) -> tuple[int | None, bytes | None, bytes | None, dict[Any, Any]]:
        raise RuntimeError("boom")

    with pytest.raises(OriginRunUnresolved):
        execute_origin_run(
            plan=plan, transport=transport, verify_manifest_sha256=plan.manifest_sha256
        )


def test_zero_retries_no_resume() -> None:
    auth = _authority()
    plan = _base_plan(auth)
    calls: dict[str, int] = {"n": 0}
    specs: dict[str, list[str]] = {}
    for case in auth.case_set.cases:
        specs.setdefault(case.structured_spec.structure_id.value, []).append(case.case_id)

    def transport(
        *, payload: bytes
    ) -> tuple[int | None, bytes | None, bytes | None, dict[Any, Any]]:
        calls["n"] += 1
        idx = calls["n"]
        if idx == 2:
            return (500, b"x", None, {})  # fail at index 2 -> no retry, no index 3
        structure = FROZEN_STRUCTURES[idx - 1].value
        return (200, None, _luna_ok(specs[structure]), {})

    result = execute_origin_run(
        plan=plan, transport=transport, verify_manifest_sha256=plan.manifest_sha256
    )
    assert calls["n"] == 2  # zero retry: exactly 2 calls, no re-issue of #2, no #3
    assert result.status is OriginRunStatus.FAILED


def test_partial_batch_cannot_unlock() -> None:
    auth = _authority()
    plan = _base_plan(auth)
    specs: dict[str, list[str]] = {}
    for case in auth.case_set.cases:
        specs.setdefault(case.structured_spec.structure_id.value, []).append(case.case_id)
    calls: dict[str, int] = {"n": 0}

    def transport(
        *, payload: bytes
    ) -> tuple[int | None, bytes | None, bytes | None, dict[Any, Any]]:
        calls["n"] += 1
        idx = calls["n"]
        if idx == 3:
            return (None, None, None, {})  # transport failure at 3
        structure = FROZEN_STRUCTURES[idx - 1].value
        return (200, None, _luna_ok(specs[structure]), {})

    result = execute_origin_run(
        plan=plan, transport=transport, verify_manifest_sha256=plan.manifest_sha256
    )
    assert result.completed is None
    assert result.status is OriginRunStatus.FAILED


def test_plan_request_bytes_have_no_leakage() -> None:
    auth = _authority()
    plan = _base_plan(auth)
    for _structure, _ids, req_bytes, _sha in plan.request_specs:
        assert b"truth_label" not in req_bytes
        assert b"observed_event" not in req_bytes
        assert b"selected_threshold" not in req_bytes


def test_manifest_is_zero_retry_and_expected_5() -> None:
    auth = _authority()
    plan = _base_plan(auth)
    assert plan.manifest.zero_retries is True
    assert plan.manifest.expected_requests == 5
    assert plan.manifest.batch_run_id
