#!/bin/bash
# Digital Kings cloud setup: paste into Environment settings -> Setup script.
# Installs Node.js 24 LTS (checksum-verified) as the default node, plus the
# global tools the Digital Kings image and Word generators use.
set -euo pipefail

NODE_VERSION=v24.21.0
NODE_DIR=/opt/node24

if [ "$("$NODE_DIR/bin/node" -v 2>/dev/null || true)" != "$NODE_VERSION" ]; then
  tmp=$(mktemp -d)
  file="node-$NODE_VERSION-linux-x64.tar.xz"
  curl -fsSL "https://nodejs.org/dist/$NODE_VERSION/$file" -o "$tmp/$file"
  curl -fsSL "https://nodejs.org/dist/$NODE_VERSION/SHASUMS256.txt" | grep " $file\$" | (cd "$tmp" && sha256sum -c -)
  rm -rf "$NODE_DIR" && mkdir -p "$NODE_DIR"
  tar -xJf "$tmp/$file" -C "$NODE_DIR" --strip-components=1
  rm -rf "$tmp"
fi

# ~/.local/bin is first on PATH, so these make Node 24 the default everywhere.
mkdir -p "$HOME/.local/bin"
for b in node npm npx corepack; do ln -sf "$NODE_DIR/bin/$b" "$HOME/.local/bin/$b"; done

# Global tools (browsers are preinstalled, so skip the download).
PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD=1 "$NODE_DIR/bin/npm" install -g --no-fund --no-audit \
  playwright@1.56.1 docx mammoth >/dev/null

"$HOME/.local/bin/node" -v
