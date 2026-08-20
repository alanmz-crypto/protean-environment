"""Inert, dependency-injected Stage 0 model-call scaffolding."""

from __future__ import annotations

import base64
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Protocol

from .artifacts import canonical_json_bytes, sha256_bytes
from .manifest import ModelConfiguration
from .parse_contract import PLAIN_DECIMAL_V1_SHA256, parse_plain_decimal_v1
from .provider_failure import (
    HttpFailure,
    ModelFormattingFailure,
    classify_provider_failure,
)
from .provider_failure import (
    ProviderFailure as ProviderFailure,
)
from .results import CallLoopResult, ParseStatus, RawResult, Stage0Decision
from .validation import ValidatedRun

# ProviderFailure is imported here and re-exported so adapters and tests can
# keep importing it from .harness (the shared adapter-facing module).
__all__ = ["ProviderFailure", "ModelRequest", "ModelResponse", "ModelClient"]


@dataclass(frozen=True, slots=True)
class ModelRequest:
    """Frozen prompt bytes and model-visible data remain separate exact inputs."""

    scoring_prompt: bytes
    model_visible_payload: Mapping[str, str]
    model_configuration: ModelConfiguration
    case_id: str

    @property
    def payload_sha256(self) -> str:
        return sha256_bytes(canonical_json_bytes(dict(self.model_visible_payload)))


@dataclass(frozen=True, slots=True)
class ModelResponse:
    raw_response: bytes
    provider_metadata: Mapping[str, Any]


class ModelClient(Protocol):
    def make_single_decision(self, request: ModelRequest) -> ModelResponse: ...


def run_single_decision_loop(
    *,
    validated_run: ValidatedRun,
    client: ModelClient,
) -> CallLoopResult:
    """Make at most one decision call per case and never retry a decision."""

    validated_run.assert_validated()
    cases = validated_run.case_set.cases
    bindings = validated_run.bindings
    manifest = validated_run.manifest
    prompt, model = bindings.require_frozen()
    if prompt.sha256 != manifest.scoring_prompt_sha256:
        raise ValueError("frozen prompt hash does not match manifest")
    if model.sha256 != manifest.model_configuration_sha256:
        raise ValueError("frozen model configuration does not match manifest")
    if manifest.parse_contract_sha256 != PLAIN_DECIMAL_V1_SHA256:
        raise ValueError("frozen parse contract does not match harness")

    results: list[RawResult] = []
    for call_order, case in enumerate(cases, start=1):
        request = ModelRequest(
            scoring_prompt=prompt.content,
            model_visible_payload=case.model_visible_payload(),
            model_configuration=model,
            case_id=case.case_id,
        )
        timestamp = datetime.now(UTC).isoformat()
        try:
            response = client.make_single_decision(request)
        except Exception as exc:  # bind any client exception; fail closed on it
            category, failure_metadata = classify_provider_failure(exc)
            # A model-formatting failure means the model produced unusable
            # output; it must never collapse into a generic provider/API failure.
            formatted = isinstance(exc, ModelFormattingFailure)
            http_status = exc.evidence.status_code if isinstance(exc, HttpFailure) else None
            raw_provider = getattr(exc, "raw_response", None)
            results.append(
                RawResult(
                    run_id=manifest.run_id,
                    case_id=case.case_id,
                    truth_label=case.truth_label,
                    returned_score=None,
                    raw_model_response=raw_provider,
                    model_provider=model.provider,
                    model_id=model.model_id,
                    model_configuration_sha256=model.sha256,
                    provider_metadata=failure_metadata,
                    timestamp=timestamp,
                    call_order=call_order,
                    parse_status=(
                        ParseStatus.MODEL_FORMATTING_FAILURE
                        if formatted
                        else ParseStatus.PROVIDER_API_FAILURE
                    ),
                    provider_failure_category=category,
                    provider_http_status=http_status,
                    provider_response_sha256=(
                        sha256_bytes(raw_provider) if raw_provider is not None else None
                    ),
                    provider_raw_b64=(
                        base64.b64encode(raw_provider).decode("ascii")
                        if raw_provider is not None
                        else None
                    ),
                )
            )
            if formatted:
                return CallLoopResult(
                    tuple(results),
                    Stage0Decision.STOP,
                    "model formatting failure; no restart authorized",
                )
            return CallLoopResult(tuple(results), Stage0Decision.STOP, "provider/API failure")

        score = parse_plain_decimal_v1(response.raw_response)
        if score is None:
            results.append(
                RawResult(
                    run_id=manifest.run_id,
                    case_id=case.case_id,
                    truth_label=case.truth_label,
                    returned_score=None,
                    raw_model_response=response.raw_response,
                    model_provider=model.provider,
                    model_id=model.model_id,
                    model_configuration_sha256=model.sha256,
                    provider_metadata=dict(response.provider_metadata),
                    timestamp=timestamp,
                    call_order=call_order,
                    parse_status=ParseStatus.MODEL_FORMATTING_FAILURE,
                )
            )
            return CallLoopResult(
                tuple(results),
                Stage0Decision.STOP,
                "model formatting failure; no restart authorized",
            )

        meta = dict(response.provider_metadata) if response.provider_metadata else {}
        results.append(
            RawResult(
                run_id=manifest.run_id,
                case_id=case.case_id,
                truth_label=case.truth_label,
                returned_score=score,
                raw_model_response=response.raw_response,
                model_provider=model.provider,
                model_id=model.model_id,
                model_configuration_sha256=model.sha256,
                provider_metadata=meta,
                timestamp=timestamp,
                call_order=call_order,
                parse_status=ParseStatus.VALID_SCORE,
                provider_response_sha256=meta.get("provider_response_sha256"),
                provider_raw_b64=meta.get("raw_provider_b64"),
            )
        )
    return CallLoopResult(tuple(results), None, None)
