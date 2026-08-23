# Protean

Protean is an **independent, pre-architecture research project**.

- Rules, workflows, governance, schemas, memories, hooks, or tooling belonging to
  another project (e.g. ConvMem) do **not** gain authority here merely because they
  are globally available inside the host or container.
- Generic safety and worker-discipline rules remain applicable.
- Cross-project mechanisms may be imported only through explicit Protean
  authorization.
- Build only what the current Protean task authorizes.

This boundary is intentionally small. Do not expand it into a constitution or
planning system.

## Complex Arc Closure Rule

A complex arc is not fully closed until all three of these gates pass:

1. **Substantive review PASS** — the arc's load-bearing result (scientific,
   governance, design, implementation, or other) has received the review
   appropriate to the arc, independent where required.
2. **Exact landing verification** — the intended artifact/change landed
   unchanged and only within authorized scope: exact landed tip, artifact/hash
   identity where applicable, `HEAD == origin/main`, and a clean worktree.
3. **Independent final-tip repository gate** — at the exact landed SHA, an
   independent verifier runs Protean's canonical verification suite plus any
   arc-specific verification (additive where applicable), and reports PASS.

The canonical Protean repository gate is:

- `PYTHONPATH=src python -m pytest -q`
- `mypy src tests`
- `ruff check .`
- `ruff format --check .`
- `python -m compileall -q src tests scripts`
- `git diff --check`

Complex docs/research/governance arcs still receive the canonical repository
gate. Trivial, non-complex ad-hoc edits may scale verification proportionally.

A verifier must distinguish a genuine repository regression from an
environment/tooling failure, and must not perform opportunistic repairs. If a
local verifier genuinely cannot execute a required gate, successful CI at the
**same exact SHA** may supply that evidence only if the substitution is
explicitly reported.

Nothing in this rule implies or authorizes model/provider/API calls.
