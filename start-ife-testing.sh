#!/bin/bash

# =============================================================================
# Maurice Ife Testing Environment Startup Script
# =============================================================================
# This script starts Maurice in a configuration optimized for Ife integration
# testing, with comprehensive logging and test endpoints enabled.
# =============================================================================

set -e  # Exit on error

echo "=============================================="
echo "  Maurice - Ife Testing Environment"
echo "=============================================="
echo ""

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Load environment variables from .env.local
if [ -f .env.local ]; then
    echo -e "${GREEN}Loading environment from .env.local${NC}"
    export $(grep -v '^#' .env.local | xargs -0)
else
    echo -e "${RED}Warning: .env.local not found!${NC}"
    echo "Please create .env.local with your configuration."
    echo "See README for required variables."
    exit 1
fi

# Set defaults if not specified
export PORT=${PORT:-8001}
export HOST=${HOST:-0.0.0.0}
export ENVIRONMENT=${ENVIRONMENT:-ife-testing}

# Create necessary directories
echo ""
echo "Creating required directories..."
mkdir -p logs/conversations
mkdir -p data/fine-tuning
mkdir -p data/metrics
echo -e "${GREEN}✓ Directories created${NC}"

# Check for required environment variables
echo ""
echo "Checking configuration..."

if [ -z "$TOGETHER_API_KEY" ]; then
    echo -e "${YELLOW}Warning: TOGETHER_API_KEY not set. LLM features may not work.${NC}"
else
    echo -e "${GREEN}✓ TOGETHER_API_KEY is set${NC}"
fi

if [ -z "$PINECONE_API_KEY" ]; then
    echo -e "${YELLOW}Warning: PINECONE_API_KEY not set. RAG features may not work.${NC}"
else
    echo -e "${GREEN}✓ PINECONE_API_KEY is set${NC}"
fi

# Check Python version
PYTHON_VERSION=$(python3 --version 2>&1 | cut -d' ' -f2)
echo -e "${GREEN}✓ Python version: $PYTHON_VERSION${NC}"

# Check if virtual environment exists, create if not
if [ ! -d "venv" ]; then
    echo ""
    echo "Creating virtual environment..."
    python3 -m venv venv
    echo -e "${GREEN}✓ Virtual environment created${NC}"
fi

# Activate virtual environment
echo ""
echo "Activating virtual environment..."
source venv/bin/activate
echo -e "${GREEN}✓ Virtual environment activated${NC}"

# Install/update dependencies
echo ""
echo "Installing dependencies..."
pip install -q -r requirements.txt
echo -e "${GREEN}✓ Dependencies installed${NC}"

# Run database migrations (create tables if needed)
echo ""
echo "Initializing database..."
python3 -c "from database import init_db; init_db()"
echo -e "${GREEN}✓ Database initialized${NC}"

# Display configuration summary
echo ""
echo "=============================================="
echo "  Configuration Summary"
echo "=============================================="
echo "  Environment:  $ENVIRONMENT"
echo "  Host:         $HOST"
echo "  Port:         $PORT"
echo "  Debug:        ${DEBUG:-false}"
echo "  Test Endpoints: ${ENABLE_TEST_ENDPOINTS:-false}"
echo "  Log Path:     ${CONVERSATION_LOG_PATH:-./logs/conversations}"
echo "=============================================="
echo ""

# Check if USE_DOCKER is set
if [ "$USE_DOCKER" = "true" ]; then
    echo -e "${YELLOW}Starting with Docker Compose...${NC}"
    docker-compose -f docker-compose.ife-testing.yml up --build
else
    # Start the server directly
    echo -e "${GREEN}Starting Maurice on http://$HOST:$PORT${NC}"
    echo ""
    echo "Endpoints available:"
    echo "  - Health:     http://localhost:$PORT/"
    echo "  - Chat:       http://localhost:$PORT/chat"
    echo "  - Chat Stream: http://localhost:$PORT/chat/stream"
    echo "  - Testing:    http://localhost:$PORT/testing/status"
    echo "  - Admin:      http://localhost:$PORT/admin?password=ife-testing"
    echo ""
    echo "Press Ctrl+C to stop the server"
    echo ""

    # Start uvicorn with hot reload for development
    uvicorn server:app --host $HOST --port $PORT --reload
fi
