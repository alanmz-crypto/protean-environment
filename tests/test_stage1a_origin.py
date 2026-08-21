"""Hermetic Stage-1A real-origin tests (no provider calls)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from protean_stage0.artifacts import sha256_bytes
from protean_stage0.grammar import FROZEN_STRUCTURES
from protean_stage0.stage1a_cases import build_stage1a_cases
from protean_stage0.stage1a_driver import (
    require_real_origin_coverage,
)
from protean_stage0.stage1a_origin import (
    OriginResponseContractFailure,
    OriginSessionArtifact,
    _parse_adoptions,
    build_origin_request_bytes,
)
from protean_stage0.textualize import TemplateBank

REPO = Path(__file__).resolve().parents[1]


def _cases() -> tuple[Any, ...]:
    bank = TemplateBank.from_bytes((REPO / "stage0/template-bank-v1.json").read_bytes())
    return build_stage1a_cases(template_bank=bank)


def _group_by_structure(cases: tuple[Any, ...]) -> dict[str, list[Any]]:
    out: dict[str, list[Any]] = {s.value: [] for s in FROZEN_STRUCTURES}
    for c in cases:
        out[c.generated.spec.structure_id.value].append(c)
    return out


def _origin_artifact(
    structure: str,
    cases: list[Any],
    *,
    origin_run_id: str,
    adopt_all: bool = True,
    extra: dict[str, Any] | None = None,
) -> OriginSessionArtifact:
    """Build a valid OriginSessionArtifact from a structure's 12 cases."""
    commitment_bytes = b"".join(c.textualized.commitment.encode() + b"\n" for c in cases)
    case_ids = tuple(c.generated.spec.case_id for c in cases)
    adoption = {cid: adopt_all for cid in case_ids}
    if extra:
        adoption.update(extra)
    return OriginSessionArtifact(
        origin_run_id=origin_run_id,
        structure=_sid(structure),
        case_ids=case_ids,
        commitment_bytes=commitment_bytes,
        commitment_sha256=sha256_bytes(commitment_bytes),
        model_configuration_sha256="0" * 64,
        request_sha256="0" * 64,
        provider_response_sha256="0" * 64,
        adoption=adoption,
        timestamp="2026-08-21T00:00:00Z",
        provider_metadata={"ok": True},
    )


def _sid(value: str) -> Any:
    from protean_stage0.grammar import StructureId

    return StructureId(value)


def _all_origins(
    cases: tuple[Any, ...], run_base: str = "origin-"
) -> tuple[OriginSessionArtifact, ...]:
    grouped = _group_by_structure(cases)
    artifacts = []
    for structure in FROZEN_STRUCTURES:
        artifacts.append(
            _origin_artifact(
                structure.value, grouped[structure.value], origin_run_id=run_base + structure.value
            )
        )
    return tuple(artifacts)


def test_exactly_five_groups_and_12_each_covering_60() -> None:
    cases = _cases()
    grouped = _group_by_structure(cases)
    assert len(grouped) == 5
    for structure in FROZEN_STRUCTURES:
        assert len(grouped[structure.value]) == 12
    ids = [c.generated.spec.case_id for c in cases]
    assert len(ids) == 60
    assert len(set(ids)) == 60  # exactly once each


def test_origin_payload_has_no_truth_or_future_state() -> None:
    cases = _cases()
    grouped = _group_by_structure(cases)
    allowed = {
        "commitment",
        "trigger_condition",
        "prior_state",
        "observed_event",
        "lifecycle_state",
    }
    for c in grouped["P"]:
        persisted = c.cross_session.judgment_context
        assert "truth_label" not in persisted
        assert "calibration" not in persisted and "selected_threshold" not in persisted
        assert "conversation" not in persisted and "raw_response" not in persisted
        assert set(persisted) <= allowed  # only the authorized persisted fields
    # Origin request bytes present ONLY the commitment, not future observed state.
    for c in grouped["P"]:
        req = build_origin_request_bytes(
            b"SCORE:{prompt}", [dict(c.cross_session.judgment_context)]
        )
        assert b"observed_event" not in req
        assert b"truth_label" not in req
        assert b"truth" not in req
        assert c.textualized.commitment.encode() in req


def test_commitment_bytes_match_frozen_stage1a() -> None:
    cases = _cases()
    grouped = _group_by_structure(cases)
    c = grouped["P"][0]
    # The artifact commitment is exactly the frozen commitment wording (unchanged).
    art = _origin_artifact("P", grouped["P"], origin_run_id="o-P")
    assert c.textualized.commitment in art.commitment_bytes.decode()


def test_malformed_origin_response_fails() -> None:
    cids = tuple(f"S1A-{i:02d}" for i in range(1, 13))
    with pytest.raises(OriginResponseContractFailure):
        _parse_adoptions(b"not a valid response", cids)


def test_partial_adoption_fails_in_artifact() -> None:
    cases = _cases()
    grouped = _group_by_structure(cases)
    with pytest.raises(ValueError, match="adoption must be true"):
        _origin_artifact("P", grouped["P"], origin_run_id="bad", adopt_all=False)


def test_parse_adoptions_missing_case_fails() -> None:
    cids = tuple(f"S1A-{i:02d}" for i in range(1, 13))
    with pytest.raises(OriginResponseContractFailure, match="coverage"):
        _parse_adoptions(json.dumps({cid: True for cid in cids[:11]}).encode(), cids)


def test_parse_adoptions_adopt_lines_valid() -> None:
    cids = tuple(f"S1A-{i:02d}" for i in range(1, 13))
    raw = b"\n".join(b"ADOPT " + cid.encode() for cid in cids)
    adoption = _parse_adoptions(raw, cids)
    assert set(adoption) == set(cids) and all(adoption.values())


def test_parse_adoptions_duplicate_line_fails() -> None:
    cids = tuple(f"S1A-{i:02d}" for i in range(1, 13))
    raw = b"\n".join(b"ADOPT " + cid.encode() for cid in cids[:-1]) + b"\nADOPT S1A-01"
    with pytest.raises(OriginResponseContractFailure):
        _parse_adoptions(raw, cids)


def test_missing_one_origin_group_fails() -> None:
    cases = _cases()
    all_ids = frozenset(c.generated.spec.case_id for c in cases)
    artifacts = list(_all_origins(cases))[:4]  # only 4 of 5
    with pytest.raises(ValueError, match="exactly 5 origin sessions"):
        require_real_origin_coverage(tuple(artifacts), all_ids)


def test_duplicate_case_origin_fails() -> None:
    cases = _cases()
    all_ids = frozenset(c.generated.spec.case_id for c in cases)
    grouped = _group_by_structure(cases)
    # Exactly 5 artifacts but the "P AND Q" artifact wrongly reuses P's 12 case IDs,
    # causing duplicate origin coverage for those cases.
    artifacts = [
        _origin_artifact("P", grouped["P"], origin_run_id="o-P"),
        _origin_artifact("P AND Q", grouped["P"], origin_run_id="o-PQ-dup"),  # overlap on P
        _origin_artifact("P AND NOT Q", grouped["P AND NOT Q"], origin_run_id="o-PN"),
        _origin_artifact("T2(P)", grouped["T2(P)"], origin_run_id="o-T2"),
        _origin_artifact("ACTIVE AND P", grouped["ACTIVE AND P"], origin_run_id="o-A"),
    ]
    with pytest.raises(ValueError, match="duplicate origin coverage"):
        require_real_origin_coverage(tuple(artifacts), all_ids)


def test_5_of_5_unlock_calibration_preflight() -> None:
    cases = _cases()
    artifacts = _all_origins(cases)
    require_real_origin_coverage(  # must not raise
        artifacts, frozenset(c.generated.spec.case_id for c in cases)
    )


def test_fewer_than_5_never_construct_scoring_client() -> None:
    from protean_stage0.stage1a_driver import Stage1APreparedRun

    cases = _cases()
    artifacts = _all_origins(cases)[:4]
    constructed: list[str] = []

    def factory() -> Any:
        constructed.append("client")
        raise AssertionError("must not construct client")

    prepared = Stage1APreparedRun(
        cases=cases,
        scoring_prompt=None,  # type: ignore[arg-type]
        model_configuration=None,  # type: ignore[arg-type]
        seal=lambda: None,
        client_factory=factory,
        origin_artifacts=artifacts,
    )
    with pytest.raises(ValueError):
        prepared.run()
    assert constructed == []


def test_scoring_context_only_authorized_persisted_case_record() -> None:
    cases = _cases()
    c = cases[0]
    ctx = dict(c.cross_session.judgment_context)
    allowed = {
        "commitment",
        "trigger_condition",
        "prior_state",
        "observed_event",
        "lifecycle_state",
    }
    assert set(ctx) <= allowed
    for bad in ("conversation", "raw_response", "origin", "truth", "calibration"):
        assert bad not in ctx


def test_no_cross_case_data_from_shared_origin_reaches_scoring() -> None:
    cases = _cases()
    grouped = _group_by_structure(cases)
    # The fresh scoring context for one case contains ONLY that case's persisted
    # record, never other cases produced in the same origin session.
    for c in grouped["P"]:
        ctx = dict(c.cross_session.judgment_context)
        other_ids = [
            x.generated.spec.case_id
            for x in grouped["P"]
            if x.generated.spec.case_id != c.generated.spec.case_id
        ]
        joined = " ".join(ctx.values()) + " " + json.dumps(ctx)
        for oid in other_ids:
            assert oid not in joined, f"cross-case leakage of {oid} into scoring context"
