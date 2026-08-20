"""Sealed Stage-0 production run driver (Prospective Control Experiment 1).

Loads ONLY the already-frozen experimental artifacts from repository bytes,
binds the authoritative direct Responses configuration, builds a real
RunManifest, and runs the full validate_pre_run preflight.

default = PREPARE mode: load + manifest + preflight, ZERO provider calls. Live
execution requires the explicit --execute-live switch AND a sealed (git-clean,
HEAD==manifest.harness_revision, artifact/mode-config/hash-matching) state; it is
NOT exercised by this authorization.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .artifacts import FrozenArtifact, FrozenCaseSet, sha256_bytes
from .direct_config import DIRECT_CONFIG_HASH, direct_model_configuration
from .direct_responses import DirectResponsesClient
from .generator import GeneratedCaseSpec
from .grammar import StructureId
from .manifest import ExperimentalBindings, RunManifest
from .parse_contract import PLAIN_DECIMAL_V1_SHA256
from .results import RawResult, freeze_raw_results
from .schema import EvaluatorProvenance, LifecycleState, Stage0Case, StructuredCaseSpec
from .validation import (
    TruthAgreementReport,
    load_evaluator_provenance,
    validate_pre_run,
    verify_truth_agreement,
)

FROZEN_CASE_SET_SHA = "06fe8d471b1fbbc226696ed6d80b706cc84a6040a7fb91a93814343420291556"
FROZEN_PROMPT_SHA = "ae8f093a69a7bae6818421000490a14c8a19a4a6be33069a1858bf0a9d7f6909"

REPO_ROOT = Path(__file__).resolve().parents[2]
CASE_SET_PATH = REPO_ROOT / "stage0/case-set-v1.jsonl-canonical.json"
SCORING_PROMPT_PATH = REPO_ROOT / "stage0/candidate-scoring-prompt-v1.txt"
PROTOCOL_PATH = REPO_ROOT / "docs/PROTOCOL-prospective-control-v1.0.md"
EXECUTION_PLAN_PATH = REPO_ROOT / "docs/EXECUTION-stage0.md"
PRIMARY_PROV_PATH = REPO_ROOT / "docs/primary-evaluator-provenance.json"
REFERENCE_PROV_PATH = REPO_ROOT / "docs/reference-evaluator-provenance.json"
PRIMARY_IMPL_PATH = REPO_ROOT / "src/protean_stage0/primary_truth.py"
REFERENCE_IMPL_PATH = REPO_ROOT / "src/protean_stage0/reference_truth.py"


def current_git_head() -> str:
    out = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=REPO_ROOT, capture_output=True, text=True
    )
    return out.stdout.strip()


def working_tree_is_clean() -> bool:
    out = subprocess.run(
        ["git", "status", "--porcelain"], cwd=REPO_ROOT, capture_output=True, text=True
    )
    return not out.stdout.strip()


def load_frozen_case_set() -> tuple[FrozenCaseSet, tuple[GeneratedCaseSpec, ...]]:
    """Reconstruct Stage0Case from the exact frozen canonical bytes; round-trip check."""
    raw = CASE_SET_PATH.read_bytes()
    if sha256_bytes(raw) != FROZEN_CASE_SET_SHA:
        raise ValueError("frozen case-set hash does not match the immutable input")
    data = json.loads(raw.decode("utf-8"))
    reconstructed: list[Stage0Case] = []
    generated_specs: list[GeneratedCaseSpec] = []
    for record in data["cases"]:
        spec_rec = record["structured_spec"]
        structure_id = StructureId(spec_rec["structure_id"])
        lifecycle_raw = spec_rec.get("lifecycle_state")
        lifecycle = LifecycleState(lifecycle_raw) if lifecycle_raw else None
        spec = StructuredCaseSpec(
            case_id=spec_rec["case_id"],
            structure_id=structure_id,
            p_now=spec_rec["p_now"],
            q_now=spec_rec.get("q_now"),
            p_previous=spec_rec.get("p_previous"),
            lifecycle_state=lifecycle,
            ordinal=spec_rec.get("ordinal", 0),
        )
        case_lifecycle = record.get("lifecycle_state")
        reconstructed.append(
            Stage0Case(
                case_id=record["case_id"],
                commitment=record["commitment"],
                trigger_condition=record["trigger_condition"],
                prior_state=record["prior_state"],
                observed_event=record["observed_event"],
                lifecycle_state=case_lifecycle,
                structured_spec=spec,
                truth_label=record["truth_label"],
                structure_id=StructureId(record["structure_id"]),
                authorship_source=record["authorship_source"],
                version_id=record["version_id"],
            )
        )
        generated_specs.append(GeneratedCaseSpec(spec=spec, truth_label=record["truth_label"]))
    frozen = FrozenCaseSet.from_cases(reconstructed)
    frozen.verify()
    if frozen.artifact_bytes != raw:
        raise ValueError("reserialization does not reproduce the frozen case-set bytes")
    if frozen.sha256 != FROZEN_CASE_SET_SHA:
        raise ValueError("reserialized case-set hash mismatch")
    return frozen, tuple(generated_specs)


@dataclass(frozen=True, slots=True)
class PreparedRun:
    manifest: RunManifest
    case_set: FrozenCaseSet
    protocol: FrozenArtifact
    execution_plan: FrozenArtifact
    bindings: ExperimentalBindings
    agreement: TruthAgreementReport
    manifest_sha256: str


def load_frozen_artifacts() -> tuple[
    FrozenCaseSet,
    tuple[GeneratedCaseSpec, ...],
    FrozenArtifact,
    FrozenArtifact,
    FrozenArtifact,
]:
    case_set, generated = load_frozen_case_set()
    prompt_bytes = SCORING_PROMPT_PATH.read_bytes()
    if sha256_bytes(prompt_bytes) != FROZEN_PROMPT_SHA:
        raise ValueError("frozen scoring prompt hash mismatch")
    prompt = FrozenArtifact.from_bytes("scoring-prompt", prompt_bytes)
    protocol = FrozenArtifact.from_bytes("protocol", PROTOCOL_PATH.read_bytes())
    execution_plan = FrozenArtifact.from_bytes("execution-plan", EXECUTION_PLAN_PATH.read_bytes())
    return case_set, generated, prompt, protocol, execution_plan


def build_run_manifest(*, harness_revision: str, run_id: str | None = None) -> PreparedRun:
    case_set, generated, prompt, protocol, execution_plan = load_frozen_artifacts()
    model_cfg = direct_model_configuration()
    if model_cfg.sha256 != DIRECT_CONFIG_HASH:
        raise ValueError("direct model configuration hash mismatch")
    bindings = ExperimentalBindings(prompt=prompt, model_configuration=model_cfg)
    primary = load_evaluator_provenance(PRIMARY_PROV_PATH, PRIMARY_IMPL_PATH)
    reference = load_evaluator_provenance(REFERENCE_PROV_PATH, REFERENCE_IMPL_PATH)
    agreement = verify_truth_agreement(
        generated,
        primary_provenance=primary,
        reference_provenance=reference,
    )
    if run_id is None:
        ts = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
        run_id = f"stage0-{harness_revision[:12]}-{ts}"
    manifest = RunManifest.create(
        protocol=protocol,
        execution_plan=execution_plan,
        case_set=case_set,
        bindings=bindings,
        parse_contract_sha256=PLAIN_DECIMAL_V1_SHA256,
        primary_evaluator=primary,
        reference_evaluator=reference,
        harness_revision=harness_revision,
        timestamp=datetime.now(UTC).isoformat(),
        run_id=run_id,
    )
    manifest.validate_completeness()
    manifest_sha256 = manifest.sha256
    return PreparedRun(
        manifest, case_set, protocol, execution_plan, bindings, agreement, manifest_sha256
    )


def write_manifest_artifact(prepared: PreparedRun, out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"run-manifest-{prepared.manifest.run_id}.json"
    if path.exists():
        raise RuntimeError(f"refusing to overwrite prepared manifest: {path}")
    path.write_bytes(prepared.manifest.to_exact_bytes())
    return path


def _eval_prov_from_dict(raw: dict[str, Any]) -> EvaluatorProvenance:
    return EvaluatorProvenance(
        evaluator_name=raw["evaluator_name"],
        author=raw["author"],
        authored_at=raw["authored_at"],
        grammar_version=raw["grammar_version"],
        grammar_sha256=raw["grammar_sha256"],
        independently_derived=raw["independently_derived"],
        implementation_sha256=raw["implementation_sha256"],
    )


def reconstruct_run_manifest_from_bytes(raw: bytes) -> RunManifest:
    """Rebuild the RunManifest EXACTLY from the prepared manifest bytes."""
    try:
        data = json.loads(raw.decode("utf-8"))
    except Exception as exc:
        raise RuntimeError(f"corrupt prepared manifest: {exc!r}") from exc
    if not isinstance(data, dict):
        raise RuntimeError("prepared manifest is not a JSON object")
    return RunManifest(
        protocol_version=data["protocol_version"],
        protocol_sha256=data["protocol_sha256"],
        execution_plan_version=data["execution_plan_version"],
        execution_plan_sha256=data["execution_plan_sha256"],
        case_set_sha256=data["case_set_sha256"],
        scoring_prompt_sha256=data["scoring_prompt_sha256"],
        parse_contract_sha256=data["parse_contract_sha256"],
        case_count=data["case_count"],
        positive_count=data["positive_count"],
        negative_count=data["negative_count"],
        model_configuration=dict(data["model_configuration"]),
        model_configuration_sha256=data["model_configuration_sha256"],
        primary_evaluator=_eval_prov_from_dict(data["primary_evaluator"]),
        reference_evaluator=_eval_prov_from_dict(data["reference_evaluator"]),
        harness_revision=data["harness_revision"],
        timestamp=data["timestamp"],
        run_id=data["run_id"],
    )


def load_prepared_manifest(path: Path) -> tuple[bytes, str, RunManifest]:
    """Read the exact prepared manifest bytes, compute SHA, reconstruct valid."""
    if not path.exists():
        raise RuntimeError(f"prepared manifest not found: {path}")
    raw = path.read_bytes()
    sha = sha256_bytes(raw)
    manifest = reconstruct_run_manifest_from_bytes(raw)
    # round-trip must be exact so the reviewed bytes == consumed bytes.
    if manifest.to_exact_bytes() != raw:
        raise RuntimeError("prepared manifest bytes do not round-trip exactly")
    if manifest.sha256 != sha:
        raise RuntimeError("prepared manifest SHA mismatch")
    manifest.validate_completeness()
    return raw, sha, manifest


def seal_reconstructed_run(manifest: RunManifest, *, head: str, clean: bool) -> None:
    """Refuse live execution unless the run is sealed to one immutable revision."""
    if not clean:
        raise RuntimeError("refusing live execution: working tree is dirty")
    if head != manifest.harness_revision:
        raise RuntimeError("refusing live execution: HEAD != manifest.harness_revision")
    case_set, generated, prompt, protocol, execution_plan = load_frozen_artifacts()
    if case_set.sha256 != manifest.case_set_sha256:
        raise RuntimeError("refusing live execution: case-set hash != manifest")
    if prompt.sha256 != manifest.scoring_prompt_sha256:
        raise RuntimeError("refusing live execution: scoring-prompt hash != manifest")
    if protocol.sha256 != manifest.protocol_sha256:
        raise RuntimeError("refusing live execution: protocol hash != manifest")
    if execution_plan.sha256 != manifest.execution_plan_sha256:
        raise RuntimeError("refusing live execution: execution-plan hash != manifest")
    if manifest.parse_contract_sha256 != PLAIN_DECIMAL_V1_SHA256:
        raise RuntimeError("refusing live execution: parse-contract hash != manifest")
    model_cfg = direct_model_configuration()
    if model_cfg.sha256 != manifest.model_configuration_sha256:
        raise RuntimeError("refusing live execution: model configuration hash != manifest")


def run_prepared_scoring(manifest: RunManifest, api_key: str) -> tuple[RawResult, ...]:
    """Live scoring path (never exercised in PREPARE mode). One decision per case."""
    from .harness import run_single_decision_loop

    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is required for live execution")
    # Rebuild frozen case set / artifacts from immutable files; their hashes must
    # match the manifest (already enforced by seal_reconstructed_run).
    case_set, generated, prompt, protocol, execution_plan = load_frozen_artifacts()
    bindings = ExperimentalBindings(prompt=prompt, model_configuration=direct_model_configuration())
    primary = load_evaluator_provenance(PRIMARY_PROV_PATH, PRIMARY_IMPL_PATH)
    reference = load_evaluator_provenance(REFERENCE_PROV_PATH, REFERENCE_IMPL_PATH)
    agreement = verify_truth_agreement(
        generated, primary_provenance=primary, reference_provenance=reference
    )
    validated = validate_pre_run(
        manifest=manifest,
        case_set=case_set,
        protocol=protocol,
        execution_plan=execution_plan,
        bindings=bindings,
        agreement=agreement,
    )
    client = DirectResponsesClient()
    result = run_single_decision_loop(validated_run=validated, client=client)
    return result.raw_results


def _manifest_json(manifest: RunManifest) -> dict[str, Any]:
    return {
        "run_id": manifest.run_id,
        "harness_revision": manifest.harness_revision,
        "protocol_sha256": manifest.protocol_sha256,
        "execution_plan_sha256": manifest.execution_plan_sha256,
        "case_set_sha256": manifest.case_set_sha256,
        "scoring_prompt_sha256": manifest.scoring_prompt_sha256,
        "parse_contract_sha256": manifest.parse_contract_sha256,
        "case_count": manifest.case_count,
        "positive_count": manifest.positive_count,
        "negative_count": manifest.negative_count,
        "model_configuration": dict(manifest.model_configuration),
        "model_configuration_sha256": manifest.model_configuration_sha256,
        "manifest_sha256": manifest.sha256,
    }


def run_cli(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Sealed Stage-0 run driver (prepare by default).")
    parser.add_argument("--prepare", action="store_true", help="Prepare+preflight only (default).")
    parser.add_argument(
        "--execute-live",
        action="store_true",
        help="(SEALED) run live scoring against the EXACT prepared manifest (--manifest).",
    )
    parser.add_argument(
        "--manifest",
        default=None,
        help="Path to the prepared manifest JSON to consume for live execution.",
    )
    parser.add_argument(
        "--out-dir",
        default=str(REPO_ROOT / "stage0/runs"),
        help="Directory to write run artifacts (ignored by git).",
    )
    args = parser.parse_args(argv)

    if args.execute_live:
        if not args.manifest:
            parser.error("--execute-live requires --manifest <prepared-manifest.json>")
        manifest_path = Path(args.manifest)
        raw, sha, manifest = load_prepared_manifest(manifest_path)
        # seal: never regenerate run id / timestamp / fields.
        seal_reconstructed_run(
            manifest,
            head=current_git_head(),
            clean=working_tree_is_clean(),
        )
        api_key = os.environ.get("OPENAI_API_KEY", "")
        raw_results = run_prepared_scoring(manifest, api_key)
        artifact = freeze_raw_results(manifest.run_id, raw_results)
        out_dir = Path(args.out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        artifact_path = out_dir / f"raw-results-{manifest.run_id}.json"
        artifact_path.write_bytes(artifact.content)
        print(f"consumed_manifest_sha256={sha}")
        print(f"run_id={manifest.run_id}")
        print(f"harness_revision={manifest.harness_revision}")
        print(f"raw_results_sha256={artifact.sha256}")
        print(f"raw_results_artifact={artifact_path}")
        return 0

    # PREPARE mode: require clean tree; build manifest once; unique immutable ID;
    # write exact bytes; never overwrite. ZERO provider calls.
    if not working_tree_is_clean():
        raise RuntimeError("prepare requires a clean working tree")
    head = current_git_head()
    prepared = build_run_manifest(harness_revision=head)
    validate_pre_run(
        manifest=prepared.manifest,
        case_set=prepared.case_set,
        protocol=prepared.protocol,
        execution_plan=prepared.execution_plan,
        bindings=prepared.bindings,
        agreement=prepared.agreement,
    )
    prepared.manifest.validate_completeness()
    manifest_path = write_manifest_artifact(prepared, Path(args.out_dir))
    print(f"harness_revision={head}")
    print(f"manifest_sha256={prepared.manifest_sha256}")
    print(f"run_id={prepared.manifest.run_id}")
    print(f"manifest_artifact={manifest_path}")
    print("preflight=OK (zero provider calls)")
    return 0


if __name__ == "__main__":
    sys.exit(run_cli())
