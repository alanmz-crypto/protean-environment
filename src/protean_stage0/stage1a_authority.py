"""Runtime loading of frozen Stage-1A authority files (B3).

Establishes execution authority from the ACTUAL committed frozen artifact bytes
loaded at runtime into FrozenArtifact objects, mirroring the proven Stage-0 driver
pattern. Hard-coded expected SHAs are only an additional guard; they never replace
loading and hashing the real committed authority bytes.

The Stage-1A case set itself is not a committed file: it is deterministically
regenerated from the frozen template bank + the frozen Stage-1A seed, then its
bytes are hashed. This is the faithful in-memory analogue of loading the case-set
artifact bytes.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .artifacts import FrozenArtifact, FrozenCaseSet
from .stage1a_cases import build_stage1a_cases, freeze_stage1a_case_set
from .stage1a_config import STAGE1A_SEED
from .textualize import TemplateBank

REPO_ROOT = Path(__file__).resolve().parents[2]

# Frozen / expected authority SHAs (hard-coded guards only; loading hashes real bytes).
EXPECTED_PROTOCOL_SHA = "dbe9d0a292ade61b980fa26045ed98c22c139f50e51836341687c2499c5481d4"
EXPECTED_FUTILITY_AMENDMENT_SHA = "1a46b2cf9aeddd379fbca46e1ab9aaa660209c752885897b30d81589721cdf1f"
EXPECTED_REAL_ORIGIN_AMENDMENT_SHA = (
    "404bada3218b5d9ce989d19e9b19ad96bb470cc39197e6ee9236c916e032718a"
)
EXPECTED_STAGE1A_CASE_SET_SHA = "6851bf6f49f080ca3ede7938e207b835e5b3ac7cf531e3a460fb74393adecf41"
EXPECTED_TEMPLATE_BANK_SHA = "295fe92fe12ba14470166d6b160492fb1564d29b06dc46500f8b2cbfdf73c758"
EXPECTED_SCORING_PROMPT_SHA = "ae8f093a69a7bae6818421000490a14c8a19a4a6be33069a1858bf0a9d7f6909"

PROTOCOL_PATH = REPO_ROOT / "docs/PROTOCOL-prospective-control-v1.0.md"
FUTILITY_AMENDMENT_PATH = (
    REPO_ROOT / "docs/RATIFIED-AMENDMENT-stage1-futility-shared-score-v1.0.1-r1.md"
)
REAL_ORIGIN_AMENDMENT_PATH = REPO_ROOT / "docs/RATIFIED-AMENDMENT-stage1a-real-origin-v1.0.2-r1.md"
TEMPLATE_BANK_PATH = REPO_ROOT / "stage0/template-bank-v1.json"
SCORING_PROMPT_PATH = REPO_ROOT / "stage0/candidate-scoring-prompt-v1.txt"


@dataclass(frozen=True, slots=True)
class LoadedStage1AAuthority:
    protocol: FrozenArtifact
    futility_amendment: FrozenArtifact
    real_origin_amendment: FrozenArtifact
    template_bank: FrozenArtifact
    scoring_prompt: FrozenArtifact
    case_set: FrozenCaseSet
    case_set_sha256: str


def load_authority_artifacts(
    *,
    verify_expected: bool = True,
) -> LoadedStage1AAuthority:
    """Load the ACTUAL committed authority bytes at runtime; hash them; guard.

    ``verify_expected`` additionally asserts each loaded artifact's real SHA equals
    its frozen expected value (an extra guard, not a substitute for loading).
    """
    protocol = FrozenArtifact.from_bytes("protocol", PROTOCOL_PATH.read_bytes())
    futility = FrozenArtifact.from_bytes("futility-amendment", FUTILITY_AMENDMENT_PATH.read_bytes())
    real_origin = FrozenArtifact.from_bytes(
        "real-origin-amendment", REAL_ORIGIN_AMENDMENT_PATH.read_bytes()
    )
    bank_bytes = TEMPLATE_BANK_PATH.read_bytes()
    template_bank = FrozenArtifact.from_bytes("template-bank", bank_bytes)
    scoring_prompt = FrozenArtifact.from_bytes("scoring-prompt", SCORING_PROMPT_PATH.read_bytes())

    if verify_expected:
        expected = {
            "protocol": (protocol.sha256, EXPECTED_PROTOCOL_SHA),
            "futility amendment": (
                futility.sha256,
                EXPECTED_FUTILITY_AMENDMENT_SHA,
            ),
            "real-origin amendment": (
                real_origin.sha256,
                EXPECTED_REAL_ORIGIN_AMENDMENT_SHA,
            ),
            "template bank": (template_bank.sha256, EXPECTED_TEMPLATE_BANK_SHA),
            "scoring prompt": (scoring_prompt.sha256, EXPECTED_SCORING_PROMPT_SHA),
        }
        for name, (actual, expected_sha) in expected.items():
            if actual != expected_sha:
                raise ValueError(f"loaded authority {name} does not match frozen SHA")

    # Regenerate the frozen Stage-1A case set from the loaded template bank + seed,
    # then verify its SHA (the in-memory analogue of loading the case-set bytes).
    bank = TemplateBank.from_bytes(bank_bytes)
    cases = build_stage1a_cases(seed=STAGE1A_SEED, template_bank=bank)
    case_set = freeze_stage1a_case_set(cases)
    if verify_expected and case_set.sha256 != EXPECTED_STAGE1A_CASE_SET_SHA:
        raise ValueError("loaded Stage-1A case set does not match frozen SHA")
    return LoadedStage1AAuthority(
        protocol=protocol,
        futility_amendment=futility,
        real_origin_amendment=real_origin,
        template_bank=template_bank,
        scoring_prompt=scoring_prompt,
        case_set=case_set,
        case_set_sha256=case_set.sha256,
    )
