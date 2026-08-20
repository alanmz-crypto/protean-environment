# STATUS: REJECTED / SUPERSEDED
#
# This Codex surface (codex exec --json and codex app-server) was REJECTED as the
# Stage-0 experimental scoring provider because it could not guarantee exactly one
# upstream Luna decision per scoring turn (see stage0/CODEX-V147-SOURCE-AUDIT.md,
# stage0/APP-SERVER-TASK0-RETRY-STOP.md, stage0/ZERO-RETRY-INVESTIGATION-RESULT.md).
# The ACTIVE experimental surface is the direct OpenAI Responses API adapter
# (src/protean_stage0/direct_responses.py). This module is retained ONLY as
# historical/evidence and MUST NOT be treated as the active scoring path.

"""Frozen Codex (gpt-5.6-luna, xhigh) scoring invocation configuration.

This module is the SINGLE literal source of the frozen experimental provider
configuration (Stage 0 freeze decision). It contains no secrets and no
per-case experimental text. Values here must be kept byte-exact; see
stage0/luna-xhigh-frozen-config.md.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

# Expected/required Codex CLI version (frozen).
CODEX_CLI_VERSION: Final = "0.147.0"

# Container-local, never host-sourced. Auth is added later by explicit
# container-local `codex login` (never baked into image or repo).
CODEX_HOME: Final = "/home/vscode/.codex-protean"

# Empty, non-git, no-AGENTS scoring working directory.
SCORING_CWD: Final = "/tmp/protean-score-empty"

# Model + reasoning effort (frozen decision).
MODEL: Final = "gpt-5.6-luna"
REASONING_EFFORT: Final = "xhigh"
SERVICE_TIER: Final = "default"

# Exact literal disabled-tool list (built-in tools; MCP/skills/plugins are
# additionally closed by empty CODEX_HOME + --ignore-rules + include_*_usage
# = false and rejected at the event level).
DISABLED_TOOLS: Final = [
    "apply_patch",
    "exec_command",
    "web_search",
    "image_gen",
    "view_image",
    "spawn_agent",
]

# The complete `codex exec` argument vector. Per-case scoring text is supplied
# as the final positional argument by the adapter (assembled from the frozen
# scoring prompt + the case model-visible payload).
EXEC_BASE_ARGS: Final = [
    "--ephemeral",
    "--ignore-user-config",
    "--ignore-rules",
    "--skip-git-repo-check",
    "--sandbox",
    "read-only",
    "--cd",
    SCORING_CWD,
    "--model",
    MODEL,
    "--config",
    f'model_reasoning_effort="{REASONING_EFFORT}"',
    "--config",
    f'service_tier="{SERVICE_TIER}"',
    "--config",
    "default_tools_enabled=false",
    "--config",
    "tools=[]",
    "--config",
    'disabled_tools=["apply_patch","exec_command","web_search","image_gen","view_image","spawn_agent"]',
    "--config",
    "approval_mode=never",
    "--config",
    "use_memories=false",
    "--config",
    "generate_memories=false",
    "--config",
    "model_messages=false",
    "--config",
    "reminder_threshold_tokens=1000000",
    "--config",
    "include_skills_usage_instructions=false",
    "--config",
    "include_plugin_usage_instructions=false",
    "--json",
    "--output-last-message",
    f"{SCORING_CWD}/last_message.txt",
]

# Environment allowlist: only these variables are set/foregrounded for the
# scoring subprocess; everything else inherits the container default.
ALLOWED_ENV: Final = ("CODEX_HOME", "HOME", "PATH", "LANG", "LC_ALL", "PYTHONPATH")


# environment built by the adapter; CODEX_HOME forced container-local.
def env_allowlist() -> dict[str, str]:
    from os import environ

    out: dict[str, str] = {}
    for key in ALLOWED_ENV:
        if key in environ:
            out[key] = environ[key]
    out["CODEX_HOME"] = CODEX_HOME
    return out


@dataclass(frozen=True, slots=True)
class CodexInvocationConfig:
    """Literal frozen Codex invocation parameters (no placeholders)."""

    exe: str = "codex"
    args: tuple[str, ...] = tuple(EXEC_BASE_ARGS)
    codex_home: str = CODEX_HOME
    scoring_cwd: str = SCORING_CWD
    model: str = MODEL
    reasoning_effort: str = REASONING_EFFORT
    expected_version: str = CODEX_CLI_VERSION
    env_allowlist: tuple[str, ...] = ALLOWED_ENV
