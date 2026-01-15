"""
FastAPI server for Blacksky Chatbot
Provides REST API for chat interactions with user tracking and admin dashboard
"""
from fastapi import FastAPI, HTTPException, UploadFile, File, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, StreamingResponse, HTMLResponse, RedirectResponse
from pydantic import BaseModel
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional, List
import time
import json
import asyncio
import re
import uuid
from datetime import datetime, timedelta

import jwt

from chatbot import BlackskyChatbot
from config import HOST, PORT, ADMIN_PASSWORD, JWT_SECRET_KEY, USE_CLOUD_LLM
from rag import DocumentStore, DOCS_DIR
from database import (
    init_db, get_or_create_user, update_user, save_conversation, update_conversation,
    get_user_context, get_leads, lookup_users_by_name, link_users,
    get_lead_details, update_lead_status, update_lead_notes, get_user_conversations,
    delete_user, get_analytics, get_user_dashboard, get_user_by_name, create_hard_user,
    verify_hard_login, get_all_exchanges, save_user_facts, get_user_facts
)

# Paths
STATIC_DIR = Path(__file__).parent / "static"
STATIC_DIR.mkdir(exist_ok=True)

# Global chatbot instance
bot = BlackskyChatbot(use_rag=True)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Load model on startup."""
    mode = "Cloud (Together AI)" if USE_CLOUD_LLM else "Local"
    print(f"Starting Blacksky Chatbot Server ({mode})...")
    bot.load_model()

    # Initialize database
    init_db()

    # Auto-load any documents in the documents folder
    if bot.doc_store and list(DOCS_DIR.glob('*')):
        print("Loading documents...")
        bot.doc_store.load_all_documents()

    yield
    print("Shutting down...")


app = FastAPI(
    title=f"Blacksky Chatbot API ({'Cloud' if USE_CLOUD_LLM else 'Local'})",
    description="A friendly chatbot for Blacksky LLC",
    version="1.0.0",
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


# JWT token utilities
def create_auth_token(user_id: str) -> str:
    """Create JWT token for authenticated session."""
    payload = {
        'user_id': user_id,
        'exp': datetime.utcnow() + timedelta(days=30),
        'iat': datetime.utcnow()
    }
    return jwt.encode(payload, JWT_SECRET_KEY, algorithm='HS256')


def decode_auth_token(token: str) -> Optional[dict]:
    """Decode and verify JWT token."""
    try:
        payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=['HS256'])
        return payload
    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        return None


class ChatRequest(BaseModel):
    message: str = ""
    user_id: Optional[str] = None
    potential_matches: Optional[List[dict]] = None
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
        "service": f"Blacksky Chatbot ({'Cloud' if USE_CLOUD_LLM else 'Local'})",
        "version": "1.0.0"
    }


@app.get("/db/health")
async def db_health():
    """Database health check."""
    from sqlalchemy import text
    from database import get_session

    session = get_session()
    if session is None:
        return {"status": "disabled", "reason": "Database not initialized"}

    try:
        session.execute(text("SELECT 1"))
        return {"status": "connected", "database": "sqlite"}
    except Exception as e:
        return {"status": "error", "reason": str(e)}
    finally:
        session.close()


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
    response = bot.chat(request.message, user_context=user_context,
                       potential_matches=request.potential_matches)
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
            for token in bot.chat_stream(message, user_context=user_context,
                                        potential_matches=request.potential_matches):
                yield f"data: {json.dumps({'token': token})}\n\n"
                await asyncio.sleep(0)  # Yield to event loop for streaming
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


@app.post("/conversation/end")
async def end_conversation(request: ConversationEndRequest):
    """Save conversation when user leaves or goes idle."""
    if not request.messages:
        return {"status": "skipped", "reason": "No messages to save"}

    # Ensure user exists before saving conversation (required for foreign key)
    get_or_create_user(request.user_id)

    # Extract summary from messages (last few exchanges)
    summary = None
    interests = []
    lead_score = 1

    # Analyze messages for lead scoring
    all_text = " ".join([m.get("content", "") for m in request.messages])

    # High intent keywords
    high_intent = ["pricing", "cost", "quote", "hire", "contract", "proposal",
                   "budget", "timeline", "availability", "rates"]
    medium_intent = ["project", "help", "need", "looking for", "interested",
                     "services", "capabilities", "experience"]

    for keyword in high_intent:
        if keyword.lower() in all_text.lower():
            lead_score = 3
            break

    if lead_score == 1:
        for keyword in medium_intent:
            if keyword.lower() in all_text.lower():
                lead_score = 2
                break

    # Create simple summary from last user message
    user_messages = [m for m in request.messages if m.get("role") == "user"]
    if user_messages:
        last_msg = user_messages[-1].get("content", "")
        summary = last_msg[:200] + "..." if len(last_msg) > 200 else last_msg

    # Extract name, email, phone, and company from messages if mentioned
    name = extract_user_name(request.messages)
    email = extract_user_email(request.messages)
    phone = extract_user_phone(request.messages)
    company = extract_user_company(request.messages)
    if name or email or phone or company:
        update_user(request.user_id, name=name, email=email, phone=phone, company=company)

    # Save or update conversation
    if request.conversation_id:
        # Update existing conversation
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
        conv_id = save_conversation(
            user_id=request.user_id,
            messages=request.messages,
            summary=summary,
            interests=interests,
            lead_score=lead_score
        )
        status = "saved" if conv_id else "save_failed"

    # Extract and save semantic facts
    semantic_facts = extract_semantic_facts(request.messages)
    facts_saved = 0
    if semantic_facts:
        facts_saved = save_user_facts(
            user_id=request.user_id,
            facts=semantic_facts,
            conversation_id=conv_id
        )
        print(f"Extracted {len(semantic_facts)} facts, saved {facts_saved} for user {request.user_id}")

    return {
        "status": status,
        "conversation_id": conv_id,
        "lead_score": lead_score,
        "name_extracted": name,
        "email_extracted": email,
        "phone_extracted": phone,
        "company_extracted": company,
        "facts_extracted": len(semantic_facts),
        "facts_saved": facts_saved
    }


def extract_user_name(messages: list) -> Optional[str]:
    """Extract user's name from conversation messages.

    Only matches explicit name declarations to avoid false positives.
    """
    # Only match explicit name patterns - removed standalone capitalized word pattern
    patterns = [
        r"(?:my name is|i'm|i am|call me|this is)\s+([A-Za-z]+(?:\s+[A-Za-z]+){0,2})",
    ]

    # Words that signal end of name
    stop_words = {'and', 'my', 'email', 'at', 'from', 'with', 'the', 'i', 'work', 'company'}

    for msg in messages:
        if msg.get("role") == "user":
            content = msg.get("content", "").strip()
            for pattern in patterns:
                match = re.search(pattern, content, re.IGNORECASE)
                if match:
                    name_part = match.group(1).strip()
                    words = name_part.split()
                    clean_words = []
                    for word in words:
                        if word.lower() in stop_words:
                            break
                        clean_words.append(word)

                    name = ' '.join(clean_words)
                    if 2 <= len(name) <= 50 and not any(c.isdigit() for c in name) and len(clean_words) <= 3:
                        return name.title()
    return None


def extract_user_email(messages: list) -> Optional[str]:
    """Extract user's email from conversation if they provided it."""
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


def extract_user_company(messages: list) -> Optional[str]:
    """Extract user's company from conversation if they provided it."""
    company_patterns = [
        r"(?:i work (?:at|for)|i'm (?:at|with|from)|my company is|company is|from)\s+([A-Za-z0-9][\w\s&.,'-]*?)(?:\s*[,.]|\s+and\s|\s+my\s|\s+email|$)",
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
                if 2 <= len(company) <= 100:
                    return company.title()

    return None


def extract_user_phone(messages: list) -> Optional[str]:
    """Extract user's phone number from conversation if they provided it."""
    # Common phone patterns for US/international
    phone_patterns = [
        r"(?:my (?:phone|number|cell|mobile)(?: number)? is|phone[:\s]+|call me at|reach me at)\s*([\d\s\-\(\)\+\.]+)",
        r"(\+?1?[-.\s]?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4})",  # US format
        r"(\d{3}[-.\s]?\d{3}[-.\s]?\d{4})",  # Simple 10 digit
    ]

    for msg in messages:
        if msg.get("role") != "user":
            continue

        text = msg.get("content", "")

        for pattern in phone_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                phone = re.sub(r'[^\d+]', '', match.group(1))  # Keep only digits and +
                if 10 <= len(phone) <= 15:  # Valid phone length
                    return phone

    return None


# ============================================
# Semantic Fact Extraction
# ============================================

# Patterns for extracting semantic facts from user messages
SEMANTIC_FACT_PATTERNS = {
    "role": [
        (r"(?:I'm|I am|work as|my role is|my title is|I'm the)\s+(?:a|an|the)?\s*([A-Za-z\s]+?(?:CTO|CEO|CFO|COO|VP|Director|Manager|Lead|Head|Engineer|Developer|Architect|Designer|Analyst|Consultant|Founder|Owner|President))", 0.9),
        (r"(?:as a|as an)\s+([A-Za-z\s]+?(?:CTO|CEO|Developer|Engineer|Manager|Director|Lead|Founder))", 0.85),
    ],
    "budget": [
        (r"\$\s*(\d{1,3}(?:,?\d{3})*(?:k|K|M)?)\s*(?:to|-)\s*\$?\s*(\d{1,3}(?:,?\d{3})*(?:k|K|M)?)", 0.9),
        (r"budget\s+(?:is|of|around|about)?\s*\$?\s*(\d{1,3}(?:,?\d{3})*(?:k|K|M)?)", 0.85),
        (r"(\d{2,3}k|\d+\s*(?:thousand|million))\s+(?:budget|to spend)", 0.8),
    ],
    "timeline": [
        (r"(?:need|want|looking to have)\s+(?:it|this|something)?\s*(?:done|ready|launched|live)?\s*(?:by|before|in)\s+([A-Za-z]+\s+\d{4}|Q[1-4]\s*\d{4}|next\s+(?:week|month|quarter|year))", 0.9),
        (r"(?:timeline|deadline)\s+(?:is|of)?\s*([A-Za-z]+\s+\d{4}|Q[1-4]\s*\d{4}|\d+\s+(?:weeks?|months?))", 0.85),
        (r"\b(ASAP|immediately|urgent|as soon as possible)\b", 0.8),
    ],
    "company_size": [
        (r"(?:we have|there are|about|around)\s+(\d+)\s*(?:employees|people|team members|engineers|developers)", 0.9),
        (r"(\d+)\s*(?:person|people|employee)\s+(?:company|team|startup)", 0.85),
        (r"\b(startup|small company|small business|enterprise|fortune\s*\d+|mid-?size)\b", 0.8),
    ],
    "project_type": [
        (r"(?:need|want|looking for|building|develop)\s+(?:a|an)?\s*(mobile app|web app|website|api|platform|dashboard|portal|e-?commerce|marketplace|saas)", 0.9),
        (r"(?:working on|building)\s+(?:a|an)?\s*([A-Za-z\s]+?(?:app|platform|system|tool|solution))", 0.8),
    ],
    "industry": [
        (r"(?:in the|work in|from)\s+(healthcare|fintech|finance|banking|insurance|retail|e-?commerce|education|government|legal|real estate|manufacturing|logistics|media|entertainment)\s+(?:industry|sector|space)?", 0.9),
        (r"(?:we're a|it's a|our)\s+(healthcare|fintech|edtech|medtech|proptech|legaltech|insurtech)\s+(?:company|startup)?", 0.85),
    ],
    "pain_point": [
        (r"(?:struggling with|problem with|issue with|challenge with|concerned about|worried about)\s+([A-Za-z\s]+?)(?:\.|,|$)", 0.85),
        (r"(?:need to|want to|trying to)\s+(scale|improve|fix|solve|automate|streamline|optimize)\s+([A-Za-z\s]+?)(?:\.|,|$)", 0.8),
    ],
    "decision_stage": [
        (r"(?:just\s+)?(researching|exploring|evaluating|comparing|looking around)", 0.8),
        (r"(?:ready to|want to|need to)\s+(start|begin|move forward|get started|hire|sign)", 0.9),
        (r"(?:still\s+)?(deciding|thinking about|considering)", 0.7),
    ],
}


def extract_semantic_facts(messages: list) -> list:
    """Extract semantic facts from conversation using regex patterns.

    Returns list of dicts: [{"type": "role", "value": "CTO", "confidence": 0.9}, ...]
    """
    extracted_facts = []
    seen_types = set()  # Track fact types we've already extracted

    for msg in messages:
        if msg.get("role") != "user":
            continue

        text = msg.get("content", "")

        for fact_type, patterns in SEMANTIC_FACT_PATTERNS.items():
            # Skip if we already found this fact type with high confidence
            if fact_type in seen_types:
                continue

            for pattern, confidence in patterns:
                match = re.search(pattern, text, re.IGNORECASE)
                if match:
                    # Get the matched value
                    if match.lastindex and match.lastindex >= 1:
                        value = match.group(1).strip()
                        # For budget with range, combine groups
                        if fact_type == "budget" and match.lastindex >= 2:
                            value = f"${match.group(1)} - ${match.group(2)}"
                    else:
                        value = match.group(0).strip()

                    # Clean up the value
                    value = value.strip('.,;:')
                    if len(value) >= 2 and len(value) <= 100:
                        extracted_facts.append({
                            "type": fact_type,
                            "value": value,
                            "confidence": confidence,
                            "source_text": text[:200]
                        })
                        seen_types.add(fact_type)
                        break  # Move to next fact type

    return extracted_facts


@app.post("/user/update")
async def user_update(request: UserUpdateRequest):
    """Update user information."""
    result = update_user(
        request.user_id,
        name=request.name,
        email=request.email,
        company=request.company
    )
    if result:
        return {"status": "updated", "user": result}
    return {"status": "failed"}


@app.get("/user/{user_id}/context")
async def get_user_context_endpoint(user_id: str):
    """Get user context for avatar display."""
    context = get_user_context(user_id)
    if context is None:
        return {"name": None, "email": None, "phone": None, "company": None, "auth_method": "soft", "is_returning": False}
    return {
        "name": context.get("name"),
        "email": context.get("email"),
        "phone": context.get("phone"),
        "company": context.get("company"),
        "auth_method": context.get("auth_method", "soft"),
        "is_returning": context.get("is_returning", False),
        "conversation_count": context.get("conversation_count", 0)
    }


@app.post("/user/lookup")
async def user_lookup(request: UserLookupRequest):
    """Look up users by name for verification."""
    matches = lookup_users_by_name(request.name)
    return {
        "count": len(matches),
        "matches": matches
    }


@app.post("/user/link")
async def user_link(request: UserLinkRequest):
    """Link current session to existing user."""
    success = link_users(request.current_user_id, request.target_user_id)
    if success:
        return {
            "status": "linked",
            "new_user_id": request.target_user_id
        }
    return {"status": "failed"}


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
        notes_display = notes_preview or '<span style="color:#444">+ Add</span>'
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
                <td class="notes-cell clickable" onclick="editNotes('{lead['id']}')" title="Click to edit notes">{notes_display}</td>
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
            <title>Maurice's Leads (Local)</title>
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
                .filter-checkbox {{ display: flex; align-items: center; gap: 6px; font-size: 0.85rem; color: #888; cursor: pointer; }}
                .filter-checkbox input {{ cursor: pointer; }}
                table {{ border-collapse: collapse; width: 100%; }}
                th, td {{ padding: 10px; text-align: left; border-bottom: 1px solid #222; }}
                th {{ color: #666; font-weight: normal; text-transform: uppercase; font-size: 0.7rem; letter-spacing: 0.1em; }}
                tr:hover {{ background: #111; }}
                tr.hidden {{ display: none; }}
                .clickable {{ cursor: pointer; }}
                .clickable:hover {{ text-decoration: underline; color: #68d; }}
                .local-badge {{ background: #2a4a2a; color: #6f6; padding: 4px 8px; border-radius: 4px; font-size: 0.75rem; margin-left: 10px; }}
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
                    <span class="local-badge">LOCAL</span>
                </div>
                <div class="actions">
                    <a href="/admin/traffic?password={password}" class="btn" style="margin-right: 10px; text-decoration: none;">View Traffic</a>
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
                <label class="filter-checkbox">
                    <input type="checkbox" id="hideTestUsers" checked onchange="filterTable()">
                    Hide test users
                </label>
                <label class="filter-checkbox">
                    <input type="checkbox" id="onlyAnonymous" onchange="filterTable()">
                    Only anonymous
                </label>
                <label class="filter-checkbox">
                    <input type="checkbox" id="onlyTestUsers" onchange="filterTable()">
                    Only test users
                </label>
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
                    const hideTestUsers = document.getElementById('hideTestUsers').checked;
                    const onlyAnonymous = document.getElementById('onlyAnonymous').checked;
                    const onlyTestUsers = document.getElementById('onlyTestUsers').checked;

                    const rows = document.querySelectorAll('#leadsTable .lead-row');
                    let visibleCount = 0;

                    rows.forEach(row => {{
                        const name = row.dataset.name;
                        const nameLower = name.toLowerCase();
                        const email = row.dataset.email.toLowerCase();
                        const company = row.dataset.company.toLowerCase();
                        const status = row.dataset.status;
                        const score = parseInt(row.dataset.score);

                        // Check user type
                        const isAnonymous = name.startsWith('ANON[');
                        const isTestUser = nameLower.startsWith('testuser_');

                        // "Only" filters take priority - exclusive mode
                        if (onlyAnonymous || onlyTestUsers) {{
                            const matchesOnly = (onlyAnonymous && isAnonymous) || (onlyTestUsers && isTestUser);
                            if (!matchesOnly) {{
                                row.classList.add('hidden');
                                return;
                            }}
                        }} else {{
                            // Normal "hide" mode
                            if (hideTestUsers && isTestUser) {{
                                row.classList.add('hidden');
                                return;
                            }}
                        }}

                        const matchesSearch = !search || nameLower.includes(search) || email.includes(search) || company.includes(search);
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


@app.get("/admin/traffic")
async def admin_traffic(password: str = Query(None), page: int = Query(1)):
    """Admin traffic dashboard showing all Q&A exchanges."""
    # Show login form if no password
    if not password:
        return HTMLResponse("""
            <html>
            <head><title>Admin Traffic - Login</title></head>
            <body style="font-family: system-ui; display: flex; justify-content: center; align-items: center; height: 100vh; background: #1a1a2e;">
                <form style="background: #16213e; padding: 40px; border-radius: 10px; color: white;">
                    <h2>Traffic Dashboard Login</h2>
                    <input type="password" name="password" placeholder="Password" style="padding: 10px; width: 200px; margin: 10px 0;">
                    <button type="submit" style="padding: 10px 20px; background: #e94560; color: white; border: none; cursor: pointer;">Login</button>
                </form>
            </body>
            </html>
        """)

    if password != ADMIN_PASSWORD:
        raise HTTPException(status_code=401, detail="Invalid password")

    # Get paginated exchanges
    data = get_all_exchanges(page=page, per_page=50)

    # Build table rows
    rows = ""
    for ex in data['exchanges']:
        question_preview = (ex['question'][:80] + '...') if len(ex['question']) > 80 else ex['question']
        answer_preview = (ex['answer'][:80] + '...') if len(ex['answer']) > 80 else ex['answer']
        timestamp = ex['timestamp'][:16].replace('T', ' ') if ex['timestamp'] else 'N/A'

        # Escape HTML in content
        question_preview = question_preview.replace('<', '&lt;').replace('>', '&gt;')
        answer_preview = answer_preview.replace('<', '&lt;').replace('>', '&gt;')
        full_question = ex['question'].replace('<', '&lt;').replace('>', '&gt;').replace('\n', '<br>')
        full_answer = ex['answer'].replace('<', '&lt;').replace('>', '&gt;').replace('\n', '<br>')

        rows += f"""
            <tr class="exchange-row" onclick="toggleExpand(this)">
                <td>{ex['user_name']}</td>
                <td>{question_preview}</td>
                <td>{answer_preview}</td>
                <td>{timestamp}</td>
            </tr>
            <tr class="expanded-row" style="display: none;">
                <td colspan="4">
                    <div class="expanded-content">
                        <div class="expanded-section">
                            <strong>Question:</strong>
                            <div class="expanded-text">{full_question}</div>
                        </div>
                        <div class="expanded-section">
                            <strong>Answer:</strong>
                            <div class="expanded-text">{full_answer}</div>
                        </div>
                    </div>
                </td>
            </tr>
        """

    # Build pagination
    prev_disabled = "disabled" if page <= 1 else ""
    next_disabled = "disabled" if page >= data['total_pages'] else ""
    pagination = f"""
        <div class="pagination">
            <button onclick="goToPage({page - 1})" {prev_disabled}>&lt; Prev</button>
            <span>Page {data['page']} of {data['total_pages']}</span>
            <button onclick="goToPage({page + 1})" {next_disabled}>Next &gt;</button>
        </div>
    """

    return HTMLResponse(f"""
        <html>
        <head>
            <title>Maurice's Traffic Dashboard</title>
            <style>
                * {{ margin: 0; padding: 0; box-sizing: border-box; }}
                body {{ font-family: system-ui, -apple-system, sans-serif; background: #1a1a2e; color: #eee; min-height: 100vh; }}
                .header {{ background: #16213e; padding: 20px 30px; display: flex; justify-content: space-between; align-items: center; }}
                .header h1 {{ font-size: 1.5rem; }}
                .local-badge {{ background: #e94560; color: white; padding: 4px 12px; border-radius: 20px; font-size: 0.75rem; margin-left: 10px; }}
                .back-link {{ color: #0f94d2; text-decoration: none; margin-top: 5px; display: inline-block; }}
                .back-link:hover {{ text-decoration: underline; }}
                .stats-bar {{ background: #16213e; margin: 20px 30px; padding: 15px 20px; border-radius: 8px; }}
                .stats-bar span {{ font-size: 1.1rem; }}
                .stats-bar strong {{ color: #0f94d2; }}
                table {{ width: calc(100% - 60px); margin: 0 30px; border-collapse: collapse; background: #16213e; border-radius: 8px; overflow: hidden; }}
                th {{ background: #0f3460; padding: 15px; text-align: left; font-weight: 600; }}
                td {{ padding: 12px 15px; border-bottom: 1px solid #0f3460; }}
                .exchange-row {{ cursor: pointer; transition: background 0.2s; }}
                .exchange-row:hover {{ background: #1f4068; }}
                .expanded-row {{ background: #0f3460; }}
                .expanded-content {{ padding: 15px; }}
                .expanded-section {{ margin-bottom: 15px; }}
                .expanded-section:last-child {{ margin-bottom: 0; }}
                .expanded-text {{ margin-top: 8px; padding: 10px; background: #1a1a2e; border-radius: 5px; white-space: pre-wrap; line-height: 1.5; }}
                .pagination {{ display: flex; justify-content: center; align-items: center; gap: 20px; padding: 20px; }}
                .pagination button {{ padding: 10px 20px; background: #0f94d2; color: white; border: none; border-radius: 5px; cursor: pointer; }}
                .pagination button:disabled {{ background: #555; cursor: not-allowed; }}
                .pagination button:hover:not(:disabled) {{ background: #0d7ab3; }}
            </style>
        </head>
        <body>
            <div class="header">
                <div>
                    <h1>Maurice's Traffic Dashboard <span class="local-badge">LOCAL</span></h1>
                    <a href="/admin?password={password}" class="back-link">&larr; Back to Leads</a>
                </div>
            </div>

            <div class="stats-bar">
                <span>Total Exchanges: <strong>{data['total']}</strong></span>
            </div>

            <table>
                <thead>
                    <tr>
                        <th style="width: 15%;">User</th>
                        <th style="width: 35%;">Question</th>
                        <th style="width: 35%;">Answer</th>
                        <th style="width: 15%;">Timestamp</th>
                    </tr>
                </thead>
                <tbody>
                    {rows if rows else '<tr><td colspan="4" style="text-align: center; padding: 40px;">No exchanges found</td></tr>'}
                </tbody>
            </table>

            {pagination}

            <script>
                function toggleExpand(row) {{
                    const expandedRow = row.nextElementSibling;
                    if (expandedRow && expandedRow.classList.contains('expanded-row')) {{
                        expandedRow.style.display = expandedRow.style.display === 'none' ? 'table-row' : 'none';
                    }}
                }}

                function goToPage(page) {{
                    window.location.href = '/admin/traffic?password={password}&page=' + page;
                }}
            </script>
        </body>
        </html>
    """)


@app.get("/admin/traffic/data")
async def admin_traffic_data(password: str = Query(...), page: int = Query(1)):
    """API endpoint for traffic data (JSON)."""
    if password != ADMIN_PASSWORD:
        raise HTTPException(status_code=401, detail="Invalid password")

    return get_all_exchanges(page=page, per_page=50)


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
    """List all indexed documents."""
    if not bot.doc_store:
        raise HTTPException(status_code=400, detail="RAG not enabled")
    return {
        "documents": bot.doc_store.list_documents(),
        "total_chunks": bot.doc_store.get_stats()["total_vectors"]
    }


@app.post("/documents/reload")
async def reload_documents():
    """Reload all documents from the documents directory."""
    if not bot.doc_store:
        raise HTTPException(status_code=400, detail="RAG not enabled")

    count = bot.doc_store.load_all_documents()
    return {
        "message": f"Loaded {count} chunks",
        "documents": bot.doc_store.list_documents()
    }


@app.post("/documents/upload")
async def upload_document(file: UploadFile = File(...)):
    """Upload a new document."""
    if not bot.doc_store:
        raise HTTPException(status_code=400, detail="RAG not enabled")

    # Only allow text files
    if not file.filename.endswith(('.txt', '.md')):
        raise HTTPException(status_code=400, detail="Only .txt and .md files supported")

    # Save file
    filepath = DOCS_DIR / file.filename
    content = await file.read()
    filepath.write_bytes(content)

    # Index it
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


# ============================================
# Auth Verification
# ============================================

class AuthTokenRequest(BaseModel):
    token: str


@app.post("/auth/verify")
async def verify_auth_token(request: AuthTokenRequest):
    """Verify auth token and return user info."""
    payload = decode_auth_token(request.token)

    if not payload:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    user_id = payload.get('user_id')
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid token payload")

    # Get user info
    user_data = get_or_create_user(user_id)
    if user_data:
        return {
            "valid": True,
            "user_id": user_data['id'],
            "name": user_data['name'],
            "email": user_data.get('email'),
            "picture": None,
            "auth_method": user_data.get('auth_method', 'medium')
        }

    raise HTTPException(status_code=404, detail="User not found")


@app.post("/auth/logout")
async def logout():
    """Log out user."""
    return {"status": "logged_out"}


# ============================================
# Hard Login Endpoints
# ============================================

class HardLoginRequest(BaseModel):
    name: str
    password: str
    interest_level: Optional[str] = None
    user_id: Optional[str] = None  # Current anonymous user ID


@app.post("/auth/hard/login")
async def hard_login(request: HardLoginRequest):
    """Login with hard credentials (name + password)."""
    # Try to verify existing user
    user = verify_hard_login(request.name, request.password)

    if user:
        # Generate JWT token
        token = create_auth_token(user['id'])
        return {
            "success": True,
            "token": token,
            "user_id": user['id'],
            "name": user['name'],
            "interest_level": user.get('interest_level'),
            "auth_method": "hard"
        }

    raise HTTPException(status_code=401, detail="Invalid credentials")


@app.post("/auth/hard/register")
async def hard_register(request: HardLoginRequest):
    """Register new hard login account."""
    # Check if name already exists
    existing = get_user_by_name(request.name)
    if existing and existing.get('password_hash'):
        raise HTTPException(status_code=400, detail="Name already registered")

    # Use provided user_id or generate new one
    user_id = request.user_id or str(uuid.uuid4())

    # Create the user
    user = create_hard_user(
        user_id=user_id,
        name=request.name,
        password=request.password,
        interest_level=request.interest_level
    )

    if not user:
        raise HTTPException(status_code=500, detail="Failed to create account")

    # Generate JWT token
    token = create_auth_token(user['id'])
    return {
        "success": True,
        "token": token,
        "user_id": user['id'],
        "name": user['name'],
        "interest_level": user.get('interest_level'),
        "auth_method": "hard"
    }


@app.get("/user/{user_id}/dashboard")
async def user_dashboard(user_id: str):
    """Get user dashboard data."""
    data = get_user_dashboard(user_id)
    if not data:
        raise HTTPException(status_code=404, detail="User not found")
    return data


# Static files and demo page
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.get("/demo")
async def demo_page():
    """Serve the demo page."""
    return FileResponse(STATIC_DIR / "demo.html")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "server:app",
        host=HOST,
        port=PORT,
        reload=False,
        workers=1
    )
