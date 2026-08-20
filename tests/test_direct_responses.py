"""Tests for the direct OpenAI Responses API Stage-0 adapter (Luna xHigh).

Uses a fake transport returning synthetic protocol-faithful Responses payloads —
NO live OpenAI model call.
"""

from __future__ import annotations

import json
import os
from collections.abc import Mapping
from typing import Any

import pytest

from protean_stage0.direct_responses import (
    MAX_OUTPUT_TOKENS,
    MODEL,
    REASONING_CONTEXT,
    REASONING_EFFORT,
    RESPONSES_ENDPOINT,
    DirectResponsesClient,
    ResponsesProviderFailure,
    TransportResult,
    build_request_body,
    parse_scoring_response,
    request_config_hash,
)
from protean_stage0.harness import ModelRequest, ModelResponse


def msg(text: str) -> dict[str, Any]:
    return {
        "type": "message",
        "role": "assistant",
        "content": [{"type": "output_text", "text": text}],
    }


def valid_response(text: str = "0.73") -> dict[str, Any]:
    return {
        "id": "resp_abc",
        "object": "response",
        "created_at": 1700000000,
        "status": "completed",
        "model": MODEL,
        "output": [
            {"type": "reasoning", "summary": []},
            msg(text),
        ],
        "usage": {
            "input_tokens": 60,
            "output_tokens": 120,
            "output_tokens_details": {"reasoning_tokens": 90},
            "total_tokens": 180,
        },
    }


class FakeTransport:
    def __init__(self, result: TransportResult, calls: list[dict[str, Any]] | None = None) -> None:
        self.result = result
        self.calls = calls if calls is not None else []
        self.attempts = 0

    def __call__(
        self,
        *,
        body: Mapping[str, Any],
        api_key: str,
        timeout_seconds: int,
    ) -> TransportResult:
        self.attempts += 1
        self.calls.append({"body": dict(body), "api_key": api_key, "timeout": timeout_seconds})
        return self.result


def make_client(transport: Any) -> DirectResponsesClient:
    return DirectResponsesClient(
        api_key_env="TEST_RESPONSES_KEY", timeout_seconds=30, transport=transport
    )


def make_request() -> ModelRequest:
    return ModelRequest(
        scoring_prompt=b"COMMITMENT:{commitment}",
        model_visible_payload={"commitment": "the dock sensor is satisfied"},
        model_configuration="unused",  # type: ignore[arg-type]
        case_id="S0-000",
    )


def test_valid_completed_response_accepted(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TEST_RESPONSES_KEY", "sk-xyz")
    t = FakeTransport(TransportResult(200, json.dumps(valid_response()).encode()))
    client = make_client(t)
    resp = client.make_single_decision(make_request())
    assert isinstance(resp, ModelResponse)
    assert resp.raw_response == b"0.73"
    assert t.attempts == 1  # exactly one request
    md = resp.provider_metadata
    assert md["response_id"] == "resp_abc"
    assert md["returned_model"] == MODEL
    assert md["reasoning_tokens"] == 90


def test_single_httphit_no_retry_attempts() -> None:
    # transport records attempts; valid response => exactly 1
    t = FakeTransport(TransportResult(200, json.dumps(valid_response()).encode()))
    client = make_client(t)
    os.environ["TEST_RESPONSES_KEY"] = "k"
    try:
        client.make_single_decision(make_request())
    finally:
        del os.environ["TEST_RESPONSES_KEY"]
    assert t.attempts == 1


def test_missing_api_key_stops() -> None:
    t = FakeTransport(TransportResult(200, json.dumps(valid_response()).encode()))
    client = make_client(t)
    os.environ.pop("TEST_RESPONSES_KEY", None)
    with pytest.raises(ResponsesProviderFailure, match="missing"):
        client.make_single_decision(make_request())


def test_malformed_decimal_stops() -> None:
    os.environ["TEST_RESPONSES_KEY"] = "k"
    resp = valid_response(text="seventy-three")
    t = FakeTransport(TransportResult(200, json.dumps(resp).encode()))
    try:
        with pytest.raises(ResponsesProviderFailure, match="PLAIN_DECIMAL_V1"):
            make_client(t).make_single_decision(make_request())
    finally:
        del os.environ["TEST_RESPONSES_KEY"]


def test_multiple_output_messages_stops() -> None:
    resp = valid_response()
    resp["output"] = [msg("0.73"), msg("0.74")]
    with pytest.raises(ResponsesProviderFailure, match="exactly one message"):
        parse_scoring_response(json.dumps(resp).encode())


def test_tool_call_output_stops() -> None:
    resp = valid_response()
    resp["output"] = [{"type": "function_call", "call_id": "c", "name": "f"}]
    with pytest.raises(ResponsesProviderFailure, match="forbidden output item"):
        parse_scoring_response(json.dumps(resp).encode())


def test_incomplete_failed_status_stops() -> None:
    resp = valid_response()
    resp["status"] = "failed"
    with pytest.raises(ResponsesProviderFailure, match="not completed"):
        parse_scoring_response(json.dumps(resp).encode())
    resp2 = valid_response()
    resp2["status"] = "incomplete"
    with pytest.raises(ResponsesProviderFailure, match="not completed"):
        parse_scoring_response(json.dumps(resp2).encode())


def test_wrong_returned_model_detected() -> None:
    # returned model != requested -> not a contract violation per se, but must be observable
    resp = valid_response()
    resp["model"] = "gpt-5.6-sol"
    parsed = parse_scoring_response(json.dumps(resp).encode())
    assert parsed.model_returned == "gpt-5.6-sol"
    assert parsed.model_returned != MODEL


def test_missing_response_id_stops() -> None:
    resp = valid_response()
    del resp["id"]
    with pytest.raises(ResponsesProviderFailure, match="response id"):
        parse_scoring_response(json.dumps(resp).encode())


def test_missing_usage_recorded_as_none() -> None:
    resp = valid_response()
    del resp["usage"]
    parsed = parse_scoring_response(json.dumps(resp).encode())
    assert parsed.usage is None


def test_http_failure_stops_no_retry() -> None:
    os.environ["TEST_RESPONSES_KEY"] = "k"
    t = FakeTransport(TransportResult(429, b"{}"))
    try:
        with pytest.raises(ResponsesProviderFailure, match="HTTP 429"):
            make_client(t).make_single_decision(make_request())
    finally:
        del os.environ["TEST_RESPONSES_KEY"]
    assert t.attempts == 1


def test_timeout_transport_raises_stop() -> None:
    def boom(*, body: Mapping[str, Any], api_key: str, timeout_seconds: int) -> Any:
        raise ResponsesProviderFailure("transport error (no retry)")

    os.environ["TEST_RESPONSES_KEY"] = "k"
    try:
        with pytest.raises(ResponsesProviderFailure, match="transport error"):
            DirectResponsesClient(
                api_key_env="TEST_RESPONSES_KEY", transport=boom
            ).make_single_decision(make_request())
    finally:
        del os.environ["TEST_RESPONSES_KEY"]


def test_build_request_body_exact_frozen_config() -> None:
    body = build_request_body("score this")
    assert body["model"] == MODEL
    assert body["reasoning"]["effort"] == REASONING_EFFORT
    assert body["reasoning"]["context"] == REASONING_CONTEXT
    assert "mode" not in body["reasoning"]  # standard mode (never pro)
    assert body["max_output_tokens"] == MAX_OUTPUT_TOKENS
    assert body["store"] is False
    assert "tools" not in body
    assert "previous_response_id" not in body
    assert "conversation" not in body
    assert "background" not in body
    assert "stream" not in body


def test_request_config_hash_stable_and_endpoint() -> None:
    h = request_config_hash()
    assert len(h) == 64
    assert RESPONSES_ENDPOINT == "https://api.openai.com/v1/responses"
    assert request_config_hash() == h


def test_zero_retry_by_construction() -> None:
    # The transport performs exactly one HTTP POST: no retry loop exists. Prove it
    # by a transport that always fails; the adapter must NOT retry (attempts==1).
    os.environ["TEST_RESPONSES_KEY"] = "k"
    t = FakeTransport(TransportResult(500, b""))
    try:
        with pytest.raises(ResponsesProviderFailure):
            make_client(t).make_single_decision(make_request())
    finally:
        del os.environ["TEST_RESPONSES_KEY"]
    assert t.attempts == 1


def test_request_bodies_are_frozen_identical() -> None:
    t = FakeTransport(TransportResult(200, json.dumps(valid_response()).encode()))
    client = make_client(t)
    os.environ["TEST_RESPONSES_KEY"] = "k"
    try:
        client.make_single_decision(make_request())
    finally:
        del os.environ["TEST_RESPONSES_KEY"]
    body = t.calls[0]["body"]
    assert body == {
        "model": MODEL,
        "input": "COMMITMENT:the dock sensor is satisfied",
        "reasoning": {"effort": REASONING_EFFORT, "context": REASONING_CONTEXT},
        "max_output_tokens": MAX_OUTPUT_TOKENS,
        "store": False,
    }
