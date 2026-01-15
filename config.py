"""
Configuration for Blacksky Chatbot
Detects platform and sets appropriate defaults for Mac (dev) vs Pi (prod)
"""
import platform
import os
from pathlib import Path
from dotenv import load_dotenv

# Build version - increment this to verify Railway is deploying new code
BUILD_VERSION = "v2.1.0-2026.01.15"
print(f"[CONFIG] Build version: {BUILD_VERSION}")

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
# Auto-detect cloud mode: if TOGETHER_API_KEY is set, we're in cloud mode
TOGETHER_API_KEY = os.getenv("TOGETHER_API_KEY", "")
USE_CLOUD_LLM = bool(TOGETHER_API_KEY)  # True if API key is set
print(f"[CONFIG] USE_CLOUD_LLM={USE_CLOUD_LLM} (TOGETHER_API_KEY={'set' if TOGETHER_API_KEY else 'not set'})")
TOGETHER_MODEL = "meta-llama/Meta-Llama-3.1-70B-Instruct-Turbo"
TOGETHER_EMBEDDING_MODEL = "togethercomputer/m2-bert-80M-8k-retrieval"  # 768 dim

# Pinecone settings (for RAG)
PINECONE_API_KEY = os.getenv("PINECONE_API_KEY", "")
# Local uses 'blacksky' (384 dim), Cloud uses 'blacksky-cloud' (768 dim)
PINECONE_INDEX_NAME_LOCAL = "blacksky"
PINECONE_INDEX_NAME_CLOUD = "blacksky-cloud"
PINECONE_INDEX_NAME = os.getenv("PINECONE_INDEX_NAME", PINECONE_INDEX_NAME_CLOUD if USE_CLOUD_LLM else PINECONE_INDEX_NAME_LOCAL)
PINECONE_DIMENSION = 768 if USE_CLOUD_LLM else 384

# Document settings
DOCS_DIR = Path(__file__).parent / "documents"
CHUNK_SIZE = 500
CHUNK_OVERLAP = 50
TOP_K = 3
