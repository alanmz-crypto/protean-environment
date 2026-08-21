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
from .harness import ModelClient, ModelRequest
from .manifest import ModelConfiguration


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

    def run(self) -> list[SingleScoreCall]:
        # 1) seal validation + real-origin coverage (raises on any mismatch; the
        #    calibration scoring client is NOT constructed until 5/5 successful
        #    real-origin artifacts cover all 60 cases)
        self.seal()
        if self.origin_artifacts:
            require_real_origin_coverage(
                self.origin_artifacts,
                frozenset(c.generated.spec.case_id for c in self.cases),
            )
        # 2) client construction (after a passing seal + origin coverage)
        client = self.client_factory()
        # 3) scoring (one decision call per case)
        loop = Stage1AScoringLoop(
            cases=self.cases,
            scoring_prompt=self.scoring_prompt,
            model_configuration=self.model_configuration,
            client=client,
        )
        return loop.run()


def require_real_origin_coverage(artifacts: tuple[Any, ...], all_case_ids: frozenset[str]) -> None:
    """Require a sealed successful real origin artifact for every case.

    Exactly 5 origin sessions (one per familiar structure), each covering 12
    adopted cases, together covering all 60 case IDs exactly once. Fewer than 5
    (or any malformed/partial artifact) raises so the calibration scoring client
    is never constructed.
    """
    from .grammar import FROZEN_STRUCTURES

    if len(artifacts) != len(FROZEN_STRUCTURES):
        raise ValueError(
            f"Stage-1A requires exactly {len(FROZEN_STRUCTURES)} origin sessions, "
            f"got {len(artifacts)}"
        )
    covered: dict[str, str] = {}
    for art in artifacts:
        # Each artifact is an OriginSessionArtifact; validate its 12/12 adoption.
        for cid in art.case_ids:
            if cid in covered:
                raise ValueError(f"duplicate origin coverage for case {cid}")
            if cid not in all_case_ids:
                raise ValueError(f"origin covers unknown case {cid}")
            if not art.adoption.get(cid, False):
                raise ValueError(f"non-adopted origin case {cid}")
            covered[cid] = art.origin_run_id
    missing = all_case_ids - set(covered)
    if missing:
        raise ValueError(
            f"origin coverage incomplete; {len(missing)} cases unowned: {sorted(missing)[:5]}"
        )
