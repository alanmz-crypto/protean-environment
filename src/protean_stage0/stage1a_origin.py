"""Stage-1A real-origin artifacts, exact adoption contract, and wire verification.

Repairs the cross-session MECHANICAL_GAP: a commitment "originates" in an earlier
model session only when an actual GPT-5.6 Luna xHigh session explicitly ADOPTS
(never authors) each externally-frozen commitment as its own, before any later
outcome/state information exists.

One origin session per familiar structure (5 total, 12 commitments each => 60).
Each artifact records an ORDERED canonical case_id -> EXACT commitment-bytes
mapping and holds REAL Responses-API wire evidence: the exact transmitted
request bytes, the complete raw provider JSON response bytes, and the extracted
final ADOPT-line output. The raw response is parsed through the SAME strict
Responses-object contract used by the direct Luna adapter (completed, response
object, exact model, reasoning context, errors/incomplete rejected), then the
exact origin-adoption-v1 contract is applied to the final output. A real artifact
unlocks calibration only after verify_origin_artifact() passes every check.

No provider call is made here; execution uses a fake transport in tests.
"""

from __future__ import annotations

import base64
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from .artifacts import canonical_json_bytes, sha256_bytes
from .direct_config import DIRECT_CONFIG_HASH, MODEL
from .direct_responses import build_request_body, parse_scoring_response
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

# ---- Frozen origin-adoption response contract (EXACT) ----
ORIGIN_RESPONSE_CONTRACT_VERSION = "origin-adoption-v1"
ORIGIN_RESPONSE_CONTRACT_SPEC = (
    b"origin-adoption-v1 EXACT: the final assistant output must be exactly the "
    b"case IDs of the presented commitments, in the exact presented order, one "
    b"per line, each line being exactly 'ADOPT <case_id>' with a single space and "
    b"no leading/trailing whitespace, lines separated by a single LF, with at "
    b"most one optional final LF and no other whitespace or content. No JSON, no "
    b"extra text, no blank lines."
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

    Computed over a bytes-level canonical stream (case_id, length-prefixed exact
    commitment bytes) so exact commitment bytes are hashed, never collapsed to text.
    """
    parts: list[bytes] = []
    for cid, cb in records:
        parts.append(cid.encode("utf-8"))
        parts.append(len(cb).to_bytes(8, "big"))
        parts.append(cb)
    return sha256_bytes(b"\x00".join(parts))


def _origin_input_text(origin_prompt: bytes, records: tuple[tuple[str, bytes], ...]) -> str:
    """The exact `input` payload text sent to Luna (prompt + ordered commitments)."""
    body = origin_prompt.decode("utf-8")
    records_json = json.dumps({"commitments": [[cid, cb.decode("utf-8")] for cid, cb in records]})
    return f"{body}\n\n{records_json}"


def build_origin_request_bytes(
    origin_prompt: bytes,
    records: list[tuple[str, bytes]],
) -> bytes:
    """Exact Luna /v1/responses request bytes for one origin session.

    Reuses the direct Responses-API request surface (gpt-5.6-luna, reasoning
    effort=xhigh, context=current_turn, store=false, max_output_tokens=128000),
    with the origin prompt + ordered commitment records as the `input`.
    """
    rec = canonical_commitment_records(records)
    return canonical_json_bytes(build_request_body(_origin_input_text(origin_prompt, rec)))


def _parse_origin_adoptions_exact(
    final_output: bytes, case_ids: tuple[str, ...]
) -> Mapping[str, bool]:
    """Parse the EXACT origin-adoption-v1 contract. No JSON/strip/coercion.

    final_output must be exactly, for all presented case IDs in the exact given
    order, one 'ADOPT <case_id>' per line, lines separated by single LF, with at
    most one optional trailing LF and no other whitespace or content.
    """
    if not case_ids:
        raise OriginResponseContractFailure("no case IDs to adopt")
    expected_lines = [b"ADOPT " + cid.encode() for cid in case_ids]
    if final_output == b"\n".join(expected_lines):
        return {cid: True for cid in case_ids}
    if final_output == (b"\n".join(expected_lines) + b"\n"):
        return {cid: True for cid in case_ids}
    raise OriginResponseContractFailure(
        "origin final output does not match EXACT origin-adoption-v1 contract"
    )


@dataclass(frozen=True, slots=True)
class OriginSessionArtifact:
    """Immutable record of one real origin session (one structure, 12 cases)."""

    origin_run_id: str
    structure: StructureId
    commitment_records: tuple[tuple[str, bytes], ...]  # ordered case_id -> exact bytes
    commitment_sha256: str
    model_configuration_sha256: str
    request_sha256: str
    raw_provider_response_sha256: str
    raw_provider_response_bytes: bytes  # complete Responses API JSON (preserved)
    final_output_sha256: str
    final_output_bytes: bytes  # extracted assistant ADOPT-line output
    timestamp: str
    provider_metadata: Mapping[str, Any]
    origin_manifest_sha256: str
    batch_run_id: str
    request_index: int

    def __post_init__(self) -> None:
        if self.structure not in FROZEN_STRUCTURES:
            raise ValueError(f"origin artifact declares unknown structure: {self.structure}")
        if self.commitment_sha256 != commitments_hash(self.commitment_records):
            raise ValueError("commitment records/hash mismatch")
        if len(self.request_sha256) != 64:
            raise ValueError("request_sha256 must be SHA-256 hex")
        if len(self.origin_manifest_sha256) != 64:
            raise ValueError("origin_manifest_sha256 must be SHA-256 hex")
        if not self.batch_run_id:
            raise ValueError("batch_run_id must be non-empty")
        if self.request_index < 1 or self.request_index > 5:
            raise ValueError("request_index must be in 1..5")
        if self.raw_provider_response_sha256 != sha256_bytes(self.raw_provider_response_bytes):
            raise ValueError("raw provider-response bytes/SHA mismatch")
        if self.final_output_sha256 != sha256_bytes(self.final_output_bytes):
            raise ValueError("final-output bytes/SHA mismatch")

    @property
    def case_ids(self) -> tuple[str, ...]:
        return tuple(e for e, _ in self.commitment_records)

    def canonical_record(self) -> dict[str, Any]:
        """Durable serialization that PRESERVES the raw provider response bytes.

        The complete raw provider JSON is base64-encoded into the record (and its
        SHA asserted), so it survives canonical serialization rather than living
        only in an in-memory field.
        """
        return {
            "commitment_records": [
                [e, b.decode("utf-8", "replace")] for e, b in self.commitment_records
            ],
            "commitment_sha256": self.commitment_sha256,
            "final_output_bytes": self.final_output_bytes.decode("utf-8", "replace"),
            "final_output_sha256": self.final_output_sha256,
            "model_configuration_sha256": self.model_configuration_sha256,
            "origin_manifest_sha256": self.origin_manifest_sha256,
            "batch_run_id": self.batch_run_id,
            "request_index": self.request_index,
            "origin_run_id": self.origin_run_id,
            "provider_metadata": dict(self.provider_metadata),
            "raw_provider_response_base64": base64.b64encode(
                self.raw_provider_response_bytes
            ).decode("ascii"),
            "raw_provider_response_sha256": self.raw_provider_response_sha256,
            "request_sha256": self.request_sha256,
            "structure": self.structure.value,
            "timestamp": self.timestamp,
        }

    def to_exact_bytes(self) -> bytes:
        return canonical_json_bytes(self.canonical_record())

    @property
    def sha256(self) -> str:
        return sha256_bytes(self.to_exact_bytes())


def parse_raw_provider_response(raw_bytes: bytes) -> str:
    """Parse the raw Responses JSON through the strict direct-Luna contract.

    Returns the extracted final assistant output_text. Raises on any contract
    violation (missing/incomplete status, model mismatch, reasoning context,
    errors, incomplete details, malformed output) so missing model/status
    evidence fails closed.
    """
    parsed = parse_scoring_response(raw_bytes)
    return parsed.final_answer


def verify_origin_artifact(
    artifact: OriginSessionArtifact,
    *,
    origin_prompt: bytes,
    expected_structure: StructureId,
    expected_case_ids: tuple[str, ...],
    expected_commitment_records: tuple[tuple[str, bytes], ...],
    authoritative_luna_config_sha256: str = DIRECT_CONFIG_HASH,
    expected_provider_model: str = MODEL,
    expected_origin_manifest_sha256: str | None = None,
    expected_batch_run_id: str | None = None,
    expected_request_index: int | None = None,
) -> None:
    """Full mechanical real-origin verifier. Raises unless EVERY proof holds.

    The verifier reparses the preserved raw provider JSON through the strict
    direct-Luna Responses contract (enforcing model gpt-5.6-luna, completed
    status, reasoning context, no errors/incomplete), extracts the final ADOPT
    output, and applies the EXACT origin-adoption-v1 contract. A manually
    populated adoption dict is never used as proof. Missing model/status evidence
    fails closed via the strict parser.

    ``expected_commitment_records`` is the mechanically-derived ORDERED
    (case_id, exact_external_commitment_bytes) tuple from the frozen Stage-1A
    cases. The artifact's records must equal it byte-for-byte and
    order-for-order (not merely an artifact-derived hash compared to another
    artifact-derived hash).
    """
    if artifact.structure is not expected_structure:
        raise OriginResponseContractFailure("origin artifact declares the wrong structure")
    if artifact.case_ids != expected_case_ids:
        raise OriginResponseContractFailure("origin artifact case IDs differ from expected")
    if artifact.commitment_records != expected_commitment_records:
        raise OriginResponseContractFailure(
            "origin commitment records do not match the frozen expected records byte/order-exactly"
        )
    if artifact.commitment_sha256 != commitments_hash(artifact.commitment_records):
        raise OriginResponseContractFailure("commitment records/hash mismatch")
    if artifact.model_configuration_sha256 != authoritative_luna_config_sha256:
        raise OriginResponseContractFailure(
            "origin model configuration != authoritative Luna config"
        )
    expected_request_sha = sha256_bytes(
        build_origin_request_bytes(origin_prompt, list(artifact.commitment_records))
    )
    if artifact.request_sha256 != expected_request_sha:
        raise OriginResponseContractFailure(
            "origin request SHA does not match the re-derived origin request"
        )
    if artifact.raw_provider_response_sha256 != sha256_bytes(artifact.raw_provider_response_bytes):
        raise OriginResponseContractFailure("raw provider-response bytes/SHA mismatch")
    if artifact.final_output_sha256 != sha256_bytes(artifact.final_output_bytes):
        raise OriginResponseContractFailure("final-output bytes/SHA mismatch")
    # Re-parse the raw provider JSON through the strict direct-Luna contract.
    # This is what fails closed on missing model/status/incomplete.
    extracted = parse_raw_provider_response(artifact.raw_provider_response_bytes)
    if extracted.encode("utf-8") != artifact.final_output_bytes:
        raise OriginResponseContractFailure(
            "final output does not match the re-extracted assistant output_text"
        )
    # Apply the EXACT origin-adoption-v1 contract to the final output.
    parsed = _parse_origin_adoptions_exact(artifact.final_output_bytes, artifact.case_ids)
    if set(parsed) != set(expected_case_ids) or not all(parsed.values()):
        raise OriginResponseContractFailure(
            "provider response did not adopt all expected commitments"
        )
    returned = artifact.provider_metadata.get("model") or artifact.provider_metadata.get(
        "returned_model"
    )
    if returned is not None and returned != expected_provider_model:
        raise OriginResponseContractFailure("provider model does not match expected")
    # Live-run binding checks (fail closed if an expected live-run authority is given).
    if (
        expected_origin_manifest_sha256 is not None
        and artifact.origin_manifest_sha256 != expected_origin_manifest_sha256
    ):
        raise OriginResponseContractFailure("artifact origin-manifest SHA mismatch")
    if expected_batch_run_id is not None and artifact.batch_run_id != expected_batch_run_id:
        raise OriginResponseContractFailure("artifact batch/run ID mismatch")
    if expected_request_index is not None and artifact.request_index != expected_request_index:
        raise OriginResponseContractFailure("artifact request index mismatch")
