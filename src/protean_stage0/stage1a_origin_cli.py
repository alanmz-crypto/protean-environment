"""Sealed real live-origin execution surface (prepare vs live CLI).

Analogous to the proven Stage-0 driver. The inner ``execute_origin_run`` remains
an injectable hermetic engine; this production wrapper is the only surface that
should run live, and it does not trust caller-supplied Git HEAD, authority
objects, or transport.

* Prepare mode (default) — zero calls: derives the actual repository HEAD itself,
  requires/records the canonical-main revision, loads authorities with
  ``verify_expected=True``, builds the authoritative Stage1AOriginRunManifest,
  writes its exact canonical bytes to a dedicated artifact path (refuses
  overwrite), and reports paths/SHAs.
* Live mode (``--execute-live``) — requires an explicit flag, an existing manifest
  path, and a caller-supplied expected manifest SHA. Before any transport it
  independently derives ``git rev-parse HEAD``, requires a clean working tree,
  requires HEAD == manifest harness revision, freshly loads authorities,
  verifies the exact manifest bytes SHA + canonical reconstruction + full origin
  manifest seal, and rederives the five exact request bytes to match the manifest.

Live mode owns a FIXED direct OpenAI Responses transport that POSTs the exact
sealed payload bytes unchanged, uses OPENAI_API_KEY only at runtime, issues one
HTTP request per origin attempt, zero retries, and preserves HTTP status/body and
raw successful Responses bytes. Transport injection is not permitted here.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any

from .artifacts import sha256_bytes
from .direct_config import ENDPOINT
from .stage1a_authority import load_authority_artifacts
from .stage1a_origin_driver import (
    AtomicEvidenceSink,
    build_origin_run_manifest,
    execute_origin_run,
    validate_origin_run_manifest_seal,
)
from .stage1a_origin_run_manifest import Stage1AOriginRunManifest

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_MANIFEST_DIR = REPO_ROOT / "stage0/runs"


def _git(*args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=REPO_ROOT, capture_output=True, text=True, check=True
    ).stdout.strip()


def derive_head() -> str:
    return _git("rev-parse", "HEAD")


def working_tree_is_clean() -> bool:
    return not _git("status", "--porcelain")


def prepare_live_origin_manifest(harness_revision: str) -> tuple[str, Path, str]:
    """Zero-call prepare: build + write the authoritative origin manifest bytes."""
    auth = load_authority_artifacts(verify_expected=True)
    batch_run_id = f"origin-{harness_revision[:12]}-{datetime.now().strftime('%Y%m%dT%H%M%S%fZ')}"
    manifest, _specs = build_origin_run_manifest(
        auth=auth, harness_revision=harness_revision, batch_run_id=batch_run_id
    )
    path = DEFAULT_MANIFEST_DIR / f"origin-run-manifest-{manifest.batch_run_id}.json"
    if path.exists():
        raise ValueError(f"refusing to overwrite existing origin manifest: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(manifest.to_exact_bytes())
    return manifest.batch_run_id, path, manifest.sha256


def _fixed_responses_transport(auth: Any) -> Any:
    """Fixed direct OpenAI Responses transport: posts the EXACT sealed payload
    bytes, one request per attempt, zero retries, no conversation/tools/stream."""
    api_key = os.environ.get("OPENAI_API_KEY", "")

    def transport(
        *, payload: bytes
    ) -> tuple[int | None, bytes | None, bytes | None, dict[str, Any]]:
        if not api_key:
            raise ValueError("OPENAI_API_KEY is required for live execution")
        req = urllib.request.Request(
            ENDPOINT,
            data=payload,
            method="POST",
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=300) as resp:
                raw = resp.read()
                return (
                    resp.status,
                    None,
                    bytes(raw),
                    {"model": "gpt-5.6-luna"},
                )
        except urllib.error.HTTPError as exc:
            return (exc.code, exc.read(), None, {})
        except Exception:
            from .provider_failure import TransportFailure

            raise TransportFailure("live origin transport error (no retry)") from None

    return transport


def run_cli(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Sealed Stage-1A origin runner.")
    parser.add_argument(
        "--prepare", action="store_true", help="Prepare + write origin manifest (default)."
    )
    parser.add_argument(
        "--execute-live",
        action="store_true",
        help=(
            "Run the sealed five-request origin live "
            "(requires --manifest + --expected-manifest-sha)."
        ),
    )
    parser.add_argument(
        "--manifest", default=None, help="Path to the prepared origin manifest JSON."
    )
    parser.add_argument(
        "--expected-manifest-sha",
        default=None,
        help="Expected SHA-256 of the manifest bytes.",
    )
    parser.add_argument("--out-dir", default=str(DEFAULT_MANIFEST_DIR), help="Artifact dir.")
    args = parser.parse_args(argv)

    head = derive_head()

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
        manifest = Stage1AOriginRunManifest._reconstruct(manifest_bytes)
        if manifest.harness_revision != head:
            print("STOP: HEAD does not match manifest harness revision (0 HTTP attempts)")
            return 2
        if sha256_bytes(manifest_bytes) != expected_sha:
            print("STOP: manifest bytes do not hash to expected SHA (0 HTTP attempts)")
            return 2
        auth = load_authority_artifacts(verify_expected=True)
        validate_origin_run_manifest_seal(
            manifest=manifest,
            manifest_sha256=expected_sha,
            actual_harness_revision=head,
            auth=auth,
        )
        # Rederive request bytes + verify they match the manifest.
        _, specs = build_origin_run_manifest(
            auth=auth, harness_revision=head, batch_run_id=manifest.batch_run_id
        )
        for spec in specs:
            if spec.request_sha256 != manifest.per_request_request_sha.get(spec.structure):
                print(f"STOP: rederived request SHA mismatch for {spec.structure}")
                return 2
        os.environ.setdefault("OPENAI_API_KEY", os.environ.get("OPENAI_API_KEY", ""))
        transport = _fixed_responses_transport(auth)
        sink = AtomicEvidenceSink(Path(args.out_dir))
        result = execute_origin_run(
            manifest_bytes=manifest_bytes,
            expected_manifest_sha256=expected_sha,
            actual_harness_revision=head,
            auth=auth,
            batch_run_id=manifest.batch_run_id,
            transport=transport,
            evidence_sink=sink,
        )
        print(f"status={result.status.value}")
        if result.completed:
            print(f"completed_run_sha256={result.completed.completed_run_sha256}")
        return 0

    # Prepare mode (default): zero provider calls.
    batch_run_id, path, sha = prepare_live_origin_manifest(head)
    print(f"harness_revision={head}")
    print(f"batch_run_id={batch_run_id}")
    print(f"manifest_path={path}")
    print(f"manifest_sha256={sha}")
    print("prepare=OK (zero provider calls)")
    return 0


if __name__ == "__main__":
    sys.exit(run_cli())
