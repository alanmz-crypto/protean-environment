"""Frozen machine-response contract for Stage 0 scores."""

from __future__ import annotations

import re

from .artifacts import sha256_bytes

PLAIN_DECIMAL_V1_SPECIFICATION = b"ascii plain decimal: (0.[0-9]{2}|1.00), optional single LF"
PLAIN_DECIMAL_V1_SHA256 = sha256_bytes(PLAIN_DECIMAL_V1_SPECIFICATION)
_PLAIN_DECIMAL_V1 = re.compile(rb"(?:0\.[0-9]{2}|1\.00)\n?\Z")


def parse_plain_decimal_v1(raw_response: bytes) -> float | None:
    """Parse without stripping, coercion, extraction, or substitution."""

    if _PLAIN_DECIMAL_V1.fullmatch(raw_response) is None:
        return None
    value = float(raw_response.removesuffix(b"\n").decode("ascii"))
    return value if 0.0 <= value <= 1.0 else None
