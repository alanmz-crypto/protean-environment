"""Stage-1A live-origin five-request driver (authoritative, sealed, hermetic).

Implements the ratified five-request origin semantics without any provider call in
this task. Authority is never a placeholder: an authoritative manifest is built
ONLY from LoadedStage1AAuthority (actual committed bytes hashed at runtime). The
seal re-hashes the actual authority files and compares every binding. Execution
consumes an existing sealed manifest (bytes + expected SHA), the actual current
harness revision, and freshly loaded authorities; it rederives all five exact
request bytes and compares every SHA before constructing any provider transport.

The live loop issues exactly five independent GPT-5.6 Luna xHigh Responses
requests (one per structure), parse strictly, enforce the exact origin-adoption-v1
contract, preserve durable lossless evidence per attempt (written atomically
before the next request), with zero retry / zero resume / zero partial salvage.
Each success yields a verifiable OriginSessionArtifact (bound to manifest SHA,
batch, request index, structure); a 5/5 run produces a single CompletedOriginRun
binding the five artifact SHAs (not merely request SHAs).
"""

from __future__ import annotations

import base64
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any, Protocol

from .artifacts import canonical_json_bytes, sha256_bytes
from .direct_config import DIRECT_CONFIG_HASH
from .grammar import FROZEN_STRUCTURES, StructureId
from .stage1a_authority import LoadedStage1AAuthority
from .stage1a_origin import (
    ORIGIN_PROMPT,
    ORIGIN_PROMPT_SHA256,
    ORIGIN_RESPONSE_CONTRACT_SHA256,
    OriginSessionArtifact,
    _parse_origin_adoptions_exact,
    build_origin_request_bytes,
    canonical_commitment_records,
    commitments_hash,
    parse_raw_provider_response,
    verify_origin_artifact,
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


class OriginRunUnresolved(Exception):
    """Unexpected programming/internal exception (mechanical error, never collated)."""


def _b64(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


@dataclass(frozen=True, slots=True)
class OriginRequestEvidence:
    """Durable, lossless per-attempt evidence, written atomically after each."""

    batch_run_id: str
    manifest_sha256: str
    request_index: int
    structure: str
    case_ids: tuple[str, ...]
    request_sha256: str
    request_bytes: bytes
    http_status: int | None
    raw_error_body: bytes | None
    raw_provider_response: bytes | None
    final_output_bytes: bytes | None
    final_output_sha256: str | None
    timestamp: str
    provider_metadata: Mapping[str, Any]
    failure_category: OriginFailureCategory | None
    success: bool
    mechanical_error: str | None = None

    def canonical_record(self) -> dict[str, Any]:
        return {
            "batch_run_id": self.batch_run_id,
            "case_ids": list(self.case_ids),
            "failure_category": self.failure_category,
            "final_output_bytes": (
                self.final_output_bytes.decode("utf-8", "replace")
                if self.final_output_bytes is not None
                else None
            ),
            "final_output_sha256": self.final_output_sha256,
            "http_status": self.http_status,
            "manifest_sha256": self.manifest_sha256,
            "mechanical_error": self.mechanical_error,
            "provider_metadata": dict(self.provider_metadata),
            "raw_error_body_base64": (
                _b64(self.raw_error_body) if self.raw_error_body is not None else None
            ),
            "raw_error_body_sha256": (
                sha256_bytes(self.raw_error_body) if self.raw_error_body is not None else None
            ),
            "raw_provider_response_base64": (
                _b64(self.raw_provider_response) if self.raw_provider_response is not None else None
            ),
            "raw_provider_response_sha256": (
                sha256_bytes(self.raw_provider_response)
                if self.raw_provider_response is not None
                else None
            ),
            "request_bytes_base64": _b64(self.request_bytes),
            "request_index": self.request_index,
            "request_sha256": self.request_sha256,
            "structure": self.structure,
            "success": self.success,
            "timestamp": self.timestamp,
        }

    def to_exact_bytes(self) -> bytes:
        return canonical_json_bytes(self.canonical_record())

    @property
    def sha256(self) -> str:
        return sha256_bytes(self.to_exact_bytes())


@dataclass(frozen=True, slots=True)
class CompletedOriginRun:
    """The ONLY authority that unlocks calibration: a sealed 5/5 successful batch.

    Binds the five individual OriginSessionArtifact SHAs, not merely request SHAs.
    """

    manifest_sha256: str
    batch_run_id: str
    artifact_shas: tuple[str, ...]
    attempts: int
    successes: int
    failures: int

    @property
    def completed_run_sha256(self) -> str:
        return sha256_bytes(self.to_exact_bytes())

    def to_exact_bytes(self) -> bytes:
        return canonical_json_bytes(
            {
                "artifact_shas": list(self.artifact_shas),
                "attempts": self.attempts,
                "batch_run_id": self.batch_run_id,
                "failures": self.failures,
                "manifest_sha256": self.manifest_sha256,
                "successes": self.successes,
            }
        )


@dataclass(frozen=True, slots=True)
class OriginRequestSpec:
    request_index: int
    structure: str
    case_ids: tuple[str, ...]
    request_bytes: bytes
    request_sha256: str
    commitment_records: tuple[tuple[str, bytes], ...]
    commitment_hash: str


def build_origin_run_manifest(
    *,
    auth: LoadedStage1AAuthority,
    harness_revision: str,
    batch_run_id: str,
) -> tuple[Stage1AOriginRunManifest, tuple[OriginRequestSpec, ...]]:
    """Build an AUTHORITATIVE origin manifest (never empty-authority)."""
    by_structure: dict[StructureId, list[str]] = {s: [] for s in FROZEN_STRUCTURES}
    by_case_commitment: dict[str, bytes] = {}
    for case in auth.case_set.cases:
        by_structure[case.structured_spec.structure_id].append(case.case_id)
        by_case_commitment[case.case_id] = case.commitment.encode()

    request_shas: dict[str, str] = {}
    case_ids_per: dict[str, tuple[str, ...]] = {}
    commitment_hash_per: dict[str, str] = {}
    specs: list[OriginRequestSpec] = []
    for idx, structure in enumerate(FROZEN_STRUCTURES, start=1):
        cids = tuple(by_structure[structure])
        records = canonical_commitment_records([(cid, by_case_commitment[cid]) for cid in cids])
        req_bytes = build_origin_request_bytes(ORIGIN_PROMPT, list(records))
        req_sha = sha256_bytes(req_bytes)
        request_shas[structure.value] = req_sha
        case_ids_per[structure.value] = cids
        commitment_hash_per[structure.value] = commitments_hash(records)
        specs.append(
            OriginRequestSpec(
                request_index=idx,
                structure=structure.value,
                case_ids=cids,
                request_bytes=req_bytes,
                request_sha256=req_sha,
                commitment_records=records,
                commitment_hash=commitments_hash(records),
            )
        )

    manifest = Stage1AOriginRunManifest(
        protocol_sha256=auth.protocol.sha256,
        real_origin_amendment_sha256=auth.real_origin_amendment.sha256,
        case_set_sha256=auth.case_set.sha256,
        origin_prompt_sha256=ORIGIN_PROMPT_SHA256,
        origin_response_contract_sha256=ORIGIN_RESPONSE_CONTRACT_SHA256,
        direct_luna_config_sha256=DIRECT_CONFIG_HASH,
        harness_revision=harness_revision,
        expected_requests=5,
        ordered_structures=tuple(s.value for s in FROZEN_STRUCTURES),
        per_structure_case_ids=case_ids_per,
        per_structure_commitment_hash=commitment_hash_per,
        per_request_request_sha=request_shas,
        zero_retries=True,
        batch_run_id=batch_run_id,
        manifest_version="stage1a-origin-run-v1",
        artifact_schema_version="stage1a-origin-artifact-v1",
    )
    return manifest, tuple(specs)


def validate_origin_run_manifest_seal(
    *,
    manifest: Stage1AOriginRunManifest,
    manifest_sha256: str,
    actual_harness_revision: str,
    auth: LoadedStage1AAuthority,
) -> None:
    """Re-hash the ACTUAL authority files and compare EVERY binding. Raises on any."""
    if manifest.sha256 != manifest_sha256:
        raise ValueError("origin manifest SHA does not match expected value")
    if manifest.harness_revision != actual_harness_revision:
        raise ValueError("origin manifest harness revision does not match current HEAD")
    bindings = {
        "protocol": (manifest.protocol_sha256, auth.protocol.sha256),
        "real-origin amendment": (
            manifest.real_origin_amendment_sha256,
            auth.real_origin_amendment.sha256,
        ),
        "case set": (manifest.case_set_sha256, auth.case_set.sha256),
        "origin prompt": (manifest.origin_prompt_sha256, ORIGIN_PROMPT_SHA256),
        "response contract": (
            manifest.origin_response_contract_sha256,
            ORIGIN_RESPONSE_CONTRACT_SHA256,
        ),
        "direct Luna config": (manifest.direct_luna_config_sha256, DIRECT_CONFIG_HASH),
    }
    for name, (recorded, actual) in bindings.items():
        if recorded != actual:
            raise ValueError(f"origin seal binding mismatch: {name}")
    if not manifest.zero_retries:
        raise ValueError("origin manifest must require zero retries")
    if manifest.expected_requests != 5:
        raise ValueError("origin manifest must require exactly 5 requests")
    if manifest.ordered_structures != tuple(s.value for s in FROZEN_STRUCTURES):
        raise ValueError("origin manifest ordered structures mismatch")

    # Recompute per-structure case IDs + commitment hashes + request SHAs from the
    # freshly loaded authorities and compare exactly.
    by_structure: dict[StructureId, list[str]] = {s: [] for s in FROZEN_STRUCTURES}
    by_commit: dict[str, bytes] = {}
    for case in auth.case_set.cases:
        by_structure[case.structured_spec.structure_id].append(case.case_id)
        by_commit[case.case_id] = case.commitment.encode()
    for structure in FROZEN_STRUCTURES:
        cids = tuple(by_structure[structure])
        if manifest.per_structure_case_ids.get(structure.value) != cids:
            raise ValueError(f"origin seal case IDs mismatch: {structure.value}")
        records = canonical_commitment_records([(cid, by_commit[cid]) for cid in cids])
        if manifest.per_structure_commitment_hash.get(structure.value) != commitments_hash(records):
            raise ValueError(f"origin seal commitment hash mismatch: {structure.value}")
        req_sha = sha256_bytes(build_origin_request_bytes(ORIGIN_PROMPT, list(records)))
        if manifest.per_request_request_sha.get(structure.value) != req_sha:
            raise ValueError(f"origin seal request SHA mismatch: {structure.value}")


class OriginTransport(Protocol):
    def __call__(
        self, *, payload: bytes
    ) -> tuple[int | None, bytes | None, bytes | None, Mapping[str, Any]]:
        """Return (http_status_or_None, raw_error_body_or_None,
        raw_provider_response_or_None, provider_metadata)."""
        ...


def _evidence_for(
    *,
    batch: str,
    manifest_sha: str,
    spec: OriginRequestSpec,
    status: int | None,
    err_body: bytes | None,
    raw_response: bytes | None,
    md: Mapping[str, Any],
    category: OriginFailureCategory | None,
    success: bool,
    mechanical: str | None = None,
) -> OriginRequestEvidence:
    ts = datetime.now(UTC).isoformat()
    final_bytes = None
    final_sha = None
    if success and raw_response is not None:
        final_text = parse_raw_provider_response(raw_response)
        final_bytes = final_text.encode()
        final_sha = sha256_bytes(final_bytes)
    return OriginRequestEvidence(
        batch_run_id=batch,
        manifest_sha256=manifest_sha,
        request_index=spec.request_index,
        structure=spec.structure,
        case_ids=spec.case_ids,
        request_sha256=spec.request_sha256,
        request_bytes=spec.request_bytes,
        http_status=status,
        raw_error_body=err_body,
        raw_provider_response=raw_response,
        final_output_bytes=final_bytes,
        final_output_sha256=final_sha,
        timestamp=ts,
        provider_metadata=md,
        failure_category=category,
        success=success,
        mechanical_error=mechanical,
    )


@dataclass
class AtomicEvidenceSink:
    """Writes one evidence file per attempt atomically, BEFORE the next request."""

    out_dir: Path

    def write(self, evidence: OriginRequestEvidence) -> Path:
        self.out_dir.mkdir(parents=True, exist_ok=True)
        path = (
            self.out_dir
            / f"origin-evidence-{evidence.batch_run_id}-r{evidence.request_index:02d}.json"
        )
        tmp = path.with_suffix(".json.tmp")
        tmp.write_bytes(evidence.to_exact_bytes())
        tmp.replace(path)  # atomic rename
        return path


@dataclass(frozen=True, slots=True)
class OriginRunResult:
    status: OriginRunStatus
    evidence: tuple[OriginRequestEvidence, ...]
    artifacts: tuple[OriginSessionArtifact, ...]
    completed: CompletedOriginRun | None


def execute_origin_run(
    *,
    manifest_bytes: bytes,
    expected_manifest_sha256: str,
    actual_harness_revision: str,
    auth: LoadedStage1AAuthority,
    batch_run_id: str,
    transport: OriginTransport,
    evidence_sink: AtomicEvidenceSink | None = None,
) -> OriginRunResult:
    """Execute the sealed five-request run from an EXISTING sealed manifest.

    Loads the manifest -> verifies expected SHA -> full seal against freshly loaded
    authorities -> rederives request bytes -> compares every SHA -> ONLY THEN
    constructs the provider transport. Any mismatch => 0 provider calls.
    """
    manifest = Stage1AOriginRunManifest._reconstruct(manifest_bytes)
    validate_origin_run_manifest_seal(
        manifest=manifest,
        manifest_sha256=expected_manifest_sha256,
        actual_harness_revision=actual_harness_revision,
        auth=auth,
    )
    if manifest.batch_run_id != batch_run_id:
        raise ValueError("provided batch/run ID does not match sealed manifest batch")

    # Rederive the five request specs from the freshly loaded authorities.
    _, specs = build_origin_run_manifest(
        auth=auth, harness_revision=actual_harness_revision, batch_run_id=batch_run_id
    )
    evidence: list[OriginRequestEvidence] = []
    artifacts: list[OriginSessionArtifact] = []

    for spec in specs:
        try:
            status, err_body, raw_response, md = transport(payload=spec.request_bytes)
        except Exception as exc:  # unexpected transport/internal failure -> mechanical
            ev = _evidence_for(
                batch=batch_run_id,
                manifest_sha=manifest.sha256,
                spec=spec,
                status=None,
                err_body=None,
                raw_response=None,
                md={},
                category=None,
                success=False,
                mechanical=f"{type(exc).__name__}: {exc}",
            )
            if evidence_sink:
                evidence_sink.write(ev)
            # Unexpected/internal exception: mechanical. Propagate; do NOT return a
            # FAILED provider result. Prior durable evidence is already written.
            raise OriginRunUnresolved(
                f"mechanical error at request {spec.request_index}: {exc!r}"
            ) from exc
        if status is not None and status != 200:
            ev = _evidence_for(
                batch=batch_run_id,
                manifest_sha=manifest.sha256,
                spec=spec,
                status=status,
                err_body=err_body,
                raw_response=None,
                md=md,
                category=OriginFailureCategory.HTTP,
                success=False,
            )
            if evidence_sink:
                evidence_sink.write(ev)
            return OriginRunResult(
                status=OriginRunStatus.FAILED,
                evidence=tuple(evidence) + (ev,),
                artifacts=tuple(artifacts),
                completed=None,
            )
        if raw_response is None:
            ev = _evidence_for(
                batch=batch_run_id,
                manifest_sha=manifest.sha256,
                spec=spec,
                status=status,
                err_body=err_body,
                raw_response=None,
                md=md,
                category=OriginFailureCategory.TRANSPORT,
                success=False,
            )
            if evidence_sink:
                evidence_sink.write(ev)
            return OriginRunResult(
                status=OriginRunStatus.FAILED,
                evidence=tuple(evidence) + (ev,),
                artifacts=tuple(artifacts),
                completed=None,
            )
        # Strict Responses parsing; any violation -> RESPONSES_CONTRACT.
        try:
            parse_raw_provider_response(raw_response)
        except Exception:
            ev = _evidence_for(
                batch=batch_run_id,
                manifest_sha=manifest.sha256,
                spec=spec,
                status=status,
                err_body=None,
                raw_response=raw_response,
                md=md,
                category=OriginFailureCategory.RESPONSES_CONTRACT,
                success=False,
            )
            if evidence_sink:
                evidence_sink.write(ev)
            return OriginRunResult(
                status=OriginRunStatus.FAILED,
                evidence=tuple(evidence) + (ev,),
                artifacts=tuple(artifacts),
                completed=None,
            )
        # Extraction of final output + exact origin-adoption-v1 acceptance.
        try:
            final_text = parse_raw_provider_response(raw_response)
            final_bytes = final_text.encode()
            _parse_origin_adoptions_exact(final_bytes, spec.case_ids)
        except Exception:
            ev = _evidence_for(
                batch=batch_run_id,
                manifest_sha=manifest.sha256,
                spec=spec,
                status=status,
                err_body=None,
                raw_response=raw_response,
                md=md,
                category=OriginFailureCategory.ADOPTION_CONTRACT,
                success=False,
            )
            if evidence_sink:
                evidence_sink.write(ev)
            return OriginRunResult(
                status=OriginRunStatus.FAILED,
                evidence=tuple(evidence) + (ev,),
                artifacts=tuple(artifacts),
                completed=None,
            )
        ev = _evidence_for(
            batch=batch_run_id,
            manifest_sha=manifest.sha256,
            spec=spec,
            status=status,
            err_body=None,
            raw_response=raw_response,
            md=md,
            category=None,
            success=True,
        )
        if evidence_sink:
            evidence_sink.write(ev)
        evidence.append(ev)
        # Build a real OriginSessionArtifact bound to manifest/batch/index/structure.
        artifact = OriginSessionArtifact(
            origin_run_id=f"{batch_run_id}-{spec.request_index:02d}",
            structure=StructureId(spec.structure),
            commitment_records=spec.commitment_records,
            commitment_sha256=spec.commitment_hash,
            model_configuration_sha256=DIRECT_CONFIG_HASH,
            request_sha256=spec.request_sha256,
            raw_provider_response_sha256=sha256_bytes(raw_response),
            raw_provider_response_bytes=raw_response,
            final_output_sha256=sha256_bytes(final_bytes),
            final_output_bytes=final_bytes,
            timestamp=ev.timestamp,
            provider_metadata=dict(md),
        )
        verify_origin_artifact(
            artifact,
            origin_prompt=ORIGIN_PROMPT,
            expected_structure=StructureId(spec.structure),
            expected_case_ids=spec.case_ids,
            expected_commitment_records=spec.commitment_records,
        )
        artifacts.append(artifact)

    # 5/5 success -> CompletedOriginRun binding the five artifact SHAs.
    completed = CompletedOriginRun(
        manifest_sha256=manifest.sha256,
        batch_run_id=batch_run_id,
        artifact_shas=tuple(a.sha256 for a in artifacts),
        attempts=5,
        successes=5,
        failures=0,
    )
    return OriginRunResult(
        status=OriginRunStatus.COMPLETED,
        evidence=tuple(evidence),
        artifacts=tuple(artifacts),
        completed=completed,
    )
