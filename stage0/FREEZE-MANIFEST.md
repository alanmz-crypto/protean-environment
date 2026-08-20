# Stage 0 — Frozen Artifact & Provider Integration Manifest

Status: FROZEN (freeze/integration; NO experimental scoring authorized yet).
Branch: feat/2026-08-19-stage0-freeze-prep

## Experiment artifacts — FROZEN (Ryan decision)
- Template bank `stage0/template-bank-v1.json` sha 295fe92fe12ba14470166d6b160492fb1564d29b06dc46500f8b2cbfdf73c758
- Canonical case-set `stage0/case-set-v1.jsonl-canonical.json` sha 06fe8d471b1fbbc226696ed6d80b706cc84a6040a7fb91a93814343420291556
- Scoring prompt `stage0/candidate-scoring-prompt-v1.txt` (APPROVED/FROZEN by Ryan; sha ae8f093a69a7bae6818421000490a14c8a19a4a6be33069a1858bf0a9d7f6909)
- Case-review listing `stage0/case-set-v1-review.json` (80 textualized) sha 92e3dbd01ed39862a67fc6025678a07aa06902b4cb20f2ca00dc240e1dd8fa1a

## Independent reviews (preserved)
- Kiro rev1 `stage0/KIRO-REVIEW-RESULT.md` (FINDINGS -> repair) sha 312cfcac752a6f27bc81c3f6694e7d38ad3798879b56e16c44413b6015ca1a0d
- Kiro rev2 `stage0/KIRO-REVIEW-RESULT-REV2.md` (PASS) sha 13ae5f142974b38b1d0576bcc151321a1ede9cf65078061850f34ada8712d5a2
- Codex/Luna qualification `stage0/CODEX-LUNA-QUALIFICATION.md` sha 772fbbc28d5b6fd1e3fded425b11dac9beb01074244fbedfb63462f5fd3245e4
- Luna High answer `stage0/LUNA-QUALIFICATION-ANSWER.md` sha a019fc2a04733281796664665a24c97720980b00fed822c40d042cebf43e96a8
- Frozen Codex config `stage0/luna-xhigh-frozen-config.md` sha 01c78ae112b651cdfa39e627007621e6f08aa87f5d3cf1ad977ce92d065bf022
- Cursor escalation `stage0/CURSOR-ESCALATION-boolean-rendering.md` sha 3c5c48709a066cc149631a7712073776246f07651b2f1089b144073b8b160a25

## Provider freeze
- OpenAI Codex CLI via Ryan ChatGPT subscription; pinned codex-cli 0.147.0 in devcontainer; model gpt-5.6-luna; reasoning effort xhigh; container-local CODEX_HOME=/home/vscode/.codex-protean; empty scoring cwd /tmp/protean-score-empty; read-only sandbox; ephemeral; no tools; no memories; no model_messages; --ignore-user-config --ignore-rules; assert-and-reject --json contract.

## Integration modules
- src/protean_stage0/codex_config.py (frozen literal invocation config)
- src/protean_stage0/codex_adapter.py (CodexModelClient, event-parser, contract)
- tests/test_codex_adapter.py (accepted fixture + all negative fixtures)
- devcontainer: codex pinned, container-local CODEX_HOME config (no baked auth)

## Zero live calls
No experimental/rehearsal provider call made. Adapter uses fakes for tests. Devcontainer build does not authenticate.
