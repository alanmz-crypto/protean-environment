"""Direct DeepSeek development/canary scoring adapter for Stage 0.

NON-experimental lane (see deepseek_config.py). Uses DeepSeek's native
/v1/responses surface (mirroring the Protean direct-provider architecture for
Luna) grounded in the devcontainer Dockerfile base_url and
stage0/model-config-decision-packet-v1.json. Never called during this task's
mechanical scope; tests use a fake transport (zero live DeepSeek/Luna requests).

Contract posture mirrors the experimental direct adapter's rigor but is explicitly
independent of Luna:

* exactly ONE POST per decision, never retried;
* request: input, reasoning.effort=high, max_output_tokens, stream=false;
  NO messages / previous_response_id / conversation / store / tools /
  response_format / thinking / temperature;
* ALWAYS fail closed on the returned model: the response.model must equal
  deepseek-v4-flash, so a hidden fallback to another model is refused;
* native Responses parsing: object==response, status==completed, exactly one
  final assistant output_text; reasoning items may exist but never supply the
  scored answer;
* exact request bytes are hashed (request_body_sha256) and exact raw response
  bytes are SHA-256'd (provider_response_sha256) into durable metadata;
* typed failures: TransportFailure / HttpFailure / ResponseContractFailure /
  ModelFormattingFailure, propagated to the harness which records the category.
"""

from __future__ import annotations

import base64
import json
import os
import urllib.error
import urllib.request
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Protocol

from .artifacts import canonical_json_bytes, sha256_bytes
from .deepseek_config import (
    API_KEY_ENV,
    DEEPSEEK_CONFIG_HASH,
    ENDPOINT,
    FORBIDDEN_REQUEST_FIELDS,
    MAX_OUTPUT_TOKENS,
    MODEL,
    NO_RETRIES,
    REASONING_EFFORT,
)
from .harness import ModelClient, ModelRequest, ModelResponse
from .provider_failure import (
    HttpFailure,
    HttpFailureEvidence,
    ModelFormattingFailure,
    ResponseContractFailure,
    TransportFailure,
)


def build_request_body(prompt_text: str) -> dict[str, Any]:
    """Return the frozen DeepSeek /v1/responses request body."""
    return {
        "model": MODEL,
        "input": prompt_text,
        "reasoning": {"effort": REASONING_EFFORT},
        "max_output_tokens": MAX_OUTPUT_TOKENS,
        "stream": False,
    }


def build_request_bytes(prompt_text: str) -> bytes:
    """Exact JSON bytes transmitted AND hashed (single serialization)."""
    return canonical_json_bytes(build_request_body(prompt_text))


_ALLOWED_OUTPUT_TYPES = frozenset({"message", "reasoning"})


@dataclass(frozen=True, slots=True)
class ParsedDeepSeekResponse:
    response_id: str
    object_type: str | None
    status: str
    model_returned: str | None
    reasoning_effort_returned: str | None
    usage: Mapping[str, Any] | None
    final_answer: str
    raw_response: bytes


class TransportResult:
    __slots__ = ("status_code", "raw_bytes")

    def __init__(self, status_code: int, raw_bytes: bytes) -> None:
        self.status_code = status_code
        self.raw_bytes = raw_bytes


class Transport(Protocol):
    def __call__(
        self, *, payload: bytes, api_key: str, timeout_seconds: int
    ) -> TransportResult: ...


def _post_once(payload: bytes, *, api_key: str, timeout_seconds: int) -> bytes:
    req = urllib.request.Request(
        ENDPOINT,
        data=payload,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout_seconds) as resp:
        raw = resp.read()
        assert isinstance(raw, bytes | bytearray)
        return bytes(raw)


def default_transport(*, payload: bytes, api_key: str, timeout_seconds: int) -> TransportResult:
    try:
        raw = _post_once(payload, api_key=api_key, timeout_seconds=timeout_seconds)
        return TransportResult(200, raw)
    except urllib.error.HTTPError as exc:
        return TransportResult(exc.code, exc.read())
    except Exception as exc:
        raise TransportFailure(f"transport error (no retry): {exc!r}") from exc


def parse_scoring_response(raw_bytes: bytes) -> ParsedDeepSeekResponse:
    """Parse + assert the deepseek /v1/responses contract. Violation => STOP."""
    try:
        obj = json.loads(raw_bytes.decode("utf-8"))
    except Exception as exc:
        raise ResponseContractFailure(
            f"malformed JSON response: {exc!r}", raw_response=raw_bytes
        ) from exc

    def _require(cond: bool, msg: str) -> None:
        if not cond:
            raise ResponseContractFailure(msg, raw_response=raw_bytes)

    _require(isinstance(obj, dict), "response is not a JSON object")

    object_type = obj.get("object")
    _require(object_type == "response", f"object must be response, got {object_type!r}")
    response_id = str(obj.get("id", ""))
    _require(bool(response_id), "missing response id")
    status = str(obj.get("status", ""))
    _require(status == "completed", f"status must be exactly completed, got {status!r}")

    model_returned = obj.get("model")
    _require(str(model_returned) == MODEL, f"returned model mismatch: {model_returned!r}")
    _require(obj.get("error") is None, "response-level error present")

    reasoning_returned = obj.get("reasoning")
    if reasoning_returned is not None:
        _require(isinstance(reasoning_returned, dict), "reasoning is not an object")
    effort_rt = reasoning_returned.get("effort") if isinstance(reasoning_returned, dict) else None
    if effort_rt is not None:
        _require(str(effort_rt) == REASONING_EFFORT, f"effort mismatch: {effort_rt!r}")

    usage = obj.get("usage")
    if usage is not None:
        _require(isinstance(usage, dict), "usage is not an object")

    output = obj.get("output")
    _require(isinstance(output, list), "missing output array")
    messages: list[str] = []
    final_message: str | None = None
    for item in output:
        _require(isinstance(item, dict), "malformed output item")
        item_type = str(item.get("type", ""))
        _require(item_type in _ALLOWED_OUTPUT_TYPES, f"unexpected output item type: {item_type!r}")
        if item_type == "message":
            role = item.get("role")
            _require(str(role) == "assistant", f"message role must be assistant, got {role!r}")
            content = item.get("content")
            _require(isinstance(content, list), "message content must be a list")
            _require(len(content) == 1, "message must have exactly one content block")
            block = content[0]
            _require(isinstance(block, dict), "content block is not an object")
            _require(
                str(block.get("type", "")) == "output_text",
                "content block type must be output_text",
            )
            text = str(block.get("text", ""))
            messages.append(text)
            final_message = text
        # reasoning items are permitted but never supply the scored answer.

    _require(len(messages) == 1, f"expected exactly one output message, saw {len(messages)}")
    _require(bool(final_message and final_message.strip()), "output message text is empty")
    assert final_message is not None

    return ParsedDeepSeekResponse(
        response_id=response_id,
        object_type=object_type,
        status=status,
        model_returned=str(model_returned) if model_returned is not None else None,
        reasoning_effort_returned=effort_rt,
        usage=usage if isinstance(usage, dict) else None,
        final_answer=final_message,
        raw_response=raw_bytes,
    )


class DeepSeekScoringClient(ModelClient):
    """One independently issued DeepSeek /v1/responses request per case."""

    def __init__(
        self,
        *,
        api_key_env: str = API_KEY_ENV,
        timeout_seconds: int = 300,
        transport: Transport = default_transport,
    ) -> None:
        self.api_key_env = api_key_env
        self.request_timeout = timeout_seconds
        self.transport = transport

    def make_single_decision(self, request: ModelRequest) -> ModelResponse:
        from .parse_contract import parse_plain_decimal_v1

        cfg = request.model_configuration
        if getattr(cfg, "sha256", None) != DEEPSEEK_CONFIG_HASH:
            raise ResponseContractFailure(
                "request model_configuration does not match frozen DeepSeek configuration"
            )
        if not cfg.api_parameters.get("endpoint", "").endswith("/responses"):
            raise ResponseContractFailure("DeepSeek config must target /v1/responses")
        if FORBIDDEN_REQUEST_FIELDS.intersection(cfg.api_parameters):
            raise ResponseContractFailure(
                "DeepSeek config must not enable chat-only/continuation/store fields"
            )

        api_key = os.environ.get(self.api_key_env, "")
        if not api_key:
            raise ResponseContractFailure(
                f"missing {self.api_key_env} (runtime credential; not baked)"
            )

        prompt_text = request.scoring_prompt.decode("utf-8").format(
            **dict(request.model_visible_payload)
        )
        payload = build_request_bytes(prompt_text)
        body_hash = sha256_bytes(payload)

        transport_result = self.transport(
            payload=payload,
            api_key=api_key,
            timeout_seconds=self.request_timeout,
        )
        if transport_result.status_code != 200:
            raw_error_body = transport_result.raw_bytes
            raise HttpFailure(
                f"HTTP {transport_result.status_code} (no retry)",
                HttpFailureEvidence(
                    status_code=transport_result.status_code,
                    raw_error_body=raw_error_body,
                    raw_error_sha256=sha256_bytes(raw_error_body) if raw_error_body else None,
                ),
            )

        raw_provider_bytes = transport_result.raw_bytes
        provider_sha = sha256_bytes(raw_provider_bytes)
        parsed = parse_scoring_response(raw_provider_bytes)

        score = parse_plain_decimal_v1(parsed.final_answer.encode("utf-8"))
        if score is None:
            raise ModelFormattingFailure(
                "final answer not a valid PLAIN_DECIMAL_V1", raw_response=raw_provider_bytes
            )

        metadata: dict[str, Any] = {
            "request_body_sha256": body_hash,
            "provider_response_sha256": provider_sha,
            "raw_provider_b64": base64.b64encode(raw_provider_bytes).decode("ascii"),
            "response_id": parsed.response_id,
            "returned_object": parsed.object_type,
            "status": parsed.status,
            "requested_model": MODEL,
            "returned_model": parsed.model_returned,
            "effective_reasoning_effort": parsed.reasoning_effort_returned,
            "usage": dict(parsed.usage) if parsed.usage else None,
            "provider": "deepseek",
            "request_config_hash": cfg.sha256,
            "deepseek_config_hash": DEEPSEEK_CONFIG_HASH,
            "no_retries": NO_RETRIES,
            "single_hit": True,
            "timestamp": datetime.now(UTC).isoformat(),
        }
        return ModelResponse(
            raw_response=f"{score:.2f}".encode(),
            provider_metadata=metadata,
        )
