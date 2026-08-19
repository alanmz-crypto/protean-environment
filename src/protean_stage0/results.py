"""Immutable raw-result representation for Stage 0."""

from __future__ import annotations

import base64
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from .artifacts import FrozenArtifact, canonical_json_bytes


class ParseStatus(StrEnum):
    VALID_SCORE = "valid_score"
    MODEL_FORMATTING_FAILURE = "model_formatting_failure"
    PROVIDER_API_FAILURE = "provider_api_failure"


class Stage0Decision(StrEnum):
    PASS = "PASS"
    STOP = "STOP"


@dataclass(frozen=True, slots=True)
class RawResult:
    run_id: str
    case_id: str
    truth_label: bool
    returned_score: float | None
    raw_model_response: bytes | None
    model_provider: str
    model_id: str
    model_configuration_sha256: str
    provider_metadata: Mapping[str, Any] | None
    timestamp: str
    call_order: int
    parse_status: ParseStatus
    mechanical_error_status: str | None = None

    def canonical_record(self) -> dict[str, Any]:
        encoded_response = (
            base64.b64encode(self.raw_model_response).decode("ascii")
            if self.raw_model_response is not None
            else None
        )
        return {
            "call_order": self.call_order,
            "case_id": self.case_id,
            "mechanical_error_status": self.mechanical_error_status,
            "model_configuration_sha256": self.model_configuration_sha256,
            "model_id": self.model_id,
            "model_provider": self.model_provider,
            "parse_status": self.parse_status.value,
            "provider_metadata": dict(self.provider_metadata) if self.provider_metadata else None,
            "raw_model_response_base64": encoded_response,
            "returned_score": self.returned_score,
            "run_id": self.run_id,
            "timestamp": self.timestamp,
            "truth_label": self.truth_label,
        }


@dataclass(frozen=True, slots=True)
class CallLoopResult:
    raw_results: tuple[RawResult, ...]
    decision: Stage0Decision | None
    stop_reason: str | None


def freeze_raw_results(run_id: str, results: tuple[RawResult, ...]) -> FrozenArtifact:
    if not results or any(result.run_id != run_id for result in results):
        raise ValueError("raw results must be non-empty and belong to one run")
    content = canonical_json_bytes(
        {"raw_results": [result.canonical_record() for result in results], "run_id": run_id}
    )
    return FrozenArtifact.from_bytes(f"raw-results-{run_id}", content)
