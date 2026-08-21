"""Dedicated Stage-1A origin run manifest (separate from calibration manifest).

Binds every frozen/loaded authority the origin phase must honor, and requires the
precomputed request SHA for each of the 5 origin requests to be reproducible from
the loaded authorities before any provider access. Any mismatch => zero provider.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from .artifacts import canonical_json_bytes, sha256_bytes

ORIGIN_RUN_MANIFEST_VERSION = "stage1a-origin-run-v1"


@dataclass(frozen=True, slots=True)
class Stage1AOriginRequestBinding:
    """Merely-planned binding is stored in the manifest; verifier recomputes SHAs."""

    request_index: int
    structure: str
    case_ids: tuple[str, ...]
    # The exact precomputed request bytes are bound by request_sha256; the verifier
    # recomputes them from loaded authorities and requires exact equality.
    request_sha256: str

    def to_struct(self) -> dict[str, Any]:
        return {
            "case_ids": list(self.case_ids),
            "request_index": self.request_index,
            "request_sha256": self.request_sha256,
            "structure": self.structure,
        }


@dataclass(frozen=True, slots=True)
class Stage1AOriginRunManifest:
    protocol_sha256: str
    real_origin_amendment_sha256: str
    case_set_sha256: str
    origin_prompt_sha256: str
    origin_response_contract_sha256: str
    direct_luna_config_sha256: str
    harness_revision: str
    expected_requests: int
    ordered_structures: tuple[str, ...]
    per_structure_case_ids: Mapping[str, tuple[str, ...]]
    per_structure_commitment_hash: Mapping[str, str]
    per_request_request_sha: Mapping[str, str]
    zero_retries: bool
    batch_run_id: str
    manifest_version: str
    artifact_schema_version: str
    _seal: object = field(repr=False, compare=False, default=None)

    def canonical_record(self) -> dict[str, Any]:
        return {
            "artifact_schema_version": self.artifact_schema_version,
            "batch_run_id": self.batch_run_id,
            "case_set_sha256": self.case_set_sha256,
            "direct_luna_config_sha256": self.direct_luna_config_sha256,
            "expected_requests": self.expected_requests,
            "harness_revision": self.harness_revision,
            "manifest_version": self.manifest_version,
            "ordered_structures": list(self.ordered_structures),
            "origin_prompt_sha256": self.origin_prompt_sha256,
            "origin_response_contract_sha256": self.origin_response_contract_sha256,
            "per_structure_case_ids": {k: list(v) for k, v in self.per_structure_case_ids.items()},
            "per_structure_commitment_hash": dict(self.per_structure_commitment_hash),
            "per_request_request_sha": dict(self.per_request_request_sha),
            "protocol_sha256": self.protocol_sha256,
            "real_origin_amendment_sha256": self.real_origin_amendment_sha256,
            "zero_retries": self.zero_retries,
        }

    def to_exact_bytes(self) -> bytes:
        return canonical_json_bytes(self.canonical_record())

    @property
    def sha256(self) -> str:
        return sha256_bytes(self.to_exact_bytes())

    @classmethod
    def _reconstruct(cls, raw: bytes) -> Stage1AOriginRunManifest:
        """Rebuild the manifest EXACTLY from its canonical bytes."""
        data = json.loads(raw.decode("utf-8"))
        return cls(
            protocol_sha256=data["protocol_sha256"],
            real_origin_amendment_sha256=data["real_origin_amendment_sha256"],
            case_set_sha256=data["case_set_sha256"],
            origin_prompt_sha256=data["origin_prompt_sha256"],
            origin_response_contract_sha256=data["origin_response_contract_sha256"],
            direct_luna_config_sha256=data["direct_luna_config_sha256"],
            harness_revision=data["harness_revision"],
            expected_requests=data["expected_requests"],
            ordered_structures=tuple(data["ordered_structures"]),
            per_structure_case_ids={k: tuple(v) for k, v in data["per_structure_case_ids"].items()},
            per_structure_commitment_hash=dict(data["per_structure_commitment_hash"]),
            per_request_request_sha=dict(data["per_request_request_sha"]),
            zero_retries=data["zero_retries"],
            batch_run_id=data["batch_run_id"],
            manifest_version=data["manifest_version"],
            artifact_schema_version=data["artifact_schema_version"],
        )
