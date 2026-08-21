# Stage-1A Mechanical Readiness — Provenance Record

STATUS: READINESS RECORD (no Stage-1A execution). Zero model calls.

## Ratified authorities (frozen, immutable)

- **Protocol v1.0** (unchanged, frozen): SHA-256
  `dbe9d0a292ade61b980fa26045ed98c22c139f50e51836341687c2499c5481d4`
- **Ratified futility/shared-score amendment** (v1.0.1-r1): SHA-256
  `1a46b2cf9aeddd379fbca46e1ab9aaa660209c752885897b30d81589721cdf1f`
  — defines the shared-score authority (one experimental score per case, shared
    byte-identically by B and C) and the C threshold == 0.50 → DETERMINISTIC FUTILITY STOP.
  This is a **separate amendment**, never presented as part of the original
  preregistration; Protocol v1.0 is preserved unchanged.
- Review draft (superseded, kept for history):
  `ceb341d9c1b5a46e74f891db53df5365bf43140ce84a44a7215106592f3eddb7`

## Stage-1A case design (frozen)

- 60 calibration cases: P / P AND Q / P AND NOT Q / T2(P) / ACTIVE AND P,
  12 per structure, 6 positive / 6 negative each; 30 positive / 30 negative total.
- Immutable Stage-1A case-set SHA-256 (deterministic, generated from the frozen
  familiar grammar + the authorized template bank):
  `6851bf6f49f080ca3ede7938e207b835e5b3ac7cf531e3a460fb74393adecf41`
- Case-set count: 60.
- Truth is mechanically derived from structured state and independently
  recomputed (primary + reference evaluators agree on all 60).

## Authorship / truth provenance

- **Calibration textualization:** deterministic/programmatic reuse of the frozen
  Stage-0 template bank (`stage0/template-bank-v1.json`), which encodes the
  already-authorized familiar-structure semantics. No Stage-0 scores or
  performance influence wording/case selection/difficulty/distribution.
- **Truth evaluators:** the independently derived primary and reference
  evaluators (`src/protean_stage0/primary_truth.py`,
  `src/protean_stage0/reference_truth.py`) with recorded provenance.
- Luna does not participate in case authorship or truth evaluation.

## Stage-1B independence (frozen procedure, holdout cases NOT generated)

- Held-out independence procedure: `docs/HOLDOUT-INDEPENDENCE-STAGE1B-r1.md`
  (SHA-256 `4d2eb72e523981bb02d417f87fcabeb457afe50e24dcfc92d2acdcc193745b9e`).
- The future Stage-1B author/process must not receive Stage-1A scores, calibration
  results, the selected C threshold, or aggregate performance; it may receive only
  the frozen Protocol/grammar. The 400 actual held-out cases are generated later
  under separate authorization.

## Stage-1A machinery (implemented, hermetic)

- `src/protean_stage0/stage1a_config.py` — allocation, grid, futility, seed.
- `src/protean_stage0/stage1a_session.py` — minimal cross-session representation.
- `src/protean_stage0/stage1a_cases.py` — 60-case generation + truth agreement.
- `src/protean_stage0/stage1a_threshold.py` — 17-threshold selection + futility.
- `src/protean_stage0/stage1a_manifest.py` — sealed Stage-1A manifest.
- `src/protean_stage0/stage1a_driver.py` — shared-score loop (not live).
- `tests/test_stage1a.py` — 18 hermetic tests (balance, truth, shared score,
  B=0.50, 17 thresholds, tie-break, futility, no-Stage-1B-from-futility,
  seal mismatch, cross-session exclusion, holdout-isolation frozen).

## Cross-session representation

- Version: `stage1a-session-v1`.
- Each case crosses the boundary with only the authorized persisted fields
  (commitment, trigger_condition, prior_state, observed_event, lifecycle_state);
  the original conversation is never carried forward.

## Not performed / not authorized

- **No Stage-1A live execution** (the 60 experimental calls are not run).
- **No Stage-1B cases or execution.**
- **No Stage-0 artifact modified**; **no threshold-grid change**; **no tuning
  based on Stage-0 scores**.
- Luna calls = 0; DeepSeek API calls = 0.
