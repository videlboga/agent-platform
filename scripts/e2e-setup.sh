#!/usr/bin/env bash
set -euo pipefail

# Manual fallback if devcontainer postCreate didn't run
# Usage: bash scripts/e2e-setup.sh

echo "=== e2e-setup: installing Python deps ==="
pip install --quiet playwright pillow requests pixelmatch 2>&1 | tail -3

echo "=== e2e-setup: installing Playwright browsers ==="
npx playwright install chromium 2>&1 | tail -3

echo "=== e2e-setup: ensuring screenshots dir ==="
mkdir -p /workspaces/agent-platform/screenshots/baseline

echo "=== e2e-setup: done ==="
python3 -c "
import playwright, PIL, requests, pixelmatch
print('All dependencies available: playwright, pillow, requests, pixelmatch')
"
