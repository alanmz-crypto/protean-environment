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
            text = resp.raw_response.decode("ascii")
            try:
                score = float(text)
            except ValueError as exc:
                raise ValueError(f"non-decimal score for {case.generated.spec.case_id}") from exc
            if not 0.0 <= score <= 1.0:
                raise ValueError(f"score out of range for {case.generated.spec.case_id}")
            out.append(
                SingleScoreCall(
                    case_id=case.generated.spec.case_id,
                    raw_score=score,
                    truth_label=case.generated.truth_label,
                    provider_metadata=dict(resp.provider_metadata or {}),
                )
            )
        return out
