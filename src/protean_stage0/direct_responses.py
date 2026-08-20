"""Direct OpenAI Responses API scoring adapter for Stage 0 (Luna xHigh).

ACTIVE experimental surface (Codex exec/app-server REJECTED). Frozen decision
unit: ONE independently issued Responses API request and its single returned
Response object. No previous_response_id / conversation / persisted prior
reasoning / tool continuation / client retry / streaming.

Fail closed on the effective response and the final output. One attempt per case
(transport issues exactly one HTTP POST, never retries). Any mismatch => STOP,
no retry. The exact raw provider-response bytes and their SHA-256 are carried in
provider_metadata for durable retention in the Stage-0 raw-result artifact.
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
from .direct_config import (
    DIRECT_CONFIG_HASH,
    ENDPOINT,
    MAX_OUTPUT_TOKENS,
    MODEL,
    NO_RETRIES,
    REASONING_CONTEXT,
    REASONING_EFFORT,
    STORE,
)
from .harness import ModelClient, ModelRequest, ModelResponse, ProviderFailure


def build_request_body(prompt_text: str) -> dict[str, Any]:
    """Return the exact frozen request body for /v1/responses."""
    return {
        "model": MODEL,
        "input": prompt_text,
        "reasoning": {
            "effort": REASONING_EFFORT,
            "context": REASONING_CONTEXT,
        },
        "max_output_tokens": MAX_OUTPUT_TOKENS,
        "store": STORE,
        # no tools / previous_response_id / conversation / background / stream
    }


API_KEY_ENV = "OPENAI_API_KEY"
_TERMINAL_FAILED_STATUSES = frozenset(
    {"failed", "cancelled", "incomplete", "queued", "in_progress"}
)
_FORBIDDEN_OUTPUT_TYPES = frozenset(
    {
        "function_call",
        "function_call_output",
        "web_search_call",
        "file_search_call",
        "computer_call",
        "computer_call_output",
        "image_gen_call",
        "code_interpreter_call",
        "local_shell_call",
        "local_shell_call_output",
        "function_shell_call",
        "function_shell_call_output",
        "apply_patch_call",
        "apply_patch_call_output",
        "mcp_call",
        "mcp_list_tools",
        "mcp_approval_request",
        "mcp_approval_response",
        "custom_call",
        "custom_call_output",
        "tool_search_call",
        "tool_search_output",
        "additional_tools",
        "compaction",
        "program",
        "program_output",
    }
)
_ALLOWED_OUTPUT_TYPES = frozenset({"message", "reasoning"})


class ResponsesProviderFailure(ProviderFailure):
    """A frozen scoring contract violation or transport failure. STOP, no retry."""


@dataclass(frozen=True, slots=True)
class TransportResult:
    status_code: int
    raw_bytes: bytes


class Transport(Protocol):
    def __call__(
        self, *, body: Mapping[str, Any], api_key: str, timeout_seconds: int
    ) -> TransportResult: ...


def _post_once(body: dict[str, Any], *, api_key: str, timeout_seconds: int) -> bytes:
    """Issue EXACTLY ONE HTTP POST; urllib has no auto-retry and we add none."""
    req = urllib.request.Request(
        ENDPOINT,
        data=json.dumps(body).encode("utf-8"),
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


def default_transport(
    *, body: Mapping[str, Any], api_key: str, timeout_seconds: int
) -> TransportResult:
    try:
        raw = _post_once(dict(body), api_key=api_key, timeout_seconds=timeout_seconds)
        return TransportResult(200, raw)
    except urllib.error.HTTPError as exc:
        return TransportResult(exc.code, exc.read())
    except Exception as exc:
        raise ResponsesProviderFailure(f"transport error (no retry): {exc!r}") from exc


@dataclass(frozen=True, slots=True)
class ParsedScoringResponse:
    response_id: str
    status: str
    object_type: str | None
    model_returned: str | None
    reasoning_effort_returned: str | None
    reasoning_context_returned: str | None
    created_at: int | None
    usage: Mapping[str, Any] | None
    final_answer: str
    raw_response: bytes


def _require(cond: bool, msg: str) -> None:
    if not cond:
        raise ResponsesProviderFailure(msg)


def parse_scoring_response(raw_bytes: bytes) -> ParsedScoringResponse:
    """Parse + assert the single-Response contract. Violation => STOP."""
    try:
        obj = json.loads(raw_bytes.decode("utf-8"))
    except Exception as exc:
        raise ResponsesProviderFailure(f"malformed JSON response: {exc!r}") from exc
    _require(isinstance(obj, dict), "response is not a JSON object")

    # Task 1: fail closed on the effective response.
    status = str(obj.get("status", ""))
    _require(status == "completed", f"status must be exactly completed, got {status!r}")
    object_type = obj.get("object")
    if object_type is not None:
        _require(str(object_type) == "response", f"object must be response, got {object_type!r}")
    model_returned = obj.get("model")
    _require(str(model_returned) == MODEL, f"returned model mismatch: {model_returned!r}")
    reasoning_returned = obj.get("reasoning")
    if isinstance(reasoning_returned, dict):
        effort_rt = reasoning_returned.get("effort")
        context_rt = reasoning_returned.get("context")
        if effort_rt is not None:
            _require(str(effort_rt) == REASONING_EFFORT, f"effort mismatch: {effort_rt!r}")
        if context_rt is not None:
            _require(str(context_rt) == REASONING_CONTEXT, f"context mismatch: {context_rt!r}")
    else:
        effort_rt = None
        context_rt = None
    _require(obj.get("error") is None, "response-level error present")
    incomplete = obj.get("incomplete_details")
    _require(incomplete is None, "response incomplete_details present")

    response_id = str(obj.get("id", ""))
    _require(bool(response_id), "missing response id")
    created_at = obj.get("created_at")
    created_at_int = int(created_at) if isinstance(created_at, int) else None

    usage = obj.get("usage")
    if usage is not None:
        _require(isinstance(usage, dict), "usage is not an object")

    # Task 2: tighten final-output parsing.
    output = obj.get("output")
    _require(isinstance(output, list), "missing output array")
    messages: list[str] = []
    final_message: str | None = None
    for item in output:
        _require(isinstance(item, dict), "malformed output item")
        item_type = str(item.get("type", ""))
        _require(
            item_type in _ALLOWED_OUTPUT_TYPES,
            f"unexpected/forbidden output item type: {item_type!r}",
        )
        if item_type == "message":
            role = item.get("role")
            _require(str(role) == "assistant", f"message role must be assistant, got {role!r}")
            status_m = item.get("status")
            if status_m is not None:
                _require(
                    str(status_m) == "completed", f"message status not completed: {status_m!r}"
                )
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

    return ParsedScoringResponse(
        response_id=response_id,
        status=status,
        object_type=str(object_type) if object_type is not None else None,
        model_returned=str(model_returned) if model_returned is not None else None,
        reasoning_effort_returned=effort_rt,
        reasoning_context_returned=context_rt,
        created_at=created_at_int,
        usage=usage if isinstance(usage, dict) else None,
        final_answer=final_message,
        raw_response=raw_bytes,
    )


def extract_reasoning_tokens(usage: Mapping[str, Any] | None) -> int | None:
    if not usage:
        return None
    details = usage.get("output_tokens_details")
    if isinstance(details, dict):
        r = details.get("reasoning_tokens")
        if isinstance(r, int):
            return r
    return None


class DirectResponsesClient(ModelClient):
    """One independently issued Responses API request per case; no retry."""

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

        # Task 4: bind the executable request to the manifest authority.
        cfg = request.model_configuration
        _require(
            getattr(cfg, "sha256", None) == DIRECT_CONFIG_HASH,
            "request model_configuration does not match frozen direct configuration",
        )

        api_key = os.environ.get(self.api_key_env, "")
        if not api_key:
            raise ResponsesProviderFailure(
                f"missing {self.api_key_env} (runtime credential; not baked)"
            )

        prompt_text = request.scoring_prompt.decode("utf-8").format(
            **dict(request.model_visible_payload)
        )
        body = build_request_body(prompt_text)
        body_hash = sha256_bytes(canonical_json_bytes(body))

        transport_result = self.transport(
            body=body,
            api_key=api_key,
            timeout_seconds=self.request_timeout,
        )
        if transport_result.status_code != 200:
            raise ResponsesProviderFailure(f"HTTP {transport_result.status_code} (no retry)")

        raw_provider_bytes = transport_result.raw_bytes
        provider_sha = sha256_bytes(raw_provider_bytes)
        parsed = parse_scoring_response(raw_provider_bytes)

        score = parse_plain_decimal_v1(parsed.final_answer.encode("utf-8"))
        if score is None:
            raise ResponsesProviderFailure("final answer not a valid PLAIN_DECIMAL_V1")

        reason_tokens = extract_reasoning_tokens(parsed.usage)
        metadata: dict[str, Any] = {
            "request_body_sha256": body_hash,
            "provider_response_sha256": provider_sha,
            "raw_provider_b64": base64.b64encode(raw_provider_bytes).decode("ascii"),
            "response_id": parsed.response_id,
            "requested_model": MODEL,
            "returned_model": parsed.model_returned,
            "effective_reasoning_context": parsed.reasoning_context_returned,
            "effective_reasoning_effort": parsed.reasoning_effort_returned,
            "status": parsed.status,
            "created_at": parsed.created_at,
            "usage": dict(parsed.usage) if parsed.usage else None,
            "reasoning_tokens": reason_tokens,
            "request_config_hash": request.model_configuration.sha256,
            "direct_config_hash": DIRECT_CONFIG_HASH,
            "no_retries": NO_RETRIES,
            "single_hit": True,
            "timestamp": datetime.now(UTC).isoformat(),
        }
        return ModelResponse(
            raw_response=f"{score:.2f}".encode(),
            provider_metadata=metadata,
        )
