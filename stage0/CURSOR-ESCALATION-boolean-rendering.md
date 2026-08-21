# Cursor Escalation — Stage 0 Boolean-world-state textualization (bounded)

Owner: DeepSeek Flash (retaining ownership of the Stage 0 freeze-prep arc).
From: Kiro independent pre-score review result (FINDINGS).
Repo: alanmz-crypto/protean-environment, branch feat/2026-08-19-stage0-freeze-prep (no commits).
Starting main: 26eb0ce24674d2906569fa99a72e7329fe7e79e2.

## Problem (bounded, single subproblem)
Kiro found a systemic material defect in the candidate template bank / 80-case textualization: every named condition's observed value is rendered as a literal `true`/`false` token in the model-visible text. Because Stage 0 ground truth is a pure function of these values, the label is recoverable by token presence/count (artificially Boolean; inconsistent with §3.4 natural-language micro-world; literal `true` token label-correlated per structure). See `stage0/KIRO-REVIEW-RESULT.md`.

## Why I cannot fix it at my tier within authorization
The frozen, merged substrate `src/protean_stage0/textualize.py:_render_context` hard-substitutes `{p_now}`/`{q_now}`/`{p_previous}`/`{lifecycle}` with the literal strings `"true"`/`"false"`/lifecycle-value. A template-only rewrite cannot remove the naked Boolean tokens: it would require either
(a) a narrow, authorized rendering extension (e.g. adding natural-status slot values like `engaged`/`not engaged` driven by the same boolean), or
(b) an explicit representation decision (how to express truth-bearing world-state in the micro-world while keeping the model able to reconstruct each condition's value without a naked `true`/`false` token and without leaking the label).
Both are beyond my pre-score correction authority and would otherwise reopen settled implementation.

## Scoped request
Produce the smallest change, and the exact updated template-bank JSON (and substrate change if required and authorized by Ryan), so the regenerated 80-case textualization:
- keeps identical truth semantics (each case's structure/boolean values unchanged);
- renders each named condition's observed state in natural operational language WITHOUT the word `true`/`false` (e.g. "the gate release has engaged" / "has not engaged"; "the manifest stamp is signed/absent");
- rewords T2(P) template #2 trigger "must be true twice in a row" to natural persistence phrasing;
- harmonizes lifecycle naming into the micro-world;
- preserves the recorded seed rule `protean-stage0-v1:26eb0ce24674d290` so the regenerated set is deterministic;
- does NOT change any scientific decision, model selection, scoring prompt, or evaluation.

## Hand-back
A single solution with the revised template-bank file and revised candidate case-set hashes for me to re-run truth evaluators + mechanical validation and hand to Ryan. Do not commit/push. No Stage-0 scoring, no model calls, no performance inspection.
