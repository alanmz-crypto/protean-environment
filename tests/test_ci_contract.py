"""CI contract test: the GitHub Actions workflow must run the full verification gate.

Prevents any future edit from silently dropping pytest, mypy, Ruff check/format,
compileall, or the git-diff whitespace gate (and keeps tools pinned).
"""

from __future__ import annotations

from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
WORKFLOW = REPO / ".github/workflows/python-ci.yml"


def test_workflow_exists() -> None:
    assert WORKFLOW.exists(), ".github/workflows/python-ci.yml must exist"


def _workflow() -> str:
    return WORKFLOW.read_text(encoding="utf-8")


def test_workflow_triggers_push_and_pr() -> None:
    wf = _workflow()
    assert "on:" in wf
    assert "push" in wf
    assert "pull_request" in wf


def test_workflow_full_gate_present() -> None:
    wf = _workflow()
    # Every mandatory gate must be present verbatim so none can be silently dropped.
    required = [
        "python -m pytest -q",
        "mypy src tests",
        "ruff check .",
        "ruff format --check .",
        "python -m compileall -q src tests scripts",
        "git diff --check",
    ]
    for gate in required:
        assert gate in wf, f"workflow is missing gate: {gate!r}"


def test_workflow_pins_python_312_and_tools() -> None:
    wf = _workflow()
    assert 'python-version: ["3.12"]' in wf or "python-version: ['3.12']" in wf
    # Runner must be the pinned ubuntu-24.04, not a moving latest.
    assert "runs-on: ubuntu-24.04" in wf
    assert "pytest==9.1.1" in wf
    assert "mypy==2.1.0" in wf
    assert "ruff==0.16.3" in wf


def test_workflow_pins_action_shas() -> None:
    wf = _workflow()
    # checkout@v4 and setup-python@v5 must be pinned to the exact SHAs from the
    # successful run so the CI cannot drift, while a comment still identifies the
    # major version.
    assert "actions/checkout@11d5960a326750d5838078e36cf38b85af677262" in wf, (
        "checkout action SHA not pinned"
    )
    assert "actions/setup-python@a26af69be951a213d495a4c3e4e4022e16d87065" in wf, (
        "setup-python action SHA not pinned"
    )
    assert "- uses: actions/checkout@v4" not in wf, "checkout uses: must not drift on a tag"
    assert "uses: actions/setup-python@v5" not in wf, "setup-python uses: must not drift on a tag"


def test_devcontainer_ruff_pin_matches_ci() -> None:
    dockerfile = (REPO / ".devcontainer/Dockerfile").read_text(encoding="utf-8")
    assert "ruff==0.16.3" in dockerfile, "devcontainer Ruff pin must match CI (0.16.3)"
    assert "ruff==0.12.8" not in dockerfile, "stale devcontainer Ruff pin must be gone"


def test_workflow_has_no_secrets_or_provider_access() -> None:
    wf = _workflow()
    # No GitHub Actions secrets usage (the `secrets.` expression) and no model/
    # provider credentials or API keys anywhere in the workflow.
    assert "secrets." not in wf
    assert "secrets:" not in wf
    for token in ("API_KEY", "OPENAI", "DEEPSEEK", "LUNA"):
        assert token not in wf, f"workflow must not reference {token!r}"
