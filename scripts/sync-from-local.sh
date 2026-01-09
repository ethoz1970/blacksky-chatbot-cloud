#!/bin/bash
# Sync shared files from local repo to cloud repo
# Run from the cloud repo root: ./scripts/sync-from-local.sh

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CLOUD_REPO="$(dirname "$SCRIPT_DIR")"
LOCAL_REPO="$CLOUD_REPO/../bsm-chatbot"

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${YELLOW}Syncing shared files: local -> cloud${NC}"
echo "Source: $LOCAL_REPO"
echo "Target: $CLOUD_REPO"
echo ""

# Check if local repo exists
if [ ! -d "$LOCAL_REPO" ]; then
    echo "Error: Local repo not found at $LOCAL_REPO"
    exit 1
fi

# Sync individual files
echo "Copying prompts.py..."
cp "$LOCAL_REPO/prompts.py" "$CLOUD_REPO/prompts.py"

echo "Copying static/demo.html..."
cp "$LOCAL_REPO/static/demo.html" "$CLOUD_REPO/static/demo.html"

echo "Copying static/panels.js..."
cp "$LOCAL_REPO/static/panels.js" "$CLOUD_REPO/static/panels.js"

echo "Copying static/panels.json..."
cp "$LOCAL_REPO/static/panels.json" "$CLOUD_REPO/static/panels.json"

# Sync images directory
echo "Copying static/images/..."
cp -r "$LOCAL_REPO/static/images/"* "$CLOUD_REPO/static/images/" 2>/dev/null || true

echo ""
echo -e "${GREEN}Sync complete!${NC}"
echo "Don't forget to test and deploy the cloud version."
