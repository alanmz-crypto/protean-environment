"""Durable Stage-1A calibration live-execution substrate (60 single-score calls).

This is the production fail-closed surface for the later 60 real scoring calls. It
mirrors the proven origin driver: a sealed calibration manifest binds the exact 60
case IDs in deterministic order together with a precomputed exact request SHA per
case; ```execute_calibration_run`` first re-verifies the ENTIRE origin chain
(authorities, origin manifest, CompletedOriginRun, all five origin artifacts),
rederives all 60 request bytes, verifies every SHA, claims an exclusive batch-start
marker, and ONLY THEN issues one independent Responses request per case. Each
request is durably persisted before the next proceeds; a failure at request N
preserves N's evidence and stops before N+1. A completed-run authority is produced
only for a genuine 60/60/0.

No live scoring call is authorized by importing this module; execution requires an
explicit ```execute_calibration_run`` invocation with a sealed manifest and a real
transport, and the live CLI gates it behind an explicit flag + API-key preflight.
"""

from __future__ import annotations

import base64
import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from types import MappingProxyType
from typing import Any, Protocol

from .artifacts import canonical_json_bytes, sha256_bytes
from .direct_config import DIRECT_CONFIG_HASH
from .direct_responses import (
    parse_scoring_response,
)
from .parse_contract import PLAIN_DECIMAL_V1_SHA256, parse_plain_decimal_v1
from .stage1a_authority import (
    EXPECTED_SCORING_PROMPT_SHA,
    LoadedStage1AAuthority,
    load_authority_artifacts,
)
from .stage1a_cases import build_stage1a_cases, freeze_stage1a_case_set
from .stage1a_config import (
    CROSS_SESSION_REP_VERSION,
    STAGE1A_SEED,
    STAGE1A_TOTAL,
)
from .stage1a_origin import OriginSessionArtifact
from .stage1a_origin_driver import CompletedOriginRun, validate_origin_run_manifest_seal
from .stage1a_origin_run_manifest import Stage1AOriginRunManifest
from .stage1a_threshold import ScoredCase, compute_stage1a_report
from .textualize import TemplateBank


def load_origin_run_artifacts(*, artifacts_dir: Path, batch_run_id: str) -> tuple[Any, ...]:
    """Reconstruct the five durable origin artifacts for the batch, in index order."""
    artifacts: list[Any] = []
    for index in range(1, 6):
        path = artifacts_dir / f"origin-artifact-{batch_run_id}-{index:02d}.json"
        if not path.exists():
            raise ValueError(f"missing origin artifact file: {path}")
        raw = path.read_bytes()
        artifacts.append(OriginSessionArtifact._reconstruct(raw))
    return tuple(artifacts)


CALIBRATION_MANIFEST_VERSION = "stage1a-calibration-run-v1"
CALIBRATION_EVIDENCE_SCHEMA_VERSION = "stage1a-calibration-evidence-v1"
CALIBRATION_COMPLETED_SCHEMA_VERSION = "stage1a-calibration-completed-v1"
REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CALIBRATION_MANIFEST_DIR = REPO_ROOT / "stage0/runs"


class CalibrationFailureCategory(StrEnum):
    TRANSPORT = "transport"
    HTTP = "http"
    RESPONSES_CONTRACT = "responses_contract"
    SCORE_PARSE = "score_parse"


class CalibrationRunStatus(StrEnum):
    PLANNED = "PLANNED"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    INCOMPLETE = "INCOMPLETE"


class CalibrationUnresolved(Exception):
    """Mechanical/internal exception: durable evidence already written; never collated."""


def _b64(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


def _now() -> str:
    return datetime.now(UTC).isoformat()


# ---------------------------------------------------------------------------
# Calibration request specs
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class CalibrationRequestSpec:
    """One exact scoring request for one case, with its sealed request SHA."""

    request_index: int
    case_id: str
    truth_label: bool
    request_bytes: bytes
    request_sha256: str
    persisted_state: Mapping[str, str]

    def to_struct(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "request_index": self.request_index,
            "request_sha256": self.request_sha256,
            "truth_label": self.truth_label,
        }


def build_calibration_request_bytes(
    scoring_prompt_content: bytes, persisted_state: Mapping[str, str]
) -> bytes:
    """Deterministic exact request bytes for one case's scoring call.

    The scoring prompt is a ``.format`` template; the only substitutions are the
    exact five authorized persisted fields. The resulting text is serialized with
    the repository canonical JSON serializer (identical to the direct Responses
    adapter), so the sealed request SHA is reproducible from loaded authorities.
    """
    from .direct_responses import build_request_bytes as _build_responses_request_bytes

    prompt_text = scoring_prompt_content.decode("utf-8").format(**dict(persisted_state))
    return _build_responses_request_bytes(prompt_text)


# ---------------------------------------------------------------------------
# Calibration manifest (sealed authority)
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Stage1ACalibrationManifest:
    """Binds the exact 60-case calibration run to the sealed origin chain.

    ``per_request_request_sha`` maps case id -> exact sealed request SHA in the
    deterministic ``ordered_case_ids`` order. Any origin-chain binding that does
    not reproduce from freshly loaded authorities => zero provider calls.
    """

    manifest_version: str
    harness_revision: str
    batch_run_id: str
    expected_requests: int
    zero_retries: bool
    protocol_sha256: str
    futility_amendment_sha256: str
    real_origin_amendment_sha256: str
    case_set_sha256: str
    scoring_prompt_sha256: str
    parse_contract_sha256: str
    direct_luna_config_sha256: str
    cross_session_rep_version: str
    origin_run_manifest_sha256: str
    origin_completed_run_sha256: str
    origin_batch_run_id: str
    ordered_case_ids: tuple[str, ...]
    per_case_request_sha: Mapping[str, str]
    truth_map: Mapping[str, bool]
    _seal: object = field(repr=False, compare=False, default=None)

    @classmethod
    def create(
        cls,
        *,
        harness_revision: str,
        batch_run_id: str,
        scoring_prompt_sha256: str,
        protocol_sha256: str,
        futility_amendment_sha256: str,
        real_origin_amendment_sha256: str,
        case_set_sha256: str,
        parse_contract_sha256: str,
        cross_session_rep_version: str,
        origin_run_manifest_sha256: str,
        origin_completed_run_sha256: str,
        origin_batch_run_id: str,
        ordered_case_ids: tuple[str, ...],
        per_case_request_sha: Mapping[str, str],
        truth_map: Mapping[str, bool],
    ) -> Stage1ACalibrationManifest:
        if len(ordered_case_ids) != STAGE1A_TOTAL:
            raise ValueError(f"calibration requires exactly {STAGE1A_TOTAL} cases")
        if len(set(ordered_case_ids)) != STAGE1A_TOTAL:
            raise ValueError("calibration case IDs must be unique")
        if set(per_case_request_sha) != set(ordered_case_ids):
            raise ValueError("per-case request SHAs must cover exactly the ordered cases")
        if set(truth_map) != set(ordered_case_ids):
            raise ValueError("truth map must cover exactly the ordered cases")
        return cls(
            manifest_version=CALIBRATION_MANIFEST_VERSION,
            harness_revision=harness_revision,
            batch_run_id=batch_run_id,
            expected_requests=STAGE1A_TOTAL,
            zero_retries=True,
            protocol_sha256=protocol_sha256,
            futility_amendment_sha256=futility_amendment_sha256,
            real_origin_amendment_sha256=real_origin_amendment_sha256,
            case_set_sha256=case_set_sha256,
            scoring_prompt_sha256=scoring_prompt_sha256,
            parse_contract_sha256=parse_contract_sha256,
            direct_luna_config_sha256=DIRECT_CONFIG_HASH,
            cross_session_rep_version=cross_session_rep_version,
            origin_run_manifest_sha256=origin_run_manifest_sha256,
            origin_completed_run_sha256=origin_completed_run_sha256,
            origin_batch_run_id=origin_batch_run_id,
            ordered_case_ids=ordered_case_ids,
            per_case_request_sha=MappingProxyType(dict(per_case_request_sha)),
            truth_map=MappingProxyType(dict(truth_map)),
        )

    def canonical_record(self) -> dict[str, Any]:
        return {
            "batch_run_id": self.batch_run_id,
            "case_set_sha256": self.case_set_sha256,
            "cross_session_rep_version": self.cross_session_rep_version,
            "direct_luna_config_sha256": self.direct_luna_config_sha256,
            "expected_requests": self.expected_requests,
            "futility_amendment_sha256": self.futility_amendment_sha256,
            "harness_revision": self.harness_revision,
            "manifest_version": self.manifest_version,
            "ordered_case_ids": list(self.ordered_case_ids),
            "origin_batch_run_id": self.origin_batch_run_id,
            "origin_completed_run_sha256": self.origin_completed_run_sha256,
            "origin_run_manifest_sha256": self.origin_run_manifest_sha256,
            "parse_contract_sha256": self.parse_contract_sha256,
            "per_case_request_sha": dict(self.per_case_request_sha),
            "protocol_sha256": self.protocol_sha256,
            "real_origin_amendment_sha256": self.real_origin_amendment_sha256,
            "scoring_prompt_sha256": self.scoring_prompt_sha256,
            "truth_map": dict(self.truth_map),
            "zero_retries": self.zero_retries,
        }

    def to_exact_bytes(self) -> bytes:
        return canonical_json_bytes(self.canonical_record())

    @classmethod
    def _reconstruct(cls, raw: bytes) -> Stage1ACalibrationManifest:
        data = json.loads(raw.decode("utf-8"))
        return cls(
            manifest_version=data["manifest_version"],
            harness_revision=data["harness_revision"],
            batch_run_id=data["batch_run_id"],
            expected_requests=data["expected_requests"],
            zero_retries=data["zero_retries"],
            protocol_sha256=data["protocol_sha256"],
            futility_amendment_sha256=data["futility_amendment_sha256"],
            real_origin_amendment_sha256=data["real_origin_amendment_sha256"],
            case_set_sha256=data["case_set_sha256"],
            scoring_prompt_sha256=data["scoring_prompt_sha256"],
            parse_contract_sha256=data["parse_contract_sha256"],
            direct_luna_config_sha256=data["direct_luna_config_sha256"],
            cross_session_rep_version=data["cross_session_rep_version"],
            origin_run_manifest_sha256=data["origin_run_manifest_sha256"],
            origin_completed_run_sha256=data["origin_completed_run_sha256"],
            origin_batch_run_id=data["origin_batch_run_id"],
            ordered_case_ids=tuple(data["ordered_case_ids"]),
            per_case_request_sha=dict(data["per_case_request_sha"]),
            truth_map=dict(data["truth_map"]),
        )

    @property
    def sha256(self) -> str:
        return sha256_bytes(self.to_exact_bytes())

    def validate_completeness(self) -> None:
        if self.expected_requests != STAGE1A_TOTAL:
            raise ValueError("calibration manifest must require exactly 60 requests")
        if not self.zero_retries:
            raise ValueError("calibration manifest must require zero retries")
        if len(self.ordered_case_ids) != STAGE1A_TOTAL:
            raise ValueError("calibration manifest must record exactly 60 ordered cases")
        required = (
            self.origin_run_manifest_sha256,
            self.origin_completed_run_sha256,
            self.origin_batch_run_id,
        )
        if not all(required):
            raise ValueError("calibration manifest is missing an origin authority binding")
        if self.direct_luna_config_sha256 != DIRECT_CONFIG_HASH:
            raise ValueError("calibration manifest must bind the authoritative Luna config")


# ---------------------------------------------------------------------------
# Evidence + durable sink
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class CalibrationEvidence:
    """Durable, lossless per-request evidence for one scoring attempt."""

    batch_run_id: str
    manifest_sha256: str
    request_index: int
    case_id: str
    request_sha256: str
    request_bytes: bytes
    http_status: int | None
    raw_provider_response: bytes | None
    final_output_sha256: str | None
    final_score: str | None  # exact decimal bytes (two decimals) when parsed
    parsed_score: float | None
    provider_metadata: Mapping[str, Any] | None
    timestamp: str
    success: bool
    failure_category: CalibrationFailureCategory | None
    mechanical_error: str | None

    def canonical_record(self) -> dict[str, Any]:
        return {
            "batch_run_id": self.batch_run_id,
            "case_id": self.case_id,
            "failure_category": (self.failure_category.value if self.failure_category else None),
            "final_output_sha256": self.final_output_sha256,
            "final_score": self.final_score,
            "http_status": self.http_status,
            "manifest_sha256": self.manifest_sha256,
            "mechanical_error": self.mechanical_error,
            "parsed_score": self.parsed_score,
            "provider_metadata": dict(self.provider_metadata or {}),
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
            "success": self.success,
            "timestamp": self.timestamp,
        }

    def to_exact_bytes(self) -> bytes:
        return canonical_json_bytes(self.canonical_record())

    @property
    def sha256(self) -> str:
        return sha256_bytes(self.to_exact_bytes())

    @classmethod
    def _reconstruct(cls, raw: bytes) -> CalibrationEvidence:
        data = json.loads(raw.decode("utf-8"))
        raw_b64 = data.get("raw_provider_response_base64")
        return cls(
            batch_run_id=data["batch_run_id"],
            manifest_sha256=data["manifest_sha256"],
            request_index=data["request_index"],
            case_id=data["case_id"],
            request_sha256=data["request_sha256"],
            request_bytes=base64.b64decode(data["request_bytes_base64"]),
            http_status=data["http_status"],
            raw_provider_response=(base64.b64decode(raw_b64) if raw_b64 is not None else None),
            final_output_sha256=data["final_output_sha256"],
            final_score=data["final_score"],
            parsed_score=data["parsed_score"],
            provider_metadata=data["provider_metadata"] or {},
            timestamp=data["timestamp"],
            success=data["success"],
            failure_category=(
                CalibrationFailureCategory(data["failure_category"])
                if data.get("failure_category")
                else None
            ),
            mechanical_error=data["mechanical_error"],
        )


class AtomicCalibrationSink:
    """Atomic, no-overwrite durable evidence sink for calibration requests."""

    def __init__(self, out_dir: Path) -> None:
        self.out_dir = Path(out_dir)

    def start_batch(self, batch_run_id: str, manifest_sha256: str) -> None:
        self.out_dir.mkdir(parents=True, exist_ok=True)
        path = self.out_dir / f"calibration-batch-{batch_run_id}.started"
        if path.exists():
            raise ValueError(
                f"calibration batch {batch_run_id} already started; no rerun permitted"
            )
        payload = json.dumps(
            {"batch_run_id": batch_run_id, "manifest_sha256": manifest_sha256},
            sort_keys=True,
        ).encode("utf-8")
        tmp = path.with_suffix(".started.tmp")
        tmp.write_bytes(payload)
        tmp.replace(path)

    def evidence_path(self, batch_run_id: str, request_index: int) -> Path:
        return self.out_dir / f"calibration-evidence-{batch_run_id}-c{request_index:02d}.json"

    def write_evidence(self, evidence: CalibrationEvidence) -> Path:
        self.out_dir.mkdir(parents=True, exist_ok=True)
        path = self.evidence_path(evidence.batch_run_id, evidence.request_index)
        if path.exists():
            raise ValueError("refusing to overwrite existing calibration evidence")
        tmp = path.with_suffix(".json.tmp")
        tmp.write_bytes(evidence.to_exact_bytes())
        tmp.replace(path)
        return path

    def completed_path(self, batch_run_id: str) -> Path:
        return self.out_dir / f"calibration-completed-{batch_run_id}.json"

    def write_completed(self, completed: CalibrationCompletedRun) -> Path:
        if not _validate_60_60_0(completed):
            raise ValueError("cannot persist a not-60/60/0 completed calibration authority")
        self.out_dir.mkdir(parents=True, exist_ok=True)
        path = self.completed_path(completed.batch_run_id)
        if path.exists():
            raise ValueError("refusing to overwrite existing completed calibration authority")
        tmp = path.with_suffix(".json.tmp")
        tmp.write_bytes(completed.to_exact_bytes())
        tmp.replace(path)
        return path


# ---------------------------------------------------------------------------
# Completed calibration authority
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class CalibrationCompletedRun:
    """Durable 60/60/0 completed-run authority binding the full evidence chain."""

    manifest_sha256: str
    batch_run_id: str
    ordered_case_ids: tuple[str, ...]
    evidence_shas: tuple[str, ...]
    scores: tuple[float, ...]

    def to_exact_bytes(self) -> bytes:
        return canonical_json_bytes(self.canonical_record())

    def canonical_record(self) -> dict[str, Any]:
        return {
            "batch_run_id": self.batch_run_id,
            "evidence_shas": list(self.evidence_shas),
            "manifest_sha256": self.manifest_sha256,
            "ordered_case_ids": list(self.ordered_case_ids),
            "scores": list(self.scores),
        }

    @classmethod
    def _reconstruct(cls, raw: bytes) -> CalibrationCompletedRun:
        data = json.loads(raw.decode("utf-8"))
        return cls(
            manifest_sha256=data["manifest_sha256"],
            batch_run_id=data["batch_run_id"],
            ordered_case_ids=tuple(data["ordered_case_ids"]),
            evidence_shas=tuple(data["evidence_shas"]),
            scores=tuple(data["scores"]),
        )

    @property
    def sha256(self) -> str:
        return sha256_bytes(self.to_exact_bytes())


def _validate_60_60_0(completed: CalibrationCompletedRun) -> bool:
    return (
        len(completed.ordered_case_ids) == STAGE1A_TOTAL
        and len(completed.evidence_shas) == STAGE1A_TOTAL
        and len(completed.scores) == STAGE1A_TOTAL
        and all(0.0 <= s <= 1.0 for s in completed.scores)
    )


def _score_of(evidence: CalibrationEvidence) -> float:
    if evidence.parsed_score is None:
        raise ValueError("successful evidence must carry a parsed score")
    return evidence.parsed_score


# ---------------------------------------------------------------------------
# Origin-chain verification (used by both prepare + live)
# ---------------------------------------------------------------------------


def _verify_origin_chain(
    *,
    auth: LoadedStage1AAuthority,
    actual_harness_revision: str,
    origin_manifest_path: Path,
    origin_manifest_sha256: str,
    origin_completed_path: Path,
    origin_completed_sha256: str,
    origin_artifacts_dir: Path,
    origin_batch_run_id: str,
) -> tuple[CompletedOriginRun, tuple[Any, ...]]:
    """Re-read and independently verify the ENTIRE origin chain (mandatory)."""
    if origin_manifest_path is None or not origin_manifest_path.exists():
        raise ValueError("origin manifest file is required")
    raw_manifest = origin_manifest_path.read_bytes()
    if sha256_bytes(raw_manifest) != origin_manifest_sha256:
        raise ValueError("origin manifest file does not hash to the authorized origin SHA")
    origin_manifest = Stage1AOriginRunManifest._reconstruct(raw_manifest)
    if origin_manifest.to_exact_bytes() != raw_manifest:
        raise ValueError("origin manifest file is not canonical")
    validate_origin_run_manifest_seal(
        manifest=origin_manifest,
        manifest_sha256=origin_manifest_sha256,
        actual_harness_revision=actual_harness_revision,
        auth=auth,
    )
    if origin_manifest.batch_run_id != origin_batch_run_id:
        raise ValueError("origin manifest batch does not match the authorized origin batch")

    if origin_completed_path is None or not origin_completed_path.exists():
        raise ValueError("origin completed-run file is required")
    raw_completed = origin_completed_path.read_bytes()
    if sha256_bytes(raw_completed) != origin_completed_sha256:
        raise ValueError("origin completed-run file does not hash to the authorized SHA")
    completed = CompletedOriginRun.from_exact_bytes(raw_completed)
    if completed.to_exact_bytes() != raw_completed:
        raise ValueError("origin completed-run file is not canonical")
    if completed.batch_run_id != origin_batch_run_id:
        raise ValueError("origin completed-run batch does not match the authorized origin batch")
    if completed.manifest_sha256 != origin_manifest_sha256:
        raise ValueError("origin completed-run manifest SHA does not match origin manifest")

    artifacts = load_origin_run_artifacts(
        artifacts_dir=origin_artifacts_dir, batch_run_id=origin_batch_run_id
    )
    if len(artifacts) != 5:
        raise ValueError("origin chain requires exactly five origin artifacts")
    # Every artifact must bind the origin manifest + completed SHA and the batch.
    for art in artifacts:
        if getattr(art, "origin_manifest_sha256", None) != origin_manifest_sha256:
            raise ValueError("origin artifact manifest SHA does not match origin manifest")
        if getattr(art, "batch_run_id", None) != origin_batch_run_id:
            raise ValueError("origin artifact batch does not match the origin batch")
    return completed, tuple(artifacts)


def _build_calibration_specs(
    *, auth: LoadedStage1AAuthority, harness_revision: str, batch_run_id: str
) -> tuple[CalibrationRequestSpec, ...]:
    """Deterministically build the 60 exact scoring requests from loaded authority."""
    cases = build_stage1a_cases(
        seed=STAGE1A_SEED,
        template_bank=TemplateBank.from_bytes(auth.template_bank.content),
    )
    specs: list[CalibrationRequestSpec] = []
    for index, case in enumerate(cases, start=1):
        persisted = dict(case.cross_session.judgment_context)
        req_bytes = build_calibration_request_bytes(auth.scoring_prompt.content, persisted)
        specs.append(
            CalibrationRequestSpec(
                request_index=index,
                case_id=case.generated.spec.case_id,
                truth_label=case.generated.truth_label,
                request_bytes=req_bytes,
                request_sha256=sha256_bytes(req_bytes),
                persisted_state=persisted,
            )
        )
    return tuple(specs)


def build_calibration_manifest(
    *,
    harness_revision: str,
    origin_manifest_path: Path | None,
    origin_manifest_sha256: str,
    origin_completed_path: Path | None,
    origin_completed_sha256: str,
    origin_artifacts_dir: Path,
    origin_batch_run_id: str,
    scoring_prompt_sha256: str = EXPECTED_SCORING_PROMPT_SHA,
) -> tuple[Stage1ACalibrationManifest, tuple[CalibrationRequestSpec, ...]]:
    """Zero-call prepare: verify the origin chain, then build the authoritative manifest.

    Re-reads and independently verifies the entire origin chain before constructing
    the calibrated authority. The per-case exact request SHAs are precomputed from
    the loaded authorities and sealed into the manifest.
    """
    if origin_manifest_path is None:
        raise ValueError("origin manifest path is required")
    if origin_completed_path is None:
        raise ValueError("origin completed path is required")
    auth = load_authority_artifacts(verify_expected=True)
    completed, _artifacts = _verify_origin_chain(
        auth=auth,
        actual_harness_revision=harness_revision,
        origin_manifest_path=origin_manifest_path,
        origin_manifest_sha256=origin_manifest_sha256,
        origin_completed_path=origin_completed_path,
        origin_completed_sha256=origin_completed_sha256,
        origin_artifacts_dir=origin_artifacts_dir,
        origin_batch_run_id=origin_batch_run_id,
    )
    cases = build_stage1a_cases(
        seed=STAGE1A_SEED, template_bank=TemplateBank.from_bytes(auth.template_bank.content)
    )
    case_set = freeze_stage1a_case_set(cases)
    batch_run_id = (
        f"calibration-{harness_revision[:12]}-{datetime.now(UTC).strftime('%Y%m%dT%H%M%S%fZ')}"
    )
    specs = _build_calibration_specs(
        auth=auth, harness_revision=harness_revision, batch_run_id=batch_run_id
    )
    ordered_ids = tuple(s.case_id for s in specs)
    truth = {s.case_id: s.truth_label for s in specs}
    req_shas = {s.case_id: s.request_sha256 for s in specs}
    manifest = Stage1ACalibrationManifest.create(
        harness_revision=harness_revision,
        batch_run_id=batch_run_id,
        scoring_prompt_sha256=scoring_prompt_sha256,
        protocol_sha256=auth.protocol.sha256,
        futility_amendment_sha256=auth.futility_amendment.sha256,
        real_origin_amendment_sha256=auth.real_origin_amendment.sha256,
        case_set_sha256=case_set.sha256,
        parse_contract_sha256=PLAIN_DECIMAL_V1_SHA256,
        cross_session_rep_version=CROSS_SESSION_REP_VERSION,
        origin_run_manifest_sha256=origin_manifest_sha256,
        origin_completed_run_sha256=origin_completed_sha256,
        origin_batch_run_id=origin_batch_run_id,
        ordered_case_ids=ordered_ids,
        per_case_request_sha=req_shas,
        truth_map=truth,
    )
    manifest.validate_completeness()
    return manifest, specs


def validate_calibration_manifest_seal_exact(
    *,
    manifest: Stage1ACalibrationManifest,
    manifest_sha256: str,
    auth: LoadedStage1AAuthority,
    actual_harness_revision: str,
) -> Stage1ACalibrationManifest:
    """Re-verify every binding and exact-byte reconstruction; return the SAME object.

    Closes N3 at the calibration layer: the returned manifest is mechanically the
    object validated, sealed against freshly rederived request SHAs.
    """
    if manifest.sha256 != manifest_sha256:
        raise ValueError("calibration manifest SHA does not match expected value")
    if manifest.harness_revision != actual_harness_revision:
        raise ValueError("calibration manifest harness revision does not match current HEAD")
    # Exact-byte reconstruction contract.
    rebuilt_raw = manifest.to_exact_bytes()
    if Stage1ACalibrationManifest._reconstruct(rebuilt_raw).to_exact_bytes() != rebuilt_raw:
        raise ValueError("calibration manifest exact-byte reconstruction failed")
    bindings = {
        "protocol": (manifest.protocol_sha256, auth.protocol.sha256),
        "futility amendment": (
            manifest.futility_amendment_sha256,
            auth.futility_amendment.sha256,
        ),
        "real-origin amendment": (
            manifest.real_origin_amendment_sha256,
            auth.real_origin_amendment.sha256,
        ),
        "case set": (manifest.case_set_sha256, auth.case_set.sha256),
        "scoring prompt": (manifest.scoring_prompt_sha256, auth.scoring_prompt.sha256),
        "parse contract": (manifest.parse_contract_sha256, PLAIN_DECIMAL_V1_SHA256),
        "Luna config": (manifest.direct_luna_config_sha256, DIRECT_CONFIG_HASH),
    }
    for name, (recorded, actual) in bindings.items():
        if recorded != actual:
            raise ValueError(f"calibration seal mismatch: {name}")
    if manifest.cross_session_rep_version != CROSS_SESSION_REP_VERSION:
        raise ValueError("calibration seal mismatch: cross-session representation version")
    if len(manifest.ordered_case_ids) != STAGE1A_TOTAL:
        raise ValueError("calibration seal mismatch: ordered case count")
    # Rederive all 60 request SHAs and require exact equality.
    specs = _build_calibration_specs(
        auth=auth, harness_revision=actual_harness_revision, batch_run_id=manifest.batch_run_id
    )
    if len(specs) != STAGE1A_TOTAL:
        raise ValueError("calibration seal mismatch: spec count")
    for spec in specs:
        if manifest.per_case_request_sha.get(spec.case_id) != spec.request_sha256:
            raise ValueError(f"calibration seal mismatch: request SHA for {spec.case_id}")
    manifest.validate_completeness()
    return manifest


# ---------------------------------------------------------------------------
# Deterministic single-score execution (one request per case, durably persisted)
# ---------------------------------------------------------------------------


class CalibrationTransport(Protocol):
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
    spec: CalibrationRequestSpec,
    status: int | None,
    error_body: bytes | None,
    raw_response: bytes | None,
    md: Mapping[str, Any] | None,
    category: CalibrationFailureCategory | None,
    success: bool,
    mechanical: str | None,
) -> CalibrationEvidence:
    final_sha = None
    final_score = None
    parsed_score = None
    if raw_response is not None:
        try:
            parsed = parse_scoring_response(raw_response)
            final_score = parsed.final_answer
            final_sha = sha256_bytes(parsed.final_answer.encode("utf-8"))
            parsed_score = parse_plain_decimal_v1(parsed.final_answer.encode("utf-8"))
        except Exception:
            # Keep the raw evidence; classification happens in the caller.
            pass
    return CalibrationEvidence(
        batch_run_id=batch,
        manifest_sha256=manifest_sha,
        request_index=spec.request_index,
        case_id=spec.case_id,
        request_sha256=spec.request_sha256,
        request_bytes=spec.request_bytes,
        http_status=status,
        raw_provider_response=raw_response,
        final_output_sha256=final_sha,
        final_score=final_score,
        parsed_score=parsed_score,
        provider_metadata=dict(md or {}),
        timestamp=_now(),
        success=success,
        failure_category=category,
        mechanical_error=mechanical,
    )


def execute_calibration_run(
    *,
    manifest_bytes: bytes,
    expected_manifest_sha256: str,
    actual_harness_revision: str,
    auth: LoadedStage1AAuthority,
    batch_run_id: str,
    transport: CalibrationTransport,
    evidence_sink: AtomicCalibrationSink,
) -> tuple[CalibrationRunStatus, tuple[CalibrationEvidence, ...], CalibrationCompletedRun | None]:
    """Execute the sealed 60-request run from an EXISTING sealed manifest.

    Manifests a true 60/60/0 completed-run authority only on full success. A
    failure at request N durably preserves N's evidence and stops before N+1.
    """
    if sha256_bytes(manifest_bytes) != expected_manifest_sha256:
        raise ValueError("calibration manifest bytes do not hash to the expected SHA")
    manifest = Stage1ACalibrationManifest._reconstruct(manifest_bytes)
    if manifest.to_exact_bytes() != manifest_bytes:
        raise ValueError("calibration manifest bytes are not canonical/substituted")
    manifest = validate_calibration_manifest_seal_exact(
        manifest=manifest,
        manifest_sha256=expected_manifest_sha256,
        auth=auth,
        actual_harness_revision=actual_harness_revision,
    )
    if manifest.batch_run_id != batch_run_id:
        raise ValueError("provided calibration batch does not match sealed manifest batch")
    evidence_sink.start_batch(batch_run_id, manifest.sha256)
    # Rederive all 60 exact request bytes from the freshly loaded authorities.
    specs = _build_calibration_specs(
        auth=auth, harness_revision=actual_harness_revision, batch_run_id=batch_run_id
    )
    evidence: list[CalibrationEvidence] = []
    for spec in specs:
        try:
            status, err_body, raw_response, md = transport(payload=spec.request_bytes)
        except Exception as exc:  # transport/mechanical -> preserve evidence, stop
            ev = _evidence_for(
                batch=batch_run_id,
                manifest_sha=manifest.sha256,
                spec=spec,
                status=None,
                error_body=None,
                raw_response=None,
                md={},
                category=CalibrationFailureCategory.TRANSPORT,
                success=False,
                mechanical=f"{type(exc).__name__}: {exc}",
            )
            evidence_sink.write_evidence(ev)
            return (
                CalibrationRunStatus.FAILED,
                tuple(evidence) + (ev,),
                None,
            )
        if status != 200 or raw_response is None:
            category = (
                CalibrationFailureCategory.HTTP
                if status is not None
                else CalibrationFailureCategory.TRANSPORT
            )
            ev = _evidence_for(
                batch=batch_run_id,
                manifest_sha=manifest.sha256,
                spec=spec,
                status=status,
                error_body=err_body,
                raw_response=raw_response,
                md=md or {},
                category=category,
                success=False,
                mechanical=None,
            )
            evidence_sink.write_evidence(ev)
            return (
                CalibrationRunStatus.FAILED,
                tuple(evidence) + (ev,),
                None,
            )
        # Successful HTTP response: parse the scoring contract + decimal score.
        try:
            parsed = parse_scoring_response(raw_response)
            score = parse_plain_decimal_v1(parsed.final_answer.encode("utf-8"))
        except Exception as exc:
            ev = _evidence_for(
                batch=batch_run_id,
                manifest_sha=manifest.sha256,
                spec=spec,
                status=status,
                error_body=None,
                raw_response=raw_response,
                md=md or {},
                category=CalibrationFailureCategory.RESPONSES_CONTRACT,
                success=False,
                mechanical=f"{type(exc).__name__}: {exc}",
            )
            evidence_sink.write_evidence(ev)
            return (
                CalibrationRunStatus.FAILED,
                tuple(evidence) + (ev,),
                None,
            )
        if score is None:
            ev = _evidence_for(
                batch=batch_run_id,
                manifest_sha=manifest.sha256,
                spec=spec,
                status=status,
                error_body=None,
                raw_response=raw_response,
                md=md or {},
                category=CalibrationFailureCategory.SCORE_PARSE,
                success=False,
                mechanical="final answer is not a valid PLAIN_DECIMAL_V1",
            )
            evidence_sink.write_evidence(ev)
            return (
                CalibrationRunStatus.FAILED,
                tuple(evidence) + (ev,),
                None,
            )
        ev = _evidence_for(
            batch=batch_run_id,
            manifest_sha=manifest.sha256,
            spec=spec,
            status=status,
            error_body=None,
            raw_response=raw_response,
            md=md or {},
            category=None,
            success=True,
            mechanical=None,
        )
        evidence_sink.write_evidence(ev)
        evidence.append(ev)
    # Only a genuine 60/60/0 produces the completed authority.
    if len(evidence) == STAGE1A_TOTAL and all(e.success for e in evidence):
        scores = tuple(_score_of(e) for e in evidence)
        completed = CalibrationCompletedRun(
            manifest_sha256=manifest.sha256,
            batch_run_id=batch_run_id,
            ordered_case_ids=tuple(e.case_id for e in evidence),
            evidence_shas=tuple(e.sha256 for e in evidence),
            scores=scores,
        )
        evidence_sink.write_completed(completed)
        return CalibrationRunStatus.COMPLETED, tuple(evidence), completed
    return CalibrationRunStatus.INCOMPLETE, tuple(evidence), None


def require_valid_completed_calibration(
    completed: CalibrationCompletedRun | None,
    *,
    expected_manifest_sha256: str,
    expected_batch_run_id: str,
) -> CalibrationCompletedRun:
    """Gate deterministic analysis behind a valid 60/60/0 completed authority."""
    if completed is None:
        raise ValueError("calibration requires a completed 60/60/0 authority")
    if len(completed.ordered_case_ids) != STAGE1A_TOTAL:
        raise ValueError("completed calibration must bind 60 case IDs")
    if len(completed.evidence_shas) != STAGE1A_TOTAL:
        raise ValueError("completed calibration must bind 60 evidence SHAs")
    if len(completed.scores) != STAGE1A_TOTAL:
        raise ValueError("completed calibration must bind 60 scores")
    if completed.manifest_sha256 != expected_manifest_sha256:
        raise ValueError("completed calibration manifest SHA does not match expected")
    if completed.batch_run_id != expected_batch_run_id:
        raise ValueError("completed calibration batch does not match expected")
    return completed


def compute_calibration_report(
    completed: CalibrationCompletedRun,
    *,
    truth_map: Mapping[str, bool],
) -> Any:
    """Deterministic Stage-1A threshold report from a valid completed run.

    Uses the SINGLE shared score per case for both B and C (no second B/C calls).
    Delegates to the frozen 17-threshold selection + futility rule.
    """
    scored = tuple(
        ScoredCase(case_id=cid, score=score, truth_label=bool(truth_map[cid]))
        for cid, score in zip(completed.ordered_case_ids, completed.scores, strict=True)
    )
    if len(scored) != STAGE1A_TOTAL:
        raise ValueError("completed calibration must cover all 60 cases")
    report = compute_stage1a_report(scored)
    return report.to_dict() | {
        "manifest_sha256": completed.manifest_sha256,
        "batch_run_id": completed.batch_run_id,
    }
