# Stage 0 Zero-Retry Codex Recovery — Luna xHigh Investigation Result (Task 1-3)

Disposition: BLOCKED — Task 3 gate fails (SINGLE_DECISION_STILL_NOT_GUARANTEED). No implementation performed.

## Gate results (from exact rust-v0.147.0 source, same Luna xHigh lane)
- Task 1 — ZERO_RETRY_PROVEN
  (a) request_max_retries=0 => one HTTP request, zero retries (run_with_retry 0..=max_attempts; should_retry(0,0)->false).
  (b) stream_max_retries=0 => run_sampling_request cannot issue a 2nd sampling request on retryable stream failure (responses_retry.rs:31 retries>=max_retries true at 0; error propagates).
  (c) supports_websockets=false => WebSocket->HTTPS fallback disabled (client.rs:524 force_http_fallback false; try_switch_fallback_transport false; first/only request is HTTPS).
  Central: NO second upstream sampling request can be issued. ZERO_RETRY_PROVEN.

- Task 2 — DEDICATED_PROVIDER_EQUIVALENT
  is_openai() keys on NAME == "OpenAI", so provider name must be exactly "OpenAI" (id protean-openai inert for capability dispatch).
  requires_openai_auth=true => ChatGPT subscription auth (not API key).
  base_url https://chatgpt.com/backend-api/codex == CHATGPT_CODEX_BASE_URL constant (honored for custom provider).
  Explicit http_headers { version = "0.147.0" } is REQUIRED (built-in injects CARGO_PKG_VERSION header per-provider; custom provider without it sends no version header).
  No silent provider/model fallback; model/effort exposed in thread config.
  PROVISO: gpt-5.6-luna/xhigh must exist in exact 0.147.0 catalog (failure = validation error, not silent fallback).

- Task 3 — SINGLE_DECISION_STILL_NOT_GUARANTEED  (DECISIVE GATE FAILS)
  Eliminated paths: retries (Task1), tool-driven needs_follow_up (tools off), mailbox preempt (empty mailbox), pending user input, auto-roll-over compaction (asserted off).
  RESIDUAL MODEL-CONTROLLED PATH: backend sets completed.end_turn=false:
    session_turn.rs:2528 if let Some(false)=end_turn { needs_follow_up=true }
    session_turn.rs:515 continue;  -> a SECOND upstream sampling request in the SAME scoring turn
    -> observable as a SECOND rawResponse/completed.
  app-server experimentalRawEvents can OBSERVE N completed responses but CANNOT PREVENT a 2nd when the backend sends end_turn=false.
  => one scoring turn cannot be mechanically constrained to exactly one upstream Luna request.

## STOP
SINGLE_DECISION_STILL_NOT_GUARANTEED per authorization => STOP. No app-server migration implemented. No commit/push. No live Luna call.

## Canonical zero-retry provider TOML (for the record; NOT implemented/active)
model = "gpt-5.6-luna"
model_reasoning_effort = "xhigh"
model_provider = "protean-openai"
approval_policy = "never"
[model_providers.protean-openai]
name = "OpenAI"
base_url = "https://chatgpt.com/backend-api/codex"
wire_api = "responses"
requires_openai_auth = true
request_max_retries = 0
stream_max_retries = 0
supports_websockets = false
supports_standalone_web_search = true
http_headers = { version = "0.147.0" }
