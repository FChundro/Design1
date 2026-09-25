#!/bin/bash
# SessionStart hook: install the project's dependencies in Claude Code on the web.
set -euo pipefail

if [ "${CLAUDE_CODE_REMOTE:-}" != "true" ]; then
  exit 0
fi

cd "$CLAUDE_PROJECT_DIR"

# pyproject.toml pins uv >= 0.11.16, but the image ships an older uv in
# ~/.local/bin. Install a current uv via pip and point the ~/.local/bin entries
# at it. Changing PATH instead would also put /usr/local/bin's older Node ahead
# of Node 22.
python3 -m pip install --quiet --disable-pip-version-check --root-user-action=ignore "uv>=0.11.16"
UV_BIN_DIR="$(dirname "$(python3 -c 'import uv; print(uv.find_uv_bin())')")"
mkdir -p "$HOME/.local/bin"
for bin in uv uvx; do
  ln -sf "$UV_BIN_DIR/$bin" "$HOME/.local/bin/$bin"
done

# Installs runtime + dev dependency groups (ruff, ty, pytest) into .venv.
uv sync

# Playwright CLI for browser automation. Browser downloads are blocked here, so
# point it at the preinstalled Chromium (the config is generated, not committed,
# because this path only exists in the web environment).
if ! command -v playwright-cli >/dev/null 2>&1; then
  npm install -g @playwright/cli@latest
fi
mkdir -p .playwright
cat > .playwright/cli.config.json << 'EOF'
{
  "browser": {
    "browserName": "chromium",
    "launchOptions": {
      "executablePath": "/opt/pw-browsers/chromium"
    }
  }
}
EOF

# Optional tools (OmniRoute, Headroom, claude-mem) take minutes to install the
# first time, so set them up in the background instead of blocking startup.
mkdir -p "$HOME/.cache"
nohup setsid "$CLAUDE_PROJECT_DIR/.claude/hooks/setup-tools.sh" < /dev/null \
  >> "$HOME/.cache/claude-session-tools.log" 2>&1 &
