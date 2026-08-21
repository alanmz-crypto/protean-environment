#!/usr/bin/env python3
"""Stage 0 mechanical-defect restart preparation (ZERO model calls).

Prepares, but does NOT execute, the protocol's single permitted Stage 0
restart: a fresh 80-case set generated from a genuinely fresh permitted seed,
plus a new immutable run manifest bound to the current HEAD and the frozen
prompt/config/parse-contract hashes.

This consumes the single restart allowance as HARNESS_IMPLEMENTATION_DEFECT.
It issues NO provider call and performs NO scoring, AUC, or DeLong analysis.
It never overwrites or deletes the original failed manifest/results.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

from protean_stage0.artifacts import FrozenArtifact, FrozenCaseSet, canonical_json_bytes, sha256_bytes
from protean_stage0.defects import (
    MechanicalDefectEvidence,
    MechanicalDefectKind,
    RestartController,
)
from protean_stage0.direct_config import DIRECT_CONFIG_HASH, direct_model_configuration
from protean_stage0.generator import generate_structured_cases
from protean_stage0.manifest import ExperimentalBindings, RunManifest
from protean_stage0.parse_contract import PLAIN_DECIMAL_V1_SHA256
from protean_stage0.textualize import TemplateBank, textualize_case
from protean_stage0.validation import (
    load_evaluator_provenance,
    validate_pre_run,
    verify_truth_agreement,
)

INVALIDATED_CASE_SET_SHA = "06fe8d471b1fbbc226696ed6d80b706cc84a6040a7fb91a93814343420291556"
FROZEN_PROMPT_SHA = "ae8f093a69a7bae6818421000490a14c8a19a4a6be33069a1858bf0a9d7f6909"
PROMPT_PATH = REPO_ROOT / "stage0/candidate-scoring-prompt-v1.txt"
PROTOCOL_PATH = REPO_ROOT / "docs/PROTOCOL-prospective-control-v1.0.md"
EXECUTION_PLAN_PATH = REPO_ROOT / "docs/EXECUTION-stage0.md"
PRIMARY_PROV_PATH = REPO_ROOT / "docs/primary-evaluator-provenance.json"
REFERENCE_PROV_PATH = REPO_ROOT / "docs/reference-evaluator-provenance.json"
PRIMARY_IMPL_PATH = REPO_ROOT / "src/protean_stage0/primary_truth.py"
REFERENCE_IMPL_PATH = REPO_ROOT / "src/protean_stage0/reference_truth.py"
TEMPLATE_BANK_PATH = REPO_ROOT / "stage0/template-bank-v1.json"

RESTART_DEFECT_REASON = (
    "The original Stage-0 harness collapsed materially different failure modes "
    "into provider_api_failure and discarded provider-response/error evidence, "
    "making the failed attempt non-adjudicable. This was corrected by commits "
    "752382c... and 9d8b7b3...."
)


def current_git_head() -> str:
    out = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=REPO_ROOT, capture_output=True, text=True
    )
    return out.stdout.strip()


def main() -> int:
    parser = argparse.ArgumentParser(description="Prepare the single Stage-0 restart (zero calls).")
    parser.add_argument(
        "--seed",
        default=None,
        help="Fresh permitted seed. Defaults to protean-stage0-restart-v1:<16 hex of current HEAD>.",
    )
    parser.add_argument(
        "--out-dir",
        default=str(REPO_ROOT / "stage0/runs"),
        help="Directory for the fresh case-set and new run manifest (gitignored).",
    )
    args = parser.parse_args(sys.argv[1:])

    head = current_git_head()
    first16 = head[:16]
    seed = args.seed if args.seed else f"protean-stage0-restart-v1:{first16}"
    print(f"head={head}")
    print(f"seed={seed}")

    # --- 1. generate + textualize the fresh set from the frozen substrate ---
    generated = generate_structured_cases(seed)
    bank = TemplateBank.from_bytes(TEMPLATE_BANK_PATH.read_bytes())
    # Text seed derives from the STABLE restart seed, not the current HEAD, so
    # re-running the prep with the same seed reproduces the identical case set.
    seed_tail = seed.rsplit(":", 1)[-1]
    text_seed = f"protean-stage0-restart-text-v1:{seed_tail}"
    cases = tuple(textualize_case(item, seed=text_seed, bank=bank) for item in generated)
    frozen = FrozenCaseSet.from_cases(cases)
    frozen.verify()
    new_sha = frozen.sha256
    print(f"case_set_sha256={new_sha}")
    if new_sha == INVALIDATED_CASE_SET_SHA:
        print("ERROR: fresh case set equals the invalidated original set")
        return 1
    if new_sha == "":
        print("ERROR: empty case set hash")
        return 1
    print(f"case_count={len(frozen.cases)}")

    # --- 2. evaluator agreement on all 80 ---
    primary = load_evaluator_provenance(PRIMARY_PROV_PATH, PRIMARY_IMPL_PATH)
    reference = load_evaluator_provenance(REFERENCE_PROV_PATH, REFERENCE_IMPL_PATH)
    agreement = verify_truth_agreement(
        generated, primary_provenance=primary, reference_provenance=reference
    )
    print(f"truth_agreement_cases={agreement.case_count}")
    print(f"truth_agreement_sha256={agreement.agreement_sha256}")

    # --- 3. no lexical truth-shortcut regression (no literal true/false) ---
    for case in frozen.cases:
        visible = case.model_visible_payload()
        joined = " ".join(visible.values()).lower()
        if " true " in joined or " false " in joined or " true." in joined or " false." in joined:
            print(f"ERROR: literal boolean token in case {case.case_id}")
            return 1
    print("no_literal_boolean_tokens=yes")

    # --- 4. bind frozen artifacts (prompt must remain unchanged) ---
    prompt_bytes = PROMPT_PATH.read_bytes()
    if sha256_bytes(prompt_bytes) != FROZEN_PROMPT_SHA:
        print("ERROR: frozen scoring prompt hash changed")
        return 1
    prompt = FrozenArtifact.from_bytes("scoring-prompt", prompt_bytes)
    protocol = FrozenArtifact.from_bytes("protocol", PROTOCOL_PATH.read_bytes())
    execution_plan = FrozenArtifact.from_bytes("execution-plan", EXECUTION_PLAN_PATH.read_bytes())
    model = direct_model_configuration()
    if model.sha256 != DIRECT_CONFIG_HASH:
        print("ERROR: Luna model configuration hash mismatch")
        return 1
    bindings = ExperimentalBindings(prompt=prompt, model_configuration=model)

    # --- 5. consume the single restart allowance as HARNESS_IMPLEMENTATION_DEFECT ---
    evidence = MechanicalDefectEvidence(
        kind=MechanicalDefectKind.HARNESS_IMPLEMENTATION_DEFECT,
        description=RESTART_DEFECT_REASON,
        expected_fingerprint=INVALIDATED_CASE_SET_SHA,
        observed_fingerprint=new_sha,
    )
    controller = RestartController()
    controller.authorize_restart(
        evidence,
        invalidated_case_set_hash=INVALIDATED_CASE_SET_SHA,
        fresh_case_set_hash=new_sha,
    )
    print(f"restarts_used={controller.restarts_used}")

    # --- 6. build + validate the new immutable run manifest ---
    ts = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    run_id = f"stage0-restart-{head[:12]}-{ts}"
    manifest = RunManifest.create(
        protocol=protocol,
        execution_plan=execution_plan,
        case_set=frozen,
        bindings=bindings,
        parse_contract_sha256=PLAIN_DECIMAL_V1_SHA256,
        primary_evaluator=primary,
        reference_evaluator=reference,
        harness_revision=head,
        timestamp=datetime.now(UTC).isoformat(),
        run_id=run_id,
    )
    validated = validate_pre_run(
        manifest=manifest,
        case_set=frozen,
        protocol=protocol,
        execution_plan=execution_plan,
        bindings=bindings,
        agreement=agreement,
    )
    validated.assert_validated()
    print("preflight=OK (zero model calls)")

    # --- 7. write immutable artifacts (never overwrite originals) ---
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    case_set_input = frozen.artifact_bytes
    cs_path = out_dir / f"restart-case-set-{new_sha}.json"
    if not cs_path.exists():
        cs_path.write_bytes(case_set_input)
    manifest_path = out_dir / f"run-manifest-{run_id}.json"
    if manifest_path.exists():
        print(f"ERROR: refusing to overwrite existing manifest: {manifest_path}")
        return 1
    manifest_path.write_bytes(manifest.to_exact_bytes())
    print(f"case_set_artifact={cs_path}")
    print(f"case_set_artifact_sha256={sha256_bytes(case_set_input)}")
    print(f"manifest_path={manifest_path}")
    print(f"manifest_sha256={manifest.sha256}")
    print(f"scoring_prompt_sha256={prompt.sha256}")
    print(f"luna_config_sha256={model.sha256}")
    print(f"protocol_sha256={protocol.sha256}")
    print(f"execution_plan_sha256={execution_plan.sha256}")
    print(f"parse_contract_sha256={PLAIN_DECIMAL_V1_SHA256}")
    print(f"run_id={run_id}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
