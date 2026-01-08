"""
FastAPI server for Blacksky Chatbot (Cloud Version)
"""
from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel
from contextlib import asynccontextmanager
from pathlib import Path
import time
import json

from chatbot import BlackskyChatbot
from config import HOST, PORT, DOCS_DIR

# Paths
STATIC_DIR = Path(__file__).parent / "static"
STATIC_DIR.mkdir(exist_ok=True)

# Global chatbot instance
bot = BlackskyChatbot(use_rag=True)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize on startup."""
    print("Starting Blacksky Chatbot Server (Cloud)...")
    bot.initialize()
    
    # Auto-load any documents in the documents folder
    if bot.doc_store and list(DOCS_DIR.glob('*')):
        print("Loading documents...")
        bot.doc_store.load_all_documents()
    
    yield
    print("Shutting down...")


app = FastAPI(
    title="Blacksky Chatbot API (Cloud)",
    description="A friendly chatbot for Blacksky LLC - Cloud Version",
    version="2.0.0",
    lifespan=lifespan
)

# CORS for web clients
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class ChatRequest(BaseModel):
    message: str


class ChatResponse(BaseModel):
    response: str
    response_time_ms: float


@app.get("/")
async def root():
    """Health check endpoint."""
    return {
        "status": "online",
        "service": "Blacksky Chatbot (Cloud)",
        "version": "2.0.0"
    }


@app.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    """Send a message and get a response."""
    if not request.message.strip():
        raise HTTPException(status_code=400, detail="Message cannot be empty")
    
    start = time.time()
    response = bot.chat(request.message)
    elapsed = (time.time() - start) * 1000
    
    return ChatResponse(
        response=response,
        response_time_ms=round(elapsed, 2)
    )


@app.post("/chat/stream")
async def chat_stream(request: ChatRequest):
    """Send a message and get a streaming response."""
    if not request.message.strip():
        raise HTTPException(status_code=400, detail="Message cannot be empty")
    
    async def generate():
        try:
            for token in bot.chat_stream(request.message):
                yield f"data: {json.dumps({'token': token})}\n\n"
            yield "data: [DONE]\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'error': str(e)})}\n\n"
    
    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        }
    )


@app.post("/clear")
async def clear():
    """Clear conversation history."""
    message = bot.clear_history()
    return {"message": message}


@app.get("/stats")
async def stats():
    """Get chatbot stats."""
    return bot.get_stats()


# RAG endpoints
@app.get("/documents")
async def list_documents():
    """List index stats."""
    if not bot.doc_store:
        raise HTTPException(status_code=400, detail="RAG not enabled")
    return bot.doc_store.get_stats()


@app.post("/documents/reload")
async def reload_documents():
    """Reload all documents from the documents directory."""
    if not bot.doc_store:
        raise HTTPException(status_code=400, detail="RAG not enabled")
    
    count = bot.doc_store.load_all_documents()
    return {
        "message": f"Loaded {count} chunks",
        "stats": bot.doc_store.get_stats()
    }


@app.post("/documents/upload")
async def upload_document(file: UploadFile = File(...)):
    """Upload a new document."""
    if not bot.doc_store:
        raise HTTPException(status_code=400, detail="RAG not enabled")
    
    if not file.filename.endswith(('.txt', '.md')):
        raise HTTPException(status_code=400, detail="Only .txt and .md files supported")
    
    filepath = DOCS_DIR / file.filename
    content = await file.read()
    filepath.write_bytes(content)
    
    chunks = bot.doc_store.add_document(filepath)
    
    return {
        "message": f"Uploaded and indexed {file.filename}",
        "chunks": chunks
    }


@app.delete("/documents")
async def clear_documents():
    """Clear all indexed documents."""
    if not bot.doc_store:
        raise HTTPException(status_code=400, detail="RAG not enabled")
    
    bot.doc_store.clear()
    return {"message": "All documents cleared"}


# Static files and demo page
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.get("/demo")
async def demo_page():
    """Serve the demo page."""
    demo_file = STATIC_DIR / "demo.html"
    if demo_file.exists():
        return FileResponse(demo_file)
    raise HTTPException(status_code=404, detail="Demo page not found. Add static/demo.html")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "server:app",
        host=HOST,
        port=PORT,
        reload=False,
        workers=1
    )
