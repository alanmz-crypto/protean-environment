"""Stage-1A live-origin five-request driver (prepared vs execute; hermetic).

Implements the ratified five-request origin semantics without making any provider
call in this task: a zero-call PREPARE/plan mode builds a sealed origin run
manifest and recomputes each request SHA from loaded authorities; EXECUTE consumes
an existing manifest + expected SHA, never generates or modifies it, and runs
exactly five independent GPT-5.6 Luna xHigh Responses requests (one per structure)
through an injected transport (fake in tests), preserving per-request failure
evidence, with zero retry / zero resume / zero partial salvage. A sealed 5/5
success produces a single CompletedOriginRun authority that later calibration must
consume; five individually valid artifacts from different batches/manifests never
satisfy it.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Protocol

from .artifacts import FrozenCaseSet, canonical_json_bytes, sha256_bytes
from .grammar import FROZEN_STRUCTURES, StructureId
from .stage1a_origin import (
    ORIGIN_PROMPT,
    build_origin_request_bytes,
    parse_raw_provider_response,
)
from .stage1a_origin_run_manifest import Stage1AOriginRunManifest


class OriginFailureCategory(StrEnum):
    TRANSPORT = "transport"
    HTTP = "http"
    RESPONSES_CONTRACT = "responses_contract"
    ADOPTION_CONTRACT = "adoption_contract"


class OriginRunStatus(StrEnum):
    PLANNED = "PLANNED"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    INCOMPLETE = "INCOMPLETE"


@dataclass(frozen=True, slots=True)
class OriginRequestEvidence:
    """Durable per-request evidence; preserved even on failure."""

    batch_run_id: str
    request_index: int
    structure: str
    request_sha256: str
    request_bytes: bytes
    http_status: int | None
    raw_error_body: bytes | None
    raw_provider_response: bytes | None
    raw_provider_response_sha256: str | None
    timestamp: str
    provider_metadata: Mapping[str, Any]
    failure_category: OriginFailureCategory | None
    success: bool
    mechanical_error: str | None = None

    def canonical_record(self) -> dict[str, Any]:
        return {
            "batch_run_id": self.batch_run_id,
            "failure_category": self.failure_category.value if self.failure_category else None,
            "http_status": self.http_status,
            "mechanical_error": self.mechanical_error,
            "provider_metadata": dict(self.provider_metadata),
            "raw_error_body_sha256": (
                sha256_bytes(self.raw_error_body) if self.raw_error_body is not None else None
            ),
            "raw_provider_response_sha256": self.raw_provider_response_sha256,
            "raw_provider_response_base64": (
                _b64(self.raw_provider_response) if self.raw_provider_response is not None else None
            ),
            "request_index": self.request_index,
            "request_sha256": self.request_sha256,
            "structure": self.structure,
            "success": self.success,
            "timestamp": self.timestamp,
        }


def _b64(data: bytes) -> str:
    import base64

    return base64.b64encode(data).decode("ascii")


@dataclass(frozen=True, slots=True)
class CompletedOriginRun:
    """The ONLY authority that unlocks calibration: a sealed 5/5 successful batch."""

    manifest_sha256: str
    batch_run_id: str
    attempts: int
    successes: int
    failures: int
    request_shas: tuple[str, ...]
    completed_run_sha256: str

    def to_exact_bytes(self) -> bytes:
        return canonical_json_bytes(
            {
                "attempts": self.attempts,
                "batch_run_id": self.batch_run_id,
                "completed_run_sha256": self.completed_run_sha256,
                "failures": self.failures,
                "manifest_sha256": self.manifest_sha256,
                "request_shas": list(self.request_shas),
                "successes": self.successes,
            }
        )


class OriginTransport(Protocol):
    def __call__(
        self, *, payload: bytes
    ) -> tuple[int | None, bytes | None, bytes | None, Mapping[str, Any]]:
        """Return (http_status_or_None, raw_error_body_or_None,
        raw_provider_response_or_None, provider_metadata)."""
        ...


@dataclass(frozen=True, slots=True)
class OriginRunPlan:
    """Zero-call prepared plan: recomputed 5 request SHAs bound by the manifest."""

    manifest: Stage1AOriginRunManifest
    manifest_sha256: str
    request_specs: tuple[
        tuple[str, tuple[str, ...], bytes, str], ...
    ]  # (structure, ids, bytes, sha)


def _recompute_request(
    structure: StructureId,
    case_ids: tuple[str, ...],
    commitment_bytes_by_case: Mapping[str, bytes],
) -> tuple[bytes, str]:
    records = [(cid, commitment_bytes_by_case[cid]) for cid in case_ids]
    req_bytes = build_origin_request_bytes(ORIGIN_PROMPT, records)
    return req_bytes, sha256_bytes(req_bytes)


def plan_origin_run(
    *,
    loaded_case_set: FrozenCaseSet,
    harness_revision: str,
    batch_run_id: str,
    verify_manifest: Stage1AOriginRunManifest | None = None,
) -> OriginRunPlan:
    """Zero-call plan: recompute the five request SHAs from loaded authorities.

    Mirrors prepared-manifest flow; does nothing with a provider. If
    ``verify_manifest`` is given, every stored per-request SHA must equal the
    recomputed value (any mismatch => ValueError => zero provider).
    """
    # Build per-structure case-id -> commitment bytes from the loaded case set.
    by_structure: dict[StructureId, list[str]] = {s: [] for s in FROZEN_STRUCTURES}
    by_case_commitment: dict[str, bytes] = {}
    for case in loaded_case_set.cases:
        by_structure[case.structured_spec.structure_id].append(case.case_id)
        by_case_commitment[case.case_id] = case.commitment.encode()

    specs: list[tuple[str, tuple[str, ...], bytes, str]] = []
    request_shas: dict[str, str] = {}
    for _idx, structure in enumerate(FROZEN_STRUCTURES, start=1):
        ids = tuple(by_structure[structure])
        req_bytes, req_sha = _recompute_request(structure, ids, by_case_commitment)
        request_shas[structure.value] = req_sha
        specs.append((structure.value, ids, req_bytes, req_sha))

    manifest = verify_manifest
    if manifest is not None:
        for structure in FROZEN_STRUCTURES:
            if (
                manifest.per_request_request_sha.get(structure.value)
                != request_shas[structure.value]
            ):
                raise ValueError(f"origin run manifest request SHA mismatch for {structure.value}")
        if manifest.expected_requests != 5:
            raise ValueError("origin run manifest must require exactly 5 requests")
    else:
        manifest = Stage1AOriginRunManifest(
            protocol_sha256="",  # caller binds loaded artifacts at seal time
            real_origin_amendment_sha256="",
            case_set_sha256="",
            origin_prompt_sha256="",
            origin_response_contract_sha256="",
            direct_luna_config_sha256="",
            harness_revision=harness_revision,
            expected_requests=5,
            ordered_structures=tuple(s.value for s in FROZEN_STRUCTURES),
            per_structure_case_ids={s.value: tuple(by_structure[s]) for s in FROZEN_STRUCTURES},
            per_structure_commitment_hash={},
            per_request_request_sha=request_shas,
            zero_retries=True,
            batch_run_id=batch_run_id,
            manifest_version="stage1a-origin-run-v1",
            artifact_schema_version="stage1a-origin-artifact-v1",
        )
    return OriginRunPlan(
        manifest=manifest,
        manifest_sha256=manifest.sha256,
        request_specs=tuple(specs),
    )


@dataclass
class OriginRunResult:
    status: OriginRunStatus
    evidence: tuple[OriginRequestEvidence, ...]
    completed: CompletedOriginRun | None


class OriginRunUnresolved(Exception):
    """Unexpected implementation exception during origin run (mechanical error)."""


def execute_origin_run(
    *,
    plan: OriginRunPlan,
    transport: OriginTransport,
    verify_manifest_sha256: str,
) -> OriginRunResult:
    """Execute the sealed 5-request origin run with zero retry/resume/salvage.

    Consumes the existing plan/manifest; never generates or modifies it. Each
    request is transmitted exactly once (zero retries). If request N fails, evidence
    through N is preserved, request N+1 is never issued, and the batch is
    FAILED/INCOMPLETE. Unexpected (non-ProviderFailure) exceptions propagate as
    mechanical errors. Only a 5/5 success produces a CompletedOriginRun.
    """
    # 1) The consumed manifest SHA must equal the expected value.
    if plan.manifest_sha256 != verify_manifest_sha256:
        raise ValueError("origin run manifest SHA does not match expected SHA")
    if plan.manifest.zero_retries is not True:
        raise ValueError("origin run must be zero-retry")
    if plan.manifest.expected_requests != 5:
        raise ValueError("origin run must require exactly 5 requests")

    evidence: list[OriginRequestEvidence] = []
    batch = plan.manifest.batch_run_id
    ts = datetime.now(UTC).isoformat()
    try:
        for idx, (structure, _ids, req_bytes, req_sha) in enumerate(plan.request_specs, start=1):
            try:
                status, err_body, raw_response, md = transport(payload=req_bytes)
            except Exception as exc:  # unexpected: mechanical error, propagates
                raise OriginRunUnresolved(
                    f"mechanical error during origin request {idx}: {exc!r}"
                ) from exc
            if status is not None and status != 200:
                evidence.append(
                    OriginRequestEvidence(
                        batch_run_id=batch,
                        request_index=idx,
                        structure=structure,
                        request_sha256=req_sha,
                        request_bytes=req_bytes,
                        http_status=status,
                        raw_error_body=err_body,
                        raw_provider_response=None,
                        raw_provider_response_sha256=None,
                        timestamp=ts,
                        provider_metadata=md,
                        failure_category=OriginFailureCategory.HTTP,
                        success=False,
                    )
                )
                return OriginRunResult(
                    status=OriginRunStatus.FAILED, evidence=tuple(evidence), completed=None
                )
            if raw_response is None:
                evidence.append(
                    OriginRequestEvidence(
                        batch_run_id=batch,
                        request_index=idx,
                        structure=structure,
                        request_sha256=req_sha,
                        request_bytes=req_bytes,
                        http_status=status,
                        raw_error_body=err_body,
                        raw_provider_response=None,
                        raw_provider_response_sha256=None,
                        timestamp=ts,
                        provider_metadata=md,
                        failure_category=OriginFailureCategory.TRANSPORT,
                        success=False,
                    )
                )
                return OriginRunResult(
                    status=OriginRunStatus.FAILED, evidence=tuple(evidence), completed=None
                )
            raw_sha = sha256_bytes(raw_response)
            # Re-parse through the strict direct-Luna Responses contract and the
            # exact origin-adoption contract; any violation => adoption failure.
            try:
                parse_raw_provider_response(raw_response)
            except Exception:
                evidence.append(
                    OriginRequestEvidence(
                        batch_run_id=batch,
                        request_index=idx,
                        structure=structure,
                        request_sha256=req_sha,
                        request_bytes=req_bytes,
                        http_status=status,
                        raw_error_body=None,
                        raw_provider_response=raw_response,
                        raw_provider_response_sha256=raw_sha,
                        timestamp=ts,
                        provider_metadata=md,
                        failure_category=OriginFailureCategory.RESPONSES_CONTRACT,
                        success=False,
                    )
                )
                return OriginRunResult(
                    status=OriginRunStatus.FAILED, evidence=tuple(evidence), completed=None
                )
            evidence.append(
                OriginRequestEvidence(
                    batch_run_id=batch,
                    request_index=idx,
                    structure=structure,
                    request_sha256=req_sha,
                    request_bytes=req_bytes,
                    http_status=status,
                    raw_error_body=None,
                    raw_provider_response=raw_response,
                    raw_provider_response_sha256=raw_sha,
                    timestamp=ts,
                    provider_metadata=md,
                    failure_category=None,
                    success=True,
                )
            )
    finally:
        pass
    # 5/5 succeeded.
    request_shas = tuple(e.request_sha256 for e in evidence)
    completed_run = canonical_json_bytes(
        {
            "attempts": 5,
            "batch_run_id": batch,
            "failures": 0,
            "manifest_sha256": plan.manifest_sha256,
            "request_shas": list(request_shas),
            "successes": 5,
        }
    )
    completed = CompletedOriginRun(
        manifest_sha256=plan.manifest_sha256,
        batch_run_id=batch,
        attempts=5,
        successes=5,
        failures=0,
        request_shas=request_shas,
        completed_run_sha256=sha256_bytes(completed_run),
    )
    return OriginRunResult(
        status=OriginRunStatus.COMPLETED, evidence=tuple(evidence), completed=completed
    )
