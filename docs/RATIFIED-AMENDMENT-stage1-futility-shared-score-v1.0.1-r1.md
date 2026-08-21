# RATIFIED AMENDMENT — Stage-1 Shared-Score Authority and Futility Rule (v1.0.1-r1)

STATUS: **RATIFIED** (Ryan/HITL ratification).
This is a **separately identified ratified revision** of PROTOCOL prospective-control-v1.0. It is **NOT** part of the original preregistration; Protocol v1.0 remains the frozen original (unchanged). This amendment becomes effective only for the Stage-1A→1B decision, prior to any Stage-1A execution, and only if separately recorded as ratified by Ryan.

## Ratification provenance

- Ratifying commit HEAD: `a154040c0d3a7d5aff20d3a2ffe680d6825a6443`
- Based on review draft: `docs/PROPOSED-AMENDMENT-stage1-futility-rule.md`
- Protocol v1.0 filenote: unchanged and preserved.
- This document SHA-256: `[FILLED AT FREEZE]` (see footer).

This amendment is ratified by Ryan/HITL and is not self-ratified by any agent.

## 1. Shared-score authority (ratified)

Each Stage-1 case receives **exactly one** experimental-model applicability-scoring
call. Its **single raw applicability score is consumed byte-identically by Arms B
and C**. The two arms do not make independent model-scoring calls. B and C differ
only in the threshold that is mechanically applied to that same shared raw score.

This is a **protocol-revision clarification**, not something silently implied by
Protocol v1.0. It is a necessary precondition for the C = 0.50 → B = C futility
proof: if B and C each made their own scoring calls, their per-case scores could
differ and B = C would not follow from a common threshold.

## 2. Futility rule (ratified)

> After the frozen Stage-1A calibration procedure is completed, if Arm C's
> selected threshold is exactly `0.50`, Stage 1B is NOT executed. Because Arm B
> also uses `0.50` and the two arms otherwise receive identical scores and
> information, the arms are mechanically decision-identical. The scalar-threshold
> adaptation mechanism therefore cannot produce the preregistered positive B-vs-C
> effect in this experiment.

Binding conditions (all must hold):

1. Frozen before any Stage-1A results exist (this ratification precedes Stage-1A execution).
2. The rule cannot depend on whether Stage-1A scores look favorable.
3. It applies only when the selected C threshold is exactly `0.50`; no other value invokes it.
4. It does not permit changing the threshold grid or tie-breaking rule.
5. It does not authorize a richer adaptive mechanism; a materially different mechanism requires a new protocol/preregistration.
6. It does not change the 17-threshold grid, which is already frozen in Protocol v1.0 (`0.10, 0.15, …, 0.90`).

## 3. Outcome classification when the rule fires — DETERMINISTIC FUTILITY STOP

When C selects exactly `0.50`, the outcome is a **DETERMINISTIC FUTILITY STOP**:

- C selected the same `0.50` policy as B;
- with shared per-case scores, B and C are decision-identical;
- Stage 1B cannot produce a B-vs-C advantage and is therefore not run;
- this is **not** Strong, Suggestive, Negative, or Invalid under the original
  Stage-1 evidence classifications, because the powered Stage-1B study was not
  executed;
- it reduces confidence in this fitted scalar-threshold adaptation mechanism but
  makes no broader null claim.

## 4. Freeze statement

FROZEN Protocol v1.0 is not altered in place by this document. This ratified
revision governs the Stage-1A→1B decision only. It is separately identified here
with a dedicated SHA and is not presented as part of the original preregistration.

## 5. Ratified-as-recorded hash

The immutable ratified hash of this document (SHA-256 of the exact ratified file
bytes) is recorded in the Stage-1A ratification provenance record and is bound in
the Stage-1A manifest. It is never presented as the Protocol v1.0 hash.

