"""
Configuration for Blacksky Chatbot (Cloud Version)
Uses Anthropic Claude for LLM and Pinecone for vector storage
"""
import os
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Together AI settings (Llama 3.1 70B)
TOGETHER_API_KEY = os.getenv("TOGETHER_API_KEY")
TOGETHER_MODEL = "meta-llama/Meta-Llama-3.1-70B-Instruct-Turbo"
TOGETHER_BASE_URL = "https://api.together.xyz/v1"

# Pinecone settings
PINECONE_API_KEY = os.getenv("PINECONE_API_KEY")
PINECONE_INDEX_NAME = os.getenv("PINECONE_INDEX_NAME", "blacksky-docs")
PINECONE_DIMENSION = 384  # Dimension for all-MiniLM-L6-v2 embeddings

# Document settings
DOCS_DIR = Path(__file__).parent / "documents"
CHUNK_SIZE = 500
CHUNK_OVERLAP = 50
TOP_K = 3

# Generation settings
MAX_TOKENS = 250
TEMPERATURE = 0.3
TOP_P = 0.9

# Server settings
HOST = "0.0.0.0"
PORT = int(os.getenv("PORT", 8000))

# Conversation settings
MAX_HISTORY_TURNS = 2

# Database settings (Railway auto-creates DATABASE_URL when you add Postgres)
DATABASE_URL = os.getenv("DATABASE_URL")

# Admin settings
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "changeme")

# Google OAuth settings
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID", "")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET", "")
GOOGLE_REDIRECT_URI = os.getenv("GOOGLE_REDIRECT_URI", "https://blacksky-chat.us/auth/google/callback")

# Session security
SESSION_SECRET_KEY = os.getenv("SESSION_SECRET_KEY", "dev-secret-key-change-in-prod")
