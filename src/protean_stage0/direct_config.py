"""Authoritative frozen direct OpenAI Responses API model configuration for Stage 0.

This is the SINGLE source of truth for the executable request configuration and
the run-manifest ModelConfiguration for the ACTIVE Stage-0 experimental surface
(direct OpenAI Responses API, Luna xHigh). It must not drift from
stage0/DIRECT-RESPONSES-FREEZE-MANIFEST.md. Codex CLI / codex app-server are
REJECTED (see stage0/CODEX-V147-SOURCE-AUDIT.md and friends).
"""

from __future__ import annotations

from .manifest import ModelConfiguration

# Provider / model / reasoning (frozen Ryan decision)
PROVIDER = "openai_responses_api"
MODEL = "gpt-5.6-luna"
VERSION_OR_SNAPSHOT: str | None = None  # OpenAI does not expose a public model snapshot id here
REASONING_EFFORT = "xhigh"
REASONING_CONTEXT = "current_turn"
REASONING_MODE: str | None = None  # omitted => standard mode (never "pro")

# Endpoint / request shape
ENDPOINT = "https://api.openai.com/v1/responses"
STORE = False
NO_RETRIES = 0
# Phase 5: raise to Luna's documented maximum output allowance so Stage 0 does
# not impose an arbitrary xHigh reasoning ceiling.
MAX_OUTPUT_TOKENS = 128_000

# No temperature: the Responses API request omits it and the manifest must
# truthfully represent omission (temperature=None), not a false 0.0.
TEMPERATURE: float | None = None
SEED: int | None = None


def direct_model_configuration() -> ModelConfiguration:
    """The authoritative ModelConfiguration for the direct Responses adapter."""
    return ModelConfiguration(
        provider=PROVIDER,
        model_id=MODEL,
        version_or_snapshot=VERSION_OR_SNAPSHOT,
        reasoning_settings={
            "effort": REASONING_EFFORT,
            "context": REASONING_CONTEXT,
            # mode omitted => standard; if present it would be "standard", never "pro"
        },
        temperature=TEMPERATURE,
        seed=SEED,
        max_output_length=MAX_OUTPUT_TOKENS,
        api_parameters={
            "endpoint": ENDPOINT,
            "store": STORE,
            "no_retries": NO_RETRIES,
            "tools": [],
            "previous_response_id": None,
            "conversation": None,
            "background": None,
            "stream": False,
        },
    )


DIRECT_CONFIG_HASH = direct_model_configuration().sha256
