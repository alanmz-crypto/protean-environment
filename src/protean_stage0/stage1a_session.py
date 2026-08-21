"""Minimal cross-session representation for Stage 1A.

Stage-1A must reflect a genuine session boundary: a prospective commitment
originates in an earlier model session, and a later applicability judgment occurs
in a fresh context. Only authorized persisted state crosses the boundary; the
original conversation is never silently carried forward.

This is a MINIMAL experimental representation, deliberately not a general Protean
persistence architecture. It models one persisted record and the one fresh-context
judgment derived from it.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any

from .stage1a_config import CROSS_SESSION_REP_VERSION

# The only persisted fields authorized to cross the session boundary. This is the
# Stage-1A analogue of the model-visible payload (no conversation, no internal state).
_AUTHORIZED_PERSISTED_FIELDS = frozenset(
    {"commitment", "trigger_condition", "prior_state", "observed_event", "lifecycle_state"}
)
_FORBIDDEN_PERSISTED_FIELDS = frozenset(
    {"conversation", "transcript", "history", "session_log", "prompt", "raw_context"}
)


@dataclass(frozen=True, slots=True)
class CrossSessionRepresentation:
    """The authorized persisted state for one case, plus its session identity.

    ``judgment_context`` is the EXACT text that crosses into the fresh later
    session and is what a scoring client would place into the model-visible
    payload. It contains only the authorized persisted fields. The original
    earlier-session conversation is never part of it.
    """

    session_id: str
    persisted_state: Mapping[str, str]
    version: str = CROSS_SESSION_REP_VERSION

    def __post_init__(self) -> None:
        if not self.session_id:
            raise ValueError("session_id must be non-empty")
        keys = set(self.persisted_state)
        if not keys <= _AUTHORIZED_PERSISTED_FIELDS:
            raise ValueError(
                f"unauthorized persisted fields: {keys - _AUTHORIZED_PERSISTED_FIELDS}"
            )
        bad = keys & _FORBIDDEN_PERSISTED_FIELDS
        if bad:
            raise ValueError(f"conversation-fields must never be persisted: {bad}")
        missing = _AUTHORIZED_PERSISTED_FIELDS - keys
        if missing:
            raise ValueError(f"missing required persisted fields: {missing}")

    @property
    def judgment_context(self) -> Mapping[str, str]:
        """Only the authorized persisted fields, immutable, for the fresh context."""
        return MappingProxyType(self.persisted_state)

    def canonical_record(self) -> dict[str, Any]:
        return {
            "persisted_state": dict(self.persisted_state),
            "session_id": self.session_id,
            "version": self.version,
        }
