#!/bin/bash
# Sync shared files from cloud repo to local repo
# Run from the cloud repo root: ./scripts/sync-to-local.sh

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CLOUD_REPO="$(dirname "$SCRIPT_DIR")"
LOCAL_REPO="$CLOUD_REPO/../bsm-chatbot"

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${YELLOW}Syncing shared files: cloud -> local${NC}"
echo "Source: $CLOUD_REPO"
echo "Target: $LOCAL_REPO"
echo ""

# Check if local repo exists
if [ ! -d "$LOCAL_REPO" ]; then
    echo "Error: Local repo not found at $LOCAL_REPO"
    exit 1
fi

# Ensure target directories exist
mkdir -p "$LOCAL_REPO/static/images"

# Sync individual files
echo "Copying prompts.py..."
cp "$CLOUD_REPO/prompts.py" "$LOCAL_REPO/prompts.py"

echo "Copying static/demo.html..."
cp "$CLOUD_REPO/static/demo.html" "$LOCAL_REPO/static/demo.html"

echo "Copying static/panels.js..."
cp "$CLOUD_REPO/static/panels.js" "$LOCAL_REPO/static/panels.js"

echo "Copying static/panels.json..."
cp "$CLOUD_REPO/static/panels.json" "$LOCAL_REPO/static/panels.json"

# Sync images directory
echo "Copying static/images/..."
cp -r "$CLOUD_REPO/static/images/"* "$LOCAL_REPO/static/images/" 2>/dev/null || true

echo ""
echo -e "${GREEN}Sync complete!${NC}"
echo "Don't forget to test the local version."
