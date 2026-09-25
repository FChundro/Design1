#!/bin/bash
# Installs and starts the optional tools used in Claude Code on the web sessions:
# OmniRoute (AI router), Headroom (context-compression proxy) and claude-mem
# (persistent memory plugin). Launched in the background by session-start.sh;
# every step is idempotent and a failure in one tool does not stop the others.
# Log: ~/.cache/claude-session-tools.log
set -uo pipefail

# The image's /usr/local/bin ships an older Node; these tools need Node 22.
export PATH="/opt/node22/bin:$HOME/.local/bin:$PATH"

log() { echo "[$(date -u +%H:%M:%S)] $*"; }
pip_install() {
  python3 -m pip install --quiet --disable-pip-version-check --root-user-action=ignore "$@"
}
running() { curl -fs -o /dev/null --max-time 3 "$1"; }
start_bg() {
  local name="$1"; shift
  nohup setsid "$@" < /dev/null > "$HOME/.cache/$name.log" 2>&1 &
}

setup_omniroute() {
  command -v omniroute >/dev/null || npm install -g omniroute
  if ! running http://127.0.0.1:20128/; then
    # Loopback only: OmniRoute otherwise listens on 0.0.0.0 without an API key.
    OMNIROUTE_SERVER_HOST=127.0.0.1 start_bg omniroute omniroute --no-color
  fi
}

setup_headroom() {
  if ! python3 -m pip show headroom-ai >/dev/null 2>&1; then
    # Debian-packaged PyJWT and cryptography cannot be upgraded in place by pip,
    # and the Debian cryptography crashes when loaded with headroom's deps.
    pip_install --ignore-installed PyJWT cryptography
    pip_install "headroom-ai[all]"
  fi
  if ! running http://127.0.0.1:8787/health; then
    start_bg headroom-proxy headroom proxy --budget 10 --budget-period daily
  fi
}

setup_claude_mem() {
  local market="$HOME/.claude/plugins/marketplaces/thedotmack"
  if [ ! -d "$market/node_modules" ]; then
    npx -y claude-mem install --provider claude --ide claude-code --no-auto-start
  fi
  # The npm installer omits .claude-plugin/marketplace.json, so Claude Code fails
  # to load the plugin ("cache-miss"); refresh the marketplace from GitHub, then
  # repair restores the runtime dependencies the refresh removes.
  if [ ! -f "$market/.claude-plugin/marketplace.json" ]; then
    claude plugin marketplace update thedotmack
    npx -y claude-mem repair
  fi
  rm -f "$HOME/.claude-mem/last-install-error.json"
  if ! running http://127.0.0.1:37700/; then
    npx -y claude-mem start
  fi
}

mkdir -p "$HOME/.cache"
for tool in omniroute headroom claude_mem; do
  log "setting up $tool"
  if "setup_$tool"; then log "$tool ready"; else log "WARNING: $tool setup failed"; fi
done
