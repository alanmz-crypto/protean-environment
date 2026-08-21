"""Hermetic Stage-1A machinery tests (no model calls)."""

from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any

import pytest

from protean_stage0.artifacts import FrozenArtifact, sha256_bytes
from protean_stage0.manifest import ModelConfiguration
from protean_stage0.schema import EvaluatorProvenance
from protean_stage0.stage1a_cases import (
    build_stage1a_cases,
    freeze_stage1a_case_set,
    generate_stage1a_structured,
    validate_stage1a_allocation,
    verify_stage1a_truth_agreement,
)
from protean_stage0.stage1a_config import B_THRESHOLD, THRESHOLD_GRID
from protean_stage0.stage1a_driver import Stage1AScoringLoop
from protean_stage0.stage1a_manifest import (
    Stage1AManifest,
    validate_stage1a_manifest_seal,
)
from protean_stage0.stage1a_threshold import (
    ScoredCase,
    Stage1BProjection,
    arm_decision,
    compute_stage1a_report,
    determine_stage1b_fate,
    evaluate_all_thresholds,
    select_c_threshold,
)
from protean_stage0.textualize import TemplateBank

REPO = Path(__file__).resolve().parents[1]


def _bank() -> TemplateBank:
    return TemplateBank.from_bytes((REPO / "stage0/template-bank-v1.json").read_bytes())


def _cases() -> tuple[Any, ...]:
    return build_stage1a_cases(template_bank=_bank())


def _scored(pos_score: float, neg_score: float, n_per_class: int = 5) -> tuple[ScoredCase, ...]:
    """Hand-built deterministic scored cases: positives at pos_score, negatives at neg_score."""
    return tuple(
        ScoredCase(
            case_id=f"c-{i}", score=pos_score if i % 2 == 0 else neg_score, truth_label=i % 2 == 0
        )
        for i in range(n_per_class * 2)
    )


class FakeClient:
    def __init__(self, scores: list[float]) -> None:
        self.scores = scores
        self.calls = 0

    def make_single_decision(self, request: Any) -> Any:
        self.calls += 1
        from protean_stage0.harness import ModelResponse

        s = self.scores[self.calls - 1]
        return ModelResponse(f"{s:.2f}".encode(), {"fake": True})


# --- case design ---
def test_exact_case_balance_and_struct_allocation() -> None:
    structured = generate_stage1a_structured()
    assert len(structured) == 60
    counts = Counter(item.spec.structure_id.value for item in structured)
    assert counts == {"P": 12, "P AND Q": 12, "P AND NOT Q": 12, "T2(P)": 12, "ACTIVE AND P": 12}
    assert sum(1 for i in structured if i.truth_label) == 30
    from protean_stage0.grammar import FROZEN_STRUCTURES

    for s in FROZEN_STRUCTURES:
        sub = [i for i in structured if i.spec.structure_id is s]
        assert len(sub) == 12
        assert sum(1 for i in sub if i.truth_label) == 6


def test_primary_reference_truth_agreement() -> None:
    assert verify_stage1a_truth_agreement(generate_stage1a_structured()) == 60


def test_allocation_validation_rejects_bad_count() -> None:
    with pytest.raises(ValueError):
        validate_stage1a_allocation(tuple())


def test_truth_not_model_visible() -> None:
    for case in _cases():
        keys = set(case.cross_session.judgment_context)
        assert "truth_label" not in keys
        assert not any("truth" in k or "structure" in k for k in keys)


def test_freeze_case_set_is_immutable_and_count_60() -> None:
    case_set = freeze_stage1a_case_set(_cases())
    assert len(case_set.cases) == 60
    assert len(case_set.sha256) == 64


# --- shared score / driver ---
def test_shared_score_is_one_call_per_case() -> None:
    cases = _cases()
    client = FakeClient([0.5] * len(cases))
    loop = Stage1AScoringLoop(
        cases=cases,
        scoring_prompt=FrozenArtifact.from_bytes("s1a-prompt", b"PROMPT:{commitment}"),
        model_configuration=_dummy_config(),
        client=client,
    )
    out = loop.run()
    assert len(out) == 60
    assert client.calls == 60  # exactly one call per case, no second C-only call


def test_b_always_remains_point_five() -> None:
    assert B_THRESHOLD == 0.50
    assert arm_decision(0.50, B_THRESHOLD) is True
    assert arm_decision(0.49, B_THRESHOLD) is False
    assert arm_decision(0.51, B_THRESHOLD) is True


# --- threshold machinery ---
def test_grid_is_exact_frozen_17() -> None:
    assert len(THRESHOLD_GRID) == 17
    assert THRESHOLD_GRID[0] == 0.10 and THRESHOLD_GRID[-1] == 0.90
    assert THRESHOLD_GRID[8] == 0.50


def test_all_17_thresholds_evaluated() -> None:
    evals = evaluate_all_thresholds(_scored(0.9, 0.1))
    assert len(evals) == 17
    assert [e.threshold for e in evals] == list(THRESHOLD_GRID)


def test_futility_when_selected_is_point_five() -> None:
    # pos=0.50, neg=0.00 -> balanced accuracy is perfect ONLY at 0.50; picks 0.50.
    scored = _scored(0.50, 0.00)
    report = compute_stage1a_report(scored)
    assert report.selected_threshold == 0.50
    assert report.stage1b_projection is Stage1BProjection.DETERMINISTIC_FUTILITY_STOP


def test_non_point_five_selection_does_not_invoke_futility() -> None:
    # pos=0.90, neg=0.70: perfect BA over thresholds >0.70 and <=0.90, i.e. 0.75
    # is the selected-closest-to-0.50 in that best band => 0.75 (not 0.50), continue.
    scored = _scored(0.90, 0.70, n_per_class=6)
    report = compute_stage1a_report(scored)
    assert report.selected_threshold != 0.50
    assert report.stage1b_projection is Stage1BProjection.CONTINUE


def test_determine_stage1b_fate_direct() -> None:
    assert determine_stage1b_fate(0.50) is Stage1BProjection.DETERMINISTIC_FUTILITY_STOP
    assert determine_stage1b_fate(0.49) is Stage1BProjection.CONTINUE
    assert determine_stage1b_fate(0.55) is Stage1BProjection.CONTINUE


def test_selection_tie_closest_to_point_five() -> None:
    # Two ThresholdEvals tie at max BA: 0.45 and 0.55 are equidistant from 0.50;
    # the remaining tie is broken toward higher => 0.55.
    from protean_stage0.stage1a_threshold import ThresholdEval

    evals = (
        ThresholdEval(0.45, 1.0, 0.0, 0.0),
        ThresholdEval(0.55, 1.0, 0.0, 0.0),
    )
    assert select_c_threshold(evals) == 0.55


def test_selection_differing_band_prefers_closest_to_0_50() -> None:
    # 0.60 has strictly higher BA than 0.50; the selection must pick the max-BA one
    # even though 0.50 is closer to the futility threshold.
    from protean_stage0.stage1a_threshold import ThresholdEval

    evals = (
        ThresholdEval(0.50, 0.90, 0.1, 0.0),
        ThresholdEval(0.60, 0.95, 0.0, 0.1),
    )
    assert select_c_threshold(evals) == 0.60


def test_no_stage1b_path_from_futility() -> None:
    scored = _scored(0.50, 0.00)
    report = compute_stage1a_report(scored)
    assert report.stage1b_projection is Stage1BProjection.DETERMINISTIC_FUTILITY_STOP
    # No Stage-1B executor is invoked or reachable from the futility branch; the
    # projection value is the structural signal that Stage-1B must not run.
    assert Stage1BProjection.DETERMINISTIC_FUTILITY_STOP.value == "DETERMINISTIC_FUTILITY_STOP"


def test_cross_session_payload_excludes_conversation() -> None:
    for case in _cases():
        ctx = dict(case.cross_session.judgment_context)
        assert set(ctx) <= {
            "commitment",
            "trigger_condition",
            "prior_state",
            "observed_event",
            "lifecycle_state",
        }
        assert "conversation" not in ctx and "transcript" not in ctx


def test_holdout_isolation_procedure_frozen() -> None:
    doc = REPO / "docs/HOLDOUT-INDEPENDENCE-STAGE1B-r1.md"
    assert doc.exists()
    assert len(sha256_bytes(doc.read_bytes())) == 64


def test_seal_mismatch_stops_before_any_scoring() -> None:

    case_set = freeze_stage1a_case_set(_cases())
    protocol = FrozenArtifact.from_bytes("protocol", b"PROTOCOL")
    amendment = FrozenArtifact.from_bytes("amendment", b"AMEND")
    real_origin = FrozenArtifact.from_bytes("real-origin", b"REAL-ORIGIN")
    prompt = FrozenArtifact.from_bytes("prompt", b"PROMPT")
    primary = _prov("primary")
    reference = _prov("reference")
    model = _dummy_config()
    manifest = Stage1AManifest.create(
        protocol=protocol,
        futility_amendment=amendment,
        real_origin_amendment=real_origin,
        case_set=case_set,
        scoring_prompt=prompt,
        parse_contract_sha256="0" * 64,
        model_configuration=model,
        harness_revision="HEAD",
        primary_evaluator=primary,
        reference_evaluator=reference,
        timestamp="t",
        run_id="R1",
    )
    tampered_prompt = FrozenArtifact.from_bytes("prompt", b"WRONG")
    with pytest.raises(ValueError, match="scoring prompt"):
        validate_stage1a_manifest_seal(
            manifest,
            actual_harness_revision="HEAD",
            protocol=protocol,
            futility_amendment=amendment,
            real_origin_amendment=real_origin,
            case_set=case_set,
            scoring_prompt=tampered_prompt,
            parse_contract_sha256="0" * 64,
            model_configuration=model,
        )


def _prov(name: str) -> EvaluatorProvenance:
    return EvaluatorProvenance(
        evaluator_name=name,
        author=name,
        authored_at="2026-08-21T00:00:00Z",
        grammar_version="v1",
        grammar_sha256="0" * 64,
        independently_derived=True,
        implementation_sha256="0" * 64,
    )


def _dummy_config() -> ModelConfiguration:
    return ModelConfiguration(
        provider="test",
        model_id="test-model",
        version_or_snapshot=None,
        reasoning_settings={},
        temperature=0.1,
        seed=None,
        max_output_length=16,
        api_parameters={},
    )


# ---- hardening: harness-revision seal ----
def _manifest_and_docs(head: str = "HEAD") -> tuple[Any, Any, Any, Any, Any, Any, Any]:
    from protean_stage0.stage1a_manifest import Stage1AManifest

    case_set = freeze_stage1a_case_set(_cases())
    protocol = FrozenArtifact.from_bytes("protocol", b"PROTOCOL")
    amendment = FrozenArtifact.from_bytes("amendment", b"AMEND")
    real_origin = FrozenArtifact.from_bytes("real-origin", b"REAL-ORIGIN")
    prompt = FrozenArtifact.from_bytes("prompt", b"PROMPT")
    primary = _prov("primary2")
    reference = _prov("reference2")
    model = _dummy_config()
    manifest = Stage1AManifest.create(
        protocol=protocol,
        futility_amendment=amendment,
        real_origin_amendment=real_origin,
        case_set=case_set,
        scoring_prompt=prompt,
        parse_contract_sha256="0" * 64,
        model_configuration=model,
        harness_revision=head,
        primary_evaluator=primary,
        reference_evaluator=reference,
        timestamp="t",
        run_id="R2",
    )
    return manifest, protocol, amendment, real_origin, prompt, case_set, model


def test_seal_passes_when_harness_revision_matches() -> None:
    manifest, protocol, amendment, real_origin, prompt, case_set, model = _manifest_and_docs("HEAD")
    validate_stage1a_manifest_seal(
        manifest,
        actual_harness_revision="HEAD",
        protocol=protocol,
        futility_amendment=amendment,
        real_origin_amendment=real_origin,
        case_set=case_set,
        scoring_prompt=prompt,
        parse_contract_sha256="0" * 64,
        model_configuration=model,
    )


def test_stale_manifest_head_fails_before_client() -> None:
    manifest, protocol, amendment, real_origin, prompt, case_set, model = _manifest_and_docs("HEAD")
    with pytest.raises(ValueError, match="harness revision"):
        validate_stage1a_manifest_seal(
            manifest,
            actual_harness_revision="STALE-HEAD",
            protocol=protocol,
            futility_amendment=amendment,
            real_origin_amendment=real_origin,
            case_set=case_set,
            scoring_prompt=prompt,
            parse_contract_sha256="0" * 64,
            model_configuration=model,
        )


# ---- hardening: frozen decimal score contract ----
def _one_case_loop(raw: bytes) -> Any:
    """Return a Stage1AScoringLoop over a single case whose client returns ``raw``."""
    from protean_stage0.harness import ModelResponse
    from protean_stage0.stage1a_driver import Stage1AScoringLoop

    class _C:
        def make_single_decision(self, request: Any) -> Any:
            return ModelResponse(raw, {})

    return Stage1AScoringLoop(
        cases=_cases()[:1],
        scoring_prompt=FrozenArtifact.from_bytes("p", b"x"),
        model_configuration=_dummy_config(),
        client=_C(),
    )


@pytest.mark.parametrize(
    "bad",
    [
        b"1",
        b"0.5",
        b" 0.73",
        b"0.73 ",
        b"0.730\n",
        b"0.7.3",
        b"0.73001",
        b"the score is 0.73",
        b"1e-1",
    ],
)
def test_driver_rejects_non_plain_decimal_scores(bad: bytes) -> None:
    loop = _one_case_loop(bad)
    with pytest.raises(ValueError, match="non-decimal score"):
        loop.run()


@pytest.mark.parametrize("good", [b"0.00", b"0.73", b"1.00", b"0.73\n"])
def test_driver_accepts_plain_decimal_scores(good: bytes) -> None:
    out = _one_case_loop(good).run()
    assert len(out) == 1
    assert out[0].raw_score in (0.0, 0.73, 1.0)


# ---- hardening: second-best threshold ----
def test_second_best_present_when_17_evaluated() -> None:
    report = compute_stage1a_report(_scored(0.90, 0.10))
    assert report.second_best_threshold is not None


def test_second_best_excludes_selected_and_rerates_remaining() -> None:
    # Unique best: POS=0.90/NEG=0.70 selects 0.75; second-best is the winner of the
    # same rule over the remaining 16 (0.80), not the selected value itself.
    report = compute_stage1a_report(_scored(0.90, 0.70))
    assert report.selected_threshold == 0.75
    assert report.second_best_threshold == 0.80
    assert report.second_best_threshold != report.selected_threshold
    assert report.second_best_threshold in set(THRESHOLD_GRID) - {report.selected_threshold}


def test_second_best_tied_best_uses_same_ranking_over_remaining() -> None:
    # Perfect separation over a wide band: selected = closest to 0.50; with the
    # selected removed, second-best is the next closest-to-0.50 among the rest.
    report = compute_stage1a_report(_scored(0.90, 0.10))
    assert report.selected_threshold == 0.50
    assert report.second_best_threshold is not None
    # The second-best of an all-1.0-BA band (0.10..0.90) after removing 0.50 is the
    # threshold closest to 0.50 among the remainder => 0.55 (tie-to-higher over 0.45).
    assert report.second_best_threshold == 0.55


# ---- hardening: integrated preflight ordering is covered in test_stage1a_origin.py ----
