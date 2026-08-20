# Codex exec 0.147.0 — Stage-0 Source-Level Surface Audit (Luna xHigh lane)

Date: 2026-08-19. Source inspected at exact tag openai/codex commit 3ed6f04f6bf8b7c46299d1cb1ff99c74ce21a51d (= rust-v0.147.0). No live Luna call.

## Task 2 — CENTRAL SINGLE-DECISION RESULT: NOT_GUARANTEED

Source (codex-rs/core/src/session/turn.rs, v0.147.0) proves multiple upstream model requests can occur inside ONE logical turn:
- The turn driver `run_turn` is an explicit `loop { ... }` (line 272) with `continue` paths (461, 489, 515).
- After each `run_sampling_request(...)` (line 347), it computes `token_limit_reached` and `should_roll_over = needs_follow_up && (take_new_context_window_request || token_limit_reached)`; if true it calls `run_auto_compact(...)` (MidTurn, CompactionReason::ContextLimit) and `continue`s -> a SECOND `run_sampling_request` in the same turn.
- `run_sampling_request` (line 1308) itself has an inner `loop { }` with `max_retries = stream_max_retries()`; a retryable stream error calls `handle_retryable_response_stream_error(...)` + `record_sampling_retry()` and loops back to `try_run_sampling_request` -> re-issues `client_session.stream(...)` (line ~2170), an additional upstream Requests request.
Therefore one `turn.completed` can aggregate MULTIPLE upstream Requests.

The exec JSONL CANNOT detect this:
- `event_processor_with_jsonl_output.rs` maps ServerNotifications only; it emits one `turn.completed` per server TurnCompleted with summed `usage` (input/output/reasoning tokens). No upstream-request-count field.
- Mid-turn compaction (`run_auto_compact`) is internal; no distinguishing exec event. `ModelVerification(_)` -> silently `Running` (swallowed). Retries are internal.
- `ModelRerouted` DOES emit an ErrorItem item ("model rerouted: X -> Y (reason)") - detectable, but only for reroute, not for extra requests.

Under the frozen conditions (tiny one-shot payload, tools/memories disabled via the (broken) overrides, xhigh, reminder_threshold_tokens=1000000) an extra request is UNLIKELY but NOT impossible and NOT provable from source: (a) xhigh can emit large reasoning/output tokens; if the resulting total approaches the (possibly undefined/effective) auto-compact token limit -> token_limit_reached -> mid-turn compaction -> 2nd request; (b) any retryable server/stream error -> automatic retry -> 2nd upstream request. The property "one turn.completed == exactly one Luna inference" is NOT guaranteed by construction.

=> `codex exec --json` (0.147.0) CANNOT prove one-upstream-request-per-case. NOT_GUARANTEED.

## Task 1 — Authoritative 0.147.0 exec JSONL wire contract
Top-level ThreadEvent enum (json tag "type"), from codex-rs/exec/src/exec_events.rs:
- thread.started {thread_id}
- turn.started {} ; turn.completed {usage}; turn.failed {error}; 
- item.started | item.updated | item.completed {item}
- error {message}
Nested ThreadItemDetails (item.type, snake_case): agent_message{text}, reasoning{text}, command_execution{...}, file_change{...}, mcp_tool_call{...}, collab_tool_call{... (incl SpawnAgent)}, web_search{...}, todo_list{...}, error{...}.
Usage (turn.completed): input_tokens, cached_input_tokens, cache_write_input_tokens, output_tokens, reasoning_output_tokens.
Detectability mapping: fresh thread=thread.started(thread_id); one turn=turn.started+turn.completed(+usage); final agent response=item.completed with item.type agent_message (text); command exec=command_execution items; file changes=file_change items; MCP=mcp_tool_call items; collab/subagent=collab_tool_call items; web search=web_search items; errors=top-level error or item error; reroute=item error message "model rerouted: ..."; compaction/continuation=NOT observable; token usage=turn.completed.usage.
This CONTRADICTS the current adapter vocab (task_started/turn_started/turn_completed/token_count/top-level agent_message /raw_response_completed) which does not exist in v0.147.0.

## Task 4 — mechanical defects in commit 7923ffb
A. Version: runner compares full first line `codex-cli 0.147.0` to "0.147.0" -> always mismatch. CONFIRMED (fail-closed wrongly).
   Correct: parse trailing token after "codex-cli " or regex ^codex-cli[ \t]+(\S+).
B. last_message.txt: fixed path reused per case; not unique; stale file can satisfy contract (run.last_message_text read if file exists, regardless of freshness). CONFIRMED. Must use unique per-case path + require presence + delete-before-run.
C. raw JSONL preservation: adapter sets raw_events_preserved=True but never persists the exact original stdout bytes to an immutable artifact. CONFIRMED. Must store the raw stdout bytes + hash on the result/artifact.
D. non-JSON stdout: runner silently skips non-JSON lines. CONFIRMED -> should fail closed unless v0.147.0 allows. (Source: emit uses println! of serialized ThreadEvent; a config warning yields a valid event; non-JSON stdout is not expected -> FAIL CLOSED.)
E. provenance/reroute: model/effort from frozen constants (not observed). Runtime reroute IS observable via item error "model rerouted"; adapter does not inspect nested item error type. CONFIRMED: do not report frozen constants as observed; parse real reroute/usage.
F. env mismatch: CODE config allowlist exists but must be reconciled with luna-xhigh-frozen-config.md (one authoritative list). CONFIRMED (doc/code drift).
G. override keys vs 0.147.0:
   - valid keys: model, model_reasoning_effort, service_tier, disabled_tools, reminders? (reminder_threshold_tokens present in config; AutoCompactTokenLimit/reminder), model_auto_compact_token_limit.
   - INVALID/RENAMED (NOT present as v0.147.0 user-config keys): approval_mode (real: approval_policy), model_messages (not a key; it is a feature/model-catalog flag), include_skills_usage_instructions (real: include_skill_instructions), include_plugin_usage_instructions (no such key; real: include_apps_instructions / include_collaboration_mode_instructions), default_tools_enabled (no such key), use_memories/generate_memories (top-level - not present; memory config is the `memories` sub-struct).
   - The frozen invocation does NOT pass --strict-config, so unknown keys are NOT fail-closed (silently ignored or warned), masking these errors.
   CONFIRMED: several frozen -c overrides are ineffective; the tool/memory/skills suppression claim is NOT actually guaranteed -> assert-and-reject premise broken at the config level too.

## Task 3 — smallest correct surface (not implemented; Ryan authorization required)
`codex exec --json` is insufficient. The smallest surface exposing every upstream model response is the Codex app-server / low-level stream, which emits per-request raw/response events (and per-turn SessionConfigured/Responses stream) that reveal each upstream Requests request count. It supports ChatGPT subscription auth, gpt-5.6-luna xhigh, and container-local CODEX_HOME, but needs a provider-surface change (switch from `codex exec` to a lower-level client), which is NOT authorized here.
STOP: surface change requires Ryan authorization. No patch made to work around NOT_GUARANTEED.

## Zero live calls
No experimental/rehearsal/one-case-probe Luna call was made. All evidence from the exact tag source + local binary + existing repo.
