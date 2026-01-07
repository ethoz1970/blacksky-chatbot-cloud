"""
Configuration for Blacksky Chatbot (Cloud Version)
Uses Together AI for LLM and Pinecone for vector storage
"""
import os
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Together AI settings
TOGETHER_API_KEY = os.getenv("TOGETHER_API_KEY")
TOGETHER_MODEL = "meta-llama/Meta-Llama-3.1-70B-Instruct-Turbo"

# Pinecone settings
PINECONE_API_KEY = os.getenv("PINECONE_API_KEY")
PINECONE_INDEX_NAME = os.getenv("PINECONE_INDEX_NAME", "blacksky-docs")
PINECONE_DIMENSION = 384  # Dimension for all-MiniLM-L6-v2 embeddings

# Document settings
DOCS_DIR = Path(__file__).parent / "documents"
CHUNK_SIZE = 500
CHUNK_OVERLAP = 50
TOP_K = 5

# Generation settings
MAX_TOKENS = 350
TEMPERATURE = 0.3
TOP_P = 0.9

# Server settings
HOST = "0.0.0.0"
PORT = int(os.getenv("PORT", 8000))

# Conversation settings
MAX_HISTORY_TURNS = 4
