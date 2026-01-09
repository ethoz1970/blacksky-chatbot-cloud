"""
FastAPI server for Blacksky Chatbot (Cloud Version)
"""
from fastapi import FastAPI, HTTPException, UploadFile, File, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, StreamingResponse, HTMLResponse
from pydantic import BaseModel
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional, List
import asyncio
import time
import json

from chatbot import BlackskyChatbot
from config import HOST, PORT, DOCS_DIR, ADMIN_PASSWORD
from database import (
    init_db, get_or_create_user, update_user, save_conversation,
    get_user_context, get_leads, lookup_users_by_name, link_users
)

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

    # Initialize database for memory system
    db_ok = init_db()
    if db_ok:
        print("Memory system enabled.")
    else:
        print("Memory system disabled (no DATABASE_URL).")

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
    user_id: Optional[str] = None
    potential_matches: Optional[List[dict]] = None  # For user verification


class ChatResponse(BaseModel):
    response: str
    response_time_ms: float


class ConversationEndRequest(BaseModel):
    user_id: str
    messages: List[dict]


class UserUpdateRequest(BaseModel):
    user_id: str
    name: Optional[str] = None
    email: Optional[str] = None
    company: Optional[str] = None


class UserLookupRequest(BaseModel):
    name: str


class UserLinkRequest(BaseModel):
    current_user_id: str
    target_user_id: str


@app.get("/")
async def root():
    """Health check endpoint."""
    return {
        "status": "online",
        "service": "Blacksky Chatbot (Cloud)",
        "version": "2.0.0"
    }


@app.get("/health/db")
async def db_health():
    """Check database connection."""
    from sqlalchemy import text
    from database import get_session, DATABASE_URL

    if not DATABASE_URL:
        return {"status": "disabled", "reason": "DATABASE_URL not set"}

    session = get_session()
    if session is None:
        return {"status": "error", "reason": "Could not create session"}

    try:
        # Try a simple query
        session.execute(text("SELECT 1"))
        session.close()
        return {"status": "connected", "database": "postgresql"}
    except Exception as e:
        return {"status": "error", "reason": str(e)}


@app.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    """Send a message and get a response."""
    if not request.message.strip():
        raise HTTPException(status_code=400, detail="Message cannot be empty")

    # Get user context if user_id provided
    user_context = None
    if request.user_id:
        get_or_create_user(request.user_id)
        user_context = get_user_context(request.user_id)

    start = time.time()
    response = bot.chat(
        request.message,
        user_context=user_context,
        potential_matches=request.potential_matches
    )
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

    # Get user context if user_id provided
    user_context = None
    if request.user_id:
        get_or_create_user(request.user_id)
        user_context = get_user_context(request.user_id)

    async def generate():
        try:
            for token in bot.chat_stream(
                request.message,
                user_context=user_context,
                potential_matches=request.potential_matches
            ):
                yield f"data: {json.dumps({'token': token})}\n\n"
                await asyncio.sleep(0)  # Flush to client immediately
            yield "data: [DONE]\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'error': str(e)})}\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
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


# Memory system endpoints
@app.post("/conversation/end")
async def end_conversation(request: ConversationEndRequest):
    """Save conversation when user leaves or after inactivity."""
    if not request.user_id or not request.messages:
        raise HTTPException(status_code=400, detail="user_id and messages required")

    # Extract and save user's name and email if they provided them
    extracted_name = extract_user_name(request.messages)
    extracted_email = extract_user_email(request.messages)
    if extracted_name or extracted_email:
        update_user(request.user_id, name=extracted_name, email=extracted_email)

    # Calculate lead score based on messages
    lead_score = calculate_lead_score(request.messages)

    # Generate summary if lead score is high enough
    summary = None
    interests = []
    if lead_score >= 2:
        summary = generate_summary(request.messages)
        interests = extract_interests(request.messages)

    # Save to database
    conv_id = save_conversation(
        user_id=request.user_id,
        messages=request.messages,
        summary=summary,
        interests=interests,
        lead_score=lead_score
    )

    return {
        "saved": conv_id is not None,
        "conversation_id": conv_id,
        "lead_score": lead_score,
        "name_extracted": extracted_name,
        "email_extracted": extracted_email
    }


@app.post("/user/update")
async def update_user_info(request: UserUpdateRequest):
    """Update user name, email, or company."""
    result = update_user(
        user_id=request.user_id,
        name=request.name,
        email=request.email,
        company=request.company
    )
    if result is None:
        raise HTTPException(status_code=404, detail="User not found")
    return result


@app.post("/user/lookup")
async def lookup_user(request: UserLookupRequest):
    """Look up users by name for verification."""
    if not request.name or len(request.name) < 2:
        raise HTTPException(status_code=400, detail="Name must be at least 2 characters")

    matches = lookup_users_by_name(request.name)
    return {
        "matches": matches,
        "count": len(matches)
    }


@app.post("/user/link")
async def link_user_sessions(request: UserLinkRequest):
    """Link current session to an existing user (merge identities)."""
    if not request.current_user_id or not request.target_user_id:
        raise HTTPException(status_code=400, detail="Both user IDs required")

    success = link_users(request.current_user_id, request.target_user_id)
    if not success:
        raise HTTPException(status_code=400, detail="Failed to link users")

    return {
        "success": True,
        "merged": True,
        "new_user_id": request.target_user_id
    }


@app.get("/admin")
async def admin_page(password: str = Query(...)):
    """Admin dashboard for viewing leads."""
    if password != ADMIN_PASSWORD:
        raise HTTPException(status_code=401, detail="Unauthorized")

    leads = get_leads(limit=50)

    # Generate simple HTML dashboard
    html = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Maurice Leads Dashboard</title>
        <style>
            body { font-family: 'IBM Plex Mono', monospace; background: #0a0a0a; color: #e0e0e0; padding: 32px; }
            h1 { color: #666; font-size: 14px; letter-spacing: 0.1em; text-transform: uppercase; }
            table { width: 100%; border-collapse: collapse; margin-top: 24px; }
            th { text-align: left; padding: 12px; border-bottom: 1px solid #333; color: #666; font-size: 11px; letter-spacing: 0.1em; text-transform: uppercase; }
            td { padding: 12px; border-bottom: 1px solid #222; }
            tr:hover { background: #111; }
            .score { display: inline-block; padding: 4px 8px; border-radius: 4px; font-size: 12px; }
            .score-1 { background: #1a1a1a; color: #666; }
            .score-2 { background: #1a2a1a; color: #6a6; }
            .score-3 { background: #2a2a1a; color: #aa6; }
            .score-4 { background: #2a1a1a; color: #a66; }
            .score-5 { background: #3a1a1a; color: #f66; }
            .summary { font-size: 12px; color: #888; margin-top: 8px; }
            .interests { font-size: 11px; color: #666; }
            .interest-tag { background: #1a1a1a; padding: 2px 6px; border-radius: 2px; margin-right: 4px; }
        </style>
    </head>
    <body>
        <h1>Maurice Leads Dashboard</h1>
        <table>
            <tr>
                <th>Score</th>
                <th>Name</th>
                <th>Email</th>
                <th>Company</th>
                <th>Last Topic</th>
                <th>Last Seen</th>
            </tr>
    """

    for lead in leads:
        score = lead.get('lead_score', 1)
        score_color = "#4a4" if score >= 3 else "#aa4" if score >= 2 else "#666"
        last_seen = lead.get('last_seen', '')[:10] if lead.get('last_seen') else '-'
        last_summary = lead.get('last_summary') or '-'
        if len(last_summary) > 50:
            last_summary = last_summary[:50] + '...'

        html += f"""
            <tr>
                <td style="color: {score_color}; font-weight: bold;">{score}</td>
                <td>{lead.get('name', 'Anonymous')}</td>
                <td>{lead.get('email') or '-'}</td>
                <td>{lead.get('company') or '-'}</td>
                <td style="color: #888;">{last_summary}</td>
                <td style="color: #666;">{last_seen}</td>
            </tr>
        """

    html += """
        </table>
    </body>
    </html>
    """

    return HTMLResponse(content=html)


def calculate_lead_score(messages: list) -> int:
    """Score 1-5 based on intent signals."""
    high_intent_phrases = [
        "pricing", "cost", "how much", "price",
        "availability", "schedule", "call", "meeting",
        "hire", "work with", "engagement", "contract",
        "proposal", "quote", "budget", "rate"
    ]

    medium_intent_phrases = [
        "can you help", "do you do", "services",
        "experience with", "worked on", "portfolio",
        "timeline", "how long", "project"
    ]

    text = " ".join([m.get("content", "").lower() for m in messages if m.get("role") == "user"])

    score = 1
    if any(phrase in text for phrase in high_intent_phrases):
        score = 4
    elif any(phrase in text for phrase in medium_intent_phrases):
        score = 2

    # Check if they provided personal info (name mentioned)
    if any(m.get("role") == "user" and ("my name is" in m.get("content", "").lower() or "i'm " in m.get("content", "").lower()) for m in messages):
        score = min(score + 1, 5)

    return score


def generate_summary(messages: list) -> str:
    """Generate a brief summary of the conversation."""
    try:
        # Use the chatbot to generate a summary
        conversation_text = "\n".join([
            f"{m.get('role', 'user').title()}: {m.get('content', '')}"
            for m in messages[-10:]  # Last 10 messages max
        ])

        prompt = f"Summarize this conversation in one sentence, focusing on what the user was interested in:\n\n{conversation_text}"

        response = bot.client.chat.completions.create(
            model="meta-llama/Meta-Llama-3.1-70B-Instruct-Turbo",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=60,
            temperature=0.3
        )

        return response.choices[0].message.content.strip()
    except Exception as e:
        print(f"Summary generation failed: {e}")
        return None


def extract_user_name(messages: list) -> str:
    """Extract user's name from conversation if they provided it."""
    import re

    name_patterns = [
        r"(?:my name is|i'm|i am|call me|this is)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)",
        r"^([A-Z][a-z]+)(?:\s+here)?[.!]?$",  # Just "John" or "John here"
    ]

    for msg in messages:
        if msg.get("role") != "user":
            continue

        text = msg.get("content", "").strip()

        for pattern in name_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                name = match.group(1).strip()
                # Basic validation - should be 2-30 chars, no numbers
                if 2 <= len(name) <= 30 and not any(c.isdigit() for c in name):
                    return name.title()

    return None


def extract_user_email(messages: list) -> str:
    """Extract user's email from conversation if they provided it."""
    import re

    # Standard email regex
    email_pattern = r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'

    for msg in messages:
        if msg.get("role") != "user":
            continue

        text = msg.get("content", "")
        match = re.search(email_pattern, text)
        if match:
            return match.group(0).lower()

    return None


def extract_interests(messages: list) -> list:
    """Extract topic keywords from conversation."""
    keywords = {
        "ai": ["ai", "machine learning", "ml", "llm", "chatbot", "artificial intelligence"],
        "cloud": ["cloud", "aws", "azure", "kubernetes", "devops", "infrastructure"],
        "drupal": ["drupal", "cms", "content management"],
        "federal": ["federal", "government", "agency", "treasury", "nih", "fda"],
        "enterprise": ["enterprise", "fortune 500", "large scale"],
        "security": ["security", "clearance", "compliance", "fisma"],
        "migration": ["migration", "upgrade", "modernization"]
    }

    text = " ".join([m.get("content", "").lower() for m in messages])
    found = []

    for topic, phrases in keywords.items():
        if any(phrase in text for phrase in phrases):
            found.append(topic)

    return found[:5]  # Max 5 interests


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
