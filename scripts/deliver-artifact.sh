#!/usr/bin/env bash
set -euo pipefail

# deliver-artifact.sh — copy artifact from codespace to control-plane and send via Telegram
#
# Usage:
#   bash scripts/deliver-artifact.sh <local_path> [caption]
#
# Example:
#   bash scripts/deliver-artifact.sh screenshots/current/homepage.png "🏠 Homepage после фикса"
#   bash scripts/deliver-artifact.sh screenshots/current/homepage.diff.png "🔄 Diff: 0.02% changed"

ARTIFACT="${1:?Usage: deliver-artifact.sh <path> [caption]}"
CAPTION="${2:-📸 Скриншот}"

# Check file exists
if [ ! -f "$ARTIFACT" ]; then
    echo "❌ File not found: $ARTIFACT"
    exit 1
fi

# Copy to a stable temp path readable by Hermes
COPY_DEST="/tmp/agent-artifacts/$(basename "$ARTIFACT")"
mkdir -p /tmp/agent-artifacts
cp "$ARTIFACT" "$COPY_DEST"

echo "✅ Artifact staged at $COPY_DEST"
echo "ℹ️  Agent will send via MEDIA: protocol"
echo "   Caption: $CAPTION"
echo ""
echo "To deliver from this session, agent does:"
echo "  send_message(message=\"${CAPTION}\nMEDIA:${COPY_DEST}\")"
