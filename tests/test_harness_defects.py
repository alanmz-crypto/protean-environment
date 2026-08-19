from __future__ import annotations

from dataclasses import replace

import pytest

from protean_stage0.defects import (
    MechanicalDefectEvidence,
    MechanicalDefectKind,
    RestartController,
)
from protean_stage0.harness import (
    ModelRequest,
    ModelResponse,
    ProviderFailure,
    run_single_decision_loop,
)
from protean_stage0.manifest import ExperimentalBindings, UnresolvedExperimentalInputs
from protean_stage0.results import ParseStatus, Stage0Decision, freeze_raw_results

from .helpers import validated_test_run


class FakeClient:
    def __init__(self, responses: list[bytes]) -> None:
        self.responses = responses
        self.calls: list[ModelRequest] = []

    def make_single_decision(self, request: ModelRequest) -> ModelResponse:
        self.calls.append(request)
        return ModelResponse(self.responses[len(self.calls) - 1], {"fake": True})


class FailingFakeClient:
    def __init__(self) -> None:
        self.call_count = 0

    def make_single_decision(self, request: ModelRequest) -> ModelResponse:
        self.call_count += 1
        raise ProviderFailure("synthetic transport failure")


def test_unresolved_inputs_prevent_any_call() -> None:
    client = FakeClient([b"0.50"])
    validated = validated_test_run()
    unresolved = replace(validated, bindings=ExperimentalBindings())
    with pytest.raises(UnresolvedExperimentalInputs):
        run_single_decision_loop(validated_run=unresolved, client=client)
    assert not client.calls


def test_malformed_model_output_is_stop_without_retry_or_coercion() -> None:
    client = FakeClient([b"The score is 0.75", b"0.75"])
    result = run_single_decision_loop(validated_run=validated_test_run(), client=client)
    assert result.decision is Stage0Decision.STOP
    assert result.stop_reason is not None
    assert "no restart" in result.stop_reason
    assert len(client.calls) == 1
    assert result.raw_results[0].parse_status is ParseStatus.MODEL_FORMATTING_FAILURE
    assert result.raw_results[0].returned_score is None


def test_valid_calls_are_exactly_one_per_case() -> None:
    client = FakeClient([b"0.50"] * 80)
    result = run_single_decision_loop(validated_run=validated_test_run(), client=client)
    assert result.decision is None
    assert len(client.calls) == 80
    assert len(result.raw_results) == 80
    artifact = freeze_raw_results("TEST-ONLY-RUN", result.raw_results)
    artifact.verify()
    assert b"raw_model_response_base64" in artifact.content


def test_provider_failure_is_unusable_and_not_retried() -> None:
    client = FailingFakeClient()
    result = run_single_decision_loop(validated_run=validated_test_run(), client=client)
    assert result.decision is Stage0Decision.STOP
    assert client.call_count == 1
    assert result.raw_results[0].parse_status is ParseStatus.PROVIDER_API_FAILURE


def test_mechanical_defect_allows_only_one_fresh_set_restart() -> None:
    evidence = MechanicalDefectEvidence(
        kind=MechanicalDefectKind.WRONG_PROMPT_ASSEMBLY,
        description="synthetic expected/observed prompt fingerprint mismatch",
        expected_fingerprint="expected",
        observed_fingerprint="observed",
    )
    controller = RestartController()
    controller.authorize_restart(
        evidence,
        invalidated_case_set_hash="old",
        fresh_case_set_hash="fresh-one",
    )
    assert controller.restarts_used == 1
    with pytest.raises(RuntimeError, match="only one"):
        controller.authorize_restart(
            evidence,
            invalidated_case_set_hash="fresh-one",
            fresh_case_set_hash="fresh-two",
        )


def test_same_case_set_cannot_be_used_for_restart() -> None:
    evidence = MechanicalDefectEvidence(
        kind=MechanicalDefectKind.CORRUPTED_CASE_PAYLOAD,
        description="synthetic payload fingerprint mismatch",
        expected_fingerprint="expected",
        observed_fingerprint="observed",
    )
    with pytest.raises(ValueError, match="fresh case set"):
        RestartController().authorize_restart(
            evidence,
            invalidated_case_set_hash="same",
            fresh_case_set_hash="same",
        )


def test_malformed_output_never_creates_mechanical_defect_evidence() -> None:
    client = FakeClient([b"0.750"])
    result = run_single_decision_loop(validated_run=validated_test_run(), client=client)
    assert result.decision is Stage0Decision.STOP
    assert result.raw_results[0].mechanical_error_status is None
