# Kiro — Independent Stage 0 Pre-score Case Review Handoff

Status: READY FOR KIRO INDEPENDENT REVIEW (no Stage 0 scoring has occurred; no model-performance results exist and must not be requested).

## What to review
Independently review the frozen template bank and the textualized 80-case candidate set for Stage 0 of Prospective Control Experiment 1, per Protocol v1.0 §"Independent authorship" and Execution plan §7.1.

Artifacts (in this `stage0/` dir):
- `template-bank-v1.json` — the natural-language template bank (author: DeepSeek V4 Flash; authored from §3.4 semantics before any generated truth labels were inspected).
- `case-set-v1-review.json` — the 80 textualized candidate cases (each with case_id, structure_id, truth_label, and the 5 model-visible rendered fields).
- `case-set-v1.jsonl-canonical.json` — the frozen canonical case-set artifact bytes.
- `generation-provenance-v1.json` — seed rule, allocation, truth-agreement result, case-set hash.

## Review criteria (from §7.1)
Check each of the 80 textualized cases + the template bank for:
1. Semantic faithfulness to the structured spec (does the natural language express the frozen trigger condition correctly for each structure?).
2. Accidental truth leakage (could the wording reveal the truth label without reading the labeled state?).
3. Label-correlated vocabulary (any words that covary with positive/negative class beyond the required state values).
4. Systematic positive/negative style differences (positives and negatives must be comparable in style, register, and complexity).
5. Length/complexity imbalance between classes or structures.
6. Malformed or ambiguous textualization.

## Independence constraints
- You must NOT be given or request any Stage 0 model-performance results: no ROC-AUC, score distributions, confidence bounds, FP/FN, or any PASS/STOP outcome. None exist.
- Ground truth labels in `case-set-v1-review.json` are mechanical truth from the frozen grammar; your review judges textualization quality, not the labels themselves.
- Do not alter the case set or template bank; report findings for Ryan/implementer before any scoring.

## Deliverable
Return a written PASS / findings report per the six criteria above. If you find leakage, label-correlated wording, style/length imbalance, or malformed cases, name the specific case_id(s) and the fix. This review occurs before any Stage 0 scoring may begin.

## Focused question — Boolean-world-state check (added by Flash before delegation)

The current textualization renders named component conditions using literal natural-language state values "true" / "false" (e.g. "Observation of the dock sensor at this moment: true"). Determine whether this use is:

1. semantically faithful and neutral (the named world-condition's observed value, not a logical-notation leak);
2. an obvious lexical/logical shortcut that makes the model's task artificially Boolean;
3. a source of label-correlated vocabulary or structural cues;
4. inconsistent with the intended natural-language operational-commitment micro-world.

Do not reject it merely because the words "true" and "false" appear. Judge whether their actual use makes the model's task materially easier or less representative than the frozen Stage 0 semantics (§3.4) intend.

Treat all current Stage 0 artifacts as pre-review **candidate** artifacts, not finally frozen experimental artifacts. Do not make model calls or inspect performance.
