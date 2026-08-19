#!/usr/bin/env bash
set -euo pipefail

repo_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_dir"

export PYTHONPATH=src
export PYTHONPYCACHEPREFIX=/tmp/protean-stage0-pycache

pytest -q
mypy
ruff check src tests
ruff format --check src tests
python3 -m compileall -q src tests
git diff --check
