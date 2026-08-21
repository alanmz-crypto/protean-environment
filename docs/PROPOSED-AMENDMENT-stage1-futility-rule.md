# PROPOSED AMENDMENT — Stage 1A → 1B Futility Rule (DRAFT for review)

**STATUS: PROPOSED REVISION — NOT RATIFIED. FROZEN FOR REVIEW ONLY.**
This is a **separate proposed amendment/revision document**. It is NOT an edit
to PROTOCOL v1.0 and must never be presented as if it were originally in the
frozen protocol. Protocol v1.0 remains frozen until Ryan (with review) ratifies
a separately documented revision.

**Proposed classification banner (do not drop):** this amendment is a futility /
decision-identity rule, not an evidence claim. It does NOT confer Strong or
Suggestive evidence. Its classification recommendation (below) is a flag for
Ryan approval, not an assumption of authority.

---

## 1. Why this rule exists (decision identity)

- Arm B uses a fixed threshold of `0.50` for every score, permanently.
- Arm C selects **one** calibration threshold from the grid
  `0.10, 0.15, …, 0.90` via the preregistered rule (maximize calibration
  balanced accuracy; tie → closest to 0.50; remaining tie → higher threshold).
- B and C otherwise receive identical model scores and identical information
  (PROTOCOL v1.0 § Equal persistent information).

Therefore, **if Stage 1A mechanically selects C threshold = 0.50**, then for
every held-out score `s`:

```text
B(s) = [s >= 0.50]
C(s) = [s >= 0.50]
```

so `B(s) = C(s)` for every held-out case. Consequently:

- the C−B balanced-accuracy difference is necessarily `0`;
- McNemar discordant pairs are necessarily `0`;
- the preregistered `+15` percentage-point practical-effect requirement cannot
  be met;
- spending the 400 held-out model calls cannot change that conclusion.

## 2. Proposed rule (exact language)

> After the frozen Stage-1A calibration procedure is completed, if Arm C's
> selected threshold is exactly `0.50`, Stage 1B is NOT executed. Because Arm B
> also uses `0.50` and the two arms otherwise receive identical scores and
> information, the arms are mechanically decision-identical. The scalar-threshold
> adaptation mechanism therefore cannot produce the preregistered positive B-vs-C
> effect in this experiment.

## 3. Binding conditions (must all hold or the rule does not apply)

1. The rule must be **frozen before any Stage-1A results exist**.
2. It cannot depend on whether Stage-1A scores look favorable or unfavorable.
3. It applies **only** when the selected C threshold is exactly `0.50`; no other
   threshold value (e.g. 0.45 or 0.55) invokes it.
4. It does not permit changing the threshold grid or the tie-breaking rule.
5. It does not authorize a richer adaptive mechanism.

A materially different or more capable mechanism requires a new protocol /
preregistration, per PROTOCOL v1.0 § Stopping discipline.

## 4. Conservative classification recommendation (flag for Ryan/ChatGPT approval)

Under PROTOCOL v1.0 vocabulary this result is best read as **Negative for the
preregistered practical hypothesis** (C−B is deterministically `0`, so the
`+15`pp practical-effect and any paired effect cannot be positive), consistent
with the Stopping-discipline statement *"Valid powered C≈B: reduce confidence
in this scalar-threshold adaptation mechanism."*

It is explicitly **not** Strong or Suggestive evidence, and it is not a claim
that the effect is *exactly* zero in any adaptive sense — only that this
scalar-threshold adaptation cannot produce it. Ryan and (where applicable)
ChatGPT review approval is required before this classification is treated as
established; this document does not self-ratify it.

## 5. Freeze statement

FROZEN Protocol v1.0 is not altered in place by this document. If ratified, this
amendment becomes a separately documented protocol revision superseding v1.0 for
the Stage-1A→1B decision only, prior to any Stage-1A execution.
