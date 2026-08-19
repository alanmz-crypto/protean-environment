# Prospective Control Experiment 1 — Stage 0 Execution Plan

Status: PLANNED — NOT YET AUTHORIZED FOR EXECUTION

Protocol authority:
`docs/PROTOCOL-prospective-control-v1.0.md`

This document is the execution-ready plan for **Stage 0 only** of Prospective
Control Experiment 1. Protocol v1.0 is authoritative. Where this plan is silent,
the implementer must not decide scientific meaning by invention; unresolved
decisions are listed explicitly at the end and require a separate Ryan decision.

Stage 0 asks one narrow question:

> Does the frozen frontier model produce a sufficiently discriminative
> prospective-trigger applicability signal for the preregistered scalar-threshold
> mechanism to be worth testing further?

The implementer builds Stage 0 from this document **without making any
scientific-design decisions**.

---

## 1. Stage 0 purpose and exclusions

Stage 0 tests raw model signal quality only.

It does **not** test:

- B versus C;
- historical adaptation;
- threshold selection;
- persistence benefit;
- structural novelty;
- Stage 1 calibration;
- Stage 1 held-out performance;
- Protean architecture.

No B/C mechanism needs to be implemented for Stage 0 beyond representations
strictly required to pose trigger-applicability cases.

---

## 2. Frozen Stage 0 constants

Carried directly from Protocol v1.0. Do not alter:

- `80` total cases;
- exactly `40` trigger-positive;
- exactly `40` trigger-negative;
- model output applicability score in range `0.00–1.00`;
- PASS requires **both**:
  - observed `ROC-AUC >= 0.60`;
  - one-sided `95%` DeLong lower confidence bound `> 0.50`;
- gate failure means **STOP. Stage 1 does not run.**;
- poor AUC does not authorize prompt optimization;
- exactly **one** Stage-0 restart allowed, only for a documented mechanical
  harness defect (see section 13);
- a restart uses a **fresh** Stage-0 set;
- poor model performance is not a mechanical defect.

No alternate metric replaces the gate.

---

## 3. Case representation

Define a minimal machine-readable Stage 0 case schema. This is **not** a generic
Protean persistence schema; it exists only to support this experiment.

### 3.1 Field groups

Separate three groups:

- **Model-visible fields** — exposed to the tested model in the scored prompt.
- **Hidden fields** — never placed in the model-visible payload.
- **Ground-truth / evaluation metadata** — never supplied to the tested model.

Truth labels must never be supplied to the tested model.

### 3.2 Required fields (per case)

| Field | Group | Purpose |
|-------|-------|---------|
| `case_id` | metadata | unique identifier |
| `commitment` | model-visible | the earlier expressed intention/commitment |
| `trigger_condition` | model-visible | the condition whose applicability is being scored |
| `prior_state` | model-visible | relevant state before the observation window |
| `observed_event` | model-visible | the later observed state/event being judged |
| `lifecycle_state` | model-visible if needed | e.g. ACTIVE / COMPLETED / CANCELLED, only as required |
| `truth_label` | **hidden/metadata** | mechanically determined, `true` or `false`; never model-visible |
| `structure_id` | metadata | which of the finalized Stage-0 structures this case exercises |
| `authorship_source` | metadata | independent-authorship provenance |
| `version_id` | metadata | case-set version/creation metadata |
| `case_set_hash` | metadata | hash of the frozen case-set artifact |

### 3.3 Model-visible composition

The model-visible payload is the concatenation of `commitment`,
`trigger_condition`, `prior_state`, `observed_event`, and any required
`lifecycle_state`, assembled by the frozen scoring prompt (section 5). It must
never contain `truth_label`, `structure_id` semantics that reveal the true
label, or any outcome information.
### 3.4 Authoritative Stage 0 semantics (Decision 2 — resolved)

Stage 0 uses a **synthetic operational-commitment micro-world**. A case
represents:

1. an earlier commitment to perform a named action when a condition becomes
   true;
2. a later world-state description;
3. any required observation history;
4. any required commitment lifecycle state.

The model's scored question is conceptually:

> Is this previously stored commitment eligible to fire now, given the later
> state and its lifecycle status?

Ground truth comes only from the structured condition/state representation. No
external world knowledge, domain expertise, unstated calendar facts, or
tested-model judgment may determine truth.

All five Protocol-v1.0 familiar structures are used:

* `P`
* `P AND Q`
* `P AND NOT Q`
* `T2(P)`
* `ACTIVE AND P`

Stage 0 structural allocation is frozen:

* exactly `16` cases per structure;
* exactly `8` true-trigger and `8` true-nontrigger within each structure.

Total:

* `80` cases;
* `40` true-trigger;
* `40` true-nontrigger.

The model-visible representation uses natural-language commitments and later
state descriptions. Do not expose:

* `P`, `Q`, or `R` identifiers as logical notation;
* `structure_id`;
* `truth_label`;
* equivalent metadata revealing the intended result.

For `T2(P)`, the structured case supplies two successive observations. For
`ACTIVE AND P`, structured lifecycle state mechanically determines whether the
commitment remains eligible to fire.

The original conversation is not carried forward. The scoring context represents
a fresh later session containing only the authorized persisted
commitment/state necessary for the test.


---

## 4. Mechanical ground truth

Define how a case receives `true-trigger` or `true-nontrigger` **without** model
judgment.

- **Who/what computes truth:** an explicit deterministic function `truth(case)`
  over the case state and the trigger definition. Implemented as a standalone,
  pure, unit-testable function independent of the model-calling harness.
- **When truth is computed:** once, at case-authoring time, and recorded in the
  immutable case artifact before any scored model call.
- **How it is independently checked:** a second, independent pass recomputes
  `truth(case)` for every case from the same inputs and the frozen trigger
  definition; the two must agree on all 80 cases. Disagreement is a mechanical
  defect.
- **Discrepancy handling:** any disagreement is resolved **before** the run by
  correcting the case or the truth function, then regenerating a fresh affected
  case; the entire 80-case set must still preserve exact 40/40 balance. No
  discrepancy is resolved by model judgment, and none is resolved after scored
  model calls begin.

No tested-model self-grading.

---

## 5. Scoring-prompt freeze procedure

The final scoring prompt is **not** written in this planning task (the frozen
protocol does not contain it). This section defines the procedure by which the
prompt is later authored and frozen.

- The prompt is authored **before** Stage 0 begins;
- it is reviewed for **label leakage** and **unintended decision cues** (nothing
  that reveals `truth_label` or that encodes a scoring shortcut);
- the exact prompt content is frozen before the 80-case run;
- a **cryptographic hash** (SHA-256) of the exact prompt bytes is recorded in the
  run manifest;
- **no AUC-driven prompt tuning** is permitted;
- any prompt change after exposure to Stage-0 performance invalidates that run
  except the protocol's allowed mechanical-defect pathway (section 13).

The prompt must request exactly the prospective-trigger applicability signal
needed for Stage 0 and output a machine-parseable `0.00–1.00` score.

---

## 6. Model freeze procedure

The experimental model is a separate Ryan decision before execution (see
section 15, Unresolved decisions). This section defines the pre-run lock that
must be recorded.

Before any scored model call, record and freeze:

- provider;
- exact model ID;
- relevant version/snapshot identifier if the provider exposes one;
- reasoning mode / settings;
- temperature;
- seed if supported;
- max output length;
- relevant API parameters.

Once Stage 0 begins, these are frozen. If exact provider reproducibility cannot
be guaranteed, record whatever provenance makes the actual model used auditable
(e.g. request/response metadata the provider returns). Model selection remains a
separate Ryan decision before execution.

---

## 7. Case authorship procedure

Stage 0 has 80 cases.

- exact `40` / `40` truth balance;
- truth decided **independently of** tested-model scoring;
- positive and negative cases must be comparable in style and complexity
  (differences constrained to the tested structure, not cosmetic wording);
- audit against obvious lexical shortcuts (e.g. signpost words correlated with
  labels);
- provenance for the authoring process is recorded;
- Stage-0 results are **not** used to rewrite cases.

Independent-authorship design for Stage 1 is not solved here except where a
Stage-0 rule genuinely requires it (only the applicability of
section-7's `authorship_source` field).
### 7.1 Authoritative case-authorship process (Decision 4 — resolved)

**Structured specifications.** The 80 machine-readable case specifications are
produced deterministically from a frozen seed and the frozen trigger grammar. The
generator enforces:

* 16 cases per familiar structure;
* 8 positive / 8 negative per structure;
* 80 total;
* 40/40 total class balance.

Truth is not chosen by a textualizing model.

**Natural-language textualization.** Use a frozen natural-language template bank.
Templates are authored without access to generated case truth labels.
Template/paraphrase assignment and slot values must be independent of
positive/negative class. DeepSeek V4 Flash may author the template bank during
the later authorized case-generation phase (not in this task).

**Independent pre-score review.** Before any experimental model call, Kiro
independently reviews the frozen template bank and the resulting textualized
80-case set for:

* semantic faithfulness to structured specs;
* accidental truth leakage;
* obvious label-correlated vocabulary;
* systematic positive/negative style differences;
* length/complexity imbalance;
* malformed or ambiguous textualization.

This review occurs before Stage 0 scoring and without access to any Stage 0
model-performance results.
**Independent truth recomputation.** The primary deterministic truth function
and the reference evaluator are **independently authored implementations** of the
same frozen trigger grammar.

Requirements:

* the primary and reference evaluators must be authored independently, with no
  shared truth/logic implementation;
* the reference-evaluator author/agent must not have access to:
  * primary evaluator source code;
  * shared executable truth logic;
  * implementation-specific fixtures derived from the primary evaluator;
  * primary evaluator expected outputs;
  * generated snapshots of primary truth results;
* shared access to the frozen trigger grammar/specification itself is required
  and allowed;
* generic test infrastructure may be shared only where it does not encode truth
  logic or expected case outcomes;
* record provenance sufficient to identify:
  * who/what authored each evaluator;
  * when;
  * from which frozen grammar version/hash;
  * confirmation that the reference implementation was independently authored.

No different programming language is required unless already necessary.
Independence is about derivation and information separation, not language choice.

Both evaluators must agree on all 80 cases before Stage 0 may begin. Any
disagreement is resolved before scoring. The tested model never participates in
ground-truth determination.


**Freeze.** After case generation, textualization, independent review, and truth
agreement:

* freeze the case set;
* compute and record its hash;
* prohibit case rewriting based on Stage 0 results.


---

## 8. Run manifest

Create a frozen Stage-0 manifest **before** the first scored model call. It must
identify:

- protocol version and protocol hash;
- execution-plan version and execution-plan hash;
- case-set hash;
- scoring-prompt hash;
- case count and class balance (80, 40/40);
- exact model/config (section 6);
- harness/code revision;
- timestamp;
- run identifier.

Purpose: reproducibility and leakage prevention. This is **not** generic
governance.

---

## 9. Model-call behavior

Specify the minimum deterministic calling loop. For every case:

1. construct the model-visible input;
2. use the frozen scoring prompt;
3. make **one** defined scoring call;
4. capture the raw response;
5. parse the score;
6. validate `0.00–1.00`;
7. record errors **without silently coercing** malformed output.

Distinguish, per case:

- **valid score** — a parseable `0.00–1.00` value from a successful response;
- **parse/mechanical failure** — response received but not valid per the frozen
  parse rules;
- **provider/API failure** — no usable response (timeout, error, connection).


> If a scored case does not yield a valid `0.00–1.00` value and the failure is
> not attributable to a documented mechanical defect, that case is unusable;
> therefore the required 80-usable-case condition is not met and Stage 0 cannot
> produce a valid PASS result.
### 9.1 Malformed-output classification (frozen before first experimental call)

The disposition below is established and frozen **before** the first experimental
model call.

**Model formatting failure.** If:

* the frozen prompt/request was assembled correctly;
* the frozen model configuration was used;
* the harness and parser behaved according to their frozen specifications;

but the model nevertheless fails to produce a valid response satisfying the
frozen `0.00–1.00` response contract, then this is **model formatting behavior,
not a mechanical defect**.

Consequences:

* no coercion;
* no substitution;
* no model-decision retry;
* no mechanical-defect restart;
* the case is unusable;
* the required 80 usable cases are not available;
* Stage 0 returns **STOP**.

**Mechanical defect.** A mechanical defect requires performance-blind evidence
that the experimental machinery deviated from its frozen specification.
Examples:

* incorrect prompt assembly;
* wrong frozen prompt supplied;
* wrong model/configuration used;
* parser behavior inconsistent with its frozen specification;
* corrupted case payload;
* harness implementation defect;
* comparable demonstrable execution failure.

The classification must be based on mechanical evidence, not on ROC-AUC, score
distributions, confidence bounds, or whether declaring a defect would rescue the
experiment.

If such a qualifying defect exists, use only the already-authorized Protocol-v1.0
mechanical-defect pathway:

* document defect;
* invalidate entire run;
* correct it;
* fresh 80-case set;
* at most the single permitted restart.


Do not invent retries that could amount to response shopping. If limited
mechanical API retry behavior is needed, specify it narrowly (e.g. one re-issue
of the identical request on an infrastructure failure) and clearly distinguish it
from rerunning a model decision. A rerun of a model decision is not permitted.

---

## 10. Raw results artifact

Define an immutable raw-result format that can reproduce the analysis. Per scored
case, record at minimum:

- run ID;
- case ID;
- hidden truth label;
- returned score;
- raw model response, or a stable reference to it;
- model identity/config;
- timestamp and call order;
- parse status;
- mechanical error status.

The raw artifact contains **no** Stage 1 B/C results, because Stage 0 has none.

---

## 11. Stage 0 analysis

Specified exact sequence:

1. verify 80 usable cases and exact 40/40 truth balance;
2. verify **no protocol-invalidating mechanical defect**;
3. compute ROC-AUC from raw applicability scores and truth labels;
4. compute one-sided 95% DeLong lower confidence bound;
5. apply both preregistered gates;
6. return **PASS** or **STOP**.

No alternate metric can replace the gate. Other descriptive statistics may be
reported only if clearly non-decisional. Do **not** recompute the protocol's
Stage-1 power calculations (e.g. the preregistered 83.2% power value).

---

## 12. DeLong implementation requirement

Before the DeLong confidence procedure is used, the implementation must prove:

- correctness against known/reference examples or a trusted implementation;
- deterministic output on fixed inputs;
- correct direction for the one-sided lower bound;
- documented handling of ties.

Do not choose a new statistical method. If the library choice is left to the
implementation agent, state acceptance requirements here rather than committing
to a package: the accepted implementation must pass the above checks.

---

## 13. Mechanical-defect rule

Operationalize the protocol's one allowed restart. A mechanical defect is narrow,
with examples:

- wrong ground-truth computation;
- malformed prompt assembly;
- parser bug;
- incorrect model configuration;
- case corruption;
- harness defect.

Explicitly excluded (not mechanical defects):

- low ROC-AUC;
- inconvenient score distribution;
- weak confidence bound;
- unexpectedly high FP/FN;
- disappointing model behavior.

If a valid mechanical defect invalidates Stage 0:

1. document it;
2. invalidate the entire run;
3. correct the defect;
4. generate a **fresh** 80-case set;
5. permit only the protocol's single restart.

---

## 14. Pre-run validity checks

Before any experiment call, require mechanical checks that:

- exactly 80 cases;
- 40/40 balance;
- unique IDs;
- all required fields complete;
- truth determinable for every case;
- no truth labels in the model-visible payload;
- prompt hash frozen and matches the manifest;
- model config frozen and matches the manifest;
- manifest complete;
- case-set hash frozen and matches the manifest.

Failure of any check means no run begins.

---

## 15. Stage 0 outputs

Define the minimum expected outputs (conceptually; do not create yet):

- frozen case-set artifact;
- frozen prompt artifact;
- run manifest;
- raw model results;
- validation report;
- Stage-0 analysis report;
- **PASS / STOP** decision.

Do **not** create a large directory hierarchy unless implementation genuinely
needs one. Keep artifacts flat and named by run identifier.

---

## 16. Decision boundary after Stage 0

If **PASS**:

- Stage 0 authorizes only consideration/preparation of Stage 1A according to
  Protocol v1.0.
- It does **not** establish that historical adaptation works.

If **STOP**:

- Stage 1 does not proceed.

After either outcome, do not automatically authorize:

- prompt tuning;
- another model;
- more cases;
- richer persistence;
- more sophisticated scoring;
- alternate statistics.

Any different mechanism or experiment requires a new explicit decision.

---

## Unresolved decisions requiring Ryan before execution

Decisions 2 and 4 are **resolved** and recorded as authoritative in this plan
(section 3.4: trigger-applicability semantics; section 7.1: independent
case-authorship process).

Two decisions remain unresolved and must be explicit Ryan decisions. They are
required **before the first experimental call**, not before mechanical
implementation:

1. **Experimental model** (original Decision 1). Protocol v1.0 does not specify
   the frontier model for the experiment. Section 6 requires provider, exact
   model ID, version, reasoning settings, temperature, seed, max output, and API
   parameters to be locked before the run. The model (and all model-config
   values) is a Ryan choice.

2. **Final scoring-prompt content** (original Decision 3). Section 5 specifies
   the freeze *procedure* but the prompt content is authored and frozen later.
   Its exact wording is a content authoring step to be approved before the run;
   the procedure enforces no AUC-driven tuning.

---

## Protocol ambiguity noticed

No conflict, contradiction, or unintended expansion was found between this work
order and Protocol v1.0; the protocol is carried as the authoritative source. Two
openings the protocol deliberately leaves unspecified (the experimental model
and the concrete trigger-applicability semantics) are recorded as unresolved
decisions above rather than resolved by invention.
