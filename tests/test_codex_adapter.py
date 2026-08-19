"""Tests for the Codex (gpt-5.6-luna) Stage-0 scoring adapter + assert-and-reject contract.

Uses a fake runner returning synthetic JSONL events — NO live Codex/Luna call.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import pytest

from protean_stage0.codex_adapter import (
    CodexContractViolation,
    CodexModelClient,
    CodexRunResult,
    evaluate_codex_contract,
)
from protean_stage0.codex_config import CODEX_CLI_VERSION
from protean_stage0.harness import ModelRequest, ModelResponse


def evt(name: str, **kw: Any) -> dict[str, Any]:
    return {"type": name, **kw}


def accepted_events(score: str = "0.73") -> tuple[dict[str, Any], ...]:
    return (
        evt("task_started"),
        evt("turn_started"),
        evt("raw_response_completed"),
        evt("agent_message", content=score),
        evt("token_count"),
        evt("turn_complete"),
        evt("task_complete"),
    )


def make_run(
    *,
    events: Sequence[dict[str, Any]] | None = None,
    exit_code: int = 0,
    version: str = CODEX_CLI_VERSION,
    last_message: str | None = None,
) -> CodexRunResult:
    return CodexRunResult(
        exit_code=exit_code,
        version=version,
        model="gpt-5.6-luna",
        reasoning_effort="xhigh",
        raw_events=tuple(events) if events is not None else accepted_events(),
        last_message_file="/tmp/protean-score-empty/last_message.txt",
        last_message_text=last_message,
    )


def make_client(run: CodexRunResult) -> CodexModelClient:
    def fake_runner(**_: Any) -> CodexRunResult:
        return run

    return CodexModelClient(
        forced_prompt_template=b"COMMITMENT:{commitment}",
        model_configuration_sha256="test-cfg-hash",
        runner=fake_runner,
    )


def make_request() -> ModelRequest:
    return ModelRequest(
        scoring_prompt=b"COMMITMENT:{commitment}",
        model_visible_payload={"commitment": "the dock sensor is satisfied"},
        model_configuration="unused",  # type: ignore[arg-type]
        case_id="S0-000",
    )


def test_accepted_single_turn_returns_score() -> None:
    run = make_run(last_message="0.73")
    response = make_client(run).make_single_decision(make_request())
    assert isinstance(response, ModelResponse)
    assert response.raw_response == b"0.73"


def test_contract_accepted_events() -> None:
    v = evaluate_codex_contract(make_run(last_message="0.73"))
    assert v.accepted and v.score == 0.73


@pytest.mark.parametrize(
    "bad",
    [
        "exec_command_begin",
        "apply_patch_begin",
        "mcp_tool_call_begin",
        "web_search",
        "image_generation_begin",
        "view_image_tool_call",
        "collab_agent_spawn_begin",
        "dynamic_tool_call_request",
        "guardian_assessment",
    ],
)
def test_tool_event_causes_stop(bad: str) -> None:
    events = accepted_events() + (evt(bad),)
    v = evaluate_codex_contract(make_run(events=events, last_message="0.73"))
    assert not v.accepted
    assert v.reason is not None and "prohibited" in v.reason


@pytest.mark.parametrize(
    "bad",
    [
        "context_compacted",
        "auto_compact",
        "thread_rolled_back",
        "fork_history",
        "replacement_history",
    ],
)
def test_compaction_fork_marker_causes_stop(bad: str) -> None:
    events = accepted_events() + (evt(bad),)
    v = evaluate_codex_contract(make_run(events=events, last_message="0.73"))
    assert not v.accepted
    assert v.reason is not None


@pytest.mark.parametrize("bad", ["generate_memories", "memory_consolidation", "thread_spawn"])
def test_injection_marker_causes_stop(bad: str) -> None:
    events = accepted_events() + (evt(bad),)
    v = evaluate_codex_contract(make_run(events=events, last_message="0.73"))
    assert not v.accepted
    assert v.reason is not None


def test_extra_turn_causes_stop() -> None:
    events = accepted_events() + (evt("turn_started"), evt("turn_complete"))
    v = evaluate_codex_contract(make_run(events=events, last_message="0.73"))
    assert not v.accepted
    assert v.reason is not None and "exactly one turn" in v.reason


def test_malformed_score_stops() -> None:
    bad = tuple(
        evt("agent_message", content="seventy-three") if e.get("type") == "agent_message" else e
        for e in accepted_events()
    )
    v = evaluate_codex_contract(make_run(events=bad, last_message="seventy-three"))
    assert not v.accepted
    assert v.reason is not None and "not a valid" in v.reason


def test_version_mismatch_stops() -> None:
    v = evaluate_codex_contract(make_run(version="0.148.0", last_message="0.73"))
    assert not v.accepted
    assert v.reason is not None and "version mismatch" in v.reason


def test_nonzero_exit_stops() -> None:
    v = evaluate_codex_contract(make_run(exit_code=1, last_message="0.73"))
    assert not v.accepted
    assert v.reason is not None and "non-zero" in v.reason


def test_final_message_mismatch_stops() -> None:
    v = evaluate_codex_contract(make_run(last_message="0.74"))
    assert not v.accepted
    assert v.reason is not None and "final-message" in v.reason


def test_missing_required_event_stops() -> None:
    events = tuple(e for e in accepted_events() if e.get("type") != "token_count")
    v = evaluate_codex_contract(make_run(events=events, last_message="0.73"))
    assert not v.accepted
    assert v.reason is not None and "token_count" in v.reason


def test_contract_violation_raised_through_client() -> None:
    run = make_run(events=accepted_events() + (evt("exec_command_begin"),), last_message="0.73")
    client = make_client(run)
    with pytest.raises(CodexContractViolation):
        client.make_single_decision(make_request())
