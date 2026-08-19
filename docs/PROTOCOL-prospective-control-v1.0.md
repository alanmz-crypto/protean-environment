# Prospective Control Experiment 1 — Protocol v1.0

## Research question

> Can verified historical outcome information improve future prospective-control decisions beyond an otherwise identical fixed persistent mechanism, without changing the underlying frontier model?

The narrow tested mechanism is **history-conditioned scalar threshold adaptation**.

A positive result does not establish a general persistent-environment architecture.

## Experimental arms

Experiment 1 operationally contains only:

### B — Fixed persistence

Stores the relevant commitment/trigger state.

Decision threshold remains:

`0.50`

throughout the experiment.

### C — History-conditioned persistence

Starts byte-identical to B and begins at:

`0.50`

After calibration/history outcomes are mechanically verified, C chooses exactly one threshold from:

```text
0.10
0.15
0.20
0.25
0.30
0.35
0.40
0.45
0.50
0.55
0.60
0.65
0.70
0.75
0.80
0.85
0.90
```

Selection criterion:

1. maximum calibration balanced accuracy;
2. ties → threshold closest to `0.50`;
3. remaining tie → higher threshold.

After selection, the threshold is frozen for held-out evaluation.

No:

* Platt scaling;
* isotonic calibration;
* alternate calibration method;
* model shopping;
* post-holdout threshold adjustment.

The complete 17-threshold calibration performance curve must be published, including:

* FP rate;
* FN rate;
* balanced accuracy;
* selected threshold;
* second-best threshold;
* all thresholds within 1 percentage point of the maximum.

Arm A / no-persistence baseline is **not part of Experiment 1**.

B-vs-A is a separate question and must not be collected or analyzed here.

## Unchanged model condition

B and C use:

* the same frontier model;
* the same model configuration;
* the same prompts except for the frozen threshold behavior where required;
* the same raw persistent state;
* the same information;
* the same token/context/inference budget.

No model-weight updates occur.

The experiment tests external persistent adaptation, not model training.

## Stage 0 — raw signal qualification

Use:

* 80 cases total;
* exactly 40 true-trigger;
* exactly 40 true-nontrigger.

The scoring prompt must be frozen before Stage 0 begins.

For every case, the model outputs an applicability estimate from:

`0.00–1.00`

Trigger truth must be mechanically or externally determined.

The tested model must not judge whether its own answer was correct.

### PASS gate

Observed ROC-AUC must satisfy both:

* ROC-AUC ≥ `0.60`
* one-sided 95% confidence lower bound > `0.50`

Confidence method:

**DeLong ROC-AUC confidence estimation**

If Stage 0 fails:

**STOP the mechanism. Stage 1 does not run.**

Poor AUC does not authorize prompt optimization.

Exactly one Stage-0 restart is allowed only for a documented mechanical harness defect such as:

* parse failure;
* malformed output handling;
* incorrect ground truth;
* incorrect model configuration;
* comparable implementation defect.

A restart uses a fresh Stage-0 set.

Poor model performance is not a mechanical defect.

## Stage 1A — calibration/history

Use:

`60` calibration/history decisions.

B and C receive the same cases and history.

After outcomes are mechanically verified:

* B remains at `0.50`;
* C selects one threshold using the preregistered 17-threshold rule.

C's threshold freezes before held-out evaluation begins.

## Stage 1B — held-out evaluation

Use:

`400` paired held-out decisions.

Exactly:

* 200 true-trigger;
* 200 true-nontrigger.

B and C receive the same cases.

No adaptation occurs during held-out evaluation.

The primary analysis pools all 400 decisions.

## Familiar / structural-novelty partition

The 400 held-out cases are divided into:

### Familiar structure

`200` cases:

* 100 positive;
* 100 negative.

### Structural novelty

`200` cases:

* 100 positive;
* 100 negative.

Novelty concerns logical composition, not cosmetic wording.

Calibration/familiar primitives:

```text
P
P AND Q
P AND NOT Q
T2(P)
ACTIVE AND P
```

`T2(X)` means X is true for two successive observations.

Novel structures:

```text
N1: P AND Q AND NOT R
N2: T2(P AND Q)
N3: ACTIVE AND P AND Q
N4: ACTIVE AND T2(P) AND NOT Q
```

Each novel family contains:

* 50 cases;
* 25 positive;
* 25 negative.

N1–N4 are reported descriptively.

They are not individually powered inferential tests.

## Primary practical effect

Minimum practically meaningful effect:

**C − B ≥ 15 percentage points in held-out balanced accuracy.**

Strong first-study evidence additionally requires the preregistered paired statistical criterion.

Use exact paired McNemar/binomial analysis.

Two-sided:

`α = 0.05`

The 400-pair design uses the conservative all-discordant power configuration previously fixed by protocol design.

At a 15pp net advantage:

* C wins 230 discordant pairs;
* B wins 170 discordant pairs.

Approximate preregistered power:

**83.2%**

Do not recompute or modify this design value during implementation.

Failure to reach 15pp may count against the practical hypothesis; it does not prove the effect is exactly zero.

Sample size is frozen at 400.

## Structural-novelty gate

The 200-case structural-novelty subset must satisfy:

* C − B ≥ `10 percentage points` balanced accuracy;
* one-sided exact paired McNemar/binomial test at `α = 0.10`;
* FP/FN guardrails pass.

A novelty failure means only:

> The single global threshold fitted on the simpler calibration structures did not demonstrate generalization to the preregistered novel logical compositions.

It does **not** establish that historical adaptation generally fails.

A richer or structure-conditioned mechanism remains untested and would require a new preregistered experiment.

If pooled performance passes but the novelty gate fails:

**Suggestive only.**

## False-positive / false-negative guardrails

Always report FP and FN separately.

Report both:

* absolute change;
* relative change.

If B's corresponding error rate is ≥5%:

* deterioration must be ≤5 percentage points absolute;
* and ≤50% relative.

If B's corresponding error rate is <5%:

* deterioration must be ≤2 percentage points absolute.

A favorable aggregate metric cannot hide a pathological FP/FN tradeoff.

Guardrail failure blocks Strong evidence.

## Cross-session requirement

Prospective commitments originate in an earlier model session.

Later trigger decisions occur in fresh context.

The original conversation must not be silently carried forward.

Persistence must be responsible for carrying authorized state across the session boundary.

## Equal persistent information

B and C receive byte-equivalent raw persistent state, including as applicable:

* original commitment;
* trigger;
* cancellations;
* supersession;
* completion/satisfaction;
* timestamps;
* lifecycle state.

The only intended experimental difference is:

* B fixed threshold `0.50`;
* C historically selected frozen threshold.

C must not receive hidden lifecycle or information advantages.

## Independent authorship

Calibration and held-out textualization must be produced through genuinely independent authorship processes.

Not sufficient:

* same model second pass;
* different random seed;
* superficial entity renaming;
* same template disguised as separate authorship.

Acceptable independence may include:

* different providers/model families;
* human vs model;
* independent humans;
* programmatic generation vs independent natural-language authorship.

Holdout authorship must not have access to calibration outputs.

Audit for lexical/style shortcuts.

## Ground truth / evaluation independence

Trigger truth is mechanically or externally determined.

The tested model does not grade itself.

Outcome labels must have independent provenance.

Self-evaluation cannot be the experiment's correctness oracle.

## Evidence classifications

### Strong first-study evidence

Requires all of:

1. pooled C−B ≥15pp balanced accuracy;
2. paired statistical criterion passes at two-sided `α=.05`;
3. paired effect uncertainty excludes no improvement;
4. structural-novelty gate passes;
5. FP/FN guardrails pass;
6. model/information/token/context/inference equality holds;
7. no leakage, ground-truth, or protocol-invalidity defect exists.

Strong first-study evidence still requires replication before architecture expansion.

### Suggestive

Examples include:

* C>B but <15pp;
* uncertainty remains;
* pooled result passes but novelty gate fails;
* other valid evidence that is directionally favorable but insufficient for Strong.

Suggestive evidence does not authorize construction of a general Protean architecture.

### Negative

A valid, appropriately powered study fails the preregistered practical hypothesis.

Negative results do not automatically justify a more complicated mechanism.

### Invalid / inconclusive

Used only for genuine protocol/data validity failure.

An unfavorable valid result is not invalid.

### Restricted Familiar-Structure Evidence

Available only if an independently established validity defect invalidates the novelty subset while the familiar subset is positively established as unaffected.

This classification supports only a narrow familiar-structure claim.

It cannot establish:

* structural transfer;
* Strong evidence.

## Familiar-Structure Robustness Result

The 200 familiar cases are always reported separately.

Report:

* B balanced accuracy;
* C balanced accuracy;
* C−B;
* exact paired inference;
* FP;
* FN;
* absolute/relative changes;
* paired uncertainty interval;
* descriptive comparison with the 15pp threshold.

The familiar subset is not independently powered to carry the same primary conservative power claim as the pooled 400.

Its result cannot independently falsify the full hypothesis merely because it does not reach 15pp.

It also cannot upgrade evidence.

It may never convert:

* Negative → Suggestive;
* Negative → Strong;
* Suggestive → Strong.

Its special role exists only after an independently demonstrated validity defect narrows what portion of the preregistered dataset remains interpretable.

## Localized invalidity

If a demonstrable protocol/data defect affects the novelty subset:

* novelty claims become invalid;
* pooled primary result becomes invalid because compromised data are included.

The familiar subset may survive only if independently established as unaffected.

A novelty result being poor is not evidence that the novelty data were invalid.

### No post-hoc salvage rule

Poor-but-valid novelty performance is a scientific outcome.

It cannot be discarded in order to rescue the familiar result.

Validity fallback is allowed only for an independently demonstrable defect.

## Blind defect-scope determination

Before Stage 1B is unblinded, preregister objective defect criteria covering areas such as:

* ground-truth error;
* authoring leakage;
* split contamination;
* malformed cases;
* harness defects.

If a suspected defect is discovered after unblinding, its scope must be assessed by an independent reviewer who is not shown:

* aggregate B/C performance;
* novelty-subset performance;
* familiar-subset performance;
* whether retaining familiar data would preserve a favorable study result.

The reviewer uses case-generation records, manifests, prompts, provenance, and fixed defect criteria.

Allowed scope classifications:

* novelty only;
* familiar only;
* both;
* indeterminate.

`Indeterminate` does not qualify as "familiar independently unaffected."

Restricted Familiar-Structure Evidence requires positive blind establishment that familiar data are unaffected.

## Stopping discipline

Stage 0 raw-signal failure:

**STOP.**

Strong first-study result:

**replicate before architecture expansion.**

Effect below 15pp:

do not lower the threshold after seeing results.

Valid powered C≈B:

reduce confidence in this scalar-threshold adaptation mechanism.

Do not automatically respond by building a more complicated mechanism.

A corrective rerun is permitted only for an identified validity/power problem, not for ordinary disappointing results.

A materially different mechanism requires:

* new rationale;
* new protocol;
* new preregistration.

## What a positive result supports

At most:

> Verified historical outcomes stored outside an unchanged frontier model can improve future cross-session prospective-control decisions beyond a fixed persistent mechanism through simple external threshold adaptation, including some structural novelty if the novelty gate passes.

## Explicit nonclaims

A positive result does not establish:

* general AI architecture;
* general intelligence improvement;
* model-weight improvement;
* universal cross-domain transfer;
* TonicAI's earlier proposed ontology;
* universal virtues/dispositions;
* a shared persistent infrastructure;
* transfer across future model generations;
* that scalar-threshold adaptation is optimal;
* that other proposed Protean behavioral dimensions work.

## Freeze statement

**FROZEN PROTOCOL v1.0 — Any substantive change after this point requires a separately documented protocol revision before execution.**
