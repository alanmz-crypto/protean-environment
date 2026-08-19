# Protean devcontainer — minimal isolated worker environment.
# Uses a stable Linux development base; a non-root user; its own HOME and config
# dirs; provides git, gh, shell tools, and Crush (pinned to host version v0.89.0).
# No host config, hooks, credentials, or home directory is mounted or copied in.

# ---- Build stage: compile Crush from source, pinned to the host version ----
# Crush is distributed as a single static Go binary on the host. Building it here
# (from a throwaway Go toolchain) keeps the runtime stage free of Go and matches
# the host binary version exactly, so file ownership in the workspace stays sane.
FROM golang:1.26 AS crush-build
ENV GOBIN=/out
ARG CRUSH_VERSION=v0.89.0
RUN go install "github.com/charmbracelet/crush@${CRUSH_VERSION}"

# ---- Runtime stage ----
# Stable Linux development base: includes a non-root user, git, gh, and standard
# shell/development tools.
FROM mcr.microsoft.com/devcontainers/base:ubuntu-24.04

COPY --from=crush-build /out/crush /usr/local/bin/crush

# gh (GitHub CLI) — provides HTTPS GitHub access. Authentication is NOT baked:
# the operator authenticates at first use via the forwarded SSH agent or `gh auth
# login`; secrets never enter the image or repository files.
RUN <<EOF
set -eu
apt-get update -qq
apt-get install -y -qq curl ca-certificates >/dev/null
curl -fsSL https://cli.github.com/packages/githubcli-archive-keyring.gpg \
  -o /usr/share/keyrings/githubcli-archive-keyring.gpg
echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/githubcli-archive-keyring.gpg] https://cli.github.com/packages stable main" \
  > /etc/apt/sources.list.d/github-cli.list
apt-get update -qq
apt-get install -y -qq gh >/dev/null
EOF

# Container-only minimal Crush configuration for the devcontainer runtime user.
# The remote user (vscode) has an isolated HOME that is never mounted from the
# host, so this fresh config directory is strictly container-local and never
# shadows or reads host Crush state. No secret is baked: the DeepSeek API key is
# referenced by environment variable and supplied at container runtime
# (devcontainer containerEnv / remoteEnv).
#
# NOTE: target /home/vscode explicitly, not "$HOME"/$(id -un): at build time the
# base image runs as root with HOME=/home/root.
RUN <<EOF
set -eu
user="vscode"
mkdir -p "/home/${user}/.config/crush"
cat > "/home/${user}/.config/crush/crush.json" <<'JSON'
{
  "$schema": "https://charm.land/crush.json",
  "providers": {
    "deepseek": {
      "name": "DeepSeek",
      "type": "openai-compat",
      "base_url": "https://api.deepseek.com/v1/",
      "api_key": "${DEEPSEEK_API_KEY}",
      "timeout": 300,
      "default_large_model_id": "deepseek-v4-pro",
      "default_small_model_id": "deepseek-v4-flash",
      "models": [
        {
          "id": "deepseek-v4-flash",
          "name": "DeepSeek V4 Flash",
          "context_window": 1000000,
          "default_max_tokens": -1,
          "cost_per_1m_in": 0.14,
          "cost_per_1m_out": 0.28
        },
        {
          "id": "deepseek-v4-pro",
          "name": "DeepSeek V4 Pro",
          "context_window": 1000000,
          "default_max_tokens": -1,
          "cost_per_1m_in": 0.44,
          "cost_per_1m_out": 0.87
        }
      ]
    }
  }
}
JSON
chown -R "${user}:${user}" "/home/${user}/.config"

# Default Crush to a writable, container-local data directory so interactive
# sessions work regardless of the current working directory (the bare binary
# otherwise tries to create "./.crush" under the cwd, which fails for e.g. "/").
# This is purely container-local and never touches host Crush config. Runtime
# DB/cache therefore live at /home/vscode/.local/share/crush-data, outside the
# repository, so nothing runtime-tracked reaches Git.
mkdir -p "/home/${user}/.local/share/crush-data"
chown "${user}:${user}" "/home/${user}/.local/share/crush-data"
for rc in .bashrc .zshrc; do
  cat >> "/home/${user}/${rc}" <<'SHELL'

# Container-local Crush default data dir (injected only when --data-dir is absent).
crush() {
  case " $* " in
    *" --data-dir "*) command crush "$@" ;;
    *) command crush --data-dir /home/vscode/.local/share/crush-data "$@" ;;
  esac
}
SHELL
done
EOF
