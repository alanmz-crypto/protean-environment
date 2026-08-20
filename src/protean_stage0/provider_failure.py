"""Typed provider-failure classification and safe evidence for Stage 0.

Provider adapters raise one of these typed exceptions so the harness can
distinguish, per decision call:

* ``TransportFailure`` — no usable HTTP response (connect/DNS/timeout/abort).
* ``HttpFailure`` — a non-2xx HTTP response, with the status code and a safe
  copy of the raw error body bytes/hash when they actually exist.
* ``ResponseContractFailure`` — a response was received but violated the frozen
  provider response contract (malformed JSON, wrong object shape, missing field).
* ``ModelFormattingFailure`` — the model produced a structurally valid response
  whose final output is not a value satisfying the frozen parse contract.

The last category is deliberately distinct: a model that returned malformed
output must never become indistinguishable from an HTTP/provider failure.
A bare base ``ProviderFailure`` is a safe default and maps to a generic provider
failure, never to model formatting.

Credential material (API keys, authorization headers) is never part of this
evidence. Raw response bytes are preserved only when the adapter actually
received them, and only their SHA-256 plus a base64 copy are recorded by the
harness (the live caller carries the bytes for durable retention, not here).
"""

from __future__ import annotations

import base64
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from .artifacts import sha256_bytes


class ProviderFailureCategory(StrEnum):
    TRANSPORT = "transport"
    HTTP = "http"
    RESPONSE_CONTRACT = "response_contract"
    MODEL_FORMATTING = "model_formatting"


class ProviderFailure(RuntimeError):
    """Base provider failure. Safe default maps to generic provider failure.

    ``raw_response`` carries the exact raw provider response bytes when the
    adapter actually received them (never credentials); it is None otherwise.
    """

    category = ProviderFailureCategory.RESPONSE_CONTRACT

    def __init__(self, *args: object, raw_response: bytes | None = None) -> None:
        super().__init__(*args)
        self.raw_response = raw_response


class TransportFailure(ProviderFailure):
    category = ProviderFailureCategory.TRANSPORT


class ResponseContractFailure(ProviderFailure):
    category = ProviderFailureCategory.RESPONSE_CONTRACT


class ModelFormattingFailure(ProviderFailure):
    category = ProviderFailureCategory.MODEL_FORMATTING


@dataclass(frozen=True, slots=True)
class HttpFailureEvidence:
    status_code: int
    raw_error_body: bytes | None = None
    raw_error_sha256: str | None = None

    def safe_record(self) -> dict[str, Any]:
        encoded = (
            base64.b64encode(self.raw_error_body).decode("ascii")
            if self.raw_error_body is not None
            else None
        )
        return {
            "status_code": self.status_code,
            "raw_error_body_base64": encoded,
            "raw_error_sha256": self.raw_error_sha256,
        }


class HttpFailure(ProviderFailure):
    """A non-2xx HTTP response was received. Carries status + safe body."""

    category = ProviderFailureCategory.HTTP

    def __init__(
        self,
        message: str,
        evidence: HttpFailureEvidence,
        *,
        raw_response: bytes | None = None,
    ) -> None:
        super().__init__(message, raw_response=raw_response)
        self.evidence = evidence


def classify_provider_failure(exc: BaseException) -> tuple[str, dict[str, Any] | None]:
    """Return (category_value, provider_metadata) for a caught failure.

    ``provider_metadata`` carries only the safe evidence and never credentials
    or request/authorization headers.
    """
    if isinstance(exc, HttpFailure):
        return (exc.category.value, exc.evidence.safe_record())
    if isinstance(exc, ProviderFailure):
        # A bare base ProviderFailure has no finer contract intent; record it as
        # a generic provider failure rather than mislabeling it as one of the
        # four explicit categories.
        if type(exc) is ProviderFailure:
            return ("provider", None)
        return (exc.category.value, None)
    # A non-ProviderFailure exception from the client is a transport-level
    # surprise; classify as transport without asserting on its internals.
    return (ProviderFailureCategory.TRANSPORT.value, None)


def response_digest(raw_response: bytes) -> str:
    """SHA-256 of exact raw provider response bytes, when real bytes exist."""
    return sha256_bytes(raw_response)
