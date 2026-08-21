# PROPOSED AMENDMENT — Stage-1A Real-Origin Mechanics (v1.0.2-r1 DRAFT)

**STATUS: PROPOSED REVISION — NOT RATIFIED. For Ryan/ChatGPT review only.**
This is a **separate proposed amendment**, not an edit to Protocol v1.0. Protocol
v1.0 remains frozen. It does **not** self-ratify. It is presented for explicit
Ryan/ChatGPT ratification before any Stage-1A execution.

## 1. Why this amendment exists

The cross-session audit classified the committed Stage-1A origin representation
as a **MECHANICAL_GAP**: commitments were template-rendered (no real earlier
model session), so "originate in an earlier model session" (Protocol v1.0 §
Cross-session requirement) was simulated, not realized. This amendment repairs
that gap by making the earlier model session **real** without testing autonomous
commitment authorship.

## 2. Real-origin semantics (defines "originates")

A Stage-1 prospective commitment **"originates in an earlier model session"**
when **GPT-5.6 Luna explicitly adopts an externally authored prospective
commitment as its own commitment in that earlier session**. Explicitly:

- **autonomous commitment wording/authorship is NOT being tested**;
- the **externally authored frozen wording remains unchanged** (Luna does not
  rewrite, paraphrase, improve, or regenerate it);
- **adoption occurs before any later outcome/state information exists**;
- the **actual earlier model session is real**, not a synthetic identifier;
- **persistence carries the adopted commitment across the boundary**;
- the **original origin-session conversation is not carried into scoring**.

## 3. Stage-1A origin allocation (frozen)

- Exactly **5 actual GPT-5.6 Luna xHigh origin requests**;
- **one request per familiar structure** (P, P AND Q, P AND NOT Q, T2(P),
  ACTIVE AND P);
- each establishes the 12 frozen commitments belonging to that structure;
- **total commitments established = 60**, matching the frozen Stage-1A case set
  of 60 (unchanged, SHA `6851bf6f49f080ca3ede7938e207b835e5b3ac7cf531e3a460fb74393adecf41`).

## 4. Origin-session isolation (mandatory)

Origin sessions must receive **no**:

- truth labels;
- calibration scores;
- selected threshold;
- future observed event/state;
- any information revealing whether a particular case will ultimately be
  positive or negative.

## 5. Model role in origin phase

The model's role is **adoption, not authorship**. Luna confirms each listed
commitment as its own for the later prospective-trigger judgment; it does not
produce or alter commitment wording.

## 6. Origin execution discipline (frozen)

- exactly **5 independent origin requests** (one per familiar structure);
- each request issues **GPT-5.6 Luna xHigh directly through the Responses API**;
- **zero retries**;
- **all 5 must complete successfully** before any of the 60 calibration scoring
  calls may begin;
- **malformed / incomplete / refusal / non-adoption of any commitment → STOP**
  before calibration scoring;
- **no partial salvage**;
- a **dedicated origin-adoption prompt** and the **adoption response contract**
  are **frozen before origin execution**;
- origin calls are **establishment/provenance calls only** and never enter
  threshold calibration, scoring, or analysis.

## 7. Freeze statement

FROZEN Protocol v1.0 is not altered in place by this document. If ratified, this
amendment becomes a separately documented protocol revision governing the
Stage-1A real-origin phase only, prior to any Stage-1A (origin or calibration)
execution.
