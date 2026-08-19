# GPT-5.6 Luna High — Codex-CLI single-decision isolation answer (received)

Date: 2026-08-19. Consultant lane: GPT-5.6 Luna High/xHigh (delegated by Flash, owner). NO model call / scoring invocation made.

## Bottom line
Each Stage-0 case = one fresh, isolated, tool-EXECUTION-free, single-TURN `codex exec` invocation is ACHIEVABLE, but "single model decision" and "zero tool events" are ASSERT-AND-REJECT properties, NOT mechanically absolute. Internal model_messages / AutoCompact / fork / guardian channels can add a model decision or emit a tool/guardrail event in an unlucky invocation. The harness MUST consume --json and auto-STOP on any violation (one permitted restart only for a documented harness defect per §13).

## Minimum guaranteed no-tool config (prevent execution side effects, data-invariant)
- -c disabled_tools=["apply_patch","shell","mcp__*","web_search","image_gen","spawn_agent"] + -c default_tools_enabled=false remove tools at the runtime tool-loading/approval layer (not by model compliance).
- -s read-only + EMPTY read-only -C cwd => even a permitted tool could not mutate cwd/workspace.
- MECHANICALLY PREVENTED: no execution side effect. NOT absolute at event level: a requested-but-denied tool may surface a begin event; guardian_assessment (a guardrail) can fire independently. => treat "zero tool events" as detect-and-reject (auto-STOP), not absolute.

## Single model decision — NOT absolute; assert-and-reject
- One exec task does NOT map to exactly one model decision with certainty: model_messages (extra messages per turn), AutoCompact/compaction (2nd model call), truncation/retry/fork (ForkHistory/replacement_history) can add decisions within one task.
- Strongest contract: freeze suppressors (-c model_messages=false, -c reminder_threshold_tokens=<very large>, --ephemeral) AND assert:
  - exactly one turn_started..turn_complete;
  - exactly one task_complete (+ task_started present);
  - exactly one raw_response_completed (>1 => multiple model generations);
  - exactly one agent_message whose text parses under PLAIN_DECIMAL_V1 (0.xx|1.00, trailing LF) => 0.00..1.00; else MODEL_FORMATTING_FAILURE => STOP;
  - zero compaction/ForkHistory/replacement_history/2nd model-decision markers;
  - token_count present; -o last-msg file equals same decimal.

## 8 residual isolation channels CLOSED (else open)
1 AGENTS.md/AGENTS.override.md discovery under -C cwd => run from EMPTY cwd, no AGENTS files; --ignore-rules is NOT sufficient for AGENTS discovery.
2 git repo state => --skip-git-repo-check AND empty non-repo -C cwd.
3 prior-session resume / replacement_history => fresh/wiped container-local CODEX_HOME per run + --ephemeral; never host ~/.codex.
4 skills/plugins usage-instruction injection (include_skills_usage_instructions/_plugin default true) => empty CODEX_HOME skills/plugins + -c include_skills_usage_instructions=false + -c include_plugin_usage_instructions=false.
5 memories => -c use_memories=false + generate_memories=false + empty CODEX_HOME memories/.
6 realtime background context (thread/workspace-scan) => --ephemeral + empty non-git cwd.
7 host ConvMem ~/.codex (AGENTS.md=ConvMem ritual, config.toml, rules, memories, history, skills, plugins, auth) => container-local CODEX_HOME not mounted + --ignore-user-config + --ignore-rules.
8 inherited dirty env => minimal clean env; don't mount anything unnecessary.

## Effort: high vs xhigh
Neither gives bit-level determinism; reproducibility from the single-decision/assert contract, not effort. Recommendation: freeze xhigh once (do not flip between cases). (If Ryan picks high, same assertion set.)

## Minimal container-local CODEX_HOME config.toml (/home/vscode/.codex-protean/config.toml)
model = "gpt-5.6-luna"
model_reasoning_effort = "xhigh"
default_tools_enabled = false
disabled_tools = ["apply_patch","shell","mcp__*","web_search","image_gen","spawn_agent"]
tools = []
approval_mode = "never"
use_memories = false
generate_memories = false
model_messages = false
reminder_threshold_tokens = 1000000
include_skills_usage_instructions = false
include_plugin_usage_instructions = false

## Frozen command (inside Protean container, CODEX_HOME=/home/vscode/.codex-protean container-local)
codex exec --ephemeral --ignore-user-config --ignore-rules --skip-git-repo-check \
  -s read-only -C /tmp/protean-score-empty -m gpt-5.6-luna \
  -c 'model_reasoning_effort="xhigh"' -c 'default_tools_enabled=false' \
  -c 'disabled_tools=["apply_patch","shell","mcp__*","web_search","image_gen","spawn_agent"]' \
  -c 'use_memories=false' -c 'generate_memories=false' -c 'model_messages=false' -c 'approval_mode="never"' \
  --json -o /tmp/protean-score-empty/last_message.txt \
  "<per-case scoring prompt text>"

## Preconditions (fail => STOP before any call)
CODEX_HOME empty of skills/plugins/memories/history/replacement_history/AGENTS*; auth.json present; host ~/.codex not mounted;
-C /tmp/protean-score-empty empty + not a git repo + no discoverable AGENTS*;
prompt == frozen manifest.scoring_prompt_sha256; model-config hash == manifest; parse contract == PLAIN_DECIMAL_V1_SHA256;
case_id -> one fresh exec; NEVER reuse a session.

## Post-invocation accept/auto-STOP assertions (score accepted ONLY if all hold; else STOP; never retry)
1 exactly one task_started + task_complete; 2 exactly one turn_started..turn_complete; 3 exactly one raw_response_completed (no 2nd gen/compaction/fork); 4 exactly one agent_message parsing to 0.00..1.00 else MODEL_FORMATTING_FAILURE=>STOP; 5 ZERO exec_command_begin/apply_patch_begin/mcp_tool_call_*/web_search/tool/guardian_assessment(tool) => auto-STOP (assert-and-reject); 6 token_count present; 7 no model_messages/skills/plugin/memory-injection; 8 -o last-msg == parsed decimal.

## Honesty note
Absolute "one decision, no tool by construction" for EVERY invocation overstates what codex-cli 0.147.0 can mechanically certify. The achievable guarantee is the assert-and-reject contract above.
