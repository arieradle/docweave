#!/usr/bin/env bash
# Runs once after the devcontainer is created.
set -euo pipefail

# rtk: compresses shell command output for Claude Code (https://github.com/rtk-ai/rtk).
# The installer verifies the release checksum and installs to ~/.local/bin.
RTK_VERSION="v1.0.1"
curl -fsSL "https://raw.githubusercontent.com/rtk-ai/rtk/refs/tags/${RTK_VERSION}/install.sh" \
  | RTK_VERSION="${RTK_VERSION}" sh

# Register rtk's PreToolUse hook in the global Claude Code config.
"$HOME/.local/bin/rtk" init -g --auto-patch --no-trust-filters
