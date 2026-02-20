#!/usr/bin/env bash
# install.sh — install claude-agents and ccnotify.py
# Usage: ./install.sh

set -euo pipefail

REPO="$(cd "$(dirname "$0")" && pwd)"
CCNOTIFY_DIR="$HOME/.claude/ccnotify"
BIN_DIR="$HOME/.local/bin"

echo "Installing claude-agents..."
echo ""

# 1. Install ccnotify.py
mkdir -p "$CCNOTIFY_DIR"
cp "$REPO/ccnotify.py" "$CCNOTIFY_DIR/ccnotify.py"
chmod +x "$CCNOTIFY_DIR/ccnotify.py"
echo "  ccnotify.py  →  $CCNOTIFY_DIR/ccnotify.py"

# 2. Install claude-agents binary
mkdir -p "$BIN_DIR"
cp "$REPO/claude-agents" "$BIN_DIR/claude-agents"
chmod +x "$BIN_DIR/claude-agents"
echo "  claude-agents  →  $BIN_DIR/claude-agents"

# 3. Warn if $BIN_DIR not on PATH
if [[ ":$PATH:" != *":$BIN_DIR:"* ]]; then
    echo ""
    echo "  ⚠  $BIN_DIR is not on your PATH."
    echo "     Add this to your ~/.zshrc or ~/.bashrc:"
    echo ""
    echo "       export PATH=\"\$HOME/.local/bin:\$PATH\""
fi

# 4. Print hook config
echo ""
echo "Add these hooks to ~/.claude/settings.json:"
echo ""
cat <<EOF
{
  "hooks": {
    "SubagentStart":     [{"matcher": "", "hooks": [{"type": "command", "command": "$CCNOTIFY_DIR/ccnotify.py SubagentStart"}]}],
    "SubagentStop":      [{"matcher": "", "hooks": [{"type": "command", "command": "$CCNOTIFY_DIR/ccnotify.py SubagentStop"}]}],
    "UserPromptSubmit":  [{"matcher": "", "hooks": [{"type": "command", "command": "$CCNOTIFY_DIR/ccnotify.py UserPromptSubmit"}]}],
    "Stop":              [{"matcher": "", "hooks": [{"type": "command", "command": "$CCNOTIFY_DIR/ccnotify.py Stop"}]}],
    "Notification":      [{"matcher": "", "hooks": [{"type": "command", "command": "$CCNOTIFY_DIR/ccnotify.py Notification"}]}],
    "PreToolUse":        [{"matcher": "", "hooks": [{"type": "command", "command": "$CCNOTIFY_DIR/ccnotify.py PreToolUse"}]}]
  }
}
EOF

echo ""
echo "Done. Run: claude-agents"
