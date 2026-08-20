"""Direct OpenAI Responses API scoring adapter for Stage 0 (Luna xHigh).

This REPLACES the Codex surface (rejected: codex exec --json and codex app-server
could not guarantee exactly one upstream decision per scoring turn). The frozen
scientific decision unit here is: ONE independently issued OpenAI Responses API
request and its single returned Response object. No previous_response_id, no
conversation object, no persisted prior reasoning, no tool continuation, no
client retry, no streaming.

One attempt per case: the transport issues exactly one HTTP POST and never
retries (urllib.request has no auto-retry; we add no retry loop). Any timeout,
HTTP, or transport error => STOP, never retry.

No live model call is made except when the harness actually runs it with a real
runtime credential; unit tests use a fake transport.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Protocol

from .artifacts import canonical_json_bytes, sha256_bytes
from .harness import ModelClient, ModelRequest, ModelResponse, ProviderFailure

# ---------------------------------------------------------------------------
# Frozen exact request configuration (Task 1)
# ---------------------------------------------------------------------------

RESPONSES_ENDPOINT: str = "https://api.openai.com/v1/responses"
MODEL: str = "gpt-5.6-luna"
REASONING_EFFORT: str = "xhigh"
REASONING_CONTEXT: str = "current_turn"
# Standard mode (not pro): default; we do NOT set reasoning.mode.
STORE: bool = False
# xHigh needs reasoning room; visible output is one decimal but reasoning tokens
# count against the output budget. 8192 is far above any xhigh reasoning output
# and far below the model context window => no truncation hazard.
MAX_OUTPUT_TOKENS: int = 8192
NO_RETRIES: int = 0  # semantic: exactly one attempt, zero retries (by construction)

# Environment key for the OpenAI API bearer token (never baked into repo/image).
API_KEY_ENV: str = "OPENAI_API_KEY"

_TERMINAL_FAILED_STATUSES = frozenset(
    {"failed", "cancelled", "incomplete", "queued", "in_progress"}
)
_ALLOWED_OUTPUT_TYPES = frozenset({"message", "reasoning"})
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
        # no tools / no previous_response_id / no conversation / no background /
        # no stream (all absent => not sent)
    }


def request_config_hash() -> str:
    """Hash of the frozen request configuration (excluding the per-case prompt)."""
    config = {
        "endpoint": RESPONSES_ENDPOINT,
        "model": MODEL,
        "reasoning": {"effort": REASONING_EFFORT, "context": REASONING_CONTEXT},
        "max_output_tokens": MAX_OUTPUT_TOKENS,
        "store": STORE,
        "no_retries": NO_RETRIES,
    }
    return sha256_bytes(canonical_json_bytes(config))


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
        RESPONSES_ENDPOINT,
        data=json.dumps(body).encode("utf-8"),
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout_seconds) as resp:
        body_bytes = resp.read()
        assert isinstance(body_bytes, bytes | bytearray)
        return bytes(body_bytes)


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
    model_returned: str | None
    created_at: int | None
    usage: Mapping[str, Any] | None
    final_answer: str
    raw_response: bytes


def parse_scoring_response(raw_bytes: bytes) -> ParsedScoringResponse:
    """Parse + assert the single-Response contract. Violations => ProviderFailure."""
    try:
        obj = json.loads(raw_bytes.decode("utf-8"))
    except Exception as exc:
        raise ResponsesProviderFailure(f"malformed JSON response: {exc!r}") from exc
    if not isinstance(obj, dict):
        raise ResponsesProviderFailure("response is not a JSON object")

    status = str(obj.get("status", ""))
    if status in _TERMINAL_FAILED_STATUSES:
        raise ResponsesProviderFailure(f"response status not completed: {status}")

    response_id = str(obj.get("id", ""))
    if not response_id:
        raise ResponsesProviderFailure("missing response id")
    model_returned = obj.get("model")
    created_at = obj.get("created_at")
    created_at_int = int(created_at) if isinstance(created_at, int) else None

    output = obj.get("output")
    if not isinstance(output, list):
        raise ResponsesProviderFailure("missing output array")

    usage = obj.get("usage")
    if usage is not None and not isinstance(usage, dict):
        raise ResponsesProviderFailure("usage is not an object")

    messages: list[str] = []
    for item in output:
        if not isinstance(item, dict):
            raise ResponsesProviderFailure(f"malformed output item: {item!r}")
        item_type = str(item.get("type", ""))
        if item_type in _FORBIDDEN_OUTPUT_TYPES:
            raise ResponsesProviderFailure(f"forbidden output item type: {item_type}")
        if item_type not in _ALLOWED_OUTPUT_TYPES:
            raise ResponsesProviderFailure(f"unexpected output item type: {item_type}")
        if item_type == "message":
            texts: list[str] = []
            content = item.get("content")
            if isinstance(content, list):
                for block in content:
                    if isinstance(block, dict) and block.get("type") == "output_text":
                        texts.append(str(block.get("text", "")))
            messages.append("".join(texts))

    non_empty = [m for m in messages if m.strip()]
    if len(non_empty) != 1:
        raise ResponsesProviderFailure(
            f"expected exactly one message with text, saw {len(non_empty)}"
        )
    final_answer = non_empty[0]

    return ParsedScoringResponse(
        response_id=response_id,
        status=status,
        model_returned=model_returned,
        created_at=created_at_int,
        usage=usage,
        final_answer=final_answer,
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

        api_key = os.environ.get(self.api_key_env, "")
        if not api_key:
            raise ResponsesProviderFailure(
                f"missing {self.api_key_env} (runtime credential; not baked)"
            )

        prompt_text = request.scoring_prompt.decode("utf-8").format(
            **dict(request.model_visible_payload)
        )
        body = build_request_body(prompt_text)
        transport_result = self.transport(
            body=body, api_key=api_key, timeout_seconds=self.request_timeout
        )
        if transport_result.status_code != 200:
            raise ResponsesProviderFailure(f"HTTP {transport_result.status_code} (no retry)")

        parsed = parse_scoring_response(transport_result.raw_bytes)
        score = parse_plain_decimal_v1(parsed.final_answer.encode("utf-8"))
        if score is None:
            raise ResponsesProviderFailure("final answer not a valid PLAIN_DECIMAL_V1")

        reason_tokens = extract_reasoning_tokens(parsed.usage)
        metadata = {
            "response_id": parsed.response_id,
            "requested_model": MODEL,
            "returned_model": parsed.model_returned,
            "status": parsed.status,
            "created_at": parsed.created_at,
            "usage": dict(parsed.usage) if parsed.usage else None,
            "reasoning_tokens": reason_tokens,
            "request_config_hash": request_config_hash(),
            "no_retries": NO_RETRIES,
            "single_hit": True,
            "timestamp": datetime.now(UTC).isoformat(),
        }
        return ModelResponse(
            raw_response=f"{score:.2f}".encode(),
            provider_metadata=metadata,
        )
