"""
Configuration for Blacksky Chatbot
Detects platform and sets appropriate defaults for Mac (dev) vs Pi (prod)
"""
import platform
import os
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Detect platform
IS_MAC = platform.system() == "Darwin"
IS_ARM_LINUX = platform.system() == "Linux" and platform.machine() == "aarch64"

# Model settings - Llama 3.1 8B Instruct (better instruction following than Mistral 7B)
MODEL_REPO = "lmstudio-community/Meta-Llama-3.1-8B-Instruct-GGUF"
MODEL_FILENAME = "Meta-Llama-3.1-8B-Instruct-Q4_K_M.gguf"
MODEL_DIR = Path(__file__).parent / "models"
MODEL_PATH = MODEL_DIR / MODEL_FILENAME

# Hardware-specific settings
if IS_MAC:
    # Mac with Metal - use GPU acceleration
    N_GPU_LAYERS = -1  # Offload all layers to GPU
    N_THREADS = 8
    N_CTX = 4096  # Mistral supports larger context
    N_BATCH = 512
elif IS_ARM_LINUX:
    # Raspberry Pi 500 - CPU only, will be slow with 7B model
    N_GPU_LAYERS = 0
    N_THREADS = 4
    N_CTX = 2048
    N_BATCH = 256
else:
    # Generic fallback
    N_GPU_LAYERS = 0
    N_THREADS = 4
    N_CTX = 4096
    N_BATCH = 512

# Generation settings (same across platforms)
MAX_TOKENS = 400
TEMPERATURE = 0.3  # Lower = more focused, less creative/hallucinatory
TOP_P = 0.9
REPEAT_PENALTY = 1.1

# Server settings
HOST = "0.0.0.0"
PORT = 8000

# Conversation settings
MAX_HISTORY_TURNS = 4  # Keep last N exchanges to manage context size

# Admin dashboard password (local dev only)
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "localdev")

# JWT secret for token signing
JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "dev-secret-key-change-in-prod")

# Cloud LLM settings (Together AI with Llama 3.1 70B)
# Set USE_CLOUD_LLM=true in Railway environment variables
USE_CLOUD_LLM = os.getenv("USE_CLOUD_LLM", "false").lower() == "true"
TOGETHER_API_KEY = os.getenv("TOGETHER_API_KEY", "")
TOGETHER_MODEL = "meta-llama/Meta-Llama-3.1-70B-Instruct-Turbo"
TOGETHER_EMBEDDING_MODEL = "BAAI/bge-base-en-v1.5"

# Pinecone settings (for RAG)
PINECONE_API_KEY = os.getenv("PINECONE_API_KEY", "")
PINECONE_INDEX_NAME = os.getenv("PINECONE_INDEX_NAME", "blacksky-docs")
# Local uses all-MiniLM-L6-v2 (384), Cloud uses bge-base-en-v1.5 (768)
PINECONE_DIMENSION_LOCAL = 384
PINECONE_DIMENSION_CLOUD = 768
PINECONE_DIMENSION = PINECONE_DIMENSION_CLOUD if USE_CLOUD_LLM else PINECONE_DIMENSION_LOCAL

# Document settings
DOCS_DIR = Path(__file__).parent / "documents"
CHUNK_SIZE = 500
CHUNK_OVERLAP = 50
TOP_K = 3
