# Stage 0 App-Server Migration — Task 0 Retry-Semantics STOP record

Arc: Prospective Control Experiment 1 — Stage 0 App-Server Surface Migration.
Disposition: RETRY_CAN_CONDITION_DECISION => per authorization, STOP. App-server migration NOT implemented. Return to Ryan.

## Source (exact rust-v0.147.0, commit openai/codex 3ed6f04f...)
- codex-rs/core/src/stream_events_utils.rs: `handle_output_item_done` calls `record_completed_response_item(...)` (-> `sess.record_conversation_items(...)`) on EVERY `ResponseEvent::OutputItemDone`, i.e. items are persisted to conversation HISTORY AS THEY STREAM, for both tool calls and non-tool (Message/AgentMessage/Reasoning) fallback items.
- codex-rs/core/src/session/turn.rs: `run_sampling_request` retry loop (line 1308) rebuilds `prompt_input` from `sess.clone_history()` on retry; a retryable error calls `handle_retryable_response_stream_error` (backs off + returns Ok) then loops back to `try_run_sampling_request` -> `client_session.stream(...)`.
- codex-rs/protocol/src/error.rs `is_retryable()` returns true for `Stream(..)`, `Timeout`, `RequestTimeout`, `ServerOverloaded`, `ResponseStreamFailed(_)`, `InternalServerError`.
- `try_run_sampling_request` breaks `Err(CodexErr::Stream("stream closed before response.completed"))` on premature stream close (turn.rs ~2246) -> this is RETRYABLE.

## Conclusion
If a Responses request fails before response/completed AND Codex retries it, any assistant/reasoning/model output whose OutputItemDone was already recorded (committed to history via record_conversation_items) IS present in `sess.clone_history()` for the retry, and CAN condition the succeeding/final scoring decision. There is no rollback of these recorded items on retry. Therefore the retry is NOT decision-neutral.

=> RETRY_CAN_CONDITION_DECISION. STOP per authorization. No app-server adapter implemented, no config change, no commit/push, no live Luna call.
