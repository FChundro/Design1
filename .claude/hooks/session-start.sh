#!/bin/bash
# SessionStart hook: install the project's Python dependencies in Claude Code on the web.
set -euo pipefail

if [ "${CLAUDE_CODE_REMOTE:-}" != "true" ]; then
  exit 0
fi

cd "$CLAUDE_PROJECT_DIR"

# pyproject.toml pins uv >= 0.11.16; the image ships an older uv, so install a
# current one via pip and put it first on PATH for this session.
python3 -m pip install --quiet --disable-pip-version-check --root-user-action=ignore "uv>=0.11.16"
UV_BIN_DIR="$(dirname "$(python3 -c 'import uv; print(uv.find_uv_bin())')")"
export PATH="$UV_BIN_DIR:$PATH"
if [ -n "${CLAUDE_ENV_FILE:-}" ]; then
  echo "export PATH=\"$UV_BIN_DIR:\$PATH\"" >> "$CLAUDE_ENV_FILE"
fi

# Installs runtime + dev dependency groups (ruff, ty, pytest) into .venv.
uv sync
