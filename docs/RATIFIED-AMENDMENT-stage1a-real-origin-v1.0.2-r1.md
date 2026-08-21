# RATIFIED AMENDMENT — Stage-1A Real-Origin Mechanics (v1.0.2-r1)

**STATUS: RATIFIED** (explicit human ratification by Ryan).

## Ratification metadata

- **status:** RATIFIED
- **ratified source path:** `docs/PROPOSED-AMENDMENT-stage1a-real-origin-v1.0.2-r1.md`
- **ratified source commit:** `86fbfc6385e976b274cf300620a63b34bb705f40` (exact PR #4 head)
- **exact human ratification statement:**
  > Ryan explicitly ratified `docs/PROPOSED-AMENDMENT-stage1a-real-origin-v1.0.2-r1.md`
  > at PR #4 head `86fbfc6385e976b274cf300620a63b34bb705f40`, including: exactly 5
  > GPT-5.6 Luna xHigh Responses API origin requests; adoption-not-authorship
  > semantics; frozen origin prompt; frozen origin-adoption-v1 response contract;
  > zero retries; all-five-before-calibration STOP discipline.
- **ratification date:** 2026-08-21
- **frozen Stage-1A case-set SHA-256:**
  `6851bf6f49f080ca3ede7938e207b835e5b3ac7cf531e3a460fb74393adecf41`
- **origin prompt SHA-256:**
  `f17d7e99f1c09abfa4869a2f8363cca283d5b859a3d824b02c4002189f93ccfe`
- **response-contract version / SHA-256:**
  `origin-adoption-v1` / `430900f7fdb4703920eb70a29f8a4e15972bf0292e8a6369a4df028c90ba4c42`
- **authoritative Luna configuration SHA-256 (DIRECT_CONFIG_HASH):**
  `b3e21561ef3f84e2c38275f761ba8c7cbdf1e4a2ede04972f924f58d4827d9fa`

The scientific substance of Sections 1-8 below is **identical** to the ratified
source (the DRAFT at commit `86fbfc6…`). Only the title/status and this metadata
header were added; no scientific rule changed.

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

## 7. Frozen execution authorities (final, for ratification)

The document we ratify names the actual frozen execution authorities:

- **origin prompt SHA-256:** `f17d7e99f1c09abfa4869a2f8363cca283d5b859a3d824b02c4002189f93ccfe`
- **response-contract version:** `origin-adoption-v1`
- **response-contract SHA-256:** `430900f7fdb4703920eb70a29f8a4e15972bf0292e8a6369a4df028c90ba4c42`
- **authoritative Luna configuration SHA-256 (DIRECT_CONFIG_HASH):**
  `b3e21561ef3f84e2c38275f761ba8c7cbdf1e4a2ede04972f924f58d4827d9fa`

## 8. Freeze statement

FROZEN Protocol v1.0 is not altered in place by this document. If ratified, this
amendment becomes a separately documented protocol revision governing the
Stage-1A real-origin phase only, prior to any Stage-1A (origin or calibration)
execution.
