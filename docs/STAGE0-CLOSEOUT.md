# Stage 0 — Durable Closeout Record

Status: CLOSED (Stage 0 PASS). Immutable record of the completed Stage 0.
This is a historical record; it does not alter any raw artifact.

## Completed run

- run ID: `stage0-restart-7ce316213719-20260821T010551860444Z`
- manifest SHA-256: `9af786c5702ea3697cf1fefb4dd46b084263aef4b9b3dcfc8046adf449952931`
- case-set SHA-256: `7099a821c74397bff188a630ed9ca84c8aeed6185947ef99bda0c7a66ef1a03e`
- raw-results SHA-256: `e1b1311ca18387a0dd799abe949ebd88d502ccdffa72a246d18f70e2ea692da4`
- analysis code revision: `7ce3162137195de5918391b02aac4340a4c92551`

## Result (frozen gate, per PROTOCOL v1.0)

- 80 / 80 VALID_SCORE
- 40 positive / 40 negative
- ROC-AUC = 1.0
- DeLong variance = 0.0
- one-sided 95% DeLong lower bound = 1.0
- **decision: PASS** (all positives scored 1.00; all negatives scored 0.00)

Frozen Stage 0 PASS rule satisfied: ROC-AUC = 1.0 ≥ 0.60 AND one-sided 95% lower bound = 1.0 > 0.50.

## Restart history

- Original attempted run: preserved and immutable (`failed raw e893b950…`, original manifest `f756daec…`).
- The single permitted Stage-0 restart was consumed as **HARNESS_IMPLEMENTATION_DEFECT** (mechanical, performance-blind).
- `restarts_used == 1`; **no restart remains**.

## Integrity / discipline

- No prompt tuning.
- No case removal (all 80 used; 40/40 intact).
- No alternate metric substituted for the frozen gate.
- No subgroup rescue.
- No response shopping / model shopping.
- Raw results analyzed by the exact frozen `analyze_stage0()` implementation at the recorded analysis revision.

## What Stage 0 establishes

Stage 0 establishes **only** that the frozen frontier model exposes a highly
discriminative prospective-trigger applicability signal under the frozen
Stage-0 framing.

It does **not** establish historical adaptation, persistence benefit, or any
Protean architecture claim. See PROTOCOL v1.0 § "Explicit nonclaims".
Stage 0 is a raw-signal qualification, not an effect demonstration.
