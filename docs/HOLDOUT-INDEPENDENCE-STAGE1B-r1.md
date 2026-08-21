# Stage-1B Holdout Independence Procedure (FROZEN — r1)

**STATUS: FROZEN as a procedure.** This does **not** generate the 400 held-out
cases. It freezes the independence/isolation procedure that the Stage-1B holdout
author/process must satisfy. It is separate from the Stage-1A calibration
authorship.

## Purpose

Stage-1B textualization must be **genuinely independently authored** from
Stage-1A (PROTOCOL v1.0 § Independent authorship). This is not solved by
re-seeding the same model or reusing the Stage-1A calibration text with superficial
changes.

## Isolation requirements (the future holdout author/process)

The future Stage-1B holdout author/process:

- MUST NOT receive Stage-1A scores;
- MUST NOT receive Stage-1A calibration results;
- MUST NOT receive the selected C threshold;
- MUST NOT receive Stage-1A aggregate performance;
- MAY receive only the frozen Protocol/grammar and the information required to
  author valid holdout cases (structures P/P AND Q/P AND NOT Q/T2(P)/ACTIVE AND P
  for familiar, and N1–N4 for novelty, per Protocol v1.0).

## Provenance / isolation mechanism

To prove isolation:

1. A provenance record identifies the Stage-1B author/process, its creation time,
   and its input allowlist (only the frozen grammar/spec, never Stage-1A outputs).
2. No Stage-1A output artifact (scores, calibration results, selected threshold,
   aggregate metrics) is ever made available to the Stage-1B author/process at
   any point.
3. A deterministic audit check confirms Stage-1B textualization was produced
   from the frozen grammar alone and shares no Stage-1A case text.

This procedure (this document) is immutable and referenceable by digest. The 400
actual held-out cases are generated later, under separate authorization, using
this frozen procedure.
