"""Sealed Stage-1A calibration loop (not live-executed by default).

Applies the shared-score authority: for each of the 60 calibration cases it makes
exactly ONE model decision call, captures that single raw applicability score, and
feeds the SAME score to B (threshold 0.50) and C. It then runs the frozen
17-threshold C selection and the ratified futility determination.

This is testable hermetically via a fake ModelClient. No live model call is made
here; the experimental 60-call execution requires separate authorization.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from .artifacts import FrozenArtifact
from .grammar import FROZEN_STRUCTURES, StructureId
from .harness import ModelClient, ModelRequest
from .manifest import ModelConfiguration
from .stage1a_origin import ORIGIN_PROMPT, verify_origin_artifact


@dataclass(frozen=True, slots=True)
class SingleScoreCall:
    """One case -> exactly one raw model score (shared), plus the scored cases."""

    case_id: str
    raw_score: float
    truth_label: bool
    provider_metadata: Mapping[str, Any]


class Stage1AScoringLoop:
    """Runs Stage-1A calibration with exactly one decision call per case."""

    def __init__(
        self,
        *,
        cases: tuple[Any, ...],
        scoring_prompt: FrozenArtifact,
        model_configuration: ModelConfiguration,
        client: ModelClient,
    ) -> None:
        self.cases = cases  # tuple of Stage1ACase
        self.scoring_prompt = scoring_prompt
        self.model_configuration = model_configuration
        self.client = client

    def run(self) -> list[SingleScoreCall]:

        out: list[SingleScoreCall] = []
        for case in self.cases:
            req = ModelRequest(
                scoring_prompt=self.scoring_prompt.content,
                model_visible_payload=dict(case.cross_session.judgment_context),
                model_configuration=self.model_configuration,
                case_id=case.generated.spec.case_id,
            )
            # Exactly one decision call per case.
            resp = self.client.make_single_decision(req)
            from .parse_contract import parse_plain_decimal_v1

            # Frozen score contract: exactly ascii (0.[0-9]{2}|1.00) with optional
            # single trailing LF. Rejects 1, 0.5, whitespace-padded, scientific
            # notation, and any extra text.
            score = parse_plain_decimal_v1(resp.raw_response)
            if score is None:
                raise ValueError(f"non-decimal score for {case.generated.spec.case_id}")
            out.append(
                SingleScoreCall(
                    case_id=case.generated.spec.case_id,
                    raw_score=score,
                    truth_label=case.generated.truth_label,
                    provider_metadata=dict(resp.provider_metadata or {}),
                )
            )
        return out


@dataclass(frozen=True, slots=True)
class Stage1APreparedRun:
    """Integrated Stage-1A preflight + scoring with strict ordering.

    Ordering guarantee: seal validation runs FIRST; only if it passes is the
    model client constructed; only then is scoring executed. A seal mismatch
    therefore results in zero client constructions and zero calls.
    """

    cases: tuple[Any, ...]
    scoring_prompt: FrozenArtifact
    model_configuration: ModelConfiguration
    seal: Any  # callable that raises on mismatch (validate_stage1a_manifest_seal)
    client_factory: Any  # callable returning a ModelClient
    origin_artifacts: tuple[Any, ...] = ()
    completed_run: Any = (
        None  # CompletedOriginRun (required; 5 standalone artifacts are NOT enough)
    )

    def run(self) -> list[SingleScoreCall]:
        # 1) seal validation + MANDATORY real-origin coverage. Structure/coverage
        #    alone is insufficient: every artifact must ALSO pass the full real
        #    origin verifier (exact structure, 12 IDs, commitment records, exact
        #    request SHA, preserved raw provider bytes + SHA, strict Responses-JSON
        #    reparse, final-output match, and the EXACT origin-adoption-v1 contract).
        #    Any failure (including zero artifacts) raises BEFORE the calibration
        #    scoring client is constructed.
        self.seal()
        require_real_origin_coverage(
            self.origin_artifacts,
            frozenset(c.generated.spec.case_id for c in self.cases),
            case_to_structure={
                c.generated.spec.case_id: c.generated.spec.structure_id for c in self.cases
            },
        )
        expected_ids_by_structure: dict[StructureId, list[str]] = {
            structure: [] for structure in FROZEN_STRUCTURES
        }
        expected_records_by_structure: dict[StructureId, list[tuple[str, bytes]]] = {
            structure: [] for structure in FROZEN_STRUCTURES
        }
        for c in self.cases:
            expected_ids_by_structure[c.generated.spec.structure_id].append(
                c.generated.spec.case_id
            )
            expected_records_by_structure[c.generated.spec.structure_id].append(
                (c.generated.spec.case_id, c.textualized.commitment.encode())
            )
        for art in self.origin_artifacts:
            expected_ids = tuple(expected_ids_by_structure[art.structure])
            expected_records = tuple(expected_records_by_structure[art.structure])
            verify_origin_artifact(
                art,
                origin_prompt=ORIGIN_PROMPT,
                expected_structure=art.structure,
                expected_case_ids=expected_ids,
                expected_commitment_records=expected_records,
            )
        # 1b) MANDATORY completed-run authority: five standalone artifacts are NOT
        #     sufficient. Require one completed run (5/5/0) whose manifest SHA and
        #     batch match all artifacts, with request indices 1..5 exactly once,
        #     expected structures exactly once, and per-index artifact SHAs
        #     matching the completed authority.
        if self.completed_run is None:
            raise ValueError("Stage-1A calibration requires a sealed CompletedOriginRun")
        completed = self.completed_run
        if (
            completed.attempts != 5
            or completed.successes != 5
            or completed.failures != 0
            or len(completed.artifact_shas) != 5
        ):
            raise ValueError("CompletedOriginRun must be 5 attempts / 5 successes / 0 failures")
        if len(self.origin_artifacts) != 5:
            raise ValueError("calibration requires exactly five origin artifacts")
        artifacts_by_index = {a.request_index: a for a in self.origin_artifacts}
        if set(artifacts_by_index) != {1, 2, 3, 4, 5}:
            raise ValueError("origin artifacts must have request indices 1..5 exactly once")
        structures_seen = {a.structure for a in self.origin_artifacts}
        if structures_seen != set(FROZEN_STRUCTURES):
            raise ValueError("origin artifacts must cover every frozen structure exactly once")
        for art in self.origin_artifacts:
            if art.batch_run_id != completed.batch_run_id:
                raise ValueError("origin artifact batch/run ID does not match completed run")
            if getattr(art, "origin_manifest_sha256", None) != completed.manifest_sha256:
                raise ValueError("origin artifact manifest SHA does not match completed run")
            if art.sha256 != completed.artifact_shas[art.request_index - 1]:
                raise ValueError("origin artifact SHA does not match completed-run authority")
        # 2) client construction (after passing seal + origin coverage + verifier
        #    + completed-run authority)
        client = self.client_factory()
        # 3) scoring (one decision call per case)
        loop = Stage1AScoringLoop(
            cases=self.cases,
            scoring_prompt=self.scoring_prompt,
            model_configuration=self.model_configuration,
            client=client,
        )
        return loop.run()


def require_real_origin_coverage(
    artifacts: tuple[Any, ...],
    all_case_ids: frozenset[str],
    case_to_structure: Mapping[str, Any] | None = None,
) -> None:
    """Require a sealed successful real origin artifact for every case. MANDATORY.

    Exactly 5 origin sessions, one per familiar structure, each covering exactly
    the 12 Stage-1A cases belonging to that structure. No case may migrate between
    structure groups. All 60 case IDs covered exactly once. ``()`` (zero artifacts)
    or any malformed/partial artifact raises, so the calibration scoring client is
    never constructed. Note: adoption correctness is proven separately by
    verify_origin_artifact (this gate checks coverage/migration only).
    """
    from .grammar import FROZEN_STRUCTURES

    if len(artifacts) != len(FROZEN_STRUCTURES):
        raise ValueError(
            f"Stage-1A requires exactly {len(FROZEN_STRUCTURES)} origin sessions, "
            f"got {len(artifacts)}"
        )
    structures_seen: set[Any] = set()
    covered: dict[str, str] = {}
    for art in artifacts:
        structure = getattr(art, "structure", None)
        if structure in structures_seen:
            raise ValueError(f"duplicate origin structure: {structure}")
        structures_seen.add(structure)
        for cid in art.case_ids:
            if cid in covered:
                raise ValueError(f"duplicate origin coverage for case {cid}")
            if cid not in all_case_ids:
                raise ValueError(f"origin covers unknown case {cid}")
            if (
                case_to_structure is not None
                and cid in case_to_structure
                and case_to_structure[cid] is not structure
            ):
                raise ValueError(f"case {cid} migrated between structure groups")
            covered[cid] = art.origin_run_id
    if set(structures_seen) != set(FROZEN_STRUCTURES):
        raise ValueError("origin sessions must cover every frozen structure exactly once")
    missing = all_case_ids - set(covered)
    if missing:
        raise ValueError(
            f"origin coverage incomplete; {len(missing)} cases unowned: {sorted(missing)[:5]}"
        )
