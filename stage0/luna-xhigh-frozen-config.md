# Stage 0 — Frozen Codex (Luna xHigh) Provider Configuration (exact, literal)

Status: FROZEN (pending adapter implementation + mechanical verification). No experimental call made.
Decision: Ryan selected Codex Luna Extra High (xHigh) as the Stage-0 experimental model via OpenAI Codex CLI on Ryan's ChatGPT subscription. DeepSeek V4 Pro is NOT the selected experimental model.

## Provider surface
- Provider surface: OpenAI Codex CLI (Ryan's ChatGPT subscription)
- Codex CLI version (expected, pinned): 0.147.0
- Model: gpt-5.6-luna
- Reasoning effort: xhigh
- Service tier: default

## Environment
- CODEX_HOME (container-local, MUST NOT be host-sourced): /home/vscode/.codex-protean
- Scoring working directory (empty, non-git, no AGENTS): /tmp/protean-score-empty
- Sandbox: read-only
- Container: the Protean devcontainer (no host ~/.codex mounted; no host HOME/config mounted; no host ~/.codex/AGENTS.md, rules, memories, history, skills, plugins, config.toml, auth.json)
- Authentication: not baked into image/repo; performed later explicitly via `codex login` into container-local CODEX_HOME (auth is not an experimental model call).

## Environment allowlist (variables the harness sets/permits)
Permitted/set by the harness:
- CODEX_HOME=/home/vscode/.codex-protean
- HOME=/home/vscode (existing container)
- PATH (container default, must resolve codex to the pinned 0.147.0)
- PYTHONPATH=src (for the Python harness, local only)
Permitted/ignored: none other. All other env is the container default. No host skill/plugin/memory/session environment.

## Container-local CODEX_HOME config.toml (/home/vscode/.codex-protean/config.toml) — EXACT
model = "gpt-5.6-luna"
model_reasoning_effort = "xhigh"
service_tier = "default"
default_tools_enabled = false
tools = []
disabled_tools = ["apply_patch", "exec_command", "web_search", "image_gen", "view_image", "spawn_agent"]
approval_mode = "never"
use_memories = false
generate_memories = false
model_messages = false
reminder_threshold_tokens = 1000000
include_skills_usage_instructions = false
include_plugin_usage_instructions = false

## Frozen invocation template (one `codex exec` process per case) — EXACT, no placeholders
codex exec \
  --ephemeral \
  --ignore-user-config \
  --ignore-rules \
  --skip-git-repo-check \
  --sandbox read-only \
  --cd /tmp/protean-score-empty \
  --model gpt-5.6-luna \
  --config 'model_reasoning_effort="xhigh"' \
  --config 'service_tier="default"' \
  --config 'default_tools_enabled=false' \
  --config 'tools=[]' \
  --config 'disabled_tools=["apply_patch","exec_command","web_search","image_gen","view_image","spawn_agent"]' \
  --config 'approval_mode="never"' \
  --config 'use_memories=false' \
  --config 'generate_memories=false' \
  --config 'model_messages=false' \
  --config 'reminder_threshold_tokens=1000000' \
  --config 'include_skills_usage_instructions=false' \
  --config 'include_plugin_usage_instructions=false' \
  --json \
  --output-last-message /tmp/protean-score-empty/last_message.txt \
  "<per-case scoring prompt text, assembled by the harness from the frozen scoring prompt (sha ae8f093a69a7bae6818421000490a14c8a19a4a6be33069a1858bf0a9d7f6909) + the case model-visible payload, per the existing prompt/case assembly mechanism>"

Execution contract: EXACTLY ONE fresh codex exec process per case. No reuse/resume/fork. No retry. If a correctly configured invocation yields an extra turn, a tool event, a malformed score, compaction/fork behavior, etc., that case is not retried and Stage 0 STOPs unless there is performance-blind evidence the harness itself violated its frozen specification (Protocol v1.0 mechanical-defect pathway, single restart).

## Expected JSON-event contract (assert-and-reject; structured, no substring guessing)
The harness consumes the full --json event stream and ACCEPTS the case score ONLY if ALL apply; otherwise STOP (no retry):
- exactly one "task_started" and exactly one "task_complete";
- exactly one "turn_started" and exactly one "turn_complete";
- exactly one "raw_response_completed" (no second model generation / compaction / fork / truncation-retry);
- exactly one "agent_message" whose text is a single decimal satisfying the frozen PLAIN_DECIMAL_V1 parse contract ((0\.[0-9]{2}|1\.00)\n?) in 0.00..1.00; else MODEL_FORMATTING_FAILURE => STOP;
- the separately captured final-message file equals the parsed decimal;
- ZERO of any of: exec_command_begin, apply_patch_begin, apply_patch_updated, apply_patch_end, mcp_tool_call_begin, mcp_tool_call_end, web_search, web_search_end, image_generation_begin, image_generation_end, view_image_tool_call, guardian_assessment (when it references a tool), dynamic_tool_call_request, dynamic_tool_call_response, collab_agent_spawn_begin, collab_agent_spawn_end, any "tool" firing event (sub_agent_activity, spawn_agents, mcp etc.);
- ZERO memory/skill/plugin injection markers (mementoprefix_compaction, generate_memories, include_skills_usage_instructions, include_plugin_usage_instructions);
- ZERO compaction/fork/continuation markers (context_compacted, thread_rolled_back, ForkHistory, replacement_history, auto_compact, window shift);
- required token/provenance events present: "token_count", and a model response ("agent_message") occurred.

## Version/provenance assertions
- The harness records codex --version (must equal 0.147.0) before and uses it as provenance;
- model/effort provenance from events where available;
- process exit status recorded (0 expected; any non-zero with the above contract not met => STOP).
