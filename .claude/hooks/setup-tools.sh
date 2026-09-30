#!/bin/bash
# Installs and starts the optional tools used in Claude Code on the web sessions:
# OmniRoute (AI router), Headroom (context-compression proxy) and claude-mem
# (persistent memory plugin). Launched in the background by session-start.sh;
# every step is idempotent and a failure in one tool does not stop the others.
# Log: ~/.cache/claude-session-tools.log
set -uo pipefail

# The image's /usr/local/bin ships an older Node; these tools need Node 22.
export PATH="/opt/node22/bin:$HOME/.npm-global/bin:$HOME/.local/bin:$HOME/.bun/bin:$PATH"

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

setup_dsh() {
  # DeepSeek Harness CLI; it reads DEEPSEEK_API_KEY from the environment.
  command -v dsh >/dev/null || npm install -g @deepseek-ai/dsh
}

setup_claude_webkit() {
  # Make the claude-webkit skills available in every session. Its CLAUDE.md is
  # deliberately not installed: it would start the landing-page interview.
  local dir="$HOME/claude-webkit"
  [ -d "$dir/.git" ] || git clone --depth 1 https://github.com/Hainrixz/claude-webkit.git "$dir"
  mkdir -p "$HOME/.claude/skills"
  for skill in "$dir"/.claude/skills/*/; do
    ln -sfn "${skill%/}" "$HOME/.claude/skills/$(basename "$skill")"
  done
}

setup_gstack() {
  local dir="$HOME/.claude/skills/gstack"
  [ -d "$dir/.git" ] || git clone --single-branch --depth 1 https://github.com/garrytan/gstack.git "$dir"
  [ -x "$dir/browse/dist/browse" ] || (cd "$dir" && ./setup < /dev/null)
  # gstack downloads its own headless Chromium from cdn.playwright.dev, which the
  # network policy may block. If it is missing, alias the image's preinstalled
  # headless shell under the build number gstack's Playwright looks for.
  local want have
  want=$(cd "$dir" && bunx playwright install --dry-run chromium-headless-shell 2>/dev/null \
    | grep -oE 'chromium_headless_shell-[0-9]+' | head -1)
  have=$(ls -d /opt/pw-browsers/chromium_headless_shell-* 2>/dev/null | head -1)
  if [ -n "$want" ] && [ -n "$have" ] && [ ! -e "/opt/pw-browsers/$want" ]; then
    local target="/opt/pw-browsers/$want/chrome-headless-shell-linux64"
    mkdir -p "$target"
    for f in "$have"/chrome-linux/*; do ln -sfn "$f" "$target/"; done
    ln -sfn "$have/chrome-linux/headless_shell" "$target/chrome-headless-shell"
    touch "/opt/pw-browsers/$want/INSTALLATION_COMPLETE" "/opt/pw-browsers/$want/DEPENDENCIES_VALIDATED"
  fi
  # The gstack README's install step adds this section to the user CLAUDE.md.
  if ! grep -q '^## gstack' "$HOME/.claude/CLAUDE.md" 2>/dev/null; then
    cat >> "$HOME/.claude/CLAUDE.md" << 'EOF'

## gstack
Use the /browse skill from gstack for all web browsing. Never use mcp__claude-in-chrome__* tools.
Available gstack skills: /office-hours, /plan-ceo-review, /plan-eng-review, /plan-design-review, /design-consultation, /design-shotgun, /design-html, /review, /deslop-shared-libs, /test-audit, /ship, /land-and-deploy, /canary, /benchmark, /browse, /connect-chrome, /qa, /qa-only, /design-review, /scrape, /setup-browser-cookies, /setup-deploy, /setup-gbrain, /retro, /investigate, /document-release, /document-generate, /codex, /cso, /autoplan, /plan-devex-review, /devex-review, /careful, /freeze, /guard, /unfreeze, /gstack-upgrade, /learn.
EOF
  fi
}

mkdir -p "$HOME/.cache"
for tool in omniroute headroom claude_mem dsh claude_webkit gstack; do
  log "setting up $tool"
  if "setup_$tool"; then log "$tool ready"; else log "WARNING: $tool setup failed"; fi
done
