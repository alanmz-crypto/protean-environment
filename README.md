# Protean

Persistent-environment research for history-conditioned model behavior

**Status:** Pre-architecture experimental research

**Current active experiment:** Prospective Control Experiment 1

Protean is not currently an AI model. Protean is not yet a general system
architecture. Frontier models provide the underlying intelligence substrate.

Protean investigates whether persistent external state can improve how
unchanged frontier models use their existing capabilities across time and
sessions.

**Current research question:**

> Can persistent, historically informed state improve cross-session control
> decisions around an unchanged frontier model beyond what fixed persistence or
> static instructions can achieve?

**Research sequence:**

```text
Research protocol
→ Stage 0 qualification
→ Full prospective-control experiment
→ Replication
→ Architecture inference only if evidence warrants it
```

## Stage 0 mechanical substrate

The `protean_stage0` Python package implements the authorized mechanical
substrate for Stage 0. It includes the frozen familiar grammar, deterministic
in-memory case generation, independently authored truth evaluators, template and
hash machinery, pre-run validation, an injected single-decision model-client
interface, raw results, DeLong analysis, and the PASS/STOP gate.

It does **not** contain or authorize:

- an experimental case-set artifact;
- a final scoring prompt;
- an experimental provider, model, or configuration;
- a provider implementation or experimental model call.

Run all mechanical verification from the repository root inside the devcontainer:

```sh
scripts/verify-stage0.sh
```
