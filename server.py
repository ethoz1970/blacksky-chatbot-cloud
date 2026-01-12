"""
FastAPI server for Blacksky Chatbot (Cloud Version)
"""
from fastapi import FastAPI, HTTPException, UploadFile, File, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, StreamingResponse, HTMLResponse, RedirectResponse
from pydantic import BaseModel
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional, List
import asyncio
import time
import json
import re
import uuid
from datetime import datetime, timedelta

from authlib.integrations.starlette_client import OAuth
from starlette.middleware.sessions import SessionMiddleware
import jwt

from chatbot import BlackskyChatbot
from config import (
    HOST, PORT, DOCS_DIR, ADMIN_PASSWORD, ANTHROPIC_MODEL,
    GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, GOOGLE_REDIRECT_URI, SESSION_SECRET_KEY
)
from database import (
    init_db, get_or_create_user, update_user, save_conversation, update_conversation,
    get_user_context, get_leads, lookup_users_by_name, link_users,
    get_lead_details, update_lead_status, update_lead_notes, get_user_conversations,
    delete_user, get_analytics, get_user_by_google_id, create_google_user, link_google_account
)

# Paths
STATIC_DIR = Path(__file__).parent / "static"
STATIC_DIR.mkdir(exist_ok=True)

# Global chatbot instance
bot = BlackskyChatbot(use_rag=True)


def run_migrations():
    """Run database migrations to add new columns if they don't exist."""
    from database import get_session
    from sqlalchemy import text

    session = get_session()
    if session is None:
        return

    try:
        # Add status column if it doesn't exist
        session.execute(text("""
            ALTER TABLE users ADD COLUMN IF NOT EXISTS status VARCHAR(20) DEFAULT 'new'
        """))

        # Add notes column if it doesn't exist
        session.execute(text("""
            ALTER TABLE users ADD COLUMN IF NOT EXISTS notes TEXT
        """))

        # Add phone column if it doesn't exist
        session.execute(text("""
            ALTER TABLE users ADD COLUMN IF NOT EXISTS phone VARCHAR(50)
        """))

        session.commit()
        print("Database migrations complete.")
    except Exception as e:
        print(f"Migration error (may be normal if columns exist): {e}")
        session.rollback()
    finally:
        session.close()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize on startup."""
    print("Starting Blacksky Chatbot Server (Cloud)...")
    bot.initialize()

    # Initialize database for memory system
    db_ok = init_db()
    if db_ok:
        print("Memory system enabled.")
        # Run migrations to add any new columns
        run_migrations()
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

# Session middleware for OAuth
app.add_middleware(SessionMiddleware, secret_key=SESSION_SECRET_KEY)

# Google OAuth configuration
oauth = OAuth()
if GOOGLE_CLIENT_ID:
    oauth.register(
        name='google',
        client_id=GOOGLE_CLIENT_ID,
        client_secret=GOOGLE_CLIENT_SECRET,
        server_metadata_url='https://accounts.google.com/.well-known/openid-configuration',
        client_kwargs={'scope': 'openid email profile'}
    )


# JWT token utilities
def create_auth_token(user_id: str, google_id: str) -> str:
    """Create JWT token for authenticated session."""
    payload = {
        'user_id': user_id,
        'google_id': google_id,
        'exp': datetime.utcnow() + timedelta(days=30),
        'iat': datetime.utcnow()
    }
    return jwt.encode(payload, SESSION_SECRET_KEY, algorithm='HS256')


def decode_auth_token(token: str) -> Optional[dict]:
    """Decode and verify JWT token."""
    try:
        payload = jwt.decode(token, SESSION_SECRET_KEY, algorithms=['HS256'])
        return payload
    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        return None


class ChatRequest(BaseModel):
    message: str = ""
    user_id: Optional[str] = None
    potential_matches: Optional[List[dict]] = None  # For user verification
    introduce: Optional[bool] = False  # Flag to trigger Maurice introduction


class ChatResponse(BaseModel):
    response: str
    response_time_ms: float


class ConversationEndRequest(BaseModel):
    user_id: str
    messages: List[dict]
    conversation_id: Optional[int] = None  # If provided, update existing; otherwise create new


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
    # Handle introduction request (Sign In flow)
    if request.introduce:
        message = "[SYSTEM: The user just clicked 'Sign In'. Introduce yourself briefly as Maurice from Blacksky, and ask for their name so you can remember them next time. Keep it warm and concise.]"
    elif not request.message.strip():
        raise HTTPException(status_code=400, detail="Message cannot be empty")
    else:
        message = request.message

    # Get user context if user_id provided
    user_context = None
    if request.user_id:
        get_or_create_user(request.user_id)
        user_context = get_user_context(request.user_id)

    async def generate():
        try:
            for token in bot.chat_stream(
                message,
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
    print(f"[DEBUG] /conversation/end called - user_id: {request.user_id}, messages: {len(request.messages) if request.messages else 0}, conv_id: {request.conversation_id}")

    if not request.user_id or not request.messages:
        raise HTTPException(status_code=400, detail="user_id and messages required")

    # Ensure user exists before saving conversation (required for PostgreSQL foreign key)
    get_or_create_user(request.user_id)

    # Extract and save user's name, email, phone, and company if they provided them
    extracted_name = extract_user_name(request.messages)
    extracted_email = extract_user_email(request.messages)
    extracted_phone = extract_user_phone(request.messages)
    extracted_company = extract_user_company(request.messages)
    if extracted_name or extracted_email or extracted_phone or extracted_company:
        update_user(request.user_id, name=extracted_name, email=extracted_email, phone=extracted_phone, company=extracted_company)

    # Calculate lead score based on messages
    lead_score = calculate_lead_score(request.messages)
    print(f"[DEBUG] Lead score: {lead_score}")

    # Generate summary if lead score is high enough
    summary = None
    interests = []
    if lead_score >= 2:
        summary = generate_summary(request.messages)
        interests = extract_interests(request.messages)

    # Save or update conversation
    if request.conversation_id:
        # Update existing conversation
        print(f"[DEBUG] Updating existing conversation {request.conversation_id}")
        success = update_conversation(
            conversation_id=request.conversation_id,
            messages=request.messages,
            summary=summary,
            interests=interests,
            lead_score=lead_score
        )
        conv_id = request.conversation_id if success else None
        status = "updated" if success else "update_failed"
    else:
        # Create new conversation
        print(f"[DEBUG] Creating new conversation for user {request.user_id}")
        conv_id = save_conversation(
            user_id=request.user_id,
            messages=request.messages,
            summary=summary,
            interests=interests,
            lead_score=lead_score
        )
        status = "saved" if conv_id else "save_failed"

    print(f"[DEBUG] Result: status={status}, conv_id={conv_id}")

    return {
        "status": status,
        "conversation_id": conv_id,
        "lead_score": lead_score,
        "name_extracted": extracted_name,
        "email_extracted": extracted_email,
        "phone_extracted": extracted_phone,
        "company_extracted": extracted_company
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


@app.get("/user/{user_id}/context")
async def get_user_context_endpoint(user_id: str):
    """Get user context for avatar display."""
    context = get_user_context(user_id)
    if context is None:
        return {"name": None, "is_returning": False}
    return {
        "name": context.get("name"),
        "email": context.get("email"),
        "phone": context.get("phone"),
        "company": context.get("company"),
        "is_returning": context.get("is_returning", False),
        "conversation_count": context.get("conversation_count", 0),
        "auth_method": context.get("auth_method"),
        "google_picture": context.get("google_picture")
    }


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
async def admin_dashboard(password: str = Query(None)):
    """Admin dashboard for viewing leads."""
    if password != ADMIN_PASSWORD:
        return HTMLResponse("""
            <html>
            <head><title>Maurice's Leads</title></head>
            <body style="font-family: monospace; background: #0a0a0a; color: #e0e0e0; padding: 40px;">
                <h1>Maurice's Leads Dashboard</h1>
                <form method="get">
                    <input type="password" name="password" placeholder="Password"
                           style="padding: 8px; font-family: monospace; background: #1a1a1a; color: #e0e0e0; border: 1px solid #333;">
                    <button type="submit" style="padding: 8px 16px; font-family: monospace; background: #333; color: #e0e0e0; border: none; cursor: pointer;">
                        Enter
                    </button>
                </form>
            </body>
            </html>
        """)

    leads = get_leads(limit=100)
    analytics = get_analytics()

    # Build HTML table rows
    rows = ""
    for lead in leads:
        score = lead.get('lead_score', 1)
        score_color = "#4a4" if score >= 3 else "#aa4" if score >= 2 else "#666"
        status = lead.get('status') or 'new'
        status_colors = {"new": "#666", "contacted": "#68d", "qualified": "#da6", "converted": "#6d6", "archived": "#888"}
        status_color = status_colors.get(status, "#666")
        notes_preview = (lead.get('notes') or '')[:30]
        if len(lead.get('notes') or '') > 30:
            notes_preview += '...'
        email = lead.get('email') or ''
        email_btn = f'<a href="mailto:{email}" class="action-btn" title="Send email">@</a>' if email else ''

        rows += f"""
            <tr class="lead-row" data-id="{lead['id']}" data-name="{lead['name']}" data-email="{email}" data-company="{lead.get('company') or ''}" data-status="{status}" data-score="{score}">
                <td style="color: {score_color}; font-weight: bold;">{score}</td>
                <td class="clickable" onclick="showConversations('{lead['id']}')">{lead['name']}</td>
                <td>{email_btn} {email or '-'}</td>
                <td>{lead.get('company') or '-'}</td>
                <td>
                    <select class="status-select" data-id="{lead['id']}" onchange="updateStatus('{lead['id']}', this.value)" style="background: #1a1a1a; color: {status_color}; border: 1px solid #333; padding: 4px; border-radius: 4px;">
                        <option value="new" {"selected" if status == "new" else ""}>New</option>
                        <option value="contacted" {"selected" if status == "contacted" else ""}>Contacted</option>
                        <option value="qualified" {"selected" if status == "qualified" else ""}>Qualified</option>
                        <option value="converted" {"selected" if status == "converted" else ""}>Converted</option>
                        <option value="archived" {"selected" if status == "archived" else ""}>Archived</option>
                    </select>
                </td>
                <td class="notes-cell clickable" onclick="editNotes('{lead['id']}')" title="Click to edit notes">{notes_preview or '<span style="color:#444">+ Add</span>'}</td>
                <td style="color: #666;">{lead['last_seen'][:10] if lead.get('last_seen') else '-'}</td>
                <td class="actions-cell">
                    <button class="action-btn delete-btn" onclick="deleteLead('{lead['id']}', '{lead['name']}')" title="Delete lead">X</button>
                </td>
            </tr>
        """

    # Analytics stats
    stats = analytics.get('status_counts', {})
    total = analytics.get('total_leads', 0)
    avg_score = analytics.get('avg_score', 0)
    this_week = analytics.get('leads_this_week', 0)

    return HTMLResponse(f"""
        <html>
        <head>
            <title>Maurice's Leads (Cloud)</title>
            <style>
                body {{ font-family: 'IBM Plex Mono', monospace; background: #0a0a0a; color: #e0e0e0; padding: 40px; }}
                h1 {{ color: #888; font-weight: normal; display: inline; }}
                .header {{ display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px; }}
                .actions {{ display: flex; gap: 10px; }}
                .btn {{ padding: 8px 16px; font-family: monospace; background: #333; color: #e0e0e0; border: none; cursor: pointer; border-radius: 4px; }}
                .btn:hover {{ background: #444; }}
                .btn-primary {{ background: #2a4a2a; color: #6f6; }}
                .stats-bar {{ display: flex; gap: 20px; padding: 15px 0; border-bottom: 1px solid #222; margin-bottom: 15px; flex-wrap: wrap; }}
                .stat {{ text-align: center; }}
                .stat-value {{ font-size: 1.5rem; font-weight: bold; }}
                .stat-label {{ font-size: 0.7rem; color: #666; text-transform: uppercase; letter-spacing: 0.1em; }}
                .stat-new .stat-value {{ color: #666; }}
                .stat-contacted .stat-value {{ color: #68d; }}
                .stat-qualified .stat-value {{ color: #da6; }}
                .stat-converted .stat-value {{ color: #6d6; }}
                .filters {{ display: flex; gap: 15px; margin-bottom: 15px; align-items: center; flex-wrap: wrap; }}
                .filter-input {{ padding: 8px 12px; font-family: monospace; background: #1a1a1a; color: #e0e0e0; border: 1px solid #333; border-radius: 4px; }}
                .filter-input:focus {{ outline: none; border-color: #555; }}
                table {{ border-collapse: collapse; width: 100%; }}
                th, td {{ padding: 10px; text-align: left; border-bottom: 1px solid #222; }}
                th {{ color: #666; font-weight: normal; text-transform: uppercase; font-size: 0.7rem; letter-spacing: 0.1em; }}
                tr:hover {{ background: #111; }}
                tr.hidden {{ display: none; }}
                .clickable {{ cursor: pointer; }}
                .clickable:hover {{ text-decoration: underline; color: #68d; }}
                .cloud-badge {{ background: #2a3a4a; color: #6af; padding: 4px 8px; border-radius: 4px; font-size: 0.75rem; margin-left: 10px; }}
                .action-btn {{ background: none; border: none; color: #666; cursor: pointer; padding: 4px 8px; font-family: monospace; border-radius: 4px; }}
                .action-btn:hover {{ background: #333; color: #fff; }}
                .delete-btn:hover {{ background: #533; color: #f66; }}
                .modal {{ display: none; position: fixed; top: 0; left: 0; width: 100%; height: 100%; background: rgba(0,0,0,0.8); z-index: 1000; }}
                .modal-content {{ background: #1a1a1a; margin: 5% auto; padding: 30px; width: 80%; max-width: 800px; max-height: 80vh; overflow-y: auto; border-radius: 8px; border: 1px solid #333; }}
                .modal-header {{ display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px; }}
                .modal-close {{ font-size: 24px; cursor: pointer; color: #666; }}
                .modal-close:hover {{ color: #fff; }}
                .message {{ padding: 10px; margin: 8px 0; border-radius: 4px; }}
                .message-user {{ background: #1a2a3a; border-left: 3px solid #68d; }}
                .message-assistant {{ background: #1a1a1a; border-left: 3px solid #666; }}
                .message-role {{ font-size: 0.75rem; color: #666; margin-bottom: 4px; }}
                .notes-textarea {{ width: 100%; height: 150px; background: #0a0a0a; color: #e0e0e0; border: 1px solid #333; padding: 10px; font-family: monospace; border-radius: 4px; resize: vertical; }}
                .conversation-date {{ color: #666; font-size: 0.8rem; margin-top: 20px; padding-top: 10px; border-top: 1px solid #333; }}
            </style>
        </head>
        <body>
            <div class="header">
                <div>
                    <h1>Maurice's Leads Dashboard</h1>
                    <span class="cloud-badge">CLOUD</span>
                </div>
                <div class="actions">
                    <button class="btn btn-primary" onclick="exportCSV()">Export CSV</button>
                </div>
            </div>

            <!-- Analytics Stats -->
            <div class="stats-bar">
                <div class="stat">
                    <div class="stat-value">{total}</div>
                    <div class="stat-label">Total</div>
                </div>
                <div class="stat stat-new">
                    <div class="stat-value">{stats.get('new', 0)}</div>
                    <div class="stat-label">New</div>
                </div>
                <div class="stat stat-contacted">
                    <div class="stat-value">{stats.get('contacted', 0)}</div>
                    <div class="stat-label">Contacted</div>
                </div>
                <div class="stat stat-qualified">
                    <div class="stat-value">{stats.get('qualified', 0)}</div>
                    <div class="stat-label">Qualified</div>
                </div>
                <div class="stat stat-converted">
                    <div class="stat-value">{stats.get('converted', 0)}</div>
                    <div class="stat-label">Converted</div>
                </div>
                <div class="stat">
                    <div class="stat-value">{avg_score}</div>
                    <div class="stat-label">Avg Score</div>
                </div>
                <div class="stat">
                    <div class="stat-value">{this_week}</div>
                    <div class="stat-label">This Week</div>
                </div>
            </div>

            <!-- Search & Filters -->
            <div class="filters">
                <input type="text" id="searchInput" class="filter-input" placeholder="Search name, email, company..." oninput="filterTable()" style="width: 250px;">
                <select id="statusFilter" class="filter-input" onchange="filterTable()">
                    <option value="">All Statuses</option>
                    <option value="new">New</option>
                    <option value="contacted">Contacted</option>
                    <option value="qualified">Qualified</option>
                    <option value="converted">Converted</option>
                    <option value="archived">Archived</option>
                </select>
                <select id="scoreFilter" class="filter-input" onchange="filterTable()">
                    <option value="">All Scores</option>
                    <option value="3">Score 3+</option>
                    <option value="2">Score 2+</option>
                    <option value="1">Score 1+</option>
                </select>
                <span id="resultCount" style="color: #666; font-size: 0.85rem;"></span>
            </div>

            <table>
                <thead>
                    <tr>
                        <th>Score</th>
                        <th>Name</th>
                        <th>Email</th>
                        <th>Company</th>
                        <th>Status</th>
                        <th>Notes</th>
                        <th>Last Seen</th>
                        <th></th>
                    </tr>
                </thead>
                <tbody id="leadsTable">
                    {rows if rows else '<tr><td colspan="8" style="color: #666; text-align: center;">No leads yet. Start chatting!</td></tr>'}
                </tbody>
            </table>

            <!-- Conversation Modal -->
            <div id="convModal" class="modal" onclick="if(event.target===this)closeModal('convModal')">
                <div class="modal-content">
                    <div class="modal-header">
                        <h2 id="convModalTitle">Conversations</h2>
                        <span class="modal-close" onclick="closeModal('convModal')">&times;</span>
                    </div>
                    <div id="convModalBody"></div>
                </div>
            </div>

            <!-- Notes Modal -->
            <div id="notesModal" class="modal" onclick="if(event.target===this)closeModal('notesModal')">
                <div class="modal-content">
                    <div class="modal-header">
                        <h2>Edit Notes</h2>
                        <span class="modal-close" onclick="closeModal('notesModal')">&times;</span>
                    </div>
                    <textarea id="notesTextarea" class="notes-textarea" placeholder="Add notes about this lead..."></textarea>
                    <div style="margin-top: 15px; text-align: right;">
                        <button class="btn" onclick="closeModal('notesModal')">Cancel</button>
                        <button class="btn btn-primary" onclick="saveNotes()" style="margin-left: 10px;">Save Notes</button>
                    </div>
                </div>
            </div>

            <script>
                const PASSWORD = '{password}';
                let currentLeadId = null;

                function filterTable() {{
                    const search = document.getElementById('searchInput').value.toLowerCase();
                    const statusFilter = document.getElementById('statusFilter').value;
                    const scoreFilter = parseInt(document.getElementById('scoreFilter').value) || 0;

                    const rows = document.querySelectorAll('#leadsTable .lead-row');
                    let visibleCount = 0;

                    rows.forEach(row => {{
                        const name = row.dataset.name.toLowerCase();
                        const email = row.dataset.email.toLowerCase();
                        const company = row.dataset.company.toLowerCase();
                        const status = row.dataset.status;
                        const score = parseInt(row.dataset.score);

                        const matchesSearch = !search || name.includes(search) || email.includes(search) || company.includes(search);
                        const matchesStatus = !statusFilter || status === statusFilter;
                        const matchesScore = !scoreFilter || score >= scoreFilter;

                        if (matchesSearch && matchesStatus && matchesScore) {{
                            row.classList.remove('hidden');
                            visibleCount++;
                        }} else {{
                            row.classList.add('hidden');
                        }}
                    }});

                    document.getElementById('resultCount').textContent = `Showing ${{visibleCount}} of ${{rows.length}}`;
                }}

                async function deleteLead(userId, name) {{
                    if (!confirm(`Delete "${{name}}" and all their conversations?`)) return;

                    const resp = await fetch(`/admin/lead/${{userId}}?password=${{PASSWORD}}`, {{
                        method: 'DELETE'
                    }});
                    if (resp.ok) {{
                        document.querySelector(`tr[data-id="${{userId}}"]`).remove();
                        filterTable();
                    }} else {{
                        alert('Failed to delete lead');
                    }}
                }}

                async function showConversations(userId) {{
                    const resp = await fetch(`/admin/lead/${{userId}}?password=${{PASSWORD}}`);
                    if (!resp.ok) {{ alert('Failed to load conversations'); return; }}
                    const data = await resp.json();

                    document.getElementById('convModalTitle').textContent = data.name + "'s Conversations";

                    let html = '';
                    if (data.conversations && data.conversations.length > 0) {{
                        for (const conv of data.conversations) {{
                            html += `<div class="conversation-date">Conversation on ${{conv.created_at ? conv.created_at.slice(0,10) : 'Unknown'}}</div>`;
                            if (conv.messages && conv.messages.length > 0) {{
                                for (const msg of conv.messages) {{
                                    const roleClass = msg.role === 'user' ? 'message-user' : 'message-assistant';
                                    const roleLabel = msg.role === 'user' ? 'User' : 'Maurice';
                                    html += `<div class="message ${{roleClass}}"><div class="message-role">${{roleLabel}}</div>${{msg.content}}</div>`;
                                }}
                            }} else {{
                                html += '<p style="color:#666">No messages recorded</p>';
                            }}
                        }}
                    }} else {{
                        html = '<p style="color:#666">No conversations yet</p>';
                    }}

                    document.getElementById('convModalBody').innerHTML = html;
                    document.getElementById('convModal').style.display = 'block';
                }}

                function editNotes(userId) {{
                    currentLeadId = userId;
                    const row = document.querySelector(`tr[data-id="${{userId}}"]`);
                    const notesCell = row.querySelector('.notes-cell');
                    const existingNotes = notesCell.textContent.includes('Add') ? '' : notesCell.textContent;
                    document.getElementById('notesTextarea').value = existingNotes.replace('...', '');
                    document.getElementById('notesModal').style.display = 'block';
                    document.getElementById('notesTextarea').focus();
                }}

                async function saveNotes() {{
                    const notes = document.getElementById('notesTextarea').value;
                    const resp = await fetch(`/admin/lead/${{currentLeadId}}/notes?password=${{PASSWORD}}&notes=${{encodeURIComponent(notes)}}`, {{
                        method: 'POST'
                    }});
                    if (resp.ok) {{
                        const row = document.querySelector(`tr[data-id="${{currentLeadId}}"]`);
                        const notesCell = row.querySelector('.notes-cell');
                        const preview = notes.length > 30 ? notes.slice(0, 30) + '...' : notes;
                        notesCell.innerHTML = preview || '<span style="color:#444">+ Add</span>';
                        closeModal('notesModal');
                    }} else {{
                        alert('Failed to save notes');
                    }}
                }}

                async function updateStatus(userId, status) {{
                    const resp = await fetch(`/admin/lead/${{userId}}/status?password=${{PASSWORD}}&status=${{status}}`, {{
                        method: 'POST'
                    }});
                    if (!resp.ok) {{
                        alert('Failed to update status');
                    }}
                    const colors = {{"new": "#666", "contacted": "#68d", "qualified": "#da6", "converted": "#6d6", "archived": "#888"}};
                    const select = document.querySelector(`select[data-id="${{userId}}"]`);
                    select.style.color = colors[status] || '#666';
                    // Update data attribute for filtering
                    document.querySelector(`tr[data-id="${{userId}}"]`).dataset.status = status;
                }}

                function exportCSV() {{
                    window.location.href = `/admin/export?password=${{PASSWORD}}`;
                }}

                function closeModal(id) {{
                    document.getElementById(id).style.display = 'none';
                }}

                document.addEventListener('keydown', (e) => {{
                    if (e.key === 'Escape') {{
                        closeModal('convModal');
                        closeModal('notesModal');
                    }}
                }});

                // Initialize count
                filterTable();
            </script>
        </body>
        </html>
    """)


@app.get("/admin/lead/{user_id}")
async def get_lead(user_id: str, password: str = Query(...)):
    """Get full lead details including conversations."""
    if password != ADMIN_PASSWORD:
        raise HTTPException(status_code=401, detail="Unauthorized")

    lead = get_lead_details(user_id)
    if lead is None:
        raise HTTPException(status_code=404, detail="Lead not found")

    return lead


@app.post("/admin/lead/{user_id}/status")
async def set_lead_status(user_id: str, status: str, password: str = Query(...)):
    """Update lead status."""
    if password != ADMIN_PASSWORD:
        raise HTTPException(status_code=401, detail="Unauthorized")

    success = update_lead_status(user_id, status)
    if not success:
        raise HTTPException(status_code=400, detail="Failed to update status")

    return {"status": "updated", "new_status": status}


@app.post("/admin/lead/{user_id}/notes")
async def set_lead_notes(user_id: str, notes: str = "", password: str = Query(...)):
    """Update lead notes."""
    if password != ADMIN_PASSWORD:
        raise HTTPException(status_code=401, detail="Unauthorized")

    success = update_lead_notes(user_id, notes)
    if not success:
        raise HTTPException(status_code=400, detail="Failed to update notes")

    return {"status": "updated"}


@app.get("/admin/export")
async def export_leads(password: str = Query(...)):
    """Export leads as CSV."""
    if password != ADMIN_PASSWORD:
        raise HTTPException(status_code=401, detail="Unauthorized")

    leads = get_leads(limit=500)

    # Build CSV
    csv_lines = ["Name,Email,Company,Status,Score,Last Topic,Last Seen"]
    for lead in leads:
        name = (lead.get("name") or "").replace(",", ";")
        email = (lead.get("email") or "").replace(",", ";")
        company = (lead.get("company") or "").replace(",", ";")
        status = lead.get("status") or "new"
        score = lead.get("lead_score") or 1
        topic = (lead.get("last_summary") or "").replace(",", ";").replace("\n", " ")[:100]
        last_seen = (lead.get("last_seen") or "")[:10]
        csv_lines.append(f"{name},{email},{company},{status},{score},{topic},{last_seen}")

    csv_content = "\n".join(csv_lines)

    return StreamingResponse(
        iter([csv_content]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=maurice_leads.csv"}
    )


@app.delete("/admin/lead/{user_id}")
async def delete_lead(user_id: str, password: str = Query(...)):
    """Delete a lead and all their conversations."""
    if password != ADMIN_PASSWORD:
        raise HTTPException(status_code=401, detail="Unauthorized")

    success = delete_user(user_id)
    if not success:
        raise HTTPException(status_code=400, detail="Failed to delete lead")

    return {"status": "deleted"}


@app.delete("/admin/clear-all")
async def clear_all_data(password: str = Query(...)):
    """Clear all users and conversations from the database."""
    if password != ADMIN_PASSWORD:
        raise HTTPException(status_code=401, detail="Unauthorized")

    from database import get_session, User, Conversation
    session = get_session()
    if session is None:
        raise HTTPException(status_code=500, detail="Database not available")

    try:
        # Delete all conversations first (foreign key constraint)
        deleted_convs = session.query(Conversation).delete()
        # Delete all users
        deleted_users = session.query(User).delete()
        session.commit()
        return {"status": "cleared", "users_deleted": deleted_users, "conversations_deleted": deleted_convs}
    except Exception as e:
        session.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        session.close()


# ============================================================
# Google OAuth Endpoints
# ============================================================

@app.get("/auth/google/login")
async def google_login(request: Request, user_id: Optional[str] = None):
    """Initiate Google OAuth flow."""
    if not GOOGLE_CLIENT_ID:
        raise HTTPException(status_code=501, detail="Google OAuth not configured")

    # Store current user_id in session for potential account linking
    if user_id:
        request.session['pending_link_user_id'] = user_id

    return await oauth.google.authorize_redirect(request, GOOGLE_REDIRECT_URI)


@app.get("/auth/google/callback")
async def google_callback(request: Request):
    """Handle Google OAuth callback."""
    if not GOOGLE_CLIENT_ID:
        raise HTTPException(status_code=501, detail="Google OAuth not configured")

    try:
        token = await oauth.google.authorize_access_token(request)
        user_info = token.get('userinfo')

        if not user_info:
            raise HTTPException(status_code=400, detail="Failed to get user info from Google")

        google_id = user_info['sub']
        google_email = user_info.get('email', '')
        google_name = user_info.get('name', '')
        google_picture = user_info.get('picture', '')

        # Check if user already exists with this Google ID
        existing_user = get_user_by_google_id(google_id)

        if existing_user:
            # Returning Google user
            user_id = existing_user['id']
        else:
            # Check if there's a pending soft-login user to link
            pending_user_id = request.session.pop('pending_link_user_id', None)

            if pending_user_id:
                # Link Google account to existing soft-login user
                result = link_google_account(
                    user_id=pending_user_id,
                    google_id=google_id,
                    google_email=google_email,
                    google_name=google_name,
                    google_picture=google_picture
                )
                user_id = pending_user_id if result else str(uuid.uuid4())
            else:
                # Create new user with Google auth
                user_id = str(uuid.uuid4())
                create_google_user(
                    user_id=user_id,
                    google_id=google_id,
                    google_email=google_email,
                    google_name=google_name,
                    google_picture=google_picture
                )

        # Create auth token
        auth_token = create_auth_token(user_id, google_id)

        # Redirect back to demo page with token
        return RedirectResponse(
            url=f"/demo?auth_token={auth_token}",
            status_code=302
        )
    except Exception as e:
        print(f"Google OAuth error: {e}")
        return RedirectResponse(
            url="/demo?auth_error=failed",
            status_code=302
        )


class AuthTokenRequest(BaseModel):
    token: str


@app.post("/auth/verify")
async def verify_auth_token(request: AuthTokenRequest):
    """Verify auth token and return user info."""
    payload = decode_auth_token(request.token)

    if not payload:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    user_id = payload.get('user_id')
    google_id = payload.get('google_id')

    # Get full user info
    user = get_user_by_google_id(google_id)
    if user:
        return {
            "valid": True,
            "user_id": user['id'],
            "name": user['name'],
            "email": user['email'],
            "picture": user['google_picture'],
            "auth_method": user['auth_method']
        }

    raise HTTPException(status_code=404, detail="User not found")


@app.post("/auth/logout")
async def logout(request: Request):
    """Log out user (clear session)."""
    request.session.clear()
    return {"status": "logged_out"}


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

        response = bot.client.messages.create(
            model=ANTHROPIC_MODEL,
            max_tokens=60,
            messages=[{"role": "user", "content": prompt}]
        )

        return response.content[0].text.strip()
    except Exception as e:
        print(f"Summary generation failed: {e}")
        return None


def extract_user_name(messages: list) -> str:
    """Extract user's name from conversation if they provided it.

    Only matches explicit name declarations to avoid false positives.
    """
    import re

    # Common words that follow "I'm" but aren't names
    not_names = {
        'not', 'just', 'very', 'so', 'really', 'quite', 'pretty', 'too',
        'looking', 'interested', 'curious', 'wondering', 'trying', 'hoping',
        'here', 'back', 'new', 'happy', 'glad', 'sorry', 'sure', 'fine',
        'good', 'great', 'okay', 'ok', 'well', 'busy', 'free', 'available',
        'calling', 'writing', 'reaching', 'contacting', 'asking', 'inquiring',
        'a', 'an', 'the', 'your', 'their', 'his', 'her', 'our', 'my',
        'working', 'using', 'building', 'developing', 'creating', 'running'
    }

    # Only match explicit name patterns
    name_patterns = [
        r"(?:my name is|i'm|i am|call me|this is)\s+([A-Za-z]+(?:\s+[A-Za-z]+){0,2})",
    ]

    # Words that signal end of name
    stop_words = {'and', 'my', 'email', 'at', 'from', 'with', 'the', 'i', 'work', 'company'}

    for msg in messages:
        if msg.get("role") != "user":
            continue

        text = msg.get("content", "").strip()

        for pattern in name_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                name_part = match.group(1).strip()
                words = name_part.split()

                # Check if first word is a common non-name
                if words and words[0].lower() in not_names:
                    continue

                clean_words = []
                for word in words:
                    if word.lower() in stop_words:
                        break
                    clean_words.append(word)

                name = ' '.join(clean_words)
                if 2 <= len(name) <= 50 and not any(c.isdigit() for c in name) and len(clean_words) <= 3:
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


def extract_user_company(messages: list) -> str:
    """Extract user's company from conversation if they provided it."""
    import re

    # Words that aren't company names
    not_companies = {
        'a', 'an', 'the', 'here', 'there', 'home', 'work', 'school',
        'looking', 'interested', 'curious', 'wondering', 'asking',
        'legacy', 'new', 'old', 'small', 'large', 'big', 'local'
    }

    company_patterns = [
        r"(?:i work (?:at|for)|i'm (?:at|with|from)|my company is)\s+([A-Za-z0-9][\w\s&.,'-]*?)(?:\s*[,.]|\s+and\s|\s+my\s|\s+email|$)",
        r"company[:\s]+([A-Za-z0-9][\w\s&.,'-]+?)(?:\s*[,.]|\s+and\s|\s+my\s|$)",
    ]

    for msg in messages:
        if msg.get("role") != "user":
            continue

        text = msg.get("content", "")

        for pattern in company_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                company = match.group(1).strip().rstrip('.,')
                words = company.split()

                # Skip if first word is a common non-company word
                if words and words[0].lower() in not_companies:
                    continue

                # Limit to max 4 words for a company name
                if len(words) > 4:
                    continue

                if 2 <= len(company) <= 50:
                    return company.title()

    return None


def extract_user_phone(messages: list) -> str:
    """Extract user's phone number from conversation if they provided it."""
    phone_patterns = [
        r"(?:my (?:phone|number|cell|mobile)(?: number)? is|phone[:\s]+|call me at|reach me at)\s*([\d\s\-\(\)\+\.]+)",
        r"(\+?1?[-.\s]?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4})",
        r"(\d{3}[-.\s]?\d{3}[-.\s]?\d{4})",
    ]

    for msg in messages:
        if msg.get("role") != "user":
            continue

        text = msg.get("content", "")

        for pattern in phone_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                phone = match.group(1).strip()
                # Clean up and validate - should have at least 10 digits
                digits_only = re.sub(r'\D', '', phone)
                if 10 <= len(digits_only) <= 15:
                    return phone

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
