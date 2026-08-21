# Codex (GPT-5.6 Luna) Stage-0 experimental-model qualification — evidence log

Date: 2026-08-19. Investigator: DeepSeek Flash (owning worker, Stage 0 freeze-prep arc). NO experimental/rehearsal model call made.

## 1. How ConvMem/global instructions inject into Codex CLI on this host
- Codex CLI is NOT innately aware of ConvMem (corpus-confirmed). It is taught via steering files in the Codex host config.
- The host `~/.codex/AGENTS.md` IS the ConvMem ritual file: it leads with "convmem — Local knowledge corpus", mandates `convmem doctor` / `brief --stdout-only` / `unresolved`, convmem branching/git-hygiene, Track-A indexing, forward-announcement, etc. This is loaded as global instructions by Codex on the host.
- Host `~/.codex/rules/default.rules` (execpolicy rules, 6.7 KB) and `~/.codex/memories/` (memory store) and `~/.codex/config.toml` (`model="gpt-5.6-sol"`, `model_reasoning_effort="high"`, plus [projects] trusted list incl. protean-environment) also live in the host Codex home.
- So on the HOST, a Codex invocation loads ConvMem instructions globally. This is exactly the cross-project contamination Stage-0 isolation must prevent.

## 2. Host Codex config/instruction/memory paths that matter
- ~/.codex/config.toml ; ~/.codex/AGENTS.md (ConvMem ritual) ; ~/.codex/rules/default.rules ; ~/.codex/memories/ ; ~/.codex/skills/ ; ~/.codex/plugins/ ; ~/.codex/auth.json ; ~/.codex/history.jsonl (input to ConvMem indexing)

## 3. Does ConvMem session indexing affect future prompt context automatically?
- NO. ConvMem indexing is ASYNCHRONOUS RETRIEVAL that is consulted explicitly (convmem "query" / convmem ask). It does NOT auto-inject context into Codex prompts. `~/.codex/history.jsonl` is an input path convmem watches/indexes (read side), but Codex does not pull convmem into its context unless a steering file (host AGENTS.md) instructs it to. Inside a container with no steering file and no host ~/.codex loaded, there is no injection.

## 4. What running Codex inside the Protean isolated devcontainer prevents from entering
- The container has HOME=/home/vscode (no ~/.codex), mounts only /workspaces/protean-environment. Absent: host ~/.codex/AGENTS.md (ConvMem ritual), config.toml, rules/default.rules, memories/, history.jsonl, skills, plugins, session/log/cache, auth.json. codex CLI is NOT currently installed in the container.

## 5. Local verification
- codex-cli 0.147.0 installed at /usr/bin/codex on host.
- `codex exec` exists with: -c key=value (config override; e.g. -c model=... / -c model_reasoning_effort=...), -m/--model, --ephemeral, --ignore-user-config, --ignore-rules, -p/--profile, -s/--sandbox (read-only|workspace-write|danger-full-access), --skip-git-repo-check, --json (events to stdout as JSONL), -o/--output-last-message <FILE>, --output-schema <FILE>.
- CODEX_HOME is a first-class env: used for $CODEX_HOME/config.toml, $CODEX_HOME/<name>.config.toml (-p profile), $CODEX_HOME/skills, $CODEX_HOME/themes. --ignore-user-config skips $CODEX_HOME/config.toml but auth still uses CODEX_HOME.
- Luna model ID: gpt-5.6-luna (display "GPT-5.6-Luna"). Supported reasoning efforts on the installed CLI: low|medium|high|xhigh|max. high and xhigh are both supported.
- Binary config surfaces include disabled_tools / enabled_tools / tools / default_tools_approval_mode / approval_mode / use_memories / generate_memories / default_tools_enabled — tools and memories can be toggled per invocation via -c.
- --json event stream includes: task_started, turn_started, turn_complete, task_complete, agent_message, agent_reasoning, mcp_tool_call_begin/end, exec_command_begin, apply_patch_begin, web_search, guardian_assessment, token_count, raw_response_item, raw_response_completed, agent_message_content_delta. => tool use and turn count ARE mechanically detectable/assertable.

## 6. container mounts / HOME / codex presence
- HOME=/home/vscode (clean); only /workspaces/protean-environment mounted; codex NOT installed in container; no ~/.codex in container home.

## 7. subscription auth in container-local CODEX_HOME
- Feasible in principle: set CODEX_HOME=/home/vscode/.codex-protean (container-local, not mounted from host), run `codex login` inside the container (browser/device-auth flows exist per binary strings) to populate auth in that dir; keep a minimal scoring config.toml there (model=gpt-5.6-luna, effort, disabled_tools, use_memories=false). Because CODEX_HOME is container-local and host ~/.codex is not mounted, host ConvMem AGENTS.md/rules/memories never load.

## 8. available Luna ID and high/xhigh
- gpt-5.6-luna; supported_reasoning_levels include high and xhigh (also low|medium|max). xhigh maps to the request-level "extra high reasoning depth".

## 9-10. can codex exec disable all tools / force single model decision; mechanical detection
- Tools: -c disabled_tools=[...] and/or default_tools_enabled=false; plus read-only sandbox + empty read-only -C cwd + --ephemeral + a no-tools prompt. This strongly suppresses tool-loop behavior.
- Multi-turn: NOT fully determinable from the binary alone whether one `codex exec` task maps to exactly one underlying model decision with zero internal tool/reasoning turns in ALL invocations, or whether agentic internals (e.g. planning/redo, model messages, compaction) can add turns. The --json turn_*/tool_* events give a mechanical ASSERTION, but a hard GUARANTEE of "one fresh isolated single-decision turn with no tool call ever" requires an authoritative Codex-internals answer. THIS IS THE NARROW QUESTION DELEGATED TO LUNA HIGH (see LUNAS-QUALIFICATION-QUESTION below).

## 11. Proposed frozen invocation skeleton (subject to Luna confirmation)
codex exec --ephemeral --ignore-user-config --ignore-rules --skip-git-repo-check \
  -s read-only -C /tmp/protean-score-empty \
  -m gpt-5.6-luna \
  -c 'model_reasoning_effort="xhigh"' \
  -c 'disabled_tools=["apply_patch","shell","mcp__*","web_search","image_gen"]' \
  -c 'use_memories=false' -c 'generate_memories=false' \
  --json -o <case_result_file> \
  "<per-case scoring prompt text>"
RUN INSIDE the Protean container with CODEX_HOME=/home/vscode/.codex-protean (container-local, no host .codex mounted).
Mechanical assertions from --json: exactly one turn_started..turn_complete; zero exec_command_begin / apply_patch_begin / mcp_tool_call_begin / web_search / guardian_assessment(with tool); exactly one agent_message whose text is a valid 0.00-1.00 decimal per the frozen parse contract; token_count present; no 'ForkHistory'/'compacted' event.

## Central question
Can Protean make each Stage-0 case ONE fresh isolated Luna scoring decision via codex exec using the container-local CODEX_HOME subscription, without ConvMem/project/session context and without agentic tool-loop behavior changing the experiment? ANSWERED: YES in design IF Luna confirms the single-turn/no-tool guarantee below; otherwise fall back to assert-and-reject via --json.
