# Stage-1A Futility Evidence Dossier

> **FACTUAL EVIDENCE ONLY — NON-AUTHORITATIVE — NO CAUSAL INTERPRETATION**

Arc: `STAGE1A_FUTILITY_INTERPRETATION`

This dossier records a read-only local inspection of the frozen Stage-1A
calibration authority and the locally retained raw provider evidence. It does
not decide what Protean should do next, alter any experimental authority, or
authorize Stage 1B.

## Scope and method

- Canonical repository: `alanmz-crypto/protean-environment`.
- Audited repository revision: `326fc5fb743edc9b6d08b0e8feffea971a96bd13`.
- Source batch: `calibration-9fe9d4e05803-20260822T022931681360Z`.
- Analysis used only local files, deterministic repository code, standard-library
  scripts, and read-only typed validators.
- No new model, provider, or API calls were made.
- No frozen authority, run artifact, source file, or test was modified.

## Authority checks

The following exact bytes and reconstructed authorities were checked:

- Calibration manifest:
  `stage0/runs/calibration-run-manifest-calibration-9fe9d4e05803-20260822T022931681360Z.json`
  — SHA-256
  `77d301db3e240b8a244ef41d0f113fadf385a072097d5be5419295878f6d6254`.
- Completed calibration authority:
  `stage0/runs/calibration-completed-calibration-9fe9d4e05803-20260822T022931681360Z.json`
  — SHA-256
  `65850d3b608fc5294e5e0a2b8c51a40f4f10b4b4bcd7312107e41f2bece595d8`.
- Regenerated Stage-1A case-set SHA-256:
  `6851bf6f49f080ca3ede7938e207b835e5b3ac7cf531e3a460fb74393adecf41`.
- Frozen template-bank SHA-256:
  `295fe92fe12ba14470166d6b160492fb1564d29b06dc46500f8b2cbfdf73c758`.
- Frozen scoring-prompt SHA-256:
  `ae8f093a69a7bae6818421000490a14c8a19a4a6be33069a1858bf0a9d7f6909`.
- The typed authority loader regenerated 60 cases and matched the expected
  case-set hash.
- The typed origin-chain validator passed 5/5 successful origin artifacts with
  0 failures.
- The calibration manifest exact seal, completed authority, and all 60 evidence
  records passed canonical byte-roundtrip, SHA, ordering, and completion checks.

The repository's pre-artifact audit state was clean on `main` and matched
`origin/main` at the audited revision. The dossier is committed on `main` as a
non-authoritative review artifact.

## Exact request reconstruction

All 60 per-case evidence files were read from:

`stage0/runs/calibration-evidence-calibration-9fe9d4e05803-20260822T022931681360Z-c01.json`
through `c60.json`.

For every case:

- `request_bytes_base64` decoded to one exact JSON request body.
- The request body was independently rederived from the frozen scoring prompt
  and regenerated Stage-1A model-visible case fields.
- Reconstructed request bytes matched the stored bytes: 60/60.
- Stored request SHA matched both the manifest SHA and recomputed SHA: 60/60.
- Case IDs were unique and in manifest order: 60/60.
- Completed-authority scores matched the evidence scores: 60/60.

All 60 request bodies had the same request-level configuration:

- model: `gpt-5.6-luna`
- reasoning context: `current_turn`
- reasoning effort: `xhigh`
- `max_output_tokens`: `128000`
- `store`: `false`

The model-visible input contained the commitment, trigger condition, prior
state, observed event, lifecycle state, and the fixed scoring instructions. It
contained no `S1A-*` case ID, truth label, structure ID, or case ID token.

## Score distributions

Overall, the frozen truth labels and parsed scores were identical:

- truth-positive: 30 cases, all `1.00`.
- truth-negative: 30 cases, all `0.00`.
- discordant truth/score pairs: 0.

By structure, every group contained 12 cases with 6 positive and 6 negative
truth labels, and every group produced 6 scores of `1.00` and 6 scores of
`0.00`:

- `P`: 6 positive / 6 negative; scores 6 × `1.00` / 6 × `0.00`.
- `P AND Q`: 6 positive / 6 negative; scores 6 × `1.00` / 6 × `0.00`.
- `P AND NOT Q`: 6 positive / 6 negative; scores 6 × `1.00` / 6 × `0.00`.
- `T2(P)`: 6 positive / 6 negative; scores 6 × `1.00` / 6 × `0.00`.
- `ACTIVE AND P`: 6 positive / 6 negative; scores 6 × `1.00` / 6 × `0.00`.

## Template and slot assignments

There are two templates per structure. Counts are shown as negative/positive:

- `P`: template 0 = 4/2; template 1 = 2/4.
- `P AND Q`: template 0 = 5/2; template 1 = 1/4.
- `P AND NOT Q`: template 0 = 2/4; template 1 = 4/2.
- `T2(P)`: template 0 = 3/2; template 1 = 3/4.
- `ACTIVE AND P`: template 0 = 2/4; template 1 = 4/2.

Aggregate template-index counts were template 0 = 16 negative/14 positive and
template 1 = 14 negative/16 positive. Every structure/template cell contained
both labels.

Slot counts are shown as negative/positive:

- slot 0: 3/3
- slot 1: 6/0
- slot 2: 4/5
- slot 3: 6/5
- slot 4: 4/6
- slot 5: 2/1
- slot 6: 3/6
- slot 7: 2/4

Slot 1 uses `transmit the status packet`, `the field unit`, `the network
uplink`, and `the encryption key`; all six slot-1 cases are negative in this
finite sample. Slot identity is not explicitly transmitted as a slot number.

## Length distributions

Input lengths are character counts; the audited inputs are ASCII, so these also
equal UTF-8 byte counts. Request-body lengths include JSON/configuration
overhead.

- Positive input: n=30, min=867, Q1=885, median=906.5, Q3=922, max=994,
  mean=910.30 characters.
- Negative input: n=30, min=870, Q1=892, median=906, Q3=914, max=979,
  mean=909.87 characters.
- Positive request body: min=1019, median=1058.5, max=1146, mean=1062.30
  bytes.
- Negative request body: min=1022, median=1058, max=1131, mean=1061.87
  bytes.

The positive and negative length ranges overlap substantially.

## Mechanical cue checks

These are document-presence counts in the model-visible request input. They are
associations in this finite corpus, not causal findings.

- `unmet`: 31 documents, 6 positive / 25 negative.
- `satisfied`: 50 documents, 30 positive / 20 negative.
- `both`: 12 documents, 6 positive / 6 negative.
- `two consecutive`: 12 documents, 6 positive / 6 negative.
- `Commitment lifecycle: ACTIVE`: 48 documents, 24 positive / 24 negative.
- `Lifecycle is ACTIVE`: 7 documents, 6 positive / 1 negative.
- `Lifecycle is CANCELLED`: 3 documents, all negative.
- `Lifecycle is COMPLETED`: 2 documents, all negative.
- Generic tokens such as `active`, `not`, `only`, and `if` occurred in all 60
  inputs and therefore did not distinguish labels by presence.

The strongest one-sided present-token associations were the slot-1 vocabulary
(`transmit`, `packet`, `field`, `network`, `uplink`: 0/6 positive) and lifecycle
values (`cancelled`: 0/3; `completed`: 0/2). The `CANCELLED`/`COMPLETED`
association corresponds to the structured lifecycle truth condition in
`ACTIVE AND P`; its presence alone is not evidence of an unintended shortcut.

Structure identity was balanced by construction. Structural wording also tracked
structure but not label in the observed counts: `both` and `two consecutive`
were each 6/6 positive/negative. Template identity was not perfectly
label-correlated. Input ordering was not perfectly label-correlated:

- first 30 requests: 17 positive / 13 negative.
- last 30 requests: 13 positive / 17 negative.
- odd request indices: 16 positive / 14 negative.
- even request indices: 14 positive / 16 negative.
- adjacent same-label pairs: 27 of 59.

## Structured decision content

The structured truth inputs contain the following observable logical ingredients:

- `P`: direct current single-condition lookup; 6 `p_now=False` negatives and
  6 `p_now=True` positives.
- `P AND Q`: current conjunction; `(False,False)`, `(False,True)`, and
  `(True,False)` each occurred twice as negatives; `(True,True)` occurred six
  times as positives.
- `P AND NOT Q`: current conjunction plus negation; `(True,False)` occurred six
  times as positives, while the other three combinations occurred twice each as
  negatives.
- `T2(P)`: two-step temporal persistence; `(previous=True,current=True)` occurred
  six times as positive, while the other three pairs occurred twice each as
  negative.
- `ACTIVE AND P`: lifecycle plus current condition; six `ACTIVE`/`p_now=True`
  cases were positive. The remaining six cases were negative, consisting of one
  `ACTIVE`/`p_now=False`, three `CANCELLED`, and two `COMPLETED` cases.

These statements describe the generated structured inputs and truth evaluator;
they do not assess difficulty or explain model behavior.

## Raw provider response details

The stored raw provider response for every case parsed as:

- object: `response`.
- status: `completed`.
- returned model: `gpt-5.6-luna`.
- top-level errors: 0.
- incomplete responses: 0.
- exactly one assistant output message per response.
- final message text: exactly `0.00` in 30 cases and `1.00` in 30 cases.
- final message SHA checks: 60/60.

The raw responses were not identical scalar records. All 60 contained encrypted
reasoning content. Fifty-nine contained one reasoning item plus one message; one
contained three reasoning items plus one message. Raw response sizes ranged from
3,594 to 16,829 bytes. Reasoning-token counts ranged from 29 to 1,552. These
raw-response differences do not change the literal final-score result.

## Stage-0 comparison

Stage-1A reused the same frozen template bank, the same five familiar
structures, the same eight vocabulary slots, the same two templates per
structure, and the same scoring-prompt bytes as Stage-0.

The construction allocation and seed differed:

- Stage-0 original construction: seed
  `protean-stage0-v1:26eb0ce24674d290`; 80 cases; 16 per structure; 8 positive
  and 8 negative per structure.
- Stage-1A construction: seed
  `protean-stage1a-calibration-v1:a154040c0d3a7d5a`; 60 cases; 12 per
  structure; 6 positive and 6 negative per structure.

Local Stage-0 raw evidence includes:

- Original failed artifact:
  `stage0/runs/raw-results-stage0-4c0f9bef9b9d-20260820T004123272209Z.json`.
  It contains one `provider_api_failure`, no parsed score, and therefore cannot
  supply an original 80-case score distribution.
- Restart artifact:
  `stage0/runs/raw-results-stage0-restart-7ce316213719-20260821T010551860444Z.json`.
  It contains 80 valid scores: 40 × `0.0` and 40 × `1.0`. Its stored truth/score
  pairs are exactly 40 `(false, 0.0)` and 40 `(true, 1.0)`.

The available Stage-0 restart raw evidence therefore also exhibits complete
0/1 score saturation. This dossier records that result without assigning a
cause to it.

## Evidence unavailable

- Plaintext reasoning is unavailable because the retained reasoning content is
  encrypted.
- No alternate provider, independent wording set, independent sample, or rerun
  was inspected.
- The original failed Stage-0 attempt has no score distribution beyond its single
  failed request.
- No causal claim is made about task separability, score elicitation, prompting,
  vocabulary, lifecycle wording, or model behavior.

## Boundary and status

This file is a review artifact only. It is non-authoritative, committed on `main`,
and does not amend the Stage-1A authority, threshold result, protocol, or Stage-1B
status. Any decision or interpretation remains outside this evidence dossier.
