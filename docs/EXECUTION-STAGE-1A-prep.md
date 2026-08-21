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
- **Shared-score authority (frozen — a protocol-revision clarification, not
  silently implied by v1.0):** each Stage-1 case receives **exactly one**
  experimental-model applicability-scoring call. Its **single raw applicability
  score is shared byte-identically by Arms B and C**; the arms do not make
  independent scoring calls and differ only in the threshold mechanically applied
  to that same score. This is necessary for the C = `0.50` → B = C futility
  proof (see the proposed futility amendment).

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
independent natural-language authorship. Audit for lexical/style shortcuts.

**Holdout preparation boundary (frozen):** **before** the first Stage-1A
execution, the **independent holdout authorship/generation procedure, its
provenance separation, and its information-isolation rule must be frozen** so
that holdout authors/process are structurally unable to access Stage-1A outputs
(calibration scores or results). This does **not** require the 400 actual
held-out cases to be generated before Stage 1A unless another protocol
requirement alone demands it; what is frozen first is the *procedure and
isolation* (who/how the holdout is authored, how it is provenance-separated,
and that it never sees Stage-1A outputs), not the cases themselves.

## 6. Unresolved scientific choices (enumerated, not decided)

| Open item | Description | Must resolve before |
|-----------|-------------|---------------------|
| Stage 1A case-set generation spec | Exact 60-case calibration set composition/seed under the frozen grammar | any Stage-1A execution |
| Stage-1A authorship provenance | Which independent author/provides the 60 calibration textualizations; provenance record | any Stage-1A execution |
| 17-threshold selection machinery | Deterministic implementation of the frozen grid selection rule + 1pp-neighborhood reporting (grid itself is PREREGISTERED in Protocol v1.0: 0.10..0.90) | before Stage-1A execution (mechanical, not scientific) |
| Equal-call / equal-information guarantee | Harness guaranteeing B and C get byte-equivalent input and one identical model score per case (see Shared-score authority) | before Stage-1A execution |

## 7. Blind defect-scope preregistration (for the later Stage-1B unblinding)

Protocol v1.0 § Blind defect-scope determination requires objective defect
criteria to be preregistered **before Stage-1B is unblinded**, covering
ground-truth error, authoring leakage, split contamination, malformed cases,
and harness defects. This plan does not unblind anything; it flags that the
defect-scope criteria must be authored and frozen before Stage 1B. A
genuinely independent reviewer (blinded to B/C/novelty/familiar aggregate
performance) is required if a defect is later suspected.

## 8. Hidden Stage-1 blockers audit (corrected)

### Must be resolved before the first 60 Stage-1A model calls

| Requirement | Already implemented | Missing | Must resolve before |
|-------------|--------------------|---------|---------------------|
| Stage-1A case-generation spec | No | No frozen 60-case Stage-1A generation/authorship authority | first 60 Stage-1A calls |
| Stage-1A authorship provenance | No | No independent-author record for the 60 calibration textualizations | first 60 Stage-1A calls |
| 17-threshold selection machinery | No | No deterministic implementation of the frozen grid selection + tie-break + 1pp-neighborhood reporting | Stage-1A execution |
| Equal-information / equal-model-call guarantee (B vs C) | No | No harness guarantee of byte-equivalent input and one identical shared model score per case (Shared-score authority) | Stage-1A execution |
| Cross-session representation | Partial (substrate case schemas) | No Stage-1 session-persistence/representation authority | Stage-1A execution |
| Holdout procedure/information-isolation (frozen) | No | No frozen independent holdout authorship/generation procedure, provenance separation, and information-isolation rule | before any Stage-1A execution (procedure only, not the 400 cases) |

### Must be resolved before Stage 1B (not Stage 1A)

| Requirement | Already implemented | Missing | Must resolve before |
|-------------|--------------------|---------|---------------------|
| Stage-1B independently authored holdout cases | No | No separate-author 400-case holdout set (procedure frozen before Stage-1A; the actual cases are generated later) | Stage-1B execution |
| Blind defect-scope criteria | No | No frozen objective defect criteria / independent-reviewer procedure | Stage-1B unblinding |
| Held-out familiar vs novelty generation | No | No 200-familiar / 200-novel (N1–N4) holdout generation spec | Stage-1B |
| Exact McNemar / guardrail analysis machinery | No | No Stage-1B exact paired McNemar/binomial + FP/FN guardrail implementation | Stage-1B analysis |

The 17-threshold grid (0.10..0.90) and its tie-break are **already frozen in
Protocol v1.0** and are not blockers. No Stage-1A or Stage-1B work is authorized
to begin until the "before Stage-1A" rows above are resolved under separate
authorization.
