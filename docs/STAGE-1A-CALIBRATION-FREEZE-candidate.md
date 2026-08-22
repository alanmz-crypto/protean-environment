# Stage 1A — Calibration Threshold Freeze (CANDIDATE — NOT RATIFIED)

STATUS: **CANDIDATE for Ryan review — UNCOMMITTED, not authoritative.** This is a
candidate closeout/freeze record produced mechanically from the existing frozen
threshold machinery. It does not establish a new scientific storage convention and
does not alter any protocol, amendment, source code, or Stage-1B surface. No prior
canonical Stage-1A threshold-freeze artifact or path existed in the repository;
this document is proposed for review only.

Science discipline: this binds preregistered calibration quantities only. It makes
no exploratory interpretation, causal explanation, architecture inference, or
post-hoc analysis. Stage 1B is NOT authorized.

## Source calibration authority

- source batch: `calibration-9fe9d4e05803-20260822T022931681360Z`
- source manifest SHA-256: `77d301db3e240b8a244ef41d0f113fadf385a072097d5be5419295878f6d6254`
- source completed-calibration SHA-256: `65850d3b608fc5294e5e0a2b8c51a40f4f10b4b4bcd7312107e41f2bece595d8`
- established execution: 60/60/0 COMPLETED; 60 requests total; one request per case; zero retries.
- analysis repository revision: `8df8d7da363718dff9b8d9b1f850c57fdbe2807e`

## Frozen rules (PROTOCOL v1.0 + ratified futility amendment)

- B threshold = exactly `0.50`.
- C evaluates exactly 17 thresholds: `0.10, 0.15, ..., 0.90`.
- per-threshold: balanced accuracy, FP rate, FN rate.
- C selection: (1) maximum balanced accuracy; (2) tie -> closest to `0.50`;
  (3) remaining tie -> higher threshold.
- second-best: repository rule (re-select over the remaining 16 with same rule).
- within-1pp: every threshold within 1 percentage point of the maximum.
- futility: selected C == `0.50` -> DETERMINISTIC_FUTILITY_STOP; Stage 1B not reachable.

## Complete 17-threshold curve (frozen order)

| threshold | balanced accuracy | FP rate | FN rate |
|-----------|-------------------|---------|---------|
| 0.10 | 1.0 | 0.0 | 0.0 |
| 0.15 | 1.0 | 0.0 | 0.0 |
| 0.20 | 1.0 | 0.0 | 0.0 |
| 0.25 | 1.0 | 0.0 | 0.0 |
| 0.30 | 1.0 | 0.0 | 0.0 |
| 0.35 | 1.0 | 0.0 | 0.0 |
| 0.40 | 1.0 | 0.0 | 0.0 |
| 0.45 | 1.0 | 0.0 | 0.0 |
| 0.50 | 1.0 | 0.0 | 0.0 |
| 0.55 | 1.0 | 0.0 | 0.0 |
| 0.60 | 1.0 | 0.0 | 0.0 |
| 0.65 | 1.0 | 0.0 | 0.0 |
| 0.70 | 1.0 | 0.0 | 0.0 |
| 0.75 | 1.0 | 0.0 | 0.0 |
| 0.80 | 1.0 | 0.0 | 0.0 |
| 0.85 | 1.0 | 0.0 | 0.0 |
| 0.90 | 1.0 | 0.0 | 0.0 |

## Result

- selected C threshold: `0.50`
- second-best threshold: `0.55`
- thresholds within 1pp of maximum: all 17 (`0.10..0.90`)
- B threshold: `0.50`
- Stage-1B projection: `DETERMINISTIC_FUTILITY_STOP`

## Futility decision

selected C threshold == `0.50` -> projection is `DETERMINISTIC_FUTILITY_STOP`;
Stage 1B is NOT reachable. This is a mechanical projection only; it is not
overridden or reinterpreted here.

## Verification

- exactly 17 evaluations; grid `0.10..0.90` step `0.05`.
- selected threshold belongs to the frozen grid.
- selected, second-best, within-1pp, and projection each rederive under the frozen
  rules from the same completed authority.
- source authority digests unchanged; no model/API calls; no run artifact modified.

## Boundary

- This is a candidate freeze record. Ratification, if any, is Ryan's.
- Stage 1B and scientific interpretation beyond the preregistered quantities above
  remain NOT AUTHORIZED.
