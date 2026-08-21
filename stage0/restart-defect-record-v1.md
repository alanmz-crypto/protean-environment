# Stage 0 — Single Restart Defect Record (HARNESS_IMPLEMENTATION_DEFECT)

Status: RECORDED — consumes the single permitted Stage-0 restart allowance per
Protocol v1.0 section 13 (mechanical-defect pathway). **No live execution, no
scoring, no AUC/DeLong performed.**

## Defect kind

`MechanicalDefectKind.HARNESS_IMPLEMENTATION_DEFECT`

## Exact documented reason

The original Stage-0 harness collapsed materially different failure modes into
`provider_api_failure` and discarded provider-response/error evidence, making
the failed attempt non-adjudicable. This was corrected by commits `752382c...`
(typed provider-failure classification + DeepSeek dev lane) and `9d8b7b3...`
(classify only typed provider failures in the decision loop).

This is a **mechanical harness implementation defect** (Protocol §9.1, §13),
not a statement about billing/payment.

## Evidence (performance-blind)

| Field | Value |
|-------|-------|
| invalidated original case-set SHA | `06fe8d471b1fbbc226696ed6d80b706cc84a6040a7fb91a93814343420291556` |
| failed raw-results artifact SHA | `e893b95096675c02150eea0944486987512d4dda7021e428e985d458d9488fc3` |
| original prepared manifest SHA | `f756daec7d4aaa12aaae678f533a8d662b71baad53c2c11e4c60541405ece05b` |
| current HEAD (harness revision) | `9d8b7b3325b4ece3a0a169adb36f90d33c435f0f` |

The failed raw attempt recorded `parse_status = provider_api_failure` with
`provider_metadata = null`, `provider_response_sha256 = null`, and
`provider_raw_base64 = null`, discarding all response/error evidence. That
evidence-losing classification is the mechanical defect corrected here.

## Corrective change

Commits `752382c` and `9d8b7b3` make the failure mode and evidence concrete:
`transport` / `http`(+status + raw body) / `response_contract` /
`model_formatting`, with raw provider bytes/their SHA preserved when they
exist and credentials never retained. Fail-closed and zero-retry behavior are
unchanged.

## Restart consumption

`RestartController` fired exactly once: `restarts_used == 1`. No second restart
authorization exists.

## Fresh case set

- Seed rule (documented pattern, fresh namespace + fresh immutable HEAD root):
  `protean-stage0-restart-v1:9d8b7b3325b4ece3`
- Fresh case-set SHA: `7099a821c74397bff188a630ed9ca84c8aeed6185947ef99bda0c7a66ef1a03e`
  (verified **≠** invalidated `06fe8d47...`)
- Balance: 80 total; 40 positive / 40 negative; 16 per structure; 8/8 per structure.
- Primary/reference evaluator agreement: 80/80 (agreement SHA `74242c5e...`).
- No literal boolean tokens / truth-revealing tokens in model-visible payload.
- Artifact: `stage0/runs/restart-case-set-7099a8...json` (gitignored).

## New immutable run manifest

See `stage0/runs/run-manifest-stage0-restart-9d8b7b3325b4-*.json`
(SHA `4677121ee8954bb717645fdb1669ff838a39f06181f3a94757b57d458acd68c5`,
run id `stage0-restart-9d8b7b3325b4-...`).

- harness revision: `9d8b7b3325b4ece3a0a169adb36f90d33c435f0f`
- new case-set SHA: `7099a821c74397bff188a630ed9ca84c8aeed6185947ef99bda0c7a66ef1a03e`
- scoring prompt SHA: `ae8f093a69a7bae6818421000490a14c8a19a4a6be33069a1858bf0a9d7f6909` (unchanged)
- Luna model config SHA: `b3e21561ef3f84e2c38275f761ba8c7cbdf1e4a2ede04972f924f58d4827d9fa`
- protocol SHA: `dbe9d0a292ade61b980fa26045ed98c22c139f50e51836341687c2499c5481d4`
- execution-plan SHA: `8a9ae0ffbc41001df87270b7962c6d4ff2273bf9d15ac7386d4658b2cd27f155`
- parse-contract SHA: `6ed00481b2cf9681ca3b7fc6952a51ae7fd134767bb52a6005a4565dd4b35af8`

Preflight passed with **zero model calls**.
