# RATIFIED ADDENDUM — Graded Signal Characterization

STATUS: **RATIFIED GOVERNANCE ADDENDUM — GOVERNANCE-ONLY — NO EXECUTION AUTHORITY — RATIFIED**

This is a ratified governance addendum only. It is not an execution protocol,
does not modify frozen Protocol v1.0 or any Stage-1A authority, and does not
authorize a study. Claude measurement-validity review: PASS WITH NON-BLOCKING
REFINEMENTS. Kiro governance adjudication: PASS. Ryan HITL ratification:
RATIFIED.

Arc: `GRADED_SIGNAL_CHARACTERIZATION_GOVERNANCE`

## 1. Purpose and motivation

The Stage-0 restart and Stage-1A both produced endpoint-only applicability
scores while perfectly separating the mechanically established truth-positive
and truth-negative cases. On the exhausted Stage-1A surface, the score support
was exactly `{0, 1}`. Because the frozen thresholds ranged from `0.10` through
`0.90`, every threshold produced the same binary decisions, so the adaptive C
threshold had no threshold-relevant information to exploit. The preregistered
tie-break selected `0.50`, B and C became identical, and the ratified
deterministic futility stop correctly fired.

The familiar surface was also small: 20 distinct logical configurations across
the five structures, with exactly one positive logical configuration per
structure and repeated textualizations of those states. This establishes a
plausible task ceiling, but does not explain why Luna's reported numeric
confidence itself occupied exactly the endpoints.

The existing evidence therefore does not distinguish:

- **H1 — task ceiling / justified extreme confidence:** the cases were easy and
  fully determined enough for Luna to report endpoint confidence;
- **H2 — confidence-elicitation collapse:** the model/prompt/output interaction
  encoded a resolved yes/no applicability decision numerically as `0` or `1`
  instead of exposing graded epistemic confidence; or
- **H3 — interaction:** both the easy case surface and elicitation behavior
  contributed.

The remaining diagnostic question is whether the exact frozen Stage-1A Luna
scoring setup can expose a reproducibly graded applicability signal when it is
applied to mechanically truth-able prospective-control cases whose decision
surface imposes substantially greater epistemic difficulty than the exhausted
familiar surface. The initial variable is the case surface, not the prompt or
model.

Nothing in this motivation implies that Stage-1A was defective. Its valid
futility result remains closed, immutable, and correctly interpreted from the
observed score support.

## 2. Classification and scope

Any future work conducted under a later ratified version of this addendum would
be a **new characterization study**. It is not any of the following:

- Stage 1A;
- Stage 1B;
- a corrective rerun;
- a replication of Stage 1;
- salvage of the Stage-1A futility result;
- richer adaptive-mechanism work; or
- architecture work.

This ratified governance addendum establishes a governance boundary for a
possible future study. It does not create that study, select its design, or
amend Protocol v1.0 in place. Any executable characterization protocol
requires a separately documented and Ryan-ratified protocol/governance
addendum before execution.

## 3. Immutability of prior results

Future characterization cannot retroactively:

- invalidate Stage-1A;
- upgrade Stage-1A;
- downgrade Stage-1A;
- reinterpret its valid deterministic futility result; or
- reopen Stage 1B.

The frozen Protocol v1.0, ratified Stage-1 futility amendment, Stage-1A
evidence, Stage-1A interpretation, and other ratified Stage-1A authorities
remain the authorities for the completed arc. A future characterization may
answer only its separately preregistered characterization question.

## 4. Frozen scientific invariants and characterization identity boundary

For the characterization study defined by this addendum, the following
scientific invariants are immutable:

- the exact frozen Luna model/configuration: `gpt-5.6-luna` on the direct
  OpenAI Responses API, standard mode, reasoning effort `xhigh`, reasoning
  context `current_turn`, `max_output_tokens=128000`, `store=false`, with
  temperature omitted, no seed, no tools, no conversation or previous response
  state, and one request with no client retry, identified by the exact
  authoritative `DIRECT_CONFIG_HASH` SHA-256
  `b3e21561ef3f84e2c38275f761ba8c7cbdf1e4a2ede04972f924f58d4827d9fa`;
- the exact frozen Stage-1A scoring-prompt bytes, identified by SHA-256
  `ae8f093a69a7bae6818421000490a14c8a19a4a6be33069a1858bf0a9d7f6909`;
- the exact frozen score-response contract, including the fail-closed
  `PLAIN_DECIMAL_V1` final answer contract: ASCII `0.[0-9]{2}` or `1.00`,
  optionally followed by one LF, with no stripping, coercion, extraction, or
  substitution. The surrounding Responses contract must also remain exact:
  completed `response` object, returned model `gpt-5.6-luna`, required
  reasoning object with `current_turn`, optional returned effort only as
  `xhigh`, no response error or incomplete details, exactly one completed
  assistant output message with exactly one `output_text` block, and no
  forbidden/tool output item;
- mechanically established external truth, independently determined rather
  than judged by the tested model; and
- prospective-control applicability as the construct being scored.

The intended experimental variable is the preregistered **case surface only**.
Changing ANY one of these five scientific invariants means the work is no
longer the characterization study defined by this addendum. It would require a
separately governed study from first principles and cannot inherit this
addendum's characterization classification merely through another ratification.

Provider deprecation or inability to reproduce the exact apparatus makes this
particular characterization infeasible; it is not authority to substitute a
different model, provider, prompt, scoring contract, truth mechanism, or
construct. Non-scientific implementation and provenance details may be handled
separately only where they do not change these invariants.

This ratified governance addendum does not authorize prompt tuning, model
swapping, threshold tuning, confidence-format tuning, adaptive prompt
experimentation, or any other change to the frozen scoring apparatus. In
particular, a characterization study must not change the Stage-1A threshold
grid or tie-break machinery as a way to restore or revisit Stage 1B.

## 5. Anti-post-hoc protections

A future executable characterization surface must be frozen, sealed, and
reviewable before its first experimental call. No case may be generated or
selected in response to an observed score.

The following iterative loop is prohibited:

```text
generate → call → inspect score → make harder → call again
```

The future protocol must also prohibit:

- changing success criteria after observing results;
- selecting favorable case families after looking at scores;
- modifying the prompt after seeing outputs; and
- treating the mere appearance of one interior decimal as proof of a useful
  graded signal.

Any difficulty increase must be specified and frozen before execution, with
truth and provenance independently auditable without using the characterization
scores.

## 6. Requirements for a later executable characterization protocol

This ratified governance addendum deliberately chooses none of the following
design values. The
later executable characterization protocol inherits the immutable scientific
invariants in Section 4. It must record and verify their exact references and
hashes in its execution authority; it does not choose or re-decide them. A
later executable characterization protocol must freeze each remaining design
item before execution:

- case-generation and authorship method;
- exact case surface;
- structures and operationalized difficulty dimensions;
- case count and allocation;
- mechanical truth authority;
- inherited exact model/configuration reference and hash;
- inherited exact scoring-prompt byte reference and hash;
- inherited exact request/response and score-response contract;
- exact call budget;
- provider-failure/retry policy, consistent with the inherited no-client-retry
  apparatus;
- analysis quantities;
- definitions of endpoint and interior scoring;
- definition of **reproducibly graded** behavior;
- discrimination and accuracy measurements;
- STOP conditions;
- provenance and evidence-retention requirements;
- independence and leakage review; and
- explicit scientific nonclaims.

The later preregistration must define how the intended difficulty manipulation
will be evaluated independently of merely observing interior decimal scores.
It must report accuracy and discrimination alongside score-distribution and
gradedness behavior for all four interpretation branches. No numerical
accuracy, discrimination, or other decision threshold is chosen here. A
nominally harder surface is not, by itself, evidence that the model experienced
greater difficulty.

The later protocol must also identify, measure, and, where practical, control
or balance foreseeable nuisance variables that may covary with intended
epistemic difficulty, including input/case length and lexical/surface
complexity. This ratified governance addendum prescribes no exact matching or
balancing procedure;
the purpose is to prevent output changes caused by incidental surface
properties from being automatically attributed to reasoning difficulty.

The later preregistration must specify, before calls, how reproducibility of
graded behavior will be assessed. Possible categories include repeated
independently constructed equivalent cases, planned repeated measurements, or
another preregistered reliability design; this ratified governance addendum
selects none of these designs, and does not require exactly one measurement per
underlying case.
Planned scientific repeated measurements must remain distinct from provider-
failure retry policy, and all such measurements must be included in the frozen
call budget before execution. A single interior decimal remains insufficient
evidence of a reproducibly graded signal.

The later protocol must record its freeze point and authority before any model,
provider, or API call. It must not make experimental decisions that belong to
that later protocol-design arc under the guise of executing this governance
addendum.

## 7. Predeclared interpretation tree

The following conceptual outcomes are preserved before execution. They are
interpretive branches, not quantitative decision criteria; this ratified
governance addendum does not choose thresholds, effect sizes, or acceptance
cutoffs for them.

### A. Stable interior scores with good discrimination

Stable interior scores emerge while discrimination remains good. This supports
task ceiling as an important contributor and establishes that the exact frozen
setup can expose graded signal on the separately preregistered characterization
surface. It does not resurrect Stage 1B.

### B. Endpoint saturation despite greater difficulty

Scores remain essentially `{0,1}` despite materially increased epistemic
difficulty. This shifts interpretive weight toward elicitation behavior or H3
and weakens the rationale for using this exact scoring setup as a scalar-
threshold input only if the independently preregistered difficulty evaluation
shows that the manipulation actually increased model difficulty. Endpoint-only
scores on a nominally harder surface do not by themselves weaken H1: the model
may have remained effectively at its competence ceiling.

### C. Interior scores without a reliable scientific relationship

Interior scores emerge but are unstable or noisy, unrelated to preregistered
difficulty, systematically misaligned with truth or discrimination, or
otherwise fail the preregistered reliability relationship. This shows that the
setup can emit intermediate decimals without establishing a reliable
threshold-adaptable signal. Numerical gradedness alone does not establish
calibration, threshold usefulness, or meaningful uncertainty representation.

### D. Accuracy degrades while confidence remains extreme

Accuracy degrades while reported confidence remains extreme. This shows that
the task ceiling was exceeded while the scoring setup still failed to express
useful uncertainty, and is particularly important evidence against treating
the output as a graded threshold-control signal.

## 8. Result authority and nonclaims

Future characterization evidence may speak only to the behavior of the exact
frozen scoring setup on its separately preregistered characterization surface.
It cannot by itself establish:

- success or failure of history-conditioned prospective control;
- success or failure of Stage 1B;
- general Luna calibration;
- general LLM calibration;
- superiority of another mechanism; or
- architecture conclusions.

It also cannot generalize beyond the frozen characterization surface, alter the
construct from prospective-control applicability, or convert an exploratory
observation into a protocol result for the closed Stage-1A arc.

### H1 identifiability limitation

A single endpoint-only result on a nominally harder characterization surface
cannot, by itself, definitively rule out H1. It may mean that elicitation
remained endpoint-collapsed, that H3 persists, or that the preregistered
surface still failed to move the model meaningfully off its competence ceiling.
Therefore this characterization can shift evidential weight among H1, H2, and
H3, but it is not claimed to uniquely identify their causal contributions.

A result in which independently measured task performance actually degrades
while reported confidence remains extreme has stronger diagnostic meaning: it
shows that the task ceiling was exceeded while the scoring setup still failed
to express useful uncertainty. This remains evidence against treating the
output as a graded threshold-control signal, without becoming a claim about
general Luna or LLM calibration.

## 9. Current authority and explicit prohibitions

Ryan's ratification authorizes, at present:

- **zero characterization execution**;
- **zero case generation**;
- **zero model/provider/API calls**;
- **zero Stage 1B work**;
- **zero corrective reruns**;
- **zero driver implementation**;
- **zero richer mechanisms**; and
- **zero architecture work**.

No characterization cases are to be created under this ratified governance
addendum. No experimental decisions that properly belong to the later
executable protocol-design arc are made here. No agent may treat this addendum
as an execution brief or as permission to alter any frozen authority.

Any executable characterization still requires a separately preregistered
protocol and separate explicit authorization. Ratification of this governance
addendum does not itself authorize execution, case generation, model/provider/
API calls, Stage 1B work, corrective reruns, driver implementation, richer
mechanisms, or architecture work.
