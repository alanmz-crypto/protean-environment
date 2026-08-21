"""Stage-1A real-origin artifacts and a deterministic adoption contract.

Repairs the cross-session MECHANICAL_GAP: a prospective commitment "originates"
in an earlier model session only when an actual GPT-5.6 Luna xHigh session
explicitly ADOPTS (never authors) each externally-frozen commitment as its own,
before any later outcome/state information exists.

This module records one origin session per familiar structure (5 total, 12
commitments each => 60 coverage) and a strict, machine-checkable response
contract proving Luna adopted all 12 listed commitments of that structure.
No provider call is made here; execution requires separate authorization.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from .artifacts import canonical_json_bytes, sha256_bytes
from .grammar import StructureId

# Deterministic adoption-response contract. The origin response must, for every
# listed case ID of a structure, affirm adoption. We accept a compact canonical
# form: one JSON object mapping each case ID to exactly True, or an ordered list
# of "ADOPT <case_id>" lines, one per case. No free prose is accepted.
_ADOPT_LINE = re.compile(rb"^ADOPT ([A-Za-z0-9_-]+)$")


class OriginResponseContractFailure(RuntimeError):
    """A malformed/incomplete/refusal origin response. STOP before calibration."""


@dataclass(frozen=True, slots=True)
class OriginSessionArtifact:
    """Immutable record of one real origin session (one structure, 12 cases)."""

    origin_run_id: str
    structure: StructureId
    case_ids: tuple[str, ...]
    commitment_bytes: bytes  # exact external commitment wording presented
    commitment_sha256: str
    model_configuration_sha256: str
    request_sha256: str
    provider_response_sha256: str
    adoption: Mapping[str, bool]  # case_id -> adopted (must be all True)
    timestamp: str
    provider_metadata: Mapping[str, Any]

    def __post_init__(self) -> None:
        if len(self.case_ids) != 12:
            raise ValueError("each origin session must cover exactly 12 cases")
        if len(set(self.case_ids)) != 12:
            raise ValueError("origin session case_ids must be unique")
        if self.adoption.keys() != set(self.case_ids):
            raise ValueError("adoption keys must exactly match the 12 case IDs")
        if not all(self.adoption.values()):
            raise ValueError("adoption must be true for all 12 commitments")
        if self.commitment_sha256 != sha256_bytes(self.commitment_bytes):
            raise ValueError("commitment bytes/hash mismatch")
        if len(self.request_sha256) != 64 or len(self.provider_response_sha256) != 64:
            raise ValueError("origin request/response hashes must be SHA-256 hex")

    def canonical_record(self) -> dict[str, Any]:
        return {
            "adoption": {k: bool(v) for k, v in self.adoption.items()},
            "case_ids": list(self.case_ids),
            "commitment_sha256": self.commitment_sha256,
            "model_configuration_sha256": self.model_configuration_sha256,
            "origin_run_id": self.origin_run_id,
            "provider_response_sha256": self.provider_response_sha256,
            "provider_metadata": dict(self.provider_metadata),
            "request_sha256": self.request_sha256,
            "structure": self.structure.value,
            "timestamp": self.timestamp,
        }

    def to_exact_bytes(self) -> bytes:
        return canonical_json_bytes(self.canonical_record())

    @property
    def sha256(self) -> str:
        return sha256_bytes(self.to_exact_bytes())


def _parse_adoptions(raw: bytes, case_ids: tuple[str, ...]) -> Mapping[str, bool]:
    """Parse a strict adoption response; any deviation raises a contract failure."""
    stripped = raw.strip()
    expected = set(case_ids)
    if not stripped:
        raise OriginResponseContractFailure("empty origin response")
    try:
        obj = json.loads(stripped.decode("utf-8"))
    except Exception:
        obj = None
    if isinstance(obj, dict):
        keys = set(obj.keys())
        if keys != expected:
            raise OriginResponseContractFailure(
                f"origin response case coverage mismatch: {sorted(keys - expected)} extra, "
                f"{sorted(expected - keys)} missing"
            )
        adoption: dict[str, bool] = {}
        for cid, val in obj.items():
            if val is not True:
                raise OriginResponseContractFailure(f"non-adoption for {cid}")
            adoption[cid] = True
        return adoption
    # fallback: ordered "ADOPT <case_id>" lines, one per case, exact count/order
    lines = stripped.splitlines()
    if len(lines) != len(case_ids):
        raise OriginResponseContractFailure(
            f"origin response expected {len(case_ids)} ADOPT lines, got {len(lines)}"
        )
    adoption2: dict[str, bool] = {}
    for line in lines:
        m = _ADOPT_LINE.fullmatch(line.strip())
        if m is None:
            raise OriginResponseContractFailure(f"malformed origin line: {line[:40]!r}")
        cid = m.group(1).decode("ascii")
        if cid not in expected or cid in adoption2:
            raise OriginResponseContractFailure(f"duplicate/unknown case id in origin line: {cid}")
        adoption2[cid] = True
    if set(adoption2) != expected:
        raise OriginResponseContractFailure("origin response did not adopt all listed commitments")
    return adoption2


def build_origin_request_bytes(
    scoring_prompt: bytes,
    case_payloads: list[Mapping[str, str]],
) -> bytes:
    """Exact request bytes for one origin session (12 commitments; no truth/state)."""
    records = [("COMMITMENT", p.get("commitment", "")) for p in case_payloads]
    return canonical_json_bytes(
        {"prompt": scoring_prompt.decode("utf-8", "replace"), "commitments": records}
    )


def verify_origin_precondition(case_ids: list[str]) -> None:
    expected = set(case_ids)
    if len(case_ids) != 12 or len(expected) != 12:
        raise OriginResponseContractFailure("origin session must cover exactly 12 distinct cases")
