"""Frozen Stage 0 familiar trigger grammar.

This module is specification only. It deliberately contains no executable truth
evaluator so the primary and reference evaluators can be independently derived.
"""

from __future__ import annotations

import hashlib
from enum import StrEnum


class StructureId(StrEnum):
    P = "P"
    P_AND_Q = "P AND Q"
    P_AND_NOT_Q = "P AND NOT Q"
    T2_P = "T2(P)"
    ACTIVE_AND_P = "ACTIVE AND P"


FROZEN_STRUCTURES: tuple[StructureId, ...] = tuple(StructureId)
GRAMMAR_VERSION = "prospective-control-v1.0/stage0-familiar-v1"

# Canonical authority text shared by both evaluator authors. It is declarative,
# contains no executable implementation, and is hashed for provenance.
GRAMMAR_SPECIFICATION = """\
P: true exactly when P is true in the current observation.
P AND Q: true exactly when P and Q are both true in the current observation.
P AND NOT Q: true exactly when P is true and Q is false in the current observation.
T2(P): true exactly when P is true in both of two successive observations.
ACTIVE AND P: true exactly when lifecycle state is ACTIVE and P is true now.
"""
GRAMMAR_SPECIFICATION_BYTES = GRAMMAR_SPECIFICATION.encode("utf-8")
GRAMMAR_SHA256 = hashlib.sha256(GRAMMAR_SPECIFICATION_BYTES).hexdigest()
