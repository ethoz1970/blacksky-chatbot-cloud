"""
RAG (Retrieval-Augmented Generation) module for Blacksky Chatbot
Uses Pinecone for vector storage and sentence-transformers for embeddings
"""
import os
from pathlib import Path
from typing import List
from pinecone import Pinecone, ServerlessSpec
from sentence_transformers import SentenceTransformer

from config import (
    PINECONE_API_KEY,
    PINECONE_INDEX_NAME,
    PINECONE_DIMENSION,
    DOCS_DIR,
    CHUNK_SIZE,
    CHUNK_OVERLAP,
    TOP_K
)


class DocumentStore:
    """Manages document storage and retrieval using Pinecone."""
    
    def __init__(self):
        self.pc = None
        self.index = None
        self.encoder = None
        
    def initialize(self):
        """Initialize Pinecone and embedding model."""
        print("Initializing document store...")
        
        # Create documents directory if needed
        DOCS_DIR.mkdir(exist_ok=True)
        
        # Initialize embedding model
        print("  Loading embedding model...")
        self.encoder = SentenceTransformer('all-MiniLM-L6-v2')
        
        # Initialize Pinecone
        print("  Connecting to Pinecone...")
        self.pc = Pinecone(api_key=PINECONE_API_KEY)
        
        # Create index if it doesn't exist
        existing_indexes = [idx.name for idx in self.pc.list_indexes()]
        
        if PINECONE_INDEX_NAME not in existing_indexes:
            print(f"  Creating index '{PINECONE_INDEX_NAME}'...")
            self.pc.create_index(
                name=PINECONE_INDEX_NAME,
                dimension=PINECONE_DIMENSION,
                metric="cosine",
                spec=ServerlessSpec(
                    cloud="aws",
                    region="us-east-1"
                )
            )
        
        self.index = self.pc.Index(PINECONE_INDEX_NAME)
        
        # Get stats
        stats = self.index.describe_index_stats()
        print(f"✓ Document store ready. {stats.total_vector_count} vectors indexed.")
        
    def _chunk_text(self, text: str, source: str) -> List[dict]:
        """Split text into overlapping chunks."""
        chunks = []
        start = 0
        chunk_id = 0
        
        # Clean the text
        text = text.replace('---', ' ').replace('###', ' ').replace('##', ' ').replace('#', ' ')
        
        while start < len(text):
            end = start + CHUNK_SIZE
            chunk = text[start:end]
            
            # Try to break at sentence boundary
            if end < len(text):
                last_period = chunk.rfind('.')
                last_newline = chunk.rfind('\n')
                break_point = max(last_period, last_newline)
                if break_point > CHUNK_SIZE // 2:
                    chunk = chunk[:break_point + 1]
                    end = start + break_point + 1
            
            chunk_text = chunk.strip()
            if chunk_text:
                chunks.append({
                    "id": f"{source}_{chunk_id}",
                    "text": chunk_text,
                    "source": source
                })
                chunk_id += 1
            
            start = end - CHUNK_OVERLAP
            
        return chunks
    
    def add_document(self, filepath: Path) -> int:
        """Add a document to the store. Returns number of chunks added."""
        if not filepath.exists():
            raise FileNotFoundError(f"Document not found: {filepath}")
        
        text = filepath.read_text(encoding='utf-8')
        source = filepath.name
        
        # Delete existing vectors from this source
        try:
            # List and delete vectors with this source prefix
            self.index.delete(filter={"source": source})
        except Exception:
            pass  # Index might be empty
        
        # Chunk the document
        chunks = self._chunk_text(text, source)
        
        if not chunks:
            return 0
        
        # Generate embeddings
        texts = [c["text"] for c in chunks]
        embeddings = self.encoder.encode(texts).tolist()
        
        # Upsert to Pinecone
        vectors = [
            {
                "id": c["id"],
                "values": emb,
                "metadata": {"text": c["text"], "source": c["source"]}
            }
            for c, emb in zip(chunks, embeddings)
        ]
        
        self.index.upsert(vectors=vectors)
        
        print(f"  Added {len(chunks)} chunks from {source}")
        return len(chunks)
    
    def load_all_documents(self) -> int:
        """Load all documents from the documents directory."""
        total_chunks = 0
        
        for ext in ['*.txt', '*.md']:
            for filepath in DOCS_DIR.glob(ext):
                total_chunks += self.add_document(filepath)
        
        return total_chunks
    
    def search(self, query: str, top_k: int = TOP_K) -> List[dict]:
        """Search for relevant document chunks."""
        # Generate query embedding
        query_embedding = self.encoder.encode(query).tolist()
        
        # Query Pinecone
        results = self.index.query(
            vector=query_embedding,
            top_k=top_k,
            include_metadata=True
        )
        
        # Format results
        chunks = []
        for match in results.matches:
            chunks.append({
                "text": match.metadata.get("text", ""),
                "source": match.metadata.get("source", ""),
                "score": match.score
            })
        
        return chunks
    
    def get_context(self, query: str, top_k: int = TOP_K) -> str:
        """Get formatted context string for injection into prompt."""
        chunks = self.search(query, top_k)
        
        if not chunks:
            return ""
        
        context_parts = ["Reference information (use naturally, do not copy formatting):"]
        for chunk in chunks:
            context_parts.append(chunk['text'])
        
        return "\n\n".join(context_parts)
    
    def get_stats(self) -> dict:
        """Get index statistics."""
        stats = self.index.describe_index_stats()
        return {
            "total_vectors": stats.total_vector_count,
            "dimension": stats.dimension
        }
    
    def clear(self):
        """Clear all documents from the store."""
        self.index.delete(delete_all=True)
        print("Document store cleared.")


# CLI for managing documents
if __name__ == "__main__":
    import sys
    
    store = DocumentStore()
    store.initialize()
    
    if len(sys.argv) < 2:
        print("\nUsage:")
        print("  python rag.py load           - Load all docs from ./documents/")
        print("  python rag.py add <file>     - Add a specific file")
        print("  python rag.py search <query> - Test search")
        print("  python rag.py stats          - Show index stats")
        print("  python rag.py clear          - Clear all documents")
        sys.exit(0)
    
    command = sys.argv[1]
    
    if command == "load":
        count = store.load_all_documents()
        print(f"\nLoaded {count} total chunks.")
        
    elif command == "add" and len(sys.argv) > 2:
        filepath = Path(sys.argv[2])
        count = store.add_document(filepath)
        print(f"\nAdded {count} chunks.")
        
    elif command == "search" and len(sys.argv) > 2:
        query = " ".join(sys.argv[2:])
        print(f"\nSearching for: {query}\n")
        chunks = store.search(query)
        for i, chunk in enumerate(chunks, 1):
            print(f"--- Result {i} (score: {chunk['score']:.3f}) ---")
            print(f"Source: {chunk['source']}")
            print(chunk['text'][:300] + "..." if len(chunk['text']) > 300 else chunk['text'])
            print()
            
    elif command == "stats":
        stats = store.get_stats()
        print(f"\nIndex stats: {stats}")
            
    elif command == "clear":
        store.clear()
        
    else:
        print("Unknown command. Run without arguments for help.")
