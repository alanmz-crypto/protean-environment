"""Hermetic tests for the DeepSeek development/canary Stage-0 adapter.

Uses a fake transport only — NO live DeepSeek call and no Luna call.
"""

from __future__ import annotations

import json
import os
from typing import Any

import pytest

from protean_stage0.artifacts import canonical_json_bytes, sha256_bytes
from protean_stage0.deepseek_config import (
    DEEPSEEK_CONFIG_HASH,
    MODEL,
    deepseek_model_configuration,
)
from protean_stage0.deepseek_responses import (
    DeepSeekScoringClient,
    TransportResult,
    build_request_body,
    build_request_bytes,
    parse_scoring_response,
)
from protean_stage0.harness import ModelRequest, ModelResponse
from protean_stage0.provider_failure import (
    HttpFailure,
    ModelFormattingFailure,
    ResponseContractFailure,
    TransportFailure,
)

TEST_KEY_ENV = "TEST_DEEPSEEK_KEY"


def message_item(text: str = "0.73") -> dict[str, Any]:
    return {
        "type": "message",
        "role": "assistant",
        "status": "completed",
        "content": [{"type": "output_text", "text": text}],
    }


def reasoning_item() -> dict[str, Any]:
    return {"type": "reasoning", "summary": []}


def deepseek_response(text: str = "0.73") -> dict[str, Any]:
    return {
        "id": "dsk-xyz",
        "object": "response",
        "created_at": 1700000000,
        "status": "completed",
        "model": MODEL,
        "reasoning": {"effort": "high"},
        "output": [reasoning_item(), message_item(text)],
        "usage": {
            "input_tokens": 60,
            "output_tokens": 24,
            "total_tokens": 84,
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


class RaisingTransport:
    def __init__(self, exc: Exception) -> None:
        self.exc = exc
        self.attempts = 0

    def __call__(self, *, payload: bytes, api_key: str, timeout_seconds: int) -> TransportResult:
        self.attempts += 1
        raise self.exc


def make_client(transport: Any) -> DeepSeekScoringClient:
    return DeepSeekScoringClient(api_key_env=TEST_KEY_ENV, timeout_seconds=30, transport=transport)


def _frozen_request() -> ModelRequest:
    return ModelRequest(
        scoring_prompt=b"COMMITMENT:{commitment}",
        model_visible_payload={"commitment": "the dock sensor is satisfied"},
        model_configuration=deepseek_model_configuration(),  # authoritative DeepSeek config
        case_id="S0-000",
    )


def _env_key() -> None:
    os.environ[TEST_KEY_ENV] = "sk-test-deepseek"


def _clear_key() -> None:
    os.environ.pop(TEST_KEY_ENV, None)


# ---- missing credential ----
def test_missing_api_key_stops() -> None:
    _clear_key()
    t = FakeTransport(TransportResult(200, json.dumps(deepseek_response()).encode()))
    with pytest.raises(ResponseContractFailure, match="missing"):
        make_client(t).make_single_decision(_frozen_request())
    assert t.attempts == 0  # never reaches transport


# ---- valid score + exactly one transport invocation ----
def test_valid_deepseek_score_accepted() -> None:
    _env_key()
    try:
        t = FakeTransport(TransportResult(200, json.dumps(deepseek_response()).encode()))
        resp = make_client(t).make_single_decision(_frozen_request())
        assert isinstance(resp, ModelResponse)
        assert resp.raw_response == b"0.73"
        assert t.attempts == 1
        md = resp.provider_metadata
        assert md["returned_model"] == MODEL
        assert md["provider"] == "deepseek"
        assert md["returned_object"] == "response"
        assert md["status"] == "completed"
        assert md["effective_reasoning_effort"] == "high"
        assert md["no_retries"] == 0
        assert md["single_hit"] is True
    finally:
        _clear_key()


def test_single_attempt_no_retry_on_success() -> None:
    _env_key()
    try:
        t = FakeTransport(TransportResult(200, json.dumps(deepseek_response()).encode()))
        make_client(t).make_single_decision(_frozen_request())
        assert t.attempts == 1
    finally:
        _clear_key()


# ---- native Responses parsing ----
def test_parse_native_responses_reasoning_not_scored() -> None:
    # reasoning items may exist but never supply the scored answer.
    raw = json.dumps(deepseek_response(text="0.81")).encode()
    parsed = parse_scoring_response(raw)
    assert parsed.object_type == "response"
    assert parsed.status == "completed"
    assert parsed.model_returned == MODEL
    assert parsed.reasoning_effort_returned == "high"
    assert parsed.final_answer == "0.81"


def test_non_output_text_content_is_contract_failure() -> None:
    _env_key()
    try:
        bad = deepseek_response()
        bad["output"] = [
            {
                "type": "message",
                "role": "assistant",
                "content": [{"type": "input_text", "text": "0.73"}],
            }
        ]
        t = FakeTransport(TransportResult(200, json.dumps(bad).encode()))
        with pytest.raises(ResponseContractFailure, match="output_text"):
            make_client(t).make_single_decision(_frozen_request())
    finally:
        _clear_key()


def test_status_not_completed_is_contract_failure() -> None:
    _env_key()
    try:
        bad = deepseek_response()
        bad["status"] = "failed"
        t = FakeTransport(TransportResult(200, json.dumps(bad).encode()))
        with pytest.raises(ResponseContractFailure, match="status"):
            make_client(t).make_single_decision(_frozen_request())
    finally:
        _clear_key()


# ---- HTTP failure: status + raw body preserved, never retried ----
def test_http_failure_preserves_status_and_raw_body_no_retry() -> None:
    _env_key()
    try:
        error_body = b'{"error":{"message":"rate limited","type":"rate_limit"}}'
        t = FakeTransport(TransportResult(429, error_body))
        with pytest.raises(HttpFailure) as ei:
            make_client(t).make_single_decision(_frozen_request())
        assert ei.value.evidence.status_code == 429
        assert ei.value.evidence.raw_error_body == error_body
        # safe record never carries credentials/authorization headers
        assert "Authorization" not in json.dumps(ei.value.evidence.safe_record())
        assert ei.value.evidence.safe_record()["status_code"] == 429
        assert t.attempts == 1  # exactly one POST, no retry
    finally:
        _clear_key()


# ---- transport exception classified correctly ----
def test_transport_exception_classified() -> None:
    _env_key()
    try:
        # default_transport converts network errors into TransportFailure; an
        # injected transport that mirrors that behavior propagates TransportFailure.
        t = RaisingTransport(TransportFailure("transport error (no retry)"))
        with pytest.raises(TransportFailure, match="transport error"):
            make_client(t).make_single_decision(_frozen_request())
        assert t.attempts == 1
    finally:
        _clear_key()


# ---- malformed JSON ----
def test_malformed_json_contract_failure() -> None:
    _env_key()
    try:
        t = FakeTransport(TransportResult(200, b"not-json{"))
        with pytest.raises(ResponseContractFailure, match="malformed JSON"):
            make_client(t).make_single_decision(_frozen_request())
    finally:
        _clear_key()


# ---- response-contract mismatch (returned model != deepseek-v4-flash) ----
def test_returned_model_mismatch_is_contract_failure() -> None:
    _env_key()
    try:
        bad = deepseek_response()
        bad["model"] = "deepseek-v4-pro"
        t = FakeTransport(TransportResult(200, json.dumps(bad).encode()))
        with pytest.raises(ResponseContractFailure, match="returned model mismatch"):
            make_client(t).make_single_decision(_frozen_request())
    finally:
        _clear_key()


def test_missing_output_is_contract_failure() -> None:
    _env_key()
    try:
        bad = deepseek_response()
        del bad["output"]
        t = FakeTransport(TransportResult(200, json.dumps(bad).encode()))
        with pytest.raises(ResponseContractFailure, match="missing output array"):
            make_client(t).make_single_decision(_frozen_request())
    finally:
        _clear_key()


# ---- malformed decimal is model-formatting failure, NOT generic API failure ----
def test_malformed_decimal_is_model_formatting_not_api_failure() -> None:
    _env_key()
    try:
        raw = json.dumps(deepseek_response(text="The score is 0.75")).encode()
        t = FakeTransport(TransportResult(200, raw))
        with pytest.raises(ModelFormattingFailure, match="PLAIN_DECIMAL_V1"):
            make_client(t).make_single_decision(_frozen_request())
        # The exception is explicitly a model-formatting failure, never a
        # transport / HTTP / generic contract failure.
        from protean_stage0.provider_failure import ProviderFailureCategory

        assert ModelFormattingFailure.category is ProviderFailureCategory.MODEL_FORMATTING
    finally:
        _clear_key()


# ---- exact request-byte/hash agreement ----
def test_exact_request_bytes_match_and_hash_recorded() -> None:
    _env_key()
    try:
        t = FakeTransport(TransportResult(200, json.dumps(deepseek_response()).encode()))
        md = make_client(t).make_single_decision(_frozen_request()).provider_metadata
        expected = build_request_bytes("COMMITMENT:the dock sensor is satisfied")
        assert t.last_payload == expected
        assert sha256_bytes(expected) == md["request_body_sha256"]
        assert md["request_config_hash"] == DEEPSEEK_CONFIG_HASH
    finally:
        _clear_key()


# ---- exact /v1/responses path and request shape ----
def test_exact_responses_endpoint_path() -> None:
    from protean_stage0.deepseek_config import ENDPOINT

    assert ENDPOINT == "https://api.deepseek.com/v1/responses"
    assert ENDPOINT.endswith("/responses")


def test_request_body_contains_only_authorized_shape() -> None:
    body = build_request_body("x")
    assert body["model"] == MODEL
    assert body["input"] == "x"  # /v1/responses uses input, not messages
    assert body["reasoning"] == {"effort": "high"}
    assert body["max_output_tokens"] == 2048  # max_output_tokens, not max_tokens
    assert body["stream"] is False
    # Chat-completions-only and continuation/persistence controls must be absent.
    for forbidden in (
        "messages",
        "max_tokens",
        "temperature",
        "thinking",
        "response_format",
        "store",
        "previous_response_id",
        "conversation",
        "background",
        "tools",
    ):
        assert forbidden not in body, f"forbidden field present: {forbidden}"


def test_no_messages_or_chat_only_fields_in_exact_bytes() -> None:
    raw = build_request_bytes("canary")
    assert b'"messages"' not in raw
    assert b'"max_tokens"' not in raw
    assert b'"temperature"' not in raw
    assert b'"thinking"' not in raw
    assert b'"response_format"' not in raw
    assert b'"store"' not in raw
    assert b'"previous_response_id"' not in raw
    assert b'"reasoning"' in raw
    assert b'"input"' in raw


# ---- exact response-byte/hash agreement ----
def test_exact_response_bytes_and_hash_agreement() -> None:
    _env_key()
    try:
        raw = json.dumps(deepseek_response()).encode()
        t = FakeTransport(TransportResult(200, raw))
        md = make_client(t).make_single_decision(_frozen_request()).provider_metadata
        assert md["provider_response_sha256"] == sha256_bytes(raw)
        # raw_provider_b64 decodes back to the exact bytes
        import base64

        assert base64.b64decode(md["raw_provider_b64"]) == raw
    finally:
        _clear_key()


def test_build_request_bytes_are_canonical_and_stable() -> None:
    body = build_request_body("canary")
    assert build_request_bytes("canary") == canonical_json_bytes(body)
    assert build_request_bytes("canary") == build_request_bytes("canary")


# ---- config mutual-exclusivity ----
def test_deepseek_config_cannot_satisfy_luna_manifest() -> None:
    # The DeepSeek config is the only config this client will accept; a Luna-shaped
    # request (direct_response config hash) is refused before transport.
    from protean_stage0.direct_config import direct_model_configuration

    _env_key()
    try:
        luna_cfg = direct_model_configuration()
        assert luna_cfg.sha256 != DEEPSEEK_CONFIG_HASH
        wrong_req = ModelRequest(
            scoring_prompt=b"x",
            model_visible_payload={"commitment": "x"},
            model_configuration=luna_cfg,
            case_id="S0-000",
        )
        t = FakeTransport(TransportResult(200, json.dumps(deepseek_response()).encode()))
        with pytest.raises(ResponseContractFailure, match="model_configuration"):
            make_client(t).make_single_decision(wrong_req)
        assert t.attempts == 0  # refused before any transport call
    finally:
        _clear_key()


def test_luna_config_cannot_satisfy_deepseek_config_hash() -> None:
    # And a DeepSeek config is never accepted by the Luna adapter (mirror check).
    from protean_stage0.direct_config import DIRECT_CONFIG_HASH
    from protean_stage0.direct_responses import DirectResponsesClient, TransportResult
    from protean_stage0.provider_failure import ProviderFailure

    os.environ["TEST_RESPONSES_KEY"] = "sk-xyz"
    try:
        deepseek_cfg = deepseek_model_configuration()
        assert deepseek_cfg.sha256 != DIRECT_CONFIG_HASH
        wrong_req = ModelRequest(
            scoring_prompt=b"x",
            model_visible_payload={"commitment": "x"},
            model_configuration=deepseek_cfg,
            case_id="S0-000",
        )

        class DirectTransport:
            attempts = 0

            def __call__(
                self, *, payload: bytes, api_key: str, timeout_seconds: int
            ) -> TransportResult:  # pragma: no cover - never reached
                self.attempts += 1
                return TransportResult(200, b"")

        t = DirectTransport()
        luna = DirectResponsesClient(
            api_key_env="TEST_RESPONSES_KEY", timeout_seconds=30, transport=t
        )
        with pytest.raises(ProviderFailure, match="model_configuration"):
            luna.make_single_decision(wrong_req)
        assert t.attempts == 0
    finally:
        os.environ.pop("TEST_RESPONSES_KEY", None)
        _clear_key()


def test_deepseek_exact_configuration_record() -> None:
    c = deepseek_model_configuration()
    assert c.provider == "deepseek"
    assert c.model_id == "deepseek-v4-flash"
    assert c.version_or_snapshot == "DeepSeek-V4-Flash-0731"
    assert c.reasoning_settings == {"effort": "high"}
    assert c.temperature is None  # omitted, never a false 0.0
    assert c.seed is None
    assert c.max_output_length > 0
    assert c.api_parameters["endpoint"].endswith("/responses")
    # no chat-only / continuation / persistence controls in the config record
    for forbidden in (
        "messages",
        "max_tokens",
        "temperature",
        "thinking",
        "response_format",
        "store",
        "previous_response_id",
        "conversation",
    ):
        assert forbidden not in c.api_parameters
