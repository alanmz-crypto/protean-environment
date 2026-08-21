# Stage 1A — Execution Plan (PREPARATION ONLY, HITL-gated)

**STATUS: PREPARATION — NOT AUTHORIZED FOR EXECUTION.**
This plan bounds the Stage-1A execution. **No Stage-1A (or any) model call is
authorized by this task.** Do not execute it.

Scope: Stage 1A only, per PROTOCOL v1.0 § "Stage 1A — calibration/history".
Stage 1B is explicitly out of scope here and is not implemented or run.

---

## 1. Bounded Stage-1A design

- Exactly **60** calibration/history decisions.
- **B** begins and remains at threshold `0.50`.
- **C** begins at `0.50`.
- **B and C receive identical raw information and identical model scores.**
  The only intended difference is that C may adapt its threshold from the
  60 collected decisions (PROTOCOL v1.0 § Equal persistent information).

## 2. Procedure (post-outcome, mechanical)

1. Run 60 calibration/history decisions (B and C receive the same cases/scores).
2. Mechanically verify outcomes (ground truth via an independent deterministic
   evaluator; no model self-grading).
3. Apply B at fixed `0.50`. For C, evaluate **exactly** the frozen 17-threshold
   grid.
4. Selection rule for C (frozen, not tunable):
   - highest calibration balanced accuracy;
   - tie → closest to `0.50`;
   - remaining tie → higher threshold.
5. Publish the complete 17‑threshold curve:
   - balanced accuracy at each threshold;
   - FP rate at each;
   - FN rate at each;
   - the selected threshold;
   - the second-best threshold;
   - every threshold within 1 percentage point of the maximum.
6. Freeze the selected C threshold before any Stage-1B held-out work begins.

## 3. HITL boundary

- **No Stage-1A model calls, case generation, or execution are authorized here.**
- This is a plan for review and subsequent authorization.

## 4. Case generation — not performed now

- Do not generate Stage-1A cases in this task **unless existing repository
  authority already fixes their exact generation/authorship process**
  mechanically.
- Where the frozen protocol leaves a scientific choice unresolved, this plan
  **enumerates** it rather than choosing it (see §6 unresolved choices).

## 5. Independent-authorship requirement (critical)

PROTOCOL v1.0 § Independent authorship requires that **calibration and
held-out textualization come from genuinely independent authorship processes**.
NOT acceptable: the same model with a different seed, a second pass, superficial
renaming, or the same template disguised as separate authorship.

This is a hard constraint. This plan does not solve it by re-seeding the same
author/template. Acceptable independence may include: different providers/model
families; human vs model; independent humans; programmatic generation vs an
independent natural-language authorship. Holdout authorship must not access
calibration outputs. Audit for lexical/style shortcuts.

## 6. Unresolved scientific choices (enumerated, not decided)

| Open item | Description | Must resolve before |
|-----------|-------------|---------------------|
| Stage 1A case-set generation spec | Exact 60-case calibration set composition/seed under the frozen grammar | any Stage-1A execution |
| Stage-1A authorship provenance | Which independent author/provides the 60 calibration textualizations; provenance record | any Stage-1A execution |
| Threshold-grid authority | The 17-threshold grid (0.10..0.90) is stated in task/plan, not verbatim in Protocol v1.0 — should be re-pinned in the ratified revision | Stage-1A selection is frozen |
| 17-threshold selection machinery | Deterministic implementation of the selection rule + 1pp-neighborhood reporting | before Stage-1A execution (mechanical, not scientific) |
| Equal-call / equal-information guarantee | Harness guaranteeing B and C get byte-equivalent input; same model score per case | before Stage-1A execution |

## 7. Blind defect-scope preregistration (for the later Stage-1B unblinding)

Protocol v1.0 § Blind defect-scope determination requires objective defect
criteria to be preregistered **before Stage-1B is unblinded**, covering
ground-truth error, authoring leakage, split contamination, malformed cases,
and harness defects. This plan does not unblind anything; it flags that the
defect-scope criteria must be authored and frozen before Stage 1B. A
genuinely independent reviewer (blinded to B/C/novelty/familiar aggregate
performance) is required if a defect is later suspected.

## 8. Hidden Stage-1 blockers audit

| Requirement | Already implemented | Missing | Must resolve before |
|-------------|--------------------|---------|---------------------|
| Calibration (Stage-1A) case-generation spec | No | No frozen 60-case Stage-1A generation/authorship authority | any Stage-1A execution |
| Stage-1A authorship provenance | No | No independent-author record for the 60 calibration textualizations | any Stage-1A execution |
| Stage-1B independently authored holdout | No | No separate-author 400-case holdout process (independent of calibration) | any Stage-1A / Stage-1B |
| 17-threshold selection machinery | No | No deterministic implementation of grid selection + tie-break + 1pp-neighborhood reporting | Stage-1A execution |
| Equal-information / equal-model-call guarantee (B vs C) | No | No harness guarantee that B and C receive byte-equivalent input and one identical model score per case | Stage-1A execution |
| Cross-session representation | Partial (Substrate has case schemas) | No Stage-1 session-persistence/representation authority | Stage-1A execution |
| Blind defect-scope criteria (before Stage-1B unblind) | No | No frozen objective defect criteria / independent-reviewer procedure | before Stage-1B unblinding |
| Held-out familiar vs novelty generation | No | No 200-familiar / 200-novel (N1–N4) holdout generation spec | before Stage-1B |
| Exact McNemar / guardrail analysis machinery | No | No Stage-1B exact paired McNemar/binomial + FP/FN guardrail implementation | before Stage-1B analysis |

All rows are unresolved; none are satisfied by existing repository work. No
Stage-1A or Stage-1B work is authorized to begin until the necessary rows above
are resolved under separate authorization.
