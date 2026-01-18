"""
RAG (Retrieval-Augmented Generation) module for Blacksky Chatbot
Uses ChromaDB for vector storage and sentence-transformers for embeddings
"""
import os
from pathlib import Path
from typing import List, Optional
import chromadb
from chromadb.utils import embedding_functions

# Configuration
DOCS_DIR = Path(__file__).parent / "documents"
# ChromaDB path - configurable for Railway persistent volumes
CHROMA_DIR = Path(os.getenv("CHROMA_DIR", str(Path(__file__).parent / "chroma_db")))
COLLECTION_NAME = "blacksky_docs"
CHUNK_SIZE = 500  # characters per chunk
CHUNK_OVERLAP = 50  # overlap between chunks
TOP_K = 3  # number of chunks to retrieve


class DocumentStore:
    """Manages document storage and retrieval using ChromaDB."""
    
    def __init__(self):
        self.client = None
        self.collection = None
        self.embedding_fn = None
        
    def initialize(self):
        """Initialize ChromaDB and load any existing documents."""
        print("Initializing document store...")
        
        # Create directories if needed
        DOCS_DIR.mkdir(exist_ok=True)
        CHROMA_DIR.mkdir(exist_ok=True)
        
        # Use a small, fast embedding model
        # all-MiniLM-L6-v2 is ~80MB and runs well on CPU
        self.embedding_fn = embedding_functions.SentenceTransformerEmbeddingFunction(
            model_name="all-MiniLM-L6-v2"
        )
        
        # Initialize ChromaDB with persistence
        self.client = chromadb.PersistentClient(path=str(CHROMA_DIR))
        
        # Get or create collection
        self.collection = self.client.get_or_create_collection(
            name=COLLECTION_NAME,
            embedding_function=self.embedding_fn,
            metadata={"description": "Blacksky LLC documents"}
        )
        
        doc_count = self.collection.count()
        print(f"✓ Document store ready. {doc_count} chunks indexed.")
        
    def _chunk_text(self, text: str, source: str) -> List[dict]:
        """Split text into overlapping chunks."""
        chunks = []
        start = 0
        chunk_id = 0
        
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
            
            chunks.append({
                "id": f"{source}_{chunk_id}",
                "text": chunk.strip(),
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
        
        # Remove existing chunks from this source
        existing = self.collection.get(where={"source": source})
        if existing['ids']:
            self.collection.delete(ids=existing['ids'])
        
        # Chunk and add
        chunks = self._chunk_text(text, source)
        
        if chunks:
            self.collection.add(
                ids=[c["id"] for c in chunks],
                documents=[c["text"] for c in chunks],
                metadatas=[{"source": c["source"]} for c in chunks]
            )
        
        print(f"  Added {len(chunks)} chunks from {source}")
        return len(chunks)
    
    def load_all_documents(self) -> int:
        """Load all documents from the documents directory (including subdirectories)."""
        total_chunks = 0

        # Support .txt and .md files in all subdirectories
        for ext in ['**/*.txt', '**/*.md']:
            for filepath in DOCS_DIR.glob(ext):
                # Skip template files (those starting with underscore)
                if filepath.name.startswith('_'):
                    continue
                total_chunks += self.add_document(filepath)

        return total_chunks
    
    def search(self, query: str, top_k: int = TOP_K) -> List[dict]:
        """Search for relevant document chunks."""
        if self.collection.count() == 0:
            return []
        
        results = self.collection.query(
            query_texts=[query],
            n_results=min(top_k, self.collection.count())
        )
        
        # Format results
        chunks = []
        for i, doc in enumerate(results['documents'][0]):
            chunks.append({
                "text": doc,
                "source": results['metadatas'][0][i]['source'],
                "distance": results['distances'][0][i] if results['distances'] else None
            })
        
        return chunks
    
    def get_context(self, query: str, top_k: int = TOP_K) -> str:
        """Get formatted context string for injection into prompt."""
        chunks = self.search(query, top_k)
        
        if not chunks:
            return ""
        
        context_parts = ["Reference information (use naturally, do not copy formatting):"]
        for chunk in chunks:
            # Clean the chunk text of markdown formatting
            clean_text = chunk['text'].replace('---', '').replace('###', '').replace('##', '').replace('#', '').strip()
            context_parts.append(clean_text)
        
        return "\n\n".join(context_parts)
    
    def list_documents(self) -> List[str]:
        """List all indexed document sources."""
        if self.collection.count() == 0:
            return []
        
        all_docs = self.collection.get()
        sources = set(m['source'] for m in all_docs['metadatas'])
        return sorted(sources)
    
    def clear(self):
        """Clear all documents from the store."""
        self.client.delete_collection(COLLECTION_NAME)
        self.collection = self.client.get_or_create_collection(
            name=COLLECTION_NAME,
            embedding_function=self.embedding_fn
        )
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
        print("  python rag.py list           - List indexed documents")
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
            print(f"--- Result {i} (distance: {chunk['distance']:.3f}) ---")
            print(f"Source: {chunk['source']}")
            print(chunk['text'][:300] + "..." if len(chunk['text']) > 300 else chunk['text'])
            print()
            
    elif command == "list":
        docs = store.list_documents()
        print(f"\nIndexed documents ({len(docs)}):")
        for doc in docs:
            print(f"  - {doc}")
            
    elif command == "clear":
        store.clear()
        
    else:
        print("Unknown command. Run without arguments for help.")
