"""Frozen Stage-1A configuration: allocation, threshold grid, futility, sessions.

Stage 1A is the calibration/history stage. This module is the single frozen
authority for its numeric constants (mirroring how direct_config.py is the
Luna-config authority). It contains no live-call code; the experimental 60 calls
are NOT executed by any component of this package's default behavior.
"""

from __future__ import annotations

import itertools

# Frozen Stage-1A allocation (Protocol v1.0 + B).
STAGE1A_TOTAL = 60
STAGE1A_PER_STRUCTURE = 12
STAGE1A_PER_CLASS_PER_STRUCTURE = 6
STAGE1A_POSITIVE = 30
STAGE1A_NEGATIVE = 30
SEED_NAMESPACE = "protean-stage1a-v1"
CROSS_SESSION_REP_VERSION = "stage1a-session-v1"
# Frozen Stage-1A generation seed (explicitly labeled Stage-1A calibration, distinct
# from the Stage-0 seeds; deterministic).
STAGE1A_SEED = "protean-stage1a-calibration-v1:a154040c0d3a7d5a"

# Frozen 17-threshold grid (Protocol v1.0).
THRESHOLD_GRID: tuple[float, ...] = tuple(round(t / 100, 2) for t in range(10, 95, 5))

# B fixed threshold (Protocol v1.0).
B_THRESHOLD = 0.50

# Futility rule (ratified amendment): if C selects exactly 0.50 -> futility stop.
FUTILITY_THRESHOLD = 0.50


def validate_grid() -> None:
    if len(THRESHOLD_GRID) != 17:
        raise ValueError("grid must have exactly 17 thresholds")
    if not (THRESHOLD_GRID[0] == 0.10 and THRESHOLD_GRID[-1] == 0.90):
        raise ValueError("grid endpoints must be 0.10 and 0.90")
    steps = {round(b - a, 2) for a, b in itertools.pairwise(THRESHOLD_GRID)}
    if steps != {0.05}:
        raise ValueError("grid step must be 0.05")


def validate_allocation(total: int, per_struct: int, per_class: int) -> None:
    if total != STAGE1A_TOTAL:
        raise ValueError("Stage-1A total allocation mismatch")
    if per_struct != STAGE1A_PER_STRUCTURE:
        raise ValueError("Stage-1A per-structure allocation mismatch")
    if per_class != STAGE1A_PER_CLASS_PER_STRUCTURE:
        raise ValueError("Stage-1A per-class-per-structure allocation mismatch")


validate_grid()
