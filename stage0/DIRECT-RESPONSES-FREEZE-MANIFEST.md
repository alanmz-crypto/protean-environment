# Stage 0 — Direct OpenAI Responses API Freeze Manifest (ACTIVE experimental surface)

Status: ACTIVE provider surface for Stage-0 scoring (direct Responses API). Codex CLI / codex app-server are REJECTED as the scoring surface.
Model: Luna xHigh = gpt-5.6-luna, reasoning.effort=xhigh, standard mode (not pro).

## Why Codex was rejected (evidence preserved)
- stage0/CODEX-V147-SOURCE-AUDIT.md — codex exec --json wire vocabulary mismatch + no upstream-request-count observability.
- stage0/APP-SERVER-TASK0-RETRY-STOP.md — RETRY_CAN_CONDITION_DECISION: run_sampling_request retry reuses clone_history() carrying partial committed output.
- stage0/ZERO-RETRY-INVESTIGATION-RESULT.md — even zero-retry custom provider leaves model-controlled end_turn=false continuation -> second upstream response.
src/protean_stage0/codex_adapter.py + codex_config.py marked REJECTED/SUPERSEDED (historical evidence only).

## ACTIVE scientific decision unit (frozen)
One Stage-0 decision = one independently issued OpenAI Responses API request and its single returned Response object.
No previous_response_id, no conversation object, no persisted prior reasoning, no tool continuation, no client retry (zero), no streaming.

## Exact frozen request configuration (Task 1)
- endpoint: POST https://api.openai.com/v1/responses
- model: gpt-5.6-luna
- reasoning.effort: xhigh
- reasoning.context: current_turn
- reasoning.mode: NOT SET (standard mode; never "pro")
- max_output_tokens: 8192 (xhigh reasoning room; no truncation hazard)
- store: false
- input: the frozen per-case scoring prompt (scoring-prompt sha ae8f093a69a7bae6818421000490a14c8a19a4a6be33069a1858bf0a9d7f6909) + case model-visible payload
- tools: absent; previous_response_id/conversation/background/stream: absent
- authorization: runtime OpenAI API key from env OPENAI_API_KEY (never baked into image/repo/inputs)

## Zero-retry transport (Task 2)
One HTTP POST via stdlib urllib.request (has no auto-retry; adapter adds no loop). Timeout/HTTP/transport error => STOP, never retry. Exactly one attempt per case (tests assert attempts==1).

## Response acceptance (Task 3 / assert-and-reject; violation => STOP, no retry)
- status == completed
- exactly one final textual message; exactly one message with non-empty text
- answer satisfies frozen PLAIN_DECIMAL_V1
- output items only of allowed types {message, reasoning}; ANY tool/other item type (function_call, web_search_call, file_search_call, mcp_*, etc.) => STOP
- record provenance: response id, requested model, returned model (if exposed), status, usage (incl. reasoning tokens under usage.output_tokens_details.reasoning_tokens), created_at, raw response artifact, timestamp, request-config hash.

## Experimental inputs (UNCHANGED; Task 4)
- template bank sha 295fe92fe12ba14470166d6b160492fb1564d29b06dc46500f8b2cbfdf73c758
- case set sha 06fe8d471b1fbbc226696ed6d80b706cc84a6040a7fb91a93814343420291556
- scoring prompt sha ae8f093a69a7bae6818421000490a14c8a19a4a6be33069a1858bf0a9d7f6909 (APPROVED/FROZEN)
Model: Luna xHigh. Only the provider/control surface changed.

## Adapter
- src/protean_stage0/direct_responses.py (ACTIVE scoring client)
- tests/test_direct_responses.py (protocol-faithful fakes; no live calls)
