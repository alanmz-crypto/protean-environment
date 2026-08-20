"""Tests for the direct OpenAI Responses API Stage-0 adapter (fail-closed contract).

Uses protocol-faithful fake fixtures — NO live OpenAI model call.
"""

from __future__ import annotations

import base64
import json
import os
from typing import Any

import pytest

from protean_stage0.direct_config import (
    DIRECT_CONFIG_HASH,
    MODEL,
    REASONING_CONTEXT,
    REASONING_EFFORT,
    direct_model_configuration,
)
from protean_stage0.direct_responses import (
    DirectResponsesClient,
    ResponsesProviderFailure,
    TransportResult,
    build_request_body,
    parse_scoring_response,
)
from protean_stage0.harness import ModelRequest, ModelResponse
from protean_stage0.results import ParseStatus, RawResult, freeze_raw_results


def msg(text: str = "0.73") -> dict[str, Any]:
    return {
        "type": "message",
        "role": "assistant",
        "status": "completed",
        "content": [{"type": "output_text", "text": text}],
    }


def reasoning_item() -> dict[str, Any]:
    return {"type": "reasoning", "summary": []}


def valid_response(text: str = "0.73") -> dict[str, Any]:
    return {
        "id": "resp_abc",
        "object": "response",
        "created_at": 1700000000,
        "status": "completed",
        "model": MODEL,
        "reasoning": {"effort": REASONING_EFFORT, "context": REASONING_CONTEXT},
        "output": [reasoning_item(), msg(text)],
        "usage": {
            "input_tokens": 60,
            "output_tokens": 120,
            "output_tokens_details": {"reasoning_tokens": 90},
            "total_tokens": 180,
        },
    }


class FakeTransport:
    def __init__(self, result: TransportResult) -> None:
        self.result = result
        self.attempts = 0
        self.last_payload: bytes | None = None

    def __call__(self, *, payload: bytes, api_key: str, timeout_seconds: int) -> TransportResult:
        self.attempts += 1
        self.last_payload = payload
        return self.result


def make_client(transport: Any) -> DirectResponsesClient:
    return DirectResponsesClient(
        api_key_env="TEST_RESPONSES_KEY", timeout_seconds=30, transport=transport
    )


def _frozen_request(ml: Any = "unused") -> ModelRequest:
    return ModelRequest(
        scoring_prompt=b"COMMITMENT:{commitment}",
        model_visible_payload={"commitment": "the dock sensor is satisfied"},
        model_configuration=direct_model_configuration(),  # real authoritative config
        case_id="S0-000",
    )


def _env_key() -> None:
    os.environ["TEST_RESPONSES_KEY"] = "sk-xyz"


def _clear_key() -> None:
    os.environ.pop("TEST_RESPONSES_KEY", None)


# ---- accepted path ----
def test_valid_completed_response_accepted() -> None:
    _env_key()
    try:
        t = FakeTransport(TransportResult(200, json.dumps(valid_response()).encode()))
        resp = make_client(t).make_single_decision(_frozen_request())
        assert isinstance(resp, ModelResponse)
        assert resp.raw_response == b"0.73"
        assert t.attempts == 1
        md = resp.provider_metadata
        assert md["response_id"] == "resp_abc"
        assert md["returned_model"] == MODEL
        assert md["reasoning_tokens"] == 90
        assert md["effective_reasoning_context"] == REASONING_CONTEXT
        assert len(md["raw_provider_b64"]) > 0
    finally:
        _clear_key()


def test_single_attempt_no_retry_on_success() -> None:
    _env_key()
    try:
        t = FakeTransport(TransportResult(200, json.dumps(valid_response()).encode()))
        make_client(t).make_single_decision(_frozen_request())
        assert t.attempts == 1
    finally:
        _clear_key()


def test_missing_api_key_stops() -> None:
    _clear_key()
    t = FakeTransport(TransportResult(200, json.dumps(valid_response()).encode()))
    with pytest.raises(ResponsesProviderFailure, match="missing"):
        make_client(t).make_single_decision(_frozen_request())


# ---- Task 1 fail-closed on effective response ----
def mutate(base: dict[str, Any], **kw: Any) -> dict[str, Any]:
    d = json.loads(json.dumps(base))
    d.update(kw)
    return dict(d)


def test_unknown_status_stops() -> None:
    for st in ("", "in_progress", "queued"):
        with pytest.raises(ResponsesProviderFailure, match="status"):
            parse_scoring_response(json.dumps(mutate(valid_response(), status=st)).encode())


def test_failed_incomplete_status_stops() -> None:
    for st in ("failed", "cancelled", "incomplete"):
        with pytest.raises(ResponsesProviderFailure, match="status"):
            parse_scoring_response(json.dumps(mutate(valid_response(), status=st)).encode())


def test_wrong_object_stops() -> None:
    with pytest.raises(ResponsesProviderFailure, match="object"):
        parse_scoring_response(json.dumps(mutate(valid_response(), object="wrong")).encode())


def test_returned_wrong_model_stops() -> None:
    # previously this was "observable"; now it must STOP.
    with pytest.raises(ResponsesProviderFailure, match="returned model"):
        parse_scoring_response(json.dumps(mutate(valid_response(), model="gpt-5.6-sol")).encode())


def test_wrong_missing_reasoning_context_stops() -> None:
    r = mutate(valid_response(), reasoning={"effort": REASONING_EFFORT, "context": "all_turns"})
    with pytest.raises(ResponsesProviderFailure, match="context"):
        parse_scoring_response(json.dumps(r).encode())
    # missing reasoning object -> STOP (reasoning is required)
    with pytest.raises(ResponsesProviderFailure, match="reasoning"):
        parse_scoring_response(json.dumps(mutate(valid_response(), reasoning=None)).encode())
    # missing context (reasoning present but no context key) -> STOP (required)
    r2 = mutate(valid_response(), reasoning={"effort": REASONING_EFFORT})
    with pytest.raises(ResponsesProviderFailure, match="context"):
        parse_scoring_response(json.dumps(r2).encode())


def test_wrong_effort_stops_when_returned() -> None:
    r = mutate(valid_response(), reasoning={"effort": "medium", "context": REASONING_CONTEXT})
    with pytest.raises(ResponsesProviderFailure, match="effort"):
        parse_scoring_response(json.dumps(r).encode())


def test_response_level_error_stops() -> None:
    r = mutate(valid_response(), error={"code": "x", "message": "y"})
    with pytest.raises(ResponsesProviderFailure, match="error"):
        parse_scoring_response(json.dumps(r).encode())


def test_incomplete_details_stops() -> None:
    r = mutate(valid_response(), incomplete_details={"reason": "max_output_tokens"})
    with pytest.raises(ResponsesProviderFailure, match="incomplete"):
        parse_scoring_response(json.dumps(r).encode())


# ---- Task 2 tight output parsing ----
def test_multiple_output_messages_stops() -> None:
    r = mutate(valid_response(), output=[msg("0.73"), msg("0.74")])
    with pytest.raises(ResponsesProviderFailure, match="exactly one output message"):
        parse_scoring_response(json.dumps(r).encode())


def test_refusal_stops() -> None:
    _env_key()
    try:
        t = FakeTransport(
            TransportResult(
                200,
                json.dumps(
                    mutate(
                        valid_response(),
                        output=[msg("I am sorry, I cannot help with that request.")],
                    )
                ).encode(),
            )
        )
        with pytest.raises(ResponsesProviderFailure, match="PLAIN_DECIMAL_V1|not a valid"):
            make_client(t).make_single_decision(_frozen_request())
    finally:
        _clear_key()


def test_multiple_content_blocks_stops() -> None:
    r = mutate(
        valid_response(),
        output=[
            {
                "type": "message",
                "role": "assistant",
                "status": "completed",
                "content": [
                    {"type": "output_text", "text": "0.73"},
                    {"type": "output_text", "text": "x"},
                ],
            }
        ],
    )
    with pytest.raises(ResponsesProviderFailure, match="exactly one content block"):
        parse_scoring_response(json.dumps(r).encode())


def test_wrong_role_stops() -> None:
    r = mutate(
        valid_response(),
        output=[
            {
                "type": "message",
                "role": "user",
                "status": "completed",
                "content": [{"type": "output_text", "text": "0.73"}],
            }
        ],
    )
    with pytest.raises(ResponsesProviderFailure, match="role"):
        parse_scoring_response(json.dumps(r).encode())


def test_content_block_type_not_output_text_stops() -> None:
    r = mutate(
        valid_response(),
        output=[
            {
                "type": "message",
                "role": "assistant",
                "status": "completed",
                "content": [{"type": "input_text", "text": "0.73"}],
            }
        ],
    )
    with pytest.raises(ResponsesProviderFailure, match="output_text"):
        parse_scoring_response(json.dumps(r).encode())


def test_tool_item_output_stops() -> None:
    r = mutate(valid_response(), output=[{"type": "function_call", "call_id": "c", "name": "f"}])
    with pytest.raises(ResponsesProviderFailure, match="unexpected/forbidden"):
        parse_scoring_response(json.dumps(r).encode())


def test_zero_messages_stops() -> None:
    r = mutate(valid_response(), output=[reasoning_item()])
    with pytest.raises(ResponsesProviderFailure, match="exactly one output message"):
        parse_scoring_response(json.dumps(r).encode())


def test_message_incomplete_status_stops() -> None:
    r = mutate(
        valid_response(),
        output=[
            {
                "type": "message",
                "role": "assistant",
                "status": "incomplete",
                "content": [{"type": "output_text", "text": "0.73"}],
            }
        ],
    )
    with pytest.raises(ResponsesProviderFailure, match="message status"):
        parse_scoring_response(json.dumps(r).encode())


# ---- Task 3 raw preservation / hash ----
def test_freeze_raw_results_retains_provider_bytes_and_hash() -> None:
    raw = json.dumps(valid_response()).encode()
    prov_sha = __import__("hashlib").sha256(raw).hexdigest()
    meta = {
        "provider_response_sha256": prov_sha,
        "raw_provider_b64": base64.b64encode(raw).decode("ascii"),
    }
    rr = RawResult(
        run_id="R",
        case_id="C1",
        truth_label=True,
        returned_score=0.73,
        raw_model_response=b"0.73",
        model_provider="openai_responses_api",
        model_id=MODEL,
        model_configuration_sha256=DIRECT_CONFIG_HASH,
        provider_metadata=meta,
        timestamp="t",
        call_order=1,
        parse_status=ParseStatus.VALID_SCORE,
        provider_response_sha256=prov_sha,
        provider_raw_b64=base64.b64encode(raw).decode("ascii"),
    )
    artifact = freeze_raw_results("R", (rr,))
    assert artifact.name == "raw-results-R"
    # lossless round trip: canonical record embeds provider_raw_base64
    record = rr.canonical_record()
    assert record["provider_response_sha256"] == prov_sha
    assert record["provider_raw_base64"] == base64.b64encode(raw).decode("ascii")
    # hash regression: artifact stable
    assert len(artifact.sha256) == 64


# ---- Task 4 manifest/config binding ----
def test_manifest_config_mismatch_stops_before_transport() -> None:
    _env_key()
    t = FakeTransport(TransportResult(200, json.dumps(valid_response()).encode()))
    client = make_client(t)
    bad_req = ModelRequest(
        scoring_prompt=b"COMMITMENT:{commitment}",
        model_visible_payload={"commitment": "x"},
        model_configuration="not-a-config",  # type: ignore[arg-type]
        case_id="S0-000",
    )
    try:
        with pytest.raises(ResponsesProviderFailure, match="model_configuration"):
            client.make_single_decision(bad_req)
        assert t.attempts == 0  # never reached transport
    finally:
        _clear_key()


def test_exact_direct_model_configuration() -> None:
    c = direct_model_configuration()
    assert c.provider == "openai_responses_api"
    assert c.model_id == "gpt-5.6-luna"
    assert c.reasoning_settings["effort"] == "xhigh"
    assert c.reasoning_settings["context"] == "current_turn"
    assert "mode" not in c.reasoning_settings
    assert c.temperature is None
    assert c.seed is None
    assert c.max_output_length == 128000
    assert c.api_parameters["tools"] == []
    assert c.api_parameters["previous_response_id"] is None
    assert c.api_parameters["stream"] is False
    # make_single_decision asserts this hash matches
    assert c.sha256 == DIRECT_CONFIG_HASH


# ---- Task 5 max output ----
def test_exact_max_output_request() -> None:
    body = build_request_body("score this")
    assert body["max_output_tokens"] == 128000
    assert body["model"] == "gpt-5.6-luna"
    assert body["reasoning"] == {"effort": "xhigh", "context": "current_turn"}
    assert body["store"] is False
    assert "tools" not in body


def test_build_request_body_frozen() -> None:
    body = build_request_body("score this")
    assert "previous_response_id" not in body
    assert "conversation" not in body
    assert "background" not in body
    assert "stream" not in body


def test_request_body_bytes_transmitted_and_hashed() -> None:
    import hashlib

    _env_key()
    try:
        t = FakeTransport(TransportResult(200, json.dumps(valid_response()).encode()))
        client = make_client(t)
        client.make_single_decision(_frozen_request())
        sent = t.last_payload
        assert sent is not None
        resp = client.make_single_decision(_frozen_request())
        md = resp.provider_metadata
        assert hashlib.sha256(sent).hexdigest() == md["request_body_sha256"]
        assert json.loads(sent) == build_request_body("COMMITMENT:the dock sensor is satisfied")
        assert md["request_body_sha256"] == hashlib.sha256(sent).hexdigest()
    finally:
        _clear_key()


# ---- transport zero-retry ----
def test_http_failure_stops_no_retry() -> None:
    _env_key()
    try:
        t = FakeTransport(TransportResult(429, b"{}"))
        with pytest.raises(ResponsesProviderFailure, match="HTTP 429"):
            make_client(t).make_single_decision(_frozen_request())
        assert t.attempts == 1
    finally:
        _clear_key()


def test_zero_retry_always_failing() -> None:
    _env_key()
    try:
        t = FakeTransport(TransportResult(500, b""))
        with pytest.raises(ResponsesProviderFailure):
            make_client(t).make_single_decision(_frozen_request())
        assert t.attempts == 1
    finally:
        _clear_key()
