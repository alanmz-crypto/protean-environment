"""Codex (gpt-5.6-luna, xhigh) Stage-0 scoring adapter with assert-and-reject.

Launches exactly one fresh `codex exec` process per case, captures the full
--json event stream and the --output-last-message file, records process exit +
Codex version, and enforces the frozen assert-and-reject contract. If any
frozen assertion is violated the case is NOT retried: the adapter stops
(assert-and-reject, never response shopping). This is a pre-score integration;
the adapter itself never inspects model performance.
"""

from __future__ import annotations

import json
import subprocess
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol

from .codex_config import CODEX_CLI_VERSION, CodexInvocationConfig, env_allowlist
from .harness import ModelClient, ModelRequest, ModelResponse, ProviderFailure

# ---------------------------------------------------------------------------
# Contract violation types
# ---------------------------------------------------------------------------


class CodexContractViolation(ProviderFailure):
    """A frozen assert-and-reject contract assertion was violated. No retry."""


@dataclass(frozen=True, slots=True)
class CodexRunResult:
    exit_code: int
    version: str
    model: str
    reasoning_effort: str
    raw_events: tuple[dict[str, Any], ...]
    last_message_file: str | None
    last_message_text: str | None


# ---------------------------------------------------------------------------
# Frozen event vocabulary (structured; not substring guessing)
# ---------------------------------------------------------------------------

# These events are PROHIBITED (zero occurrences) for a valid scoring invocation.
_PROHIBITED_TOOL_EVENTS: frozenset[str] = frozenset(
    {
        # shell / patch / fs-mutation
        "exec_command_begin",
        "exec_command_output_delta",
        "apply_patch_begin",
        "apply_patch_updated",
        "apply_patch_end",
        "apply_patch_approval_request",
        "terminate_agent",
        # MCP / tool calls
        "mcp_tool_call_begin",
        "mcp_tool_call_end",
        "mcp_startup_update",
        "mcp_startup_complete",
        # web / network
        "web_search",
        "web_search_end",
        # image / view
        "image_generation_begin",
        "image_generation_end",
        "view_image_tool_call",
        # agent / spawn
        "collab_agent_spawn_begin",
        "collab_agent_spawn_end",
        "collab_agent_interaction_begin",
        "collab_agent_interaction_end",
        "spawn_agents",
        "sub_agent_activity",
        # generic tool activity
        "dynamic_tool_call_request",
        "dynamic_tool_call_response",
        "elicitation_request",
        "request_user_input",
        "guardian_assessment",
        "exec_approval_request",
    }
)

# Memory / skill / plugin injection markers (zero occurrences).
_PROHIBITED_INJECTION_EVENTS: frozenset[str] = frozenset(
    {
        "mementoprefix_compaction",
        "generate_memories",
        "memory_consolidation",
        "thread_spawn",
    }
)

# Compaction / fork / continuation markers (zero occurrences).
_PROHIBITED_COMPACTION_EVENTS: frozenset[str] = frozenset(
    {
        "context_compacted",
        "context_compaction",
        "auto_compact",
        "response_compacted",
        "thread_rolled_back",
        "fork_history",
        "replacement_history",
        "model_reroute",
        "compacted",
    }
)

# Events that must each occur EXACTLY once for a valid single decision.
_REQUIRED_SINGLE_EVENTS: tuple[str, ...] = (
    "task_started",
    "task_complete",
    "turn_started",
    "turn_complete",
    "raw_response_completed",
)

# Events that must be present at least once (provenance / activity).
_REQUIRED_PRESENT_EVENTS: tuple[str, ...] = (
    "token_count",
    "agent_message",
)


class _EventKind(Protocol):
    pass


def _event_name(item: Mapping[str, Any]) -> str:
    # The JSONL event dictionaries carry the event type under key "type".
    return str(item.get("type", ""))


@dataclass(frozen=True, slots=True)
class ParsedVerification:
    """Outcome of applying the assert-and-reject contract to one invocation."""

    accepted: bool
    reason: str | None = None
    score: float | None = None
    counts: Mapping[str, int] = field(default_factory=dict)
    agent_messages: tuple[str, ...] = ()


def _parse_decimal(text: str) -> float | None:
    """Parse a strict PLAIN_DECIMAL_V1 response (0.xx|1.00 with optional LF)."""
    from .parse_contract import parse_plain_decimal_v1

    return parse_plain_decimal_v1(text.encode("utf-8"))


def evaluate_codex_contract(run: CodexRunResult) -> ParsedVerification:
    """Apply every frozen assertion. accepted=False means STOP, never retry."""
    counts: dict[str, int] = {}
    prohibited_seen: list[str] = []

    for item in run.raw_events:
        name = _event_name(item)
        counts[name] = counts.get(name, 0) + 1
        if name in _PROHIBITED_TOOL_EVENTS:
            prohibited_seen.append(f"tool_event:{name}")
        if name in _PROHIBITED_INJECTION_EVENTS:
            prohibited_seen.append(f"injection:{name}")
        if name in _PROHIBITED_COMPACTION_EVENTS:
            prohibited_seen.append(f"compaction:{name}")

    if run.exit_code != 0:
        return ParsedVerification(False, f"non-zero exit code {run.exit_code}", counts=counts)
    if run.version != CODEX_CLI_VERSION:
        return ParsedVerification(
            False,
            f"codex version mismatch: expected {CODEX_CLI_VERSION} got {run.version}",
            counts=counts,
        )

    for name in _REQUIRED_SINGLE_EVENTS:
        if counts.get(name, 0) != 1:
            return ParsedVerification(
                False, f"expected exactly one {name}, saw {counts.get(name, 0)}", counts=counts
            )
    for name in _REQUIRED_PRESENT_EVENTS:
        if counts.get(name, 0) < 1:
            return ParsedVerification(False, f"required event absent: {name}", counts=counts)

    if prohibited_seen:
        return ParsedVerification(
            False,
            "prohibited event(s): " + ", ".join(sorted(set(prohibited_seen))[:8]),
            counts=counts,
        )

    # exactly one agent message; parse it
    agent_messages = tuple(
        str(item.get("content", ""))
        for item in run.raw_events
        if _event_name(item) == "agent_message"
    )
    if len(agent_messages) != 1:
        return ParsedVerification(
            False, f"expected exactly one agent_message, saw {len(agent_messages)}", counts=counts
        )
    score = _parse_decimal(agent_messages[0])
    if score is None:
        return ParsedVerification(
            False,
            "agent_message not a valid PLAIN_DECIMAL_V1",
            counts=counts,
            agent_messages=agent_messages,
        )

    # final-message file equals the parsed decimal
    if run.last_message_text is not None:
        file_score = _parse_decimal(run.last_message_text)
        if file_score is None or abs(file_score - score) > 1e-12:
            return ParsedVerification(
                False,
                "final-message file does not equal the parsed agent_message",
                counts=counts,
                agent_messages=agent_messages,
            )

    if not (0.0 <= score <= 1.0):
        return ParsedVerification(
            False, "parsed score out of [0,1]", counts=counts, agent_messages=agent_messages
        )

    return ParsedVerification(True, None, score, counts, agent_messages)


# ---------------------------------------------------------------------------
# Process runner abstraction (replaced by fakes in tests; no live call)
# ---------------------------------------------------------------------------


class CodexRunner(Protocol):
    def __call__(
        self,
        *,
        args: Sequence[str],
        cwd: str,
        env: Mapping[str, str],
        last_message_path: str,
        prompt_text: str,
    ) -> CodexRunResult: ...


def default_codex_runner(
    *,
    args: Sequence[str],
    cwd: str,
    env: Mapping[str, str],
    last_message_path: str,
    prompt_text: str,
) -> CodexRunResult:
    """Run one fresh `codex exec` process; capture JSONL, file, exit, version."""
    cmd = list(args) + [prompt_text]
    proc = subprocess.run(
        cmd,
        cwd=cwd,
        env=dict(env),
        capture_output=True,
        text=True,
        timeout=600,
    )
    events: list[dict[str, Any]] = []
    for line in proc.stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict):
            events.append(obj)

    version = "unknown"
    try:
        vp = subprocess.run(
            ["codex", "--version"],
            cwd=cwd,
            env=dict(env),
            capture_output=True,
            text=True,
            timeout=30,
        )
        version = vp.stdout.strip().splitlines()[0] if vp.stdout.strip() else "unknown"
    except Exception:  # pragma: no cover - defensive
        version = "unknown"

    last_text: str | None = None
    if Path(last_message_path).exists():
        try:
            last_text = Path(last_message_path).read_text(encoding="utf-8")
        except OSError:
            last_text = None

    return CodexRunResult(
        exit_code=proc.returncode,
        version=version,
        model="gpt-5.6-luna",
        reasoning_effort="xhigh",
        raw_events=tuple(events),
        last_message_file=last_message_path,
        last_message_text=last_text,
    )


# ---------------------------------------------------------------------------
# CodexModelClient (conforms to the harness ModelClient)
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class CodexModelClient(ModelClient):
    """Stage-0 scoring client backed by one fresh codex exec per case."""

    forced_prompt_template: bytes
    model_configuration_sha256: str
    runner: CodexRunner = default_codex_runner
    invocation: CodexInvocationConfig = CodexInvocationConfig()

    def make_single_decision(self, request: ModelRequest) -> ModelResponse:
        # Assemble the per-case prompt from the frozen scoring prompt + payload.
        payload = dict(request.model_visible_payload)
        prompt_text = self.forced_prompt_template.decode("utf-8").format(**payload)

        env = env_allowlist()
        last_path = Path(self.invocation.scoring_cwd) / "last_message.txt"
        run = self.runner(
            args=self.invocation.args,
            cwd=self.invocation.scoring_cwd,
            env=env,
            last_message_path=str(last_path),
            prompt_text=prompt_text,
        )
        verification = evaluate_codex_contract(run)
        if not verification.accepted:
            raise CodexContractViolation(
                f"codex contract violation for {request.case_id}: {verification.reason}"
            )
        assert verification.score is not None
        metadata = {
            "codex_cli_version": run.version,
            "model": self.invocation.model,
            "reasoning_effort": self.invocation.reasoning_effort,
            "model_configuration_sha256": self.model_configuration_sha256,
            "exit_code": run.exit_code,
            "raw_events_preserved": True,
            "timestamp": datetime.now(UTC).isoformat(),
        }
        return ModelResponse(
            raw_response=f"{verification.score:.2f}".encode(),
            provider_metadata=metadata,
        )
