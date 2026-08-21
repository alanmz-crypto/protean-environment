"""Stage-1A real-origin artifacts, frozen origin prompt, and a real verifier.

Repairs the cross-session MECHANICAL_GAP: a prospective commitment "originates"
in an earlier model session only when an actual GPT-5.6 Luna xHigh session
explicitly ADOPTS (never authors) each externally-frozen commitment as its own,
before any later outcome/state information exists.

One origin session per familiar structure (5 total, 12 commitments each => 60
coverage). Each artifact records an ORDERED canonical mapping of case_id ->
EXACT commitment bytes (the actual records presented), never merely an aggregate
hash. A dedicated origin prompt is frozen, and a strict, machine-checkable
adoption response contract is frozen. A real artifact can unlock calibration only
after mechanical verification (structure, 12 IDs, commitment records, Luna
config hash, re-derived request hash, preserved raw provider bytes + SHA,
response reparse, all-12 adoption, and provider metadata model/status/reasoning
when live evidence exists).

No provider call is made here; execution requires separate authorization.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from .artifacts import canonical_json_bytes, sha256_bytes
from .grammar import FROZEN_STRUCTURES, StructureId

# ---- Frozen dedicated origin-adoption prompt (adopt, not rewrite) ----
ORIGIN_PROMPT = (
    b"You are GPT-5.6 Luna xHigh. Below you are supplied with a list of "
    b"externally authored prospective commitments, each identified by a case_id. "
    b"For EACH commitment, DO NOT rewrite, paraphrase, improve, or regenerate its "
    b"wording. Explicitly adopt it as your OWN prospective commitment: confirm that "
    b"you will treat that exact commitment text as a commitment you hold, to be "
    b"judged later only against its stated trigger condition. You have no information "
    b"about any outcome, truth label, calibration score, selected threshold, or future "
    b"observed state. Respond with ONLY the frozen machine response: for each "
    b'case_id, a line "ADOPT <case_id>", one per case, in the order given, and '
    b"nothing else."
)
ORIGIN_PROMPT_SHA256 = sha256_bytes(ORIGIN_PROMPT)

# ---- Frozen adoption response-contract specification ----
ORIGIN_RESPONSE_CONTRACT_SPEC = (
    b"origin-adoption-v1: exact ASCII lines 'ADOPT <case_id>' (uppercase, space), "
    b"one per presented commitment, in the exact order presented, then an optional "
    b"trailing LF. Exactly matching the presented case_id set; no extra or missing "
    b"case_ids; no other content. A single 'ADOPT <case_id>' marks that commitment "
    b"as adopted by the model."
)
ORIGIN_RESPONSE_CONTRACT_SHA256 = sha256_bytes(ORIGIN_RESPONSE_CONTRACT_SPEC)

_ADOPT_LINE = re.compile(rb"^ADOPT ([A-Za-z0-9_-]+)$")


class OriginResponseContractFailure(RuntimeError):
    """A malformed/incomplete/refusal origin response. STOP before calibration."""


def canonical_commitment_records(
    records: list[tuple[str, bytes]],
) -> tuple[tuple[str, bytes], ...]:
    """Canonicalize an ordered case_id -> exact-commitment-bytes mapping."""
    ids = [rid for rid, _ in records]
    if len(ids) != 12 or len(set(ids)) != 12:
        raise OriginResponseContractFailure(
            "origin session must cover exactly 12 distinct case IDs"
        )
    out: list[tuple[str, bytes]] = []
    seen: set[str] = set()
    for cid, cbytes in records:
        if not cid or not cbytes:
            raise OriginResponseContractFailure("empty case_id or commitment bytes")
        if cid in seen:
            raise OriginResponseContractFailure(f"duplicate case_id {cid}")
        seen.add(cid)
        out.append((cid, cbytes))
    return tuple(out)


def commitments_hash(records: tuple[tuple[str, bytes], ...]) -> str:
    """SHA-256 over the ORDERED canonical case_id -> commitment-bytes mapping.

    The hash is computed over a bytes-level canonical stream (case_id, length-
    prefixed exact commitment bytes) so that exact binary commitment bytes are
    preserved and hashed, never collapsed to text.
    """
    parts: list[bytes] = []
    for cid, cb in records:
        parts.append(cid.encode("utf-8"))
        parts.append(len(cb).to_bytes(8, "big"))
        parts.append(cb)
    return sha256_bytes(b"\x00".join(parts))


@dataclass(frozen=True, slots=True)
class OriginSessionArtifact:
    """Immutable record of one real origin session (one structure, 12 cases)."""

    origin_run_id: str
    structure: StructureId
    commitment_records: tuple[tuple[str, bytes], ...]  # ordered case_id -> exact bytes
    commitment_sha256: str
    model_configuration_sha256: str
    request_sha256: str
    provider_response_sha256: str
    provider_response_bytes: bytes  # preserved raw provider bytes (verifier proves)
    adoption: Mapping[str, bool]  # case_id -> adopted (verifier proves all True)
    timestamp: str
    provider_metadata: Mapping[str, Any]

    def __post_init__(self) -> None:
        if self.structure not in FROZEN_STRUCTURES:
            raise ValueError(f"origin artifact declares unknown structure: {self.structure}")
        expected = set(e for e, _ in self.commitment_records)
        if set(self.adoption) != expected:
            raise ValueError("adoption keys must match the presented case IDs exactly")
        if self.commitment_sha256 != commitments_hash(self.commitment_records):
            raise ValueError("commitment records/hash mismatch")
        if len(self.request_sha256) != 64 or len(self.provider_response_sha256) != 64:
            raise ValueError("origin request/response hashes must be SHA-256 hex")
        if self.provider_response_sha256 != sha256_bytes(self.provider_response_bytes):
            raise ValueError("provider-response bytes/SHA mismatch")

    @property
    def case_ids(self) -> tuple[str, ...]:
        return tuple(e for e, _ in self.commitment_records)

    def canonical_record(self) -> dict[str, Any]:
        return {
            "adoption": {k: bool(v) for k, v in self.adoption.items()},
            "commitment_records": [
                [e, b.decode("utf-8", "replace")] for e, b in self.commitment_records
            ],
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


def build_origin_request_bytes(
    origin_prompt: bytes,
    records: list[tuple[str, bytes]],
) -> bytes:
    """Exact request bytes for one origin session (ordered case_id -> commitment).

    Embeds the SAME case IDs the response contract references, so the response
    parse can be checked against exactly the presented set.
    """
    rec = canonical_commitment_records(records)
    return canonical_json_bytes(
        {
            "input": [
                {"role": "user", "content": origin_prompt.decode("utf-8")},
                {
                    "role": "user",
                    "content": json.dumps(
                        {"commitments": [[cid, cb.decode("utf-8")] for cid, cb in rec]}
                    ),
                },
            ],
            "max_output_tokens": 64,
        }
    )


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


def verify_origin_artifact(
    artifact: OriginSessionArtifact,
    *,
    origin_prompt: bytes,
    expected_structure: StructureId,
    expected_case_ids: tuple[str, ...],
    authoritative_luna_config_sha256: str,
    expected_provider_model: str | None = None,
    expected_provider_status: str | None = None,
) -> None:
    """Mechanical real-origin verifier. Raises unless every proof holds.

    A manually populated adoption dict alone never constitutes proof; the verifier
    re-checks structure, the exact 12 case IDs, exact commitment records, the Luna
    config hash, the re-derived request SHA, preserved provider bytes + SHA,
    whether the provider response reparses under the frozen contract, and that all
    12 commitments are adopted (recomputed from the re-parsed response, not from
    the artifact's populated booleans). When live provider metadata is supplied,
    it also asserts the expected model/status.
    """
    if artifact.structure is not expected_structure:
        raise OriginResponseContractFailure("origin artifact declares the wrong structure")
    if artifact.case_ids != expected_case_ids:
        raise OriginResponseContractFailure("origin artifact case IDs differ from expected")
    if artifact.commitment_sha256 != commitments_hash(artifact.commitment_records):
        raise OriginResponseContractFailure("commitment records/hash mismatch")
    if artifact.model_configuration_sha256 != authoritative_luna_config_sha256:
        raise OriginResponseContractFailure("origin model configuration != Luna config")
    expected_request_sha = sha256_bytes(
        build_origin_request_bytes(origin_prompt, list(artifact.commitment_records))
    )
    if artifact.request_sha256 != expected_request_sha:
        raise OriginResponseContractFailure(
            "origin request SHA does not match the re-derived origin request"
        )
    if artifact.provider_response_sha256 != sha256_bytes(artifact.provider_response_bytes):
        raise OriginResponseContractFailure("provider-response bytes/SHA mismatch")
    # Reparse the provider response under the frozen contract; this is the proof,
    # not the artifact's stored adoption booleans.
    parsed = _parse_adoptions(artifact.provider_response_bytes, artifact.case_ids)
    if set(parsed) != set(expected_case_ids) or not all(parsed.values()):
        raise OriginResponseContractFailure(
            "provider response did not adopt all expected commitments"
        )
    if expected_provider_model is not None:
        returned = artifact.provider_metadata.get("model") or artifact.provider_metadata.get(
            "returned_model"
        )
        if returned and returned != expected_provider_model:
            raise OriginResponseContractFailure("provider model does not match expected")
    if expected_provider_status is not None:
        status = artifact.provider_metadata.get("status")
        if status and status != expected_provider_status:
            raise OriginResponseContractFailure("provider status does not match expected")
