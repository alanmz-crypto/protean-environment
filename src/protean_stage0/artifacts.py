"""Exact-byte hashing and frozen artifact helpers."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

from .schema import Stage0Case


def sha256_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


@dataclass(frozen=True, slots=True)
class FrozenArtifact:
    name: str
    content: bytes
    sha256: str

    @classmethod
    def from_bytes(cls, name: str, content: bytes) -> FrozenArtifact:
        if not content:
            raise ValueError(f"{name} must not be empty")
        return cls(name=name, content=content, sha256=sha256_bytes(content))

    def verify(self) -> None:
        if sha256_bytes(self.content) != self.sha256:
            raise ValueError(f"{self.name} hash mismatch")


@dataclass(frozen=True, slots=True)
class FrozenCaseSet:
    """Frozen canonical case bytes plus runtime cases stamped with their hash.

    The exact artifact bytes omit the redundant per-record ``case_set_hash``.
    The SHA-256 of those exact bytes is injected into each runtime case as
    metadata and recorded in the run manifest.
    """

    cases: tuple[Stage0Case, ...]
    artifact_bytes: bytes
    sha256: str

    @classmethod
    def from_cases(cls, cases: Iterable[Stage0Case]) -> FrozenCaseSet:
        source = tuple(cases)
        if not source:
            raise ValueError("case set must not be empty")
        records = []
        for case in source:
            record = case.canonical_record()
            record.pop("case_set_hash")
            records.append(record)
        artifact_bytes = canonical_json_bytes({"cases": records})
        digest = sha256_bytes(artifact_bytes)
        stamped = tuple(case.with_case_set_hash(digest) for case in source)
        return cls(stamped, artifact_bytes, digest)

    def verify(self) -> None:
        records = []
        for case in self.cases:
            record = case.canonical_record()
            record.pop("case_set_hash")
            records.append(record)
        expected_bytes = canonical_json_bytes({"cases": records})
        if expected_bytes != self.artifact_bytes:
            raise ValueError("case-set objects do not match frozen artifact bytes")
        if sha256_bytes(self.artifact_bytes) != self.sha256:
            raise ValueError("case-set artifact hash mismatch")
        if any(case.case_set_hash != self.sha256 for case in self.cases):
            raise ValueError("per-case case_set_hash mismatch")
