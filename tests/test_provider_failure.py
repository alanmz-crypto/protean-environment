"""Harness-level tests for provider-failure evidence classification.

These exercise run_single_decision_loop against clients that raise the typed
provider failures, and assert the recorded RawResult carries the failure category,
HTTP status, and preserved raw bytes — and that a model-formatting failure is
NEVER recorded as a generic provider/API failure.
"""

from __future__ import annotations

from typing import Any

import pytest

from protean_stage0.harness import (
    ModelClient,
    ModelRequest,
    ModelResponse,
    ProviderFailure,
    run_single_decision_loop,
)
from protean_stage0.provider_failure import (
    HttpFailure,
    HttpFailureEvidence,
    ModelFormattingFailure,
    ResponseContractFailure,
    TransportFailure,
)
from protean_stage0.results import ParseStatus, Stage0Decision

from .helpers import validated_test_run


class TypedFailingClient(ModelClient):
    """Fails the first call with the configured exception; counts calls."""

    def __init__(self, exc: Exception) -> None:
        self.exc = exc
        self.calls = 0

    def make_single_decision(self, request: ModelRequest) -> ModelResponse:
        self.calls += 1
        raise self.exc


def _run(exc: Exception) -> tuple[Any, int]:
    client = TypedFailingClient(exc)
    result = run_single_decision_loop(validated_run=validated_test_run(), client=client)
    return result, client.calls


def test_model_formatting_failure_recorded_not_generic_provider() -> None:
    result, calls = _run(ModelFormattingFailure("malformed decimal", raw_response=b"0.xx"))
    assert calls == 1
    assert result.decision is Stage0Decision.STOP
    row = result.raw_results[0]
    assert row.parse_status is ParseStatus.MODEL_FORMATTING_FAILURE
    assert row.provider_failure_category == "model_formatting"
    assert row.mechanical_error_status is None
    # raw provider bytes preserved when they exist
    assert row.raw_model_response == b"0.xx"


def test_transport_failure_recorded_as_provider_api_failure() -> None:
    result, calls = _run(TransportFailure("no route"))
    assert calls == 1
    row = result.raw_results[0]
    assert row.parse_status is ParseStatus.PROVIDER_API_FAILURE
    assert row.provider_failure_category == "transport"
    assert row.raw_model_response is None


def test_http_failure_records_status_and_category() -> None:
    evidence = HttpFailureEvidence(status_code=429, raw_error_body=b'{"error":"busy"}')
    result, calls = _run(HttpFailure("HTTP 429 (no retry)", evidence))
    assert calls == 1
    row = result.raw_results[0]
    assert row.parse_status is ParseStatus.PROVIDER_API_FAILURE
    assert row.provider_failure_category == "http"
    assert row.provider_http_status == 429
    # safe evidence in metadata never carries credentials
    assert row.provider_metadata == evidence.safe_record()


def test_contract_failure_recorded_as_provider_api_failure() -> None:
    result, calls = _run(ResponseContractFailure("returned model mismatch"))
    assert calls == 1
    row = result.raw_results[0]
    assert row.parse_status is ParseStatus.PROVIDER_API_FAILURE
    assert row.provider_failure_category == "response_contract"


def test_bare_provider_failure_defaults_to_generic() -> None:
    result, calls = _run(ProviderFailure("unclassified"))
    assert calls == 1
    row = result.raw_results[0]
    assert row.parse_status is ParseStatus.PROVIDER_API_FAILURE
    assert row.provider_failure_category == "provider"


def test_unexpected_client_exception_propagates_not_transport() -> None:
    # A RuntimeError/TypeError from client code is an internal/mechanical harness
    # failure, NOT a transport result. It must propagate out of the loop and
    # never be recorded with provider_failure_category == "transport".
    for exc in (RuntimeError("client bug"), TypeError("bad call")):
        client = TypedFailingClient(exc)
        with pytest.raises(type(exc)):
            run_single_decision_loop(validated_run=validated_test_run(), client=client)
        assert client.calls == 1


def test_model_formatting_never_creates_mechanical_defect_evidence() -> None:
    result, calls = _run(ModelFormattingFailure("bad output"))
    assert calls == 1
    assert result.raw_results[0].mechanical_error_status is None
    assert result.raw_results[0].parse_status is not ParseStatus.VALID_SCORE


def test_no_retry_after_any_failure() -> None:
    # The loop must make exactly one decision call and stop.
    for exc in (
        TransportFailure("x"),
        HttpFailure("x", HttpFailureEvidence(500)),
        ResponseContractFailure("x"),
        ModelFormattingFailure("x"),
    ):
        _, calls = _run(exc)
        assert calls == 1
