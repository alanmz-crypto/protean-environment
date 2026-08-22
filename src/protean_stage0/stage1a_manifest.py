"""Stage-1A manifest: binds every frozen authority; fails closed before any call.

Mirrors the Stage-0 RunManifest philosophy but for the Stage-1A calibration run.
A Stage-1A manifest is created ONCE and is immutable; any hash/field mismatch
must stop before any provider call. It is not a Stage-0 manifest and does not
reuse the Stage-0 case set.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any

from .artifacts import FrozenArtifact, FrozenCaseSet, canonical_json_bytes, sha256_bytes
from .direct_config import DIRECT_CONFIG_HASH
from .manifest import ModelConfiguration
from .schema import EvaluatorProvenance
from .stage1a_config import (
    CROSS_SESSION_REP_VERSION,
    STAGE1A_NEGATIVE,
    STAGE1A_PER_CLASS_PER_STRUCTURE,
    STAGE1A_PER_STRUCTURE,
    STAGE1A_POSITIVE,
    STAGE1A_TOTAL,
)
from .stage1a_origin import (
    ORIGIN_PROMPT_SHA256,
    ORIGIN_RESPONSE_CONTRACT_SHA256,
    ORIGIN_RESPONSE_CONTRACT_VERSION,
)

# Authoritative ratified real-origin amendment artifact (not the DRAFT).
RATIFIED_REAL_ORIGIN_AMENDMENT_SHA256 = (
    "404bada3218b5d9ce989d19e9b19ad96bb470cc39197e6ee9236c916e032718a"
)


@dataclass(frozen=True, slots=True)
class Stage1AManifest:
    protocol_sha256: str
    protocol_version: str
    futility_amendment_sha256: str
    futility_amendment_version: str
    real_origin_amendment_sha256: str
    real_origin_amendment_version: str
    origin_mechanism_version: str
    expected_origin_sessions: int
    origin_response_contract: str
    origin_prompt_sha256: str
    origin_response_contract_sha256: str
    origin_run_manifest_sha256: str
    origin_completed_run_sha256: str
    origin_batch_run_id: str
    case_set_sha256: str
    scoring_prompt_sha256: str
    parse_contract_sha256: str
    model_configuration_sha256: str
    model_configuration: Mapping[str, Any]
    harness_revision: str
    cross_session_rep_version: str
    total_cases: int
    positive_count: int
    negative_count: int
    per_structure: int
    per_class_per_structure: int
    primary_evaluator: EvaluatorProvenance
    reference_evaluator: EvaluatorProvenance
    timestamp: str
    run_id: str
    _seal: object = field(repr=False, compare=False, default=None)

    @classmethod
    def create(
        cls,
        *,
        protocol: FrozenArtifact,
        futility_amendment: FrozenArtifact,
        real_origin_amendment: FrozenArtifact,
        case_set: FrozenCaseSet,
        scoring_prompt: FrozenArtifact,
        parse_contract_sha256: str,
        model_configuration: ModelConfiguration,
        harness_revision: str,
        primary_evaluator: EvaluatorProvenance,
        reference_evaluator: EvaluatorProvenance,
        timestamp: str,
        run_id: str,
        origin_mechanism_version: str = "stage1a-real-origin-v1",
        origin_response_contract: str = ORIGIN_RESPONSE_CONTRACT_VERSION,
        expected_origin_sessions: int = 5,
        origin_prompt_sha256: str = ORIGIN_PROMPT_SHA256,
        origin_response_contract_sha256: str = ORIGIN_RESPONSE_CONTRACT_SHA256,
        origin_run_manifest_sha256: str = "",
        origin_completed_run_sha256: str = "",
        origin_batch_run_id: str = "",
    ) -> Stage1AManifest:
        if len(case_set.cases) != STAGE1A_TOTAL:
            raise ValueError("Stage-1A manifest requires exactly 60 cases")
        if real_origin_amendment.sha256 != RATIFIED_REAL_ORIGIN_AMENDMENT_SHA256:
            raise ValueError(
                "Stage-1A manifest must bind the RATIFIED real-origin amendment, not the DRAFT"
            )
        from .generator import GeneratedCaseSpec
        from .stage1a_cases import validate_stage1a_allocation

        validate_stage1a_allocation(
            tuple(GeneratedCaseSpec(c.structured_spec, c.truth_label) for c in case_set.cases)
        )
        return cls(
            protocol_sha256=protocol.sha256,
            protocol_version="prospective-control-v1.0",
            futility_amendment_sha256=futility_amendment.sha256,
            futility_amendment_version="stage1-futility-shared-score-v1.0.1-r1",
            real_origin_amendment_sha256=real_origin_amendment.sha256,
            real_origin_amendment_version="stage1a-real-origin-v1.0.2-r1",
            origin_mechanism_version=origin_mechanism_version,
            expected_origin_sessions=expected_origin_sessions,
            origin_response_contract=origin_response_contract,
            origin_prompt_sha256=origin_prompt_sha256,
            origin_response_contract_sha256=origin_response_contract_sha256,
            origin_run_manifest_sha256=origin_run_manifest_sha256,
            origin_completed_run_sha256=origin_completed_run_sha256,
            origin_batch_run_id=origin_batch_run_id,
            case_set_sha256=case_set.sha256,
            scoring_prompt_sha256=scoring_prompt.sha256,
            parse_contract_sha256=parse_contract_sha256,
            model_configuration_sha256=model_configuration.sha256,
            model_configuration=MappingProxyType(dict(model_configuration.canonical_record())),
            harness_revision=harness_revision,
            cross_session_rep_version=CROSS_SESSION_REP_VERSION,
            total_cases=STAGE1A_TOTAL,
            positive_count=STAGE1A_POSITIVE,
            negative_count=STAGE1A_NEGATIVE,
            per_structure=STAGE1A_PER_STRUCTURE,
            per_class_per_structure=STAGE1A_PER_CLASS_PER_STRUCTURE,
            primary_evaluator=primary_evaluator,
            reference_evaluator=reference_evaluator,
            timestamp=timestamp,
            run_id=run_id,
        )

    def canonical_record(self) -> dict[str, Any]:
        def prov(p: EvaluatorProvenance) -> dict[str, Any]:
            return {
                "authored_at": p.authored_at,
                "author": p.author,
                "evaluator_name": p.evaluator_name,
                "grammar_sha256": p.grammar_sha256,
                "grammar_version": p.grammar_version,
                "implementation_sha256": p.implementation_sha256,
                "independently_derived": p.independently_derived,
            }

        return {
            "protocol_sha256": self.protocol_sha256,
            "protocol_version": self.protocol_version,
            "futility_amendment_sha256": self.futility_amendment_sha256,
            "futility_amendment_version": self.futility_amendment_version,
            "real_origin_amendment_sha256": self.real_origin_amendment_sha256,
            "real_origin_amendment_version": self.real_origin_amendment_version,
            "origin_mechanism_version": self.origin_mechanism_version,
            "expected_origin_sessions": self.expected_origin_sessions,
            "origin_response_contract": self.origin_response_contract,
            "origin_prompt_sha256": self.origin_prompt_sha256,
            "origin_response_contract_sha256": self.origin_response_contract_sha256,
            "origin_run_manifest_sha256": self.origin_run_manifest_sha256,
            "origin_completed_run_sha256": self.origin_completed_run_sha256,
            "origin_batch_run_id": self.origin_batch_run_id,
            "case_set_sha256": self.case_set_sha256,
            "scoring_prompt_sha256": self.scoring_prompt_sha256,
            "parse_contract_sha256": self.parse_contract_sha256,
            "model_configuration_sha256": self.model_configuration_sha256,
            "model_configuration": dict(self.model_configuration),
            "harness_revision": self.harness_revision,
            "cross_session_rep_version": self.cross_session_rep_version,
            "total_cases": self.total_cases,
            "positive_count": self.positive_count,
            "negative_count": self.negative_count,
            "per_structure": self.per_structure,
            "per_class_per_structure": self.per_class_per_structure,
            "primary_evaluator": prov(self.primary_evaluator),
            "reference_evaluator": prov(self.reference_evaluator),
            "timestamp": self.timestamp,
            "run_id": self.run_id,
        }

    def to_exact_bytes(self) -> bytes:
        return canonical_json_bytes(self.canonical_record())

    @classmethod
    def _reconstruct(cls, raw: bytes) -> Stage1AManifest:
        """Rebuild the manifest EXACTLY from its canonical bytes.

        Strict N3 reconstruction contract: canonical reserialization of the rebuilt
        object must reproduce the exact input bytes, and the recomputed SHA must
        match the input (self-consistent). ``validate_stage1a_manifest_seal_exact``
        enforces byte equality before any caller may use the object.
        """
        import json

        from .schema import EvaluatorProvenance

        def prov(d: Any) -> EvaluatorProvenance:
            return EvaluatorProvenance(
                evaluator_name=d["evaluator_name"],
                author=d["author"],
                authored_at=d["authored_at"],
                grammar_version=d["grammar_version"],
                grammar_sha256=d["grammar_sha256"],
                independently_derived=d["independently_derived"],
                implementation_sha256=d["implementation_sha256"],
            )

        data = json.loads(raw.decode("utf-8"))
        return cls(
            protocol_sha256=data["protocol_sha256"],
            protocol_version=data["protocol_version"],
            futility_amendment_sha256=data["futility_amendment_sha256"],
            futility_amendment_version=data["futility_amendment_version"],
            real_origin_amendment_sha256=data["real_origin_amendment_sha256"],
            real_origin_amendment_version=data["real_origin_amendment_version"],
            origin_mechanism_version=data["origin_mechanism_version"],
            expected_origin_sessions=data["expected_origin_sessions"],
            origin_response_contract=data["origin_response_contract"],
            origin_prompt_sha256=data["origin_prompt_sha256"],
            origin_response_contract_sha256=data["origin_response_contract_sha256"],
            origin_run_manifest_sha256=data["origin_run_manifest_sha256"],
            origin_completed_run_sha256=data["origin_completed_run_sha256"],
            origin_batch_run_id=data["origin_batch_run_id"],
            case_set_sha256=data["case_set_sha256"],
            scoring_prompt_sha256=data["scoring_prompt_sha256"],
            parse_contract_sha256=data["parse_contract_sha256"],
            model_configuration_sha256=data["model_configuration_sha256"],
            model_configuration=data["model_configuration"],
            harness_revision=data["harness_revision"],
            cross_session_rep_version=data["cross_session_rep_version"],
            total_cases=data["total_cases"],
            positive_count=data["positive_count"],
            negative_count=data["negative_count"],
            per_structure=data["per_structure"],
            per_class_per_structure=data["per_class_per_structure"],
            primary_evaluator=prov(data["primary_evaluator"]),
            reference_evaluator=prov(data["reference_evaluator"]),
            timestamp=data["timestamp"],
            run_id=data["run_id"],
        )

    @property
    def sha256(self) -> str:
        return sha256_bytes(self.to_exact_bytes())

    def validate_completeness(self) -> None:
        required = (
            self.protocol_sha256,
            self.protocol_version,
            self.futility_amendment_sha256,
            self.futility_amendment_version,
            self.real_origin_amendment_sha256,
            self.real_origin_amendment_version,
            self.origin_mechanism_version,
            self.origin_response_contract,
            self.origin_prompt_sha256,
            self.origin_response_contract_sha256,
            self.origin_run_manifest_sha256,
            self.origin_completed_run_sha256,
            self.origin_batch_run_id,
            self.case_set_sha256,
            self.scoring_prompt_sha256,
            self.parse_contract_sha256,
            self.model_configuration_sha256,
            self.harness_revision,
            self.cross_session_rep_version,
            self.run_id,
        )
        if not all(required):
            raise ValueError("Stage-1A manifest contains an empty required field")
        if self.expected_origin_sessions != 5:
            raise ValueError("Stage-1A manifest must require exactly 5 origin sessions")
        if (self.total_cases, self.positive_count, self.negative_count) != (60, 30, 30):
            raise ValueError("Stage-1A manifest must record 60/30/30")
        if (self.per_structure, self.per_class_per_structure) != (12, 6):
            raise ValueError("Stage-1A manifest must record 12-per-structure, 6/6 per structure")


def validate_stage1a_manifest_seal(
    manifest: Stage1AManifest,
    *,
    actual_harness_revision: str,
    protocol: FrozenArtifact,
    futility_amendment: FrozenArtifact,
    real_origin_amendment: FrozenArtifact,
    case_set: FrozenCaseSet,
    scoring_prompt: FrozenArtifact,
    parse_contract_sha256: str,
    model_configuration: ModelConfiguration,
    cross_session_rep_version: str = CROSS_SESSION_REP_VERSION,
    expected_origin_sessions: int = 5,
    origin_mechanism_version: str = "stage1a-real-origin-v1",
    origin_response_contract_version: str = ORIGIN_RESPONSE_CONTRACT_VERSION,
    expected_origin_run_manifest_sha256: str = "",
    expected_origin_completed_run_sha256: str = "",
    expected_origin_batch_run_id: str = "",
) -> None:
    """Fail closed (raise) before any provider call on any Stage-1A mismatch.

    ``actual_harness_revision`` is the executing harness revision (e.g. current
    git HEAD). It must equal ``manifest.harness_revision`` exactly; a stale or
    substituted manifest revision stops before any model client is constructed.
    """
    checks = {
        "protocol": (manifest.protocol_sha256, protocol.sha256),
        "futility amendment": (manifest.futility_amendment_sha256, futility_amendment.sha256),
        "real-origin amendment": (
            manifest.real_origin_amendment_sha256,
            real_origin_amendment.sha256,
        ),
        "case set": (manifest.case_set_sha256, case_set.sha256),
        "scoring prompt": (manifest.scoring_prompt_sha256, scoring_prompt.sha256),
        "parse contract": (manifest.parse_contract_sha256, parse_contract_sha256),
        "origin prompt": (manifest.origin_prompt_sha256, ORIGIN_PROMPT_SHA256),
        "origin response contract": (
            manifest.origin_response_contract_sha256,
            ORIGIN_RESPONSE_CONTRACT_SHA256,
        ),
    }
    for name, (recorded, actual) in checks.items():
        if recorded != actual:
            raise ValueError(f"Stage-1A seal mismatch: {name}")
    if actual_harness_revision != manifest.harness_revision:
        raise ValueError("Stage-1A seal mismatch: harness revision")
    if manifest.cross_session_rep_version != cross_session_rep_version:
        raise ValueError("Stage-1A seal mismatch: cross-session representation version")
    if manifest.expected_origin_sessions != expected_origin_sessions:
        raise ValueError("Stage-1A seal mismatch: expected origin sessions")
    if manifest.origin_mechanism_version != origin_mechanism_version:
        raise ValueError("Stage-1A seal mismatch: origin mechanism version")
    if manifest.origin_response_contract != origin_response_contract_version:
        raise ValueError("Stage-1A seal mismatch: origin response-contract version")
    # Authoritative Luna configuration must be the frozen direct Responses config.
    if model_configuration.sha256 != DIRECT_CONFIG_HASH:
        raise ValueError("Stage-1A seal mismatch: model configuration != authoritative Luna config")
    # The origin outer-authority bindings are MANDATORY for a calibration-authorizing
    # manifest and must equal the externally supplied sealed values.
    for name, recorded, expected in (
        (
            "origin run manifest SHA",
            manifest.origin_run_manifest_sha256,
            expected_origin_run_manifest_sha256,
        ),
        (
            "origin completed-run SHA",
            manifest.origin_completed_run_sha256,
            expected_origin_completed_run_sha256,
        ),
        ("origin batch/run ID", manifest.origin_batch_run_id, expected_origin_batch_run_id),
    ):
        if not expected:
            raise ValueError(f"Stage-1A seal requires an expected {name} for calibration")
        if recorded != expected:
            raise ValueError(f"Stage-1A seal mismatch: {name}")
    manifest.validate_completeness()


def validate_stage1a_manifest_seal_exact(
    manifest: Stage1AManifest,
    *,
    actual_harness_revision: str,
    protocol: FrozenArtifact,
    futility_amendment: FrozenArtifact,
    real_origin_amendment: FrozenArtifact,
    case_set: FrozenCaseSet,
    scoring_prompt: FrozenArtifact,
    parse_contract_sha256: str,
    model_configuration: ModelConfiguration,
    expected_origin_run_manifest_sha256: str,
    expected_origin_completed_run_sha256: str,
    expected_origin_batch_run_id: str,
) -> Stage1AManifest:
    """Canonical production calibration seal (closes N3).

    Validates ``manifest`` against the freshly loaded authorities and the expected
    origin-chain bindings, then verifies exact-byte canonical reconstruction, then
    returns the SAME manifest object that was passed through validation. There is no
    separate calibration authority and no way to validate manifest A while the caller
    consumes manifest B: the live wrapper must pass the object returned here into
    ``Stage1APreparedRun.seal``, which mechanically forwards it as the authority.
    """
    validate_stage1a_manifest_seal(
        manifest,
        actual_harness_revision=actual_harness_revision,
        protocol=protocol,
        futility_amendment=futility_amendment,
        real_origin_amendment=real_origin_amendment,
        case_set=case_set,
        scoring_prompt=scoring_prompt,
        parse_contract_sha256=parse_contract_sha256,
        model_configuration=model_configuration,
        expected_origin_run_manifest_sha256=expected_origin_run_manifest_sha256,
        expected_origin_completed_run_sha256=expected_origin_completed_run_sha256,
        expected_origin_batch_run_id=expected_origin_batch_run_id,
    )
    # Exact-byte reconstruction contract: reserializing the manifest must reproduce
    # the exact canonical bytes, and the recomputed SHA must self-consist.
    rebuilt_raw = manifest.to_exact_bytes()
    rebuilt = Stage1AManifest._reconstruct(rebuilt_raw)
    if rebuilt.to_exact_bytes() != rebuilt_raw:
        raise ValueError("Stage-1A manifest exact-byte reconstruction failed")
    return manifest
