"""Sealed production Stage-1A calibration live-execution surface (prepare vs live).

Analogous to the sealed real-origin CLI. The inner ``execute_calibration_run`` is an
injectable hermetic engine; this production wrapper is the only surface intended to
run live, and it does not trust caller-supplied Git HEAD, authority objects, or
transport.

* Prepare mode (default) — zero calls: derives the actual repository HEAD itself,
  requires the canonical-main revision, loads authorities with ``verify_expected``,
  independently re-verifies the ENTIRE origin chain (origin manifest + SHA,
  CompletedOriginRun + SHA, all five origin artifacts), builds the authoritative
  calibration manifest with all 60 exact sealed request SHAs, writes its canonical
  bytes to a dedicated path (refuses overwrite), and reports path/batch/SHA.
* Live mode (``--execute-live``) — requires an explicit flag, an existing calibration
  manifest + expected SHA, and the same explicit origin-chain inputs. Before any
  model client construction it derives ``git rev-parse HEAD``, requires a clean tree,
  reloads authorities, re-reads + verifies the origin chain, reconstructs the
  calibration manifest from exact bytes (SHA + full seal), rederives all 60 request
  bytes/SHAs, and requires a non-empty ``OPENAI_API_KEY`` before irreversible batch
  start. It uses a FIXED direct OpenAI Responses transport (one independent request
  per case, zero retries) ; transport injection is not permitted here.

This module does NOT execute live calls on import; the 60 real scoring calls require
a separate explicit authorization. Importing/``--prepare`` remains zero-call.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

from .artifacts import sha256_bytes
from .direct_responses import default_transport
from .stage1a_authority import load_authority_artifacts
from .stage1a_calibration_driver import (
    AtomicCalibrationSink,
    Stage1ACalibrationManifest,
    _build_calibration_specs,
    build_calibration_manifest,
    execute_calibration_run,
    validate_calibration_manifest_seal_exact,
)
from .stage1a_origin_driver import CompletedOriginRun, validate_origin_run_manifest_seal
from .stage1a_origin_run_manifest import Stage1AOriginRunManifest

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_MANIFEST_DIR = REPO_ROOT / "stage0/runs"

# Authorized origin chain for this calibration surface (the real-origin closeout).
AUTHORIZED_ORIGIN_MANIFEST_SHA = "93bfddcb87bd1d0d3d4a55a8bba0aab3f3c26ecea5eaae322708e7b386b2145c"
AUTHORIZED_ORIGIN_COMPLETED_SHA = "5cd48f96ca5ce569ecbb2ec1670fdecbdcefcf497cb80dce4d19fdedeb4f0e29"
AUTHORIZED_ORIGIN_BATCH = "origin-52ed337bb583-20260821T173319220626Z"


def _git(*args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=REPO_ROOT, capture_output=True, text=True, check=True
    ).stdout.strip()


def derive_head() -> str:
    return _git("rev-parse", "HEAD")


def working_tree_is_clean() -> bool:
    return not _git("status", "--porcelain")


def _fixed_calibration_transport() -> Any:
    """Fixed direct OpenAI Responses transport: EXACT sealed bytes, one request per
    case, zero retries, no previous_response_id/conversation. Returns the origin-shaped
    4-tuple (status_code, error_body, raw_provider_bytes, metadata). Key read per call."""
    from .provider_failure import TransportFailure

    def transport(*, payload: bytes) -> Any:
        try:
            result = default_transport(
                payload=payload,
                api_key=os.environ.get("OPENAI_API_KEY", ""),
                timeout_seconds=300,
            )
        except TransportFailure:
            raise  # typed transport failure -> classified mechanically
        if result.status_code == 200:
            return (200, None, result.raw_bytes, {"model": "gpt-5.6-luna"})
        return (result.status_code, result.raw_bytes, None, {})

    return transport


def _default_origin_inputs() -> dict[str, Any]:
    return {
        "origin_manifest_path": DEFAULT_MANIFEST_DIR
        / f"origin-run-manifest-{AUTHORIZED_ORIGIN_BATCH}.json",
        "origin_completed_path": DEFAULT_MANIFEST_DIR
        / f"origin-completed-{AUTHORIZED_ORIGIN_BATCH}.json",
        "origin_artifacts_dir": DEFAULT_MANIFEST_DIR,
        "origin_batch_run_id": AUTHORIZED_ORIGIN_BATCH,
    }


def prepare_calibration_manifest(harness_revision: str) -> tuple[str, Path, str, str]:
    """Zero-call prepare: verify origin chain, build + write calibration manifest bytes."""
    origin = _default_origin_inputs()
    manifest, _specs = build_calibration_manifest(
        harness_revision=harness_revision,
        origin_manifest_path=origin["origin_manifest_path"],
        origin_manifest_sha256=AUTHORIZED_ORIGIN_MANIFEST_SHA,
        origin_completed_path=origin["origin_completed_path"],
        origin_completed_sha256=AUTHORIZED_ORIGIN_COMPLETED_SHA,
        origin_artifacts_dir=origin["origin_artifacts_dir"],
        origin_batch_run_id=origin["origin_batch_run_id"],
    )
    path = DEFAULT_MANIFEST_DIR / f"calibration-run-manifest-{manifest.batch_run_id}.json"
    if path.exists():
        raise ValueError(f"refusing to overwrite existing calibration manifest: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(manifest.to_exact_bytes())
    return manifest.batch_run_id, path, manifest.sha256, AUTHORIZED_ORIGIN_BATCH


def run_cli(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Sealed Stage-1A calibration runner.")
    parser.add_argument(
        "--prepare", action="store_true", help="Prepare + write calibration manifest (default)."
    )
    parser.add_argument(
        "--execute-live",
        action="store_true",
        help=(
            "Run the sealed 60-request calibration live "
            "(requires --manifest + --expected-manifest-sha)."
        ),
    )
    parser.add_argument(
        "--manifest", default=None, help="Path to prepared calibration manifest JSON."
    )
    parser.add_argument(
        "--expected-manifest-sha",
        default=None,
        help="Expected SHA-256 of the calibration manifest bytes.",
    )
    parser.add_argument(
        "--origin-manifest", default=None, help="Path to the authorized origin-run manifest JSON."
    )
    parser.add_argument(
        "--origin-manifest-sha",
        default=None,
        help="Expected SHA of the authorized origin manifest bytes.",
    )
    parser.add_argument(
        "--origin-completed", default=None, help="Path to the authorized origin completed-run JSON."
    )
    parser.add_argument(
        "--origin-completed-sha",
        default=None,
        help="Expected SHA of the authorized origin completed-run bytes.",
    )
    parser.add_argument(
        "--origin-artifacts-dir",
        default=None,
        help="Directory containing the five durable origin artifacts.",
    )
    parser.add_argument("--origin-batch", default=None, help="Authorized origin batch/run ID.")
    parser.add_argument(
        "--out-dir", default=str(DEFAULT_MANIFEST_DIR), help="Evidence artifact dir."
    )
    args = parser.parse_args(argv)

    head = derive_head()

    origin = _default_origin_inputs()
    origin_manifest_sha = args.origin_manifest_sha or AUTHORIZED_ORIGIN_MANIFEST_SHA
    origin_completed_sha = args.origin_completed_sha or AUTHORIZED_ORIGIN_COMPLETED_SHA
    origin_batch = args.origin_batch or AUTHORIZED_ORIGIN_BATCH
    origin_manifest_path = (
        Path(args.origin_manifest) if args.origin_manifest else origin["origin_manifest_path"]
    )
    origin_completed_path = (
        Path(args.origin_completed) if args.origin_completed else origin["origin_completed_path"]
    )
    origin_artifacts_dir = (
        Path(args.origin_artifacts_dir)
        if args.origin_artifacts_dir
        else origin["origin_artifacts_dir"]
    )

    if args.execute_live:
        if not args.manifest or not args.expected_manifest_sha:
            parser.error("--execute-live requires --manifest and --expected-manifest-sha")
        manifest_path = Path(args.manifest)
        expected_sha = args.expected_manifest_sha
        if not working_tree_is_clean():
            print("STOP: working tree is not clean (no HTTP attempts made)")
            return 2
        if head is None:
            print("STOP: could not derive real git HEAD")
            return 2
        manifest_bytes = manifest_path.read_bytes()
        manifest = Stage1ACalibrationManifest._reconstruct(manifest_bytes)
        if manifest.harness_revision != head:
            print("STOP: HEAD does not match calibration manifest harness revision (0 calls)")
            return 2
        if sha256_bytes(manifest_bytes) != expected_sha:
            print("STOP: calibration manifest bytes do not hash to expected SHA (0 calls)")
            return 2
        auth = load_authority_artifacts(verify_expected=True)
        # Re-read + verify the entire origin chain freshly.
        if sha256_bytes(origin_manifest_path.read_bytes()) != origin_manifest_sha:
            print("STOP: origin manifest does not hash to authorized SHA (0 calls)")
            return 2
        om = Stage1AOriginRunManifest._reconstruct(origin_manifest_path.read_bytes())
        if om.to_exact_bytes() != origin_manifest_path.read_bytes():
            print("STOP: origin manifest is not canonical (0 calls)")
            return 2
        validate_origin_run_manifest_seal(
            manifest=om,
            manifest_sha256=origin_manifest_sha,
            actual_harness_revision=head,
            auth=auth,
        )
        if sha256_bytes(origin_completed_path.read_bytes()) != origin_completed_sha:
            print("STOP: origin completed does not hash to authorized SHA (0 calls)")
            return 2
        oc = CompletedOriginRun.from_exact_bytes(origin_completed_path.read_bytes())
        if oc.to_exact_bytes() != origin_completed_path.read_bytes():
            print("STOP: origin completed is not canonical (0 calls)")
            return 2
        if oc.batch_run_id != origin_batch or om.batch_run_id != origin_batch:
            print("STOP: origin batch mismatch (0 calls)")
            return 2
        # Reload + verify all five durable origin artifacts for the batch.
        for index in range(1, 6):
            ap = origin_artifacts_dir / f"origin-artifact-{origin_batch}-{index:02d}.json"
            if not ap.exists():
                print(f"STOP: missing origin artifact {ap} (0 calls)")
                return 2
            if sha256_bytes(ap.read_bytes()) != oc.artifact_shas[index - 1]:
                print("STOP: origin artifact does not hash to completed authority (0 calls)")
                return 2
        # Reconstruct the calibration manifest from exact bytes + full seal (N3 exact).
        manifest = validate_calibration_manifest_seal_exact(
            manifest=manifest,
            manifest_sha256=expected_sha,
            auth=auth,
            actual_harness_revision=head,
        )
        # Rederive all 60 request bytes/SHAs and require equality.
        cal_specs = _build_calibration_specs(
            auth=auth, harness_revision=head, batch_run_id=origin_batch
        )
        for spec in cal_specs:
            if spec.request_sha256 != manifest.per_case_request_sha.get(spec.case_id):
                print(f"STOP: rederived calibration request SHA mismatch for {spec.case_id}")
                return 2
        # Preflight a non-empty OPENAI_API_KEY before any transport / batch start.
        if not os.environ.get("OPENAI_API_KEY", ""):
            print("STOP: OPENAI_API_KEY is not set (no HTTP attempts, no batch started)")
            return 2
        sink = AtomicCalibrationSink(Path(args.out_dir))
        status, evidence, completed = execute_calibration_run(
            manifest_bytes=manifest_bytes,
            expected_manifest_sha256=expected_sha,
            actual_harness_revision=head,
            auth=auth,
            batch_run_id=manifest.batch_run_id,
            transport=_fixed_calibration_transport(),
            evidence_sink=sink,
        )
        print(f"calibration_status={status.value}")
        if completed is not None:
            print(f"completed_calibration_sha256={completed.sha256}")
        return 0 if status.value == "COMPLETED" else 1

    # Prepare mode (default): zero provider calls.
    batch_run_id, path, sha, _origin_batch = prepare_calibration_manifest(head)
    print(f"harness_revision={head}")
    print(f"calibration_batch_run_id={batch_run_id}")
    print(f"calibration_manifest_path={path}")
    print(f"calibration_manifest_sha256={sha}")
    print("prepare=OK (zero provider calls)")
    return 0


if __name__ == "__main__":
    sys.exit(run_cli())
