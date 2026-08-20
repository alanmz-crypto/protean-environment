"""Authoritative frozen DeepSeek development/canary configuration for Stage 0.

This is a NON-experimental provider lane for low-consequence development and
canary scoring. It is deliberately separate from the Luna experimental provider
(direct_config.py / direct_responses.py). Provider contracts are independent:

* credential     : DEEPSEEK_API_KEY (runtime env; never baked into image/repo)
* model          : deepseek-v4-flash (per stage0/model-config-decision-packet-v1.json)
* surface        : DeepSeek /v1/responses (native Responses object), mirroring
                   the Protean direct-provider architecture for Luna but with an
                   independent request shape (no messages, no response_format, no
                   thinking, no temperature, no store; reasoning.effort high
                   instead of Luna's xhigh context/effort pair).
* request shape  : input, reasoning.effort=high, max_output_tokens, stream=false;
                   NO previous_response_id / conversation / store / tools.
* determinism    : temperature is omitted entirely (the provider ignores it under
                   a high-reasoning configuration, so we do not pretend it
                   supplies deterministic control).

This config can never satisfy a Luna experimental manifest/config: provider,
model_id, and every api_parameter differ, so the canonical ModelConfiguration
record and its SHA-256 are distinct. The adapter enforces its own config hash at
request time, so a DeepSeek request can never be issued against a Luna config
and vice versa.
"""

from __future__ import annotations

from .manifest import ModelConfiguration

# Grounded DeepSeek base URL (devcontainer Dockerfile + decision packet v1).
DEEPSEEK_BASE_URL = "https://api.deepseek.com/v1/"

# Provider / model (development lane; not the experimental Luna surface).
PROVIDER = "deepseek"
MODEL = "deepseek-v4-flash"
VERSION_OR_SNAPSHOT = "DeepSeek-V4-Flash-0731"

# Reasoning: native Responses `reasoning.effort`. Luna's context field and its
# xhigh value are NOT copied; DeepSeek uses effort=high.
REASONING_EFFORT = "high"

# Temperature is omitted (None): the provider ignores it under high reasoning
# effort, so representing its absence is truthful (never a false 0.0).
TEMPERATURE: float | None = None
SEED: int | None = None
# One decimal comfortably fits the score response.
MAX_OUTPUT_TOKENS = 16

# Endpoint / request shape
ENDPOINT = DEEPSEEK_BASE_URL + "responses"
STORE = False
NO_RETRIES = 0

# Runtime credential env var (never printed or committed).
API_KEY_ENV = "DEEPSEEK_API_KEY"

# Request fields that must never appear (no chat-completions-only or continuation
# controls, no persistence store, no silent-ignore reliance).
FORBIDDEN_REQUEST_FIELDS = frozenset(
    {"previous_response_id", "conversation", "store", "messages", "thinking", "temperature"}
)


def deepseek_model_configuration() -> ModelConfiguration:
    """The authoritative ModelConfiguration for the DeepSeek dev/canary adapter."""
    return ModelConfiguration(
        provider=PROVIDER,
        model_id=MODEL,
        version_or_snapshot=VERSION_OR_SNAPSHOT,
        reasoning_settings={"effort": REASONING_EFFORT},
        temperature=TEMPERATURE,
        seed=SEED,
        max_output_length=MAX_OUTPUT_TOKENS,
        api_parameters={
            "endpoint": ENDPOINT,
            "no_retries": NO_RETRIES,
            "tools": [],
        },
    )


DEEPSEEK_CONFIG_HASH = deepseek_model_configuration().sha256
