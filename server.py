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
from config import HOST, PORT, ADMIN_PASSWORD, JWT_SECRET_KEY, CORS_ORIGINS, AGENT_FAST_TIMEOUT
from agents import agent_client
from rag import DocumentStore, DOCS_DIR
from database import (
    init_db, get_or_create_user, update_user, save_conversation, update_conversation,
    get_user_context, get_leads, lookup_users_by_name, link_users,
    get_lead_details, update_lead_status, update_lead_notes, get_user_conversations,
    delete_user, get_analytics, get_user_dashboard, get_user_by_name, create_hard_user,
    verify_hard_login, get_all_exchanges, save_user_facts, get_user_facts,
    get_all_users, get_user_full_profile, save_page_view, get_user_page_views,
    save_response_feedback, get_response_feedback, get_feedback_stats,
    get_exemplary_responses, get_problematic_responses,
    save_training_example, get_training_examples, update_training_example,
    delete_training_example, get_training_stats, export_training_data_jsonl,
    get_training_candidates, create_training_example_from_feedback,
    get_funnel_analytics, get_intent_signals, get_user_journey, get_recent_high_intent_leads,
    analyze_response_quality, get_quality_metrics, get_flagged_responses, get_hallucination_examples,
    create_handoff_package, get_intent_signals_for_user
)

# Paths
STATIC_DIR = Path(__file__).parent / "static"
STATIC_DIR.mkdir(exist_ok=True)

# Global chatbot instance (stateless - no conversation history stored)
bot = BlackskyChatbot(use_rag=True)

# Per-user session storage for conversation history
# Key: user_id, Value: list of {"user": ..., "assistant": ...} dicts
user_sessions: dict[str, list[dict]] = {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Load model on startup."""
    print("Starting Blacksky Chatbot Server (Local)...")
    bot.load_model()

    # Initialize database
    init_db()

    # Auto-load any documents in the documents folder
    if bot.doc_store and list(DOCS_DIR.glob('*')):
        print("Loading documents...")
        bot.doc_store.load_all_documents()

    # Check agent platform connectivity
    if agent_client.is_configured:
        agent_healthy = await agent_client.health_check()
        if agent_healthy:
            print(f"[AGENTS] Connected to agent platform at {agent_client.base_url}")
        else:
            print(f"[AGENTS] Warning: Agent platform at {agent_client.base_url} not reachable")
    else:
        print("[AGENTS] Agent platform not configured (AGENT_PLATFORM_URL not set)")

    yield

    # Cleanup
    print("Shutting down...")
    await agent_client.close()


app = FastAPI(
    title="Blacksky Chatbot API (Local)",
    description="A friendly chatbot for Blacksky LLC - Local Development",
    version="1.0.0",
    lifespan=lifespan
)

# CORS for web clients
# In production, set CORS_ORIGINS to specific domains (e.g., "https://yourdomain.com")
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True if CORS_ORIGINS != ["*"] else False,  # Credentials only with specific origins
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
    is_admin: Optional[bool] = False  # Flag for admin mode with enhanced responses
    panel_views: Optional[List[str]] = None  # Recent panels viewed by user
    include_debug: Optional[bool] = False  # Flag to include debug context in response


class AdminLoginRequest(BaseModel):
    password: str


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


class PageViewRequest(BaseModel):
    user_id: str
    view_type: str  # "panel", "link", "external"
    title: str
    url: Optional[str] = None
    panel_key: Optional[str] = None


class FeedbackRequest(BaseModel):
    conversation_id: int
    message_index: int
    rating: Optional[int] = None  # 1-5 stars
    feedback_type: Optional[str] = None  # "accurate", "helpful", "tone", "hallucination", "off-topic", "missed-opportunity"
    notes: Optional[str] = None
    corrected_response: Optional[str] = None
    is_exemplary: bool = False
    is_problematic: bool = False


class TrainingExampleRequest(BaseModel):
    user_message: str
    assistant_response: str
    category: Optional[str] = None  # greeting, pricing, technical, objection_handling, lead_capture
    difficulty: Optional[str] = None  # easy, medium, hard
    relevant_facts: Optional[dict] = None
    rag_context: Optional[str] = None
    source_conversation_id: Optional[int] = None
    source_feedback_id: Optional[int] = None
    quality_score: Optional[int] = None  # 1-5
    reviewer_notes: Optional[str] = None


class TrainingExampleUpdateRequest(BaseModel):
    user_message: Optional[str] = None
    assistant_response: Optional[str] = None
    category: Optional[str] = None
    difficulty: Optional[str] = None
    relevant_facts: Optional[dict] = None
    rag_context: Optional[str] = None
    quality_score: Optional[int] = None
    reviewer_notes: Optional[str] = None
    status: Optional[str] = None  # pending, approved, rejected


@app.get("/")
async def root():
    """Health check endpoint."""
    return {
        "status": "online",
        "service": "Blacksky Chatbot (Local)",
        "version": "1.0.0"
    }


@app.get("/db/health")
async def db_health():
    """Database health check."""
    from sqlalchemy import text
    from database import get_session, DATABASE_URL

    session = get_session()
    if session is None:
        return {"status": "disabled", "reason": "Database not initialized"}

    db_type = "postgresql" if DATABASE_URL.startswith("postgresql") else "sqlite"

    try:
        session.execute(text("SELECT 1"))
        return {"status": "connected", "database": db_type}
    except Exception as e:
        return {"status": "error", "reason": str(e)}
    finally:
        session.close()


@app.get("/agent/status")
async def agent_status():
    """Agent platform health check."""
    if not agent_client.is_configured:
        return {"status": "not_configured", "reason": "AGENT_PLATFORM_URL not set"}

    try:
        healthy = await agent_client.health_check()
        if healthy:
            return {"status": "connected", "url": agent_client.base_url}
        else:
            return {"status": "unreachable", "url": agent_client.base_url}
    except Exception as e:
        return {"status": "error", "reason": str(e), "url": agent_client.base_url}


@app.post("/track/pageview")
async def track_pageview(request: PageViewRequest):
    """Log a page view or link click for user tracking."""
    # Ensure user exists
    get_or_create_user(request.user_id)

    view_id = save_page_view(
        user_id=request.user_id,
        view_type=request.view_type,
        title=request.title,
        url=request.url,
        panel_key=request.panel_key
    )

    return {"status": "tracked", "view_id": view_id}


@app.post("/admin/chat/login")
async def admin_chat_login(request: AdminLoginRequest):
    """Validate admin password for chat admin mode."""
    if request.password == ADMIN_PASSWORD:
        return {"success": True, "message": "Admin mode activated"}
    raise HTTPException(status_code=401, detail="Invalid password")


@app.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    """Send a message and get a response."""
    if not request.message.strip():
        raise HTTPException(status_code=400, detail="Message cannot be empty")

    # Get user context if user_id provided
    user_context = None
    conversation_history = []
    if request.user_id:
        get_or_create_user(request.user_id)
        user_context = get_user_context(request.user_id)
        # Get this user's conversation history from session storage
        conversation_history = user_sessions.get(request.user_id, [])

    start = time.time()
    response = bot.chat(
        request.message,
        conversation_history=conversation_history,
        user_context=user_context,
        potential_matches=request.potential_matches,
        is_admin=request.is_admin
    )
    elapsed = (time.time() - start) * 1000

    # Store the exchange in this user's session
    if request.user_id:
        if request.user_id not in user_sessions:
            user_sessions[request.user_id] = []
        user_sessions[request.user_id].append({
            "user": request.message,
            "assistant": response
        })

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
    conversation_history = []
    agent_data = None
    agent_task = None

    if request.user_id:
        get_or_create_user(request.user_id)
        user_context = get_user_context(request.user_id)
        # Get this user's conversation history from session storage
        conversation_history = user_sessions.get(request.user_id, [])

        # Start agent lookup in background (non-blocking for fast first token)
        if agent_client.is_configured:
            # Check cache first for instant response
            agent_data = agent_client.get_cached(request.user_id)
            if agent_data:
                print(f"[AGENTS] Using cached context for user {request.user_id}")
            else:
                # Start background fetch
                agent_task = asyncio.create_task(
                    agent_client.lookup_user_context(request.user_id)
                )
                # Try to get fresh data with short timeout
                try:
                    agent_data = await asyncio.wait_for(agent_task, timeout=AGENT_FAST_TIMEOUT)
                    if agent_data.get("success"):
                        print(f"[AGENTS] Got enriched context for user {request.user_id}")
                    else:
                        print(f"[AGENTS] No agent data for user {request.user_id}: {agent_data.get('error', 'unknown')}")
                        agent_data = None
                except asyncio.TimeoutError:
                    # Continue without agent data - task will complete in background and cache result
                    print(f"[AGENTS] Fast timeout - streaming without agent data for {request.user_id}")
                    agent_data = None
                except Exception as e:
                    print(f"[AGENTS] Error fetching agent data: {e}")
                    agent_data = None

    # We need to collect the full response for session storage
    collected_response = []

    async def generate():
        try:
            # Send agent status for admin mode at start of stream
            if request.is_admin and agent_client.is_configured:
                agent_status_info = {
                    "agent_status": "connected" if agent_data and agent_data.get("success") else "no_data",
                }
                if agent_data and agent_data.get("success"):
                    agent_status_info["interest_level"] = agent_data.get("interest_level")
                    agent_status_info["lead_status"] = agent_data.get("lead_status")
                    if agent_data.get("enhanced_facts"):
                        agent_status_info["facts_count"] = len(agent_data["enhanced_facts"])
                yield f"data: {json.dumps(agent_status_info)}\n\n"

            for item in bot.chat_stream(
                message,
                conversation_history=conversation_history,
                user_context=user_context,
                potential_matches=request.potential_matches,
                is_admin=request.is_admin,
                panel_views=request.panel_views,
                agent_data=agent_data,
                include_debug=request.include_debug
            ):
                # Check if this is debug info (tuple with __DEBUG__ marker)
                if isinstance(item, tuple) and item[0] == "__DEBUG__":
                    debug_info = item[1]
                    yield f"data: {json.dumps({'debug_info': debug_info})}\n\n"
                    continue

                token = item
                collected_response.append(token)
                yield f"data: {json.dumps({'token': token})}\n\n"
                await asyncio.sleep(0)  # Yield to event loop for streaming

            # Store the exchange in this user's session after streaming completes
            if request.user_id:
                full_response = "".join(collected_response)
                if request.user_id not in user_sessions:
                    user_sessions[request.user_id] = []
                user_sessions[request.user_id].append({
                    "user": message,
                    "assistant": full_response
                })

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

    # Notify agent platform of lead capture (non-blocking background task)
    if agent_client.is_configured and (email or phone or lead_score >= 2):
        asyncio.create_task(
            agent_client.notify_lead_captured(
                user_id=request.user_id,
                lead_data={
                    "name": name,
                    "email": email,
                    "phone": phone,
                    "company": company,
                    "interest_level": "hot" if lead_score >= 3 else "warm" if lead_score >= 2 else "cold",
                    "conversation_summary": summary
                }
            )
        )

    # Trigger company research if company detected (non-blocking)
    if agent_client.is_configured and company:
        asyncio.create_task(
            agent_client.trigger_company_research(
                user_id=request.user_id,
                company_name=company,
                context=f"Lead from chat - {name or 'Unknown'}"
            )
        )

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
    feedback_stats = get_feedback_stats()
    funnel_data = get_funnel_analytics(days=30)
    intent_data = get_intent_signals(days=30, min_mentions=2)[:10]  # Top 10 signals

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
                <td>
                    <span class="clickable" onclick="showConversations('{lead['id']}')">{lead['name']}</span>
                    <a href="/admin/users?password={password}&highlight={lead['id']}" class="profile-link" title="View Profile">👤</a>
                </td>
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
                <td class="notes-cell clickable" onclick="editNotes('{lead['id']}')" title="Click to edit notes">{notes_preview or '<span style=\"color:#444\">+ Add</span>'}</td>
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
                .profile-link {{ color: #666; text-decoration: none; margin-left: 8px; font-size: 0.9rem; opacity: 0.6; transition: opacity 0.2s; }}
                .profile-link:hover {{ opacity: 1; color: #68d; }}
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
                    <a href="/admin?password={password}" class="btn" style="text-decoration: none; background: #1a1a1a; border-color: #68d;">Leads</a>
                    <a href="/admin/users?password={password}" class="btn" style="text-decoration: none;">Users</a>
                    <a href="/admin/traffic?password={password}" class="btn" style="text-decoration: none;">Traffic</a>
                    <a href="/admin/quality-dashboard?password={password}" class="btn" style="text-decoration: none; color: #f88;">Quality</a>
                    <a href="/admin/training-data?password={password}" class="btn" style="text-decoration: none; background: #2a2a1a; color: #fd0;">Training</a>
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
                <div style="width: 1px; background: #333; margin: 0 10px;"></div>
                <div class="stat">
                    <div class="stat-value" style="color: #fd0;">{feedback_stats.get('exemplary_count', 0)}</div>
                    <div class="stat-label">Exemplary</div>
                </div>
                <div class="stat">
                    <div class="stat-value" style="color: #f66;">{feedback_stats.get('problematic_count', 0)}</div>
                    <div class="stat-label">Flagged</div>
                </div>
                <div class="stat">
                    <div class="stat-value">{feedback_stats.get('avg_rating') or '-'}</div>
                    <div class="stat-label">Avg Rating</div>
                </div>
            </div>

            <!-- Lead Intelligence Panels -->
            <div style="display: flex; gap: 20px; margin-bottom: 20px; flex-wrap: wrap;">
                <!-- Funnel Panel -->
                <div style="flex: 1; min-width: 300px; background: #111; padding: 15px; border-radius: 8px; border: 1px solid #222;">
                    <div style="font-size: 0.7rem; color: #666; text-transform: uppercase; letter-spacing: 0.1em; margin-bottom: 15px;">Lead Funnel (30 days)</div>
                    {"".join([f'''
                        <div style="margin-bottom: 8px;">
                            <div style="display: flex; justify-content: space-between; font-size: 0.8rem; margin-bottom: 3px;">
                                <span style="color: #888;">{stage["stage"]}</span>
                                <span style="color: #e0e0e0;">{stage["count"]} <span style="color: #555;">({stage["pct"]}%)</span></span>
                            </div>
                            <div style="background: #222; height: 6px; border-radius: 3px; overflow: hidden;">
                                <div style="background: {"#6d6" if stage["stage"] == "Converted" else "#68d" if stage["stage"] in ["Contacted", "High-Intent"] else "#fd0" if stage["stage"] in ["Named", "Contact Info"] else "#888"}; height: 100%; width: {min(stage["pct"], 100)}%;"></div>
                            </div>
                        </div>
                    ''' for stage in funnel_data.get("funnel", [])]) if funnel_data.get("funnel") else '<div style="color: #555; text-align: center;">No funnel data</div>'}
                </div>

                <!-- Intent Signals Panel -->
                <div style="flex: 1; min-width: 300px; background: #111; padding: 15px; border-radius: 8px; border: 1px solid #222;">
                    <div style="font-size: 0.7rem; color: #666; text-transform: uppercase; letter-spacing: 0.1em; margin-bottom: 15px;">High-Intent Triggers (30 days)</div>
                    {"".join([f'''
                        <div style="display: flex; justify-content: space-between; padding: 4px 0; border-bottom: 1px solid #1a1a1a; font-size: 0.8rem;">
                            <span style="color: #e0e0e0;">"{sig["keyword"]}"</span>
                            <span>
                                <span style="color: #888;">{sig["mentions"]} mentions</span>
                                <span style="color: {"#6d6" if sig["intent_rate"] >= 70 else "#fd0" if sig["intent_rate"] >= 50 else "#888"}; margin-left: 8px;">{sig["intent_rate"]}% high-intent</span>
                            </span>
                        </div>
                    ''' for sig in intent_data[:8]]) if intent_data else '<div style="color: #555; text-align: center;">No signals yet</div>'}
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
                    // Fetch conversations and journey in parallel
                    const [convResp, journeyResp] = await Promise.all([
                        fetch(`/admin/lead/${{userId}}?password=${{PASSWORD}}`),
                        fetch(`/admin/user/${{userId}}/journey?password=${{PASSWORD}}`)
                    ]);

                    if (!convResp.ok) {{ alert('Failed to load conversations'); return; }}
                    const data = await convResp.json();
                    const journeyData = journeyResp.ok ? await journeyResp.json() : {{ journey: [] }};

                    document.getElementById('convModalTitle').textContent = data.name + "'s Profile";

                    let html = '';

                    // User Journey Timeline
                    if (journeyData.journey && journeyData.journey.length > 0) {{
                        html += '<div style="margin-bottom: 25px; padding: 15px; background: #0d1117; border-radius: 8px; border: 1px solid #222;">';
                        html += '<div style="font-size: 0.7rem; color: #666; text-transform: uppercase; letter-spacing: 0.1em; margin-bottom: 12px;">User Journey</div>';
                        html += '<div style="position: relative; padding-left: 20px; border-left: 2px solid #333;">';

                        let prevDate = '';
                        for (const event of journeyData.journey.slice(0, 15)) {{
                            const date = event.timestamp ? event.timestamp.slice(0, 10) : '';
                            const time = event.timestamp ? event.timestamp.slice(11, 16) : '';
                            const isNewDay = date !== prevDate;
                            prevDate = date;

                            const typeColors = {{
                                'milestone': '#6d6',
                                'intent': '#fd0',
                                'browse': '#68d',
                                'conversation': '#888',
                                'status': '#f6f'
                            }};
                            const color = typeColors[event.type] || '#666';

                            if (isNewDay && date) {{
                                html += `<div style="font-size: 0.7rem; color: #555; margin: 10px 0 5px -20px; padding-left: 20px; border-left: 2px solid #555;">${{date}}</div>`;
                            }}

                            html += `<div style="margin-bottom: 8px; position: relative;">`;
                            html += `<div style="position: absolute; left: -24px; top: 3px; width: 8px; height: 8px; background: ${{color}}; border-radius: 50%;"></div>`;
                            html += `<div style="font-size: 0.8rem;">`;
                            html += `<span style="color: ${{color}};">${{event.event}}</span>`;
                            if (event.details) {{
                                html += `<span style="color: #555; margin-left: 8px;">${{event.details}}</span>`;
                            }}
                            if (time) {{
                                html += `<span style="color: #444; margin-left: 8px; font-size: 0.7rem;">${{time}}</span>`;
                            }}
                            html += `</div></div>`;
                        }}

                        html += '</div></div>';
                    }}

                    // Conversations
                    html += '<div style="font-size: 0.7rem; color: #666; text-transform: uppercase; letter-spacing: 0.1em; margin-bottom: 12px;">Conversations</div>';

                    if (data.conversations && data.conversations.length > 0) {{
                        for (const conv of data.conversations) {{
                            html += `<div class="conversation-date">Conversation on ${{conv.created_at ? conv.created_at.slice(0,10) : 'Unknown'}} (Score: ${{conv.lead_score || 1}})</div>`;
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
                        html += '<p style="color:#666">No conversations yet</p>';
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
        timestamp_full = ex['timestamp'] if ex['timestamp'] else ''
        timestamp_display = ex['timestamp'][:16].replace('T', ' ') if ex['timestamp'] else 'N/A'

        # Escape HTML in content
        question_preview = question_preview.replace('<', '&lt;').replace('>', '&gt;')
        answer_preview = answer_preview.replace('<', '&lt;').replace('>', '&gt;')
        full_question = ex['question'].replace('<', '&lt;').replace('>', '&gt;').replace('\n', '<br>')
        full_answer = ex['answer'].replace('<', '&lt;').replace('>', '&gt;').replace('\n', '<br>')

        rows += f"""
            <tr class="exchange-row" onclick="toggleExpand(this)">
                <td class="user-link" onclick="event.stopPropagation(); showUserProfile('{ex['user_id']}')">{ex['user_name']}</td>
                <td>{question_preview}</td>
                <td>{answer_preview}</td>
                <td class="timestamp" data-timestamp="{timestamp_full}">{timestamp_display}</td>
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
                .user-link {{ cursor: pointer; transition: color 0.2s; }}
                .user-link:hover {{ color: #0f94d2; text-decoration: underline; }}
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
                </div>
                <div style="display: flex; gap: 10px;">
                    <a href="/admin?password={password}" style="color: #68d; text-decoration: none; padding: 8px 16px; border: 1px solid #333; border-radius: 4px;">Leads</a>
                    <a href="/admin/users?password={password}" style="color: #68d; text-decoration: none; padding: 8px 16px; border: 1px solid #333; border-radius: 4px;">Users</a>
                    <a href="/admin/traffic?password={password}" style="color: #68d; text-decoration: none; padding: 8px 16px; border: 1px solid #68d; border-radius: 4px; background: #1a1a1a;">Traffic</a>
                    <a href="/admin/quality-dashboard?password={password}" style="color: #f88; text-decoration: none; padding: 8px 16px; border: 1px solid #333; border-radius: 4px;">Quality</a>
                    <a href="/admin/training-data?password={password}" style="color: #fd0; text-decoration: none; padding: 8px 16px; border: 1px solid #333; border-radius: 4px;">Training</a>
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
                const PASSWORD = '{password}';

                function toggleExpand(row) {{
                    const expandedRow = row.nextElementSibling;
                    if (expandedRow && expandedRow.classList.contains('expanded-row')) {{
                        expandedRow.style.display = expandedRow.style.display === 'none' ? 'table-row' : 'none';
                    }}
                }}

                function goToPage(page) {{
                    window.location.href = '/admin/traffic?password=' + PASSWORD + '&page=' + page;
                }}

                function showUserProfile(userId) {{
                    window.location.href = '/admin/users?password=' + PASSWORD + '&highlight=' + userId;
                }}

                // Format timestamps as relative time
                function formatRelativeTime(timestamp) {{
                    if (!timestamp) return 'N/A';
                    const date = new Date(timestamp);
                    const now = new Date();
                    const diffMs = now - date;
                    const diffSec = Math.floor(diffMs / 1000);
                    const diffMin = Math.floor(diffSec / 60);
                    const diffHour = Math.floor(diffMin / 60);
                    const diffDay = Math.floor(diffHour / 24);

                    if (diffSec < 60) return 'just now';
                    if (diffMin < 60) return diffMin + ' min ago';
                    if (diffHour < 24) return diffHour + 'h ago';
                    if (diffDay < 7) return diffDay + 'd ago';
                    return date.toLocaleDateString();
                }}

                // Update timestamps on load
                document.querySelectorAll('.timestamp[data-timestamp]').forEach(el => {{
                    const ts = el.getAttribute('data-timestamp');
                    if (ts) {{
                        el.textContent = formatRelativeTime(ts);
                        el.title = ts.slice(0, 16).replace('T', ' ');
                    }}
                }});
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


@app.get("/admin/users")
async def admin_users(
    password: str = Query(None),
    auth: str = Query(None),
    status: str = Query(None),
    search: str = Query(None),
    sort: str = Query('last_seen'),
    page: int = Query(1),
    highlight: str = Query(None)
):
    """Admin users dashboard - view and manage all users."""
    # Show login form if no password
    if not password:
        return HTMLResponse("""
            <html>
            <head><title>Admin Users - Login</title></head>
            <body style="font-family: monospace; display: flex; justify-content: center; align-items: center; height: 100vh; background: #0a0a0a;">
                <form style="background: #1a1a1a; padding: 40px; border-radius: 10px; color: #e0e0e0; border: 1px solid #333;">
                    <h2>Users Dashboard Login</h2>
                    <input type="password" name="password" placeholder="Password" style="padding: 10px; width: 200px; margin: 10px 0; background: #0d0d0d; color: #e0e0e0; border: 1px solid #333;">
                    <button type="submit" style="padding: 10px 20px; background: #333; color: #e0e0e0; border: none; cursor: pointer;">Login</button>
                </form>
            </body>
            </html>
        """)

    if password != ADMIN_PASSWORD:
        raise HTTPException(status_code=401, detail="Invalid password")

    # Get paginated users
    per_page = 50
    offset = (page - 1) * per_page
    data = get_all_users(
        auth_method=auth if auth != 'all' else None,
        status=status if status != 'all' else None,
        search=search,
        sort_by=sort,
        sort_order='desc',
        limit=per_page,
        offset=offset
    )

    # Build table rows
    rows = ""
    for user in data['users']:
        # Auth badge
        auth_method = user.get('auth_method', 'soft')
        if user.get('name', '').startswith('ANON['):
            auth_badge = '<span class="auth-badge auth-anon" title="Anonymous">?</span>'
        elif auth_method == 'medium':
            auth_badge = '<span class="auth-badge auth-hard" title="Hard Login">H</span>'
        elif auth_method == 'google':
            auth_badge = '<span class="auth-badge auth-google" title="Google">G</span>'
        else:
            auth_badge = '<span class="auth-badge auth-soft" title="Soft Login">S</span>'

        # Status color
        status_val = user.get('status') or 'new'
        status_colors = {"new": "#666", "contacted": "#68d", "qualified": "#da6", "converted": "#6d6", "archived": "#888"}
        status_color = status_colors.get(status_val, "#666")

        # Format last seen
        last_seen = user.get('last_seen', '')[:10] if user.get('last_seen') else '-'

        name = user.get('name') or '-'
        email = user.get('email') or '-'
        company = user.get('company') or '-'

        rows += f"""
            <tr class="user-row" data-id="{user['id']}">
                <td>{auth_badge}</td>
                <td class="clickable" onclick="showUserDetail('{user['id']}')">{name}</td>
                <td>{email}</td>
                <td>{company}</td>
                <td style="color: {status_color};">{status_val}</td>
                <td>{user.get('conversation_count', 0)}</td>
                <td>{user.get('fact_count', 0)}</td>
                <td>{last_seen}</td>
            </tr>
        """

    # Build pagination
    prev_disabled = "disabled" if page <= 1 else ""
    next_disabled = "disabled" if page >= data['total_pages'] else ""

    # Build query string for pagination
    query_params = f"password={password}"
    if auth:
        query_params += f"&auth={auth}"
    if status:
        query_params += f"&status={status}"
    if search:
        query_params += f"&search={search}"
    if sort:
        query_params += f"&sort={sort}"

    return HTMLResponse(f"""
        <html>
        <head>
            <title>Maurice's Users Dashboard</title>
            <style>
                * {{ margin: 0; padding: 0; box-sizing: border-box; }}
                body {{ font-family: 'IBM Plex Mono', monospace; background: #0a0a0a; color: #e0e0e0; min-height: 100vh; padding: 30px; }}
                .header {{ display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px; }}
                .header h1 {{ font-size: 1.4rem; font-weight: normal; color: #888; }}
                .local-badge {{ background: #2a4a2a; color: #6f6; padding: 4px 8px; border-radius: 4px; font-size: 0.75rem; margin-left: 10px; }}
                .nav-links {{ display: flex; gap: 10px; }}
                .nav-links a {{ color: #68d; text-decoration: none; padding: 8px 16px; border: 1px solid #333; border-radius: 4px; }}
                .nav-links a:hover {{ background: #1a1a1a; }}
                .nav-links a.active {{ background: #1a1a1a; border-color: #68d; }}
                .filters {{ display: flex; gap: 15px; margin-bottom: 20px; flex-wrap: wrap; align-items: center; }}
                .filter-group {{ display: flex; align-items: center; gap: 8px; }}
                .filter-group label {{ color: #666; font-size: 0.8rem; }}
                .filter-input {{ padding: 8px 12px; font-family: monospace; background: #1a1a1a; color: #e0e0e0; border: 1px solid #333; border-radius: 4px; }}
                .filter-input:focus {{ outline: none; border-color: #555; }}
                .stats-bar {{ display: flex; gap: 20px; padding: 15px 0; margin-bottom: 15px; }}
                .stat {{ text-align: center; }}
                .stat-value {{ font-size: 1.3rem; font-weight: bold; color: #68d; }}
                .stat-label {{ font-size: 0.7rem; color: #666; text-transform: uppercase; }}
                table {{ border-collapse: collapse; width: 100%; background: #111; border-radius: 8px; overflow: hidden; }}
                th {{ background: #1a1a1a; padding: 12px; text-align: left; font-weight: normal; text-transform: uppercase; font-size: 0.7rem; letter-spacing: 0.1em; color: #666; }}
                td {{ padding: 12px; border-bottom: 1px solid #222; }}
                tr:hover {{ background: #1a1a1a; }}
                .clickable {{ cursor: pointer; }}
                .clickable:hover {{ text-decoration: underline; color: #68d; }}
                .user-row.highlighted {{ background: #1a3a2a; animation: highlight-fade 3s ease-out; }}
                @keyframes highlight-fade {{ from {{ background: #2a5a3a; }} to {{ background: #1a3a2a; }} }}
                .auth-badge {{ display: inline-flex; align-items: center; justify-content: center; width: 24px; height: 24px; border-radius: 50%; font-size: 0.75rem; font-weight: bold; }}
                .auth-hard {{ background: #2a4a2a; color: #6d6; }}
                .auth-soft {{ background: #2a3a4a; color: #68d; }}
                .auth-google {{ background: #4a3a2a; color: #da6; }}
                .auth-anon {{ background: #333; color: #666; }}
                .pagination {{ display: flex; justify-content: center; align-items: center; gap: 20px; padding: 20px; }}
                .pagination button {{ padding: 8px 16px; background: #333; color: #e0e0e0; border: none; border-radius: 4px; cursor: pointer; font-family: monospace; }}
                .pagination button:disabled {{ background: #222; color: #555; cursor: not-allowed; }}
                .pagination button:hover:not(:disabled) {{ background: #444; }}
                .modal {{ display: none; position: fixed; top: 0; left: 0; width: 100%; height: 100%; background: rgba(0,0,0,0.8); z-index: 1000; overflow-y: auto; }}
                .modal-content {{ background: #1a1a1a; margin: 3% auto; padding: 30px; width: 90%; max-width: 900px; border-radius: 8px; border: 1px solid #333; }}
                .modal-header {{ display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px; padding-bottom: 15px; border-bottom: 1px solid #333; }}
                .modal-close {{ font-size: 24px; cursor: pointer; color: #666; }}
                .modal-close:hover {{ color: #fff; }}
                .user-profile {{ display: grid; grid-template-columns: 1fr 1fr; gap: 20px; margin-bottom: 20px; }}
                .profile-field {{ }}
                .profile-label {{ font-size: 0.7rem; color: #666; text-transform: uppercase; margin-bottom: 4px; }}
                .profile-value {{ color: #e0e0e0; }}
                .section-title {{ font-size: 0.8rem; color: #666; text-transform: uppercase; letter-spacing: 0.1em; margin: 20px 0 10px; padding-bottom: 5px; border-bottom: 1px solid #333; }}
                .fact-item {{ display: flex; justify-content: space-between; padding: 8px 0; border-bottom: 1px solid #222; }}
                .fact-type {{ color: #68d; }}
                .fact-value {{ color: #e0e0e0; }}
                .fact-confidence {{ color: #666; font-size: 0.8rem; }}
                .conversation-item {{ background: #111; border-radius: 4px; padding: 15px; margin-bottom: 10px; }}
                .conversation-header {{ display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px; }}
                .conversation-date {{ color: #666; }}
                .conversation-score {{ padding: 2px 8px; border-radius: 4px; font-size: 0.8rem; }}
                .score-high {{ background: #2a4a2a; color: #6d6; }}
                .score-med {{ background: #4a4a2a; color: #aa4; }}
                .score-low {{ background: #333; color: #666; }}
                .message {{ padding: 8px 12px; margin: 4px 0; border-radius: 4px; font-size: 0.9rem; }}
                .message-user {{ background: #1a2a3a; border-left: 3px solid #68d; }}
                .message-assistant {{ background: #1a1a1a; border-left: 3px solid #666; }}
                .message-role {{ font-size: 0.7rem; color: #666; margin-bottom: 4px; }}
                .stats-grid {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 15px; margin-bottom: 20px; }}
                .stat-card {{ background: #111; padding: 15px; border-radius: 4px; text-align: center; }}
            </style>
        </head>
        <body>
            <div class="header">
                <div>
                    <h1>Maurice's Users Dashboard <span class="local-badge">LOCAL</span></h1>
                </div>
                <div class="nav-links">
                    <a href="/admin?password={password}">Leads</a>
                    <a href="/admin/users?password={password}" class="active">Users</a>
                    <a href="/admin/traffic?password={password}">Traffic</a>
                    <a href="/admin/quality-dashboard?password={password}" style="color: #f88;">Quality</a>
                    <a href="/admin/training-data?password={password}" style="color: #fd0;">Training</a>
                </div>
            </div>

            <div class="stats-bar">
                <div class="stat">
                    <div class="stat-value">{data['total']}</div>
                    <div class="stat-label">Total Users</div>
                </div>
            </div>

            <div class="filters">
                <div class="filter-group">
                    <label>Auth:</label>
                    <select class="filter-input" id="authFilter" onchange="applyFilters()">
                        <option value="all" {"selected" if not auth or auth == "all" else ""}>All</option>
                        <option value="anonymous" {"selected" if auth == "anonymous" else ""}>Anonymous</option>
                        <option value="soft" {"selected" if auth == "soft" else ""}>Soft Login</option>
                        <option value="medium" {"selected" if auth == "medium" else ""}>Hard Login</option>
                        <option value="google" {"selected" if auth == "google" else ""}>Google</option>
                    </select>
                </div>
                <div class="filter-group">
                    <label>Status:</label>
                    <select class="filter-input" id="statusFilter" onchange="applyFilters()">
                        <option value="all" {"selected" if not status or status == "all" else ""}>All</option>
                        <option value="new" {"selected" if status == "new" else ""}>New</option>
                        <option value="contacted" {"selected" if status == "contacted" else ""}>Contacted</option>
                        <option value="qualified" {"selected" if status == "qualified" else ""}>Qualified</option>
                        <option value="converted" {"selected" if status == "converted" else ""}>Converted</option>
                        <option value="archived" {"selected" if status == "archived" else ""}>Archived</option>
                    </select>
                </div>
                <div class="filter-group">
                    <label>Sort:</label>
                    <select class="filter-input" id="sortFilter" onchange="applyFilters()">
                        <option value="last_seen" {"selected" if sort == "last_seen" else ""}>Last Seen</option>
                        <option value="created_at" {"selected" if sort == "created_at" else ""}>Created</option>
                        <option value="name" {"selected" if sort == "name" else ""}>Name</option>
                        <option value="conversations" {"selected" if sort == "conversations" else ""}>Conversations</option>
                    </select>
                </div>
                <div class="filter-group">
                    <label>Search:</label>
                    <input type="text" class="filter-input" id="searchInput" value="{search or ''}" placeholder="Name, email, company..." style="width: 200px;">
                    <button class="filter-input" onclick="applyFilters()" style="cursor: pointer;">Search</button>
                </div>
                <div style="color: #666; font-size: 0.85rem;">
                    Showing {len(data['users'])} of {data['total']}
                </div>
            </div>

            <table>
                <thead>
                    <tr>
                        <th style="width: 50px;">Auth</th>
                        <th>Name</th>
                        <th>Email</th>
                        <th>Company</th>
                        <th>Status</th>
                        <th style="width: 80px;">Conv</th>
                        <th style="width: 80px;">Facts</th>
                        <th style="width: 100px;">Last Seen</th>
                    </tr>
                </thead>
                <tbody id="usersTable">
                    {rows if rows else '<tr><td colspan="8" style="text-align: center; padding: 40px; color: #666;">No users found</td></tr>'}
                </tbody>
            </table>

            <div class="pagination">
                <button onclick="goToPage({page - 1})" {prev_disabled}>&lt; Prev</button>
                <span>Page {data['page']} of {data['total_pages']}</span>
                <button onclick="goToPage({page + 1})" {next_disabled}>Next &gt;</button>
            </div>

            <!-- User Detail Modal -->
            <div id="userModal" class="modal" onclick="if(event.target===this)closeModal()">
                <div class="modal-content">
                    <div class="modal-header">
                        <h2 id="modalTitle">User Details</h2>
                        <span class="modal-close" onclick="closeModal()">&times;</span>
                    </div>
                    <div id="modalBody">Loading...</div>
                </div>
            </div>

            <script>
                const PASSWORD = '{password}';

                function applyFilters() {{
                    const auth = document.getElementById('authFilter').value;
                    const status = document.getElementById('statusFilter').value;
                    const sort = document.getElementById('sortFilter').value;
                    const search = document.getElementById('searchInput').value;

                    let url = `/admin/users?password=${{PASSWORD}}`;
                    if (auth && auth !== 'all') url += `&auth=${{auth}}`;
                    if (status && status !== 'all') url += `&status=${{status}}`;
                    if (sort) url += `&sort=${{sort}}`;
                    if (search) url += `&search=${{encodeURIComponent(search)}}`;

                    window.location.href = url;
                }}

                function goToPage(page) {{
                    const auth = document.getElementById('authFilter').value;
                    const status = document.getElementById('statusFilter').value;
                    const sort = document.getElementById('sortFilter').value;
                    const search = document.getElementById('searchInput').value;

                    let url = `/admin/users?password=${{PASSWORD}}&page=${{page}}`;
                    if (auth && auth !== 'all') url += `&auth=${{auth}}`;
                    if (status && status !== 'all') url += `&status=${{status}}`;
                    if (sort) url += `&sort=${{sort}}`;
                    if (search) url += `&search=${{encodeURIComponent(search)}}`;

                    window.location.href = url;
                }}

                async function showUserDetail(userId) {{
                    document.getElementById('userModal').style.display = 'block';
                    document.getElementById('modalBody').innerHTML = 'Loading...';

                    try {{
                        const resp = await fetch(`/admin/users/${{userId}}?password=${{PASSWORD}}`);
                        if (!resp.ok) throw new Error('Failed to load user');
                        const data = await resp.json();

                        const user = data.user;
                        document.getElementById('modalTitle').textContent = user.name || 'Unknown User';

                        // Build profile HTML
                        let html = `
                            <div class="stats-grid">
                                <div class="stat-card">
                                    <div class="stat-value">${{data.stats.total_conversations}}</div>
                                    <div class="stat-label">Conversations</div>
                                </div>
                                <div class="stat-card">
                                    <div class="stat-value">${{data.stats.total_messages}}</div>
                                    <div class="stat-label">Messages</div>
                                </div>
                                <div class="stat-card">
                                    <div class="stat-value">${{data.stats.avg_lead_score}}</div>
                                    <div class="stat-label">Avg Score</div>
                                </div>
                                <div class="stat-card">
                                    <div class="stat-value">${{data.stats.days_since_first_contact}}</div>
                                    <div class="stat-label">Days Active</div>
                                </div>
                            </div>

                            <div class="user-profile">
                                <div class="profile-field">
                                    <div class="profile-label">Email</div>
                                    <div class="profile-value">${{user.email || '-'}}</div>
                                </div>
                                <div class="profile-field">
                                    <div class="profile-label">Phone</div>
                                    <div class="profile-value">${{user.phone || '-'}}</div>
                                </div>
                                <div class="profile-field">
                                    <div class="profile-label">Company</div>
                                    <div class="profile-value">${{user.company || '-'}}</div>
                                </div>
                                <div class="profile-field">
                                    <div class="profile-label">Auth Method</div>
                                    <div class="profile-value">${{user.auth_method || 'soft'}}</div>
                                </div>
                                <div class="profile-field">
                                    <div class="profile-label">Status</div>
                                    <div class="profile-value">${{user.status || 'new'}}</div>
                                </div>
                                <div class="profile-field">
                                    <div class="profile-label">Interest Level</div>
                                    <div class="profile-value">${{user.interest_level || '-'}}</div>
                                </div>
                                <div class="profile-field">
                                    <div class="profile-label">First Contact</div>
                                    <div class="profile-value">${{user.created_at ? user.created_at.slice(0,10) : '-'}}</div>
                                </div>
                                <div class="profile-field">
                                    <div class="profile-label">Last Seen</div>
                                    <div class="profile-value">${{user.last_seen ? user.last_seen.slice(0,10) : '-'}}</div>
                                </div>
                            </div>
                        `;

                        // Facts section
                        if (data.facts && data.facts.length > 0) {{
                            html += '<div class="section-title">Extracted Facts</div>';
                            for (const fact of data.facts) {{
                                const confidence = Math.round(fact.confidence * 100);
                                html += `
                                    <div class="fact-item">
                                        <span class="fact-type">${{fact.type}}</span>
                                        <span class="fact-value">${{fact.value}}</span>
                                        <span class="fact-confidence">${{confidence}}%</span>
                                    </div>
                                `;
                            }}
                        }}

                        // Browsing History section
                        if (data.browsing_history && data.browsing_history.length > 0) {{
                            html += '<div class="section-title">Browsing Activity</div>';
                            html += '<div style="max-height: 200px; overflow-y: auto; background: #1a1a2e; border-radius: 8px; padding: 10px;">';
                            for (const view of data.browsing_history) {{
                                const timestamp = view.created_at ? view.created_at.slice(0, 16).replace('T', ' ') : '?';
                                const viewType = view.view_type || 'view';
                                const title = view.title || 'unknown';
                                let icon = '📄';
                                let displayText = title;

                                if (viewType === 'panel') {{
                                    icon = '📁';
                                    displayText = title;
                                }} else if (viewType === 'link') {{
                                    icon = '🔗';
                                    displayText = title;
                                }} else if (viewType === 'external') {{
                                    icon = '🌐';
                                    // Extract domain from URL
                                    const url = view.url || title;
                                    try {{
                                        displayText = new URL(url).hostname;
                                    }} catch {{
                                        displayText = url.substring(0, 50);
                                    }}
                                }}

                                html += `
                                    <div style="display: flex; gap: 8px; padding: 4px 0; border-bottom: 1px solid #333; font-size: 0.85rem;">
                                        <span style="color: #666; white-space: nowrap;">${{timestamp}}</span>
                                        <span>${{icon}}</span>
                                        <span style="color: #aaa; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">${{displayText}}</span>
                                    </div>
                                `;
                            }}
                            html += '</div>';
                        }}

                        // Conversations section
                        if (data.conversations && data.conversations.length > 0) {{
                            html += '<div class="section-title">Conversation History</div>';
                            for (const conv of data.conversations) {{
                                const scoreClass = conv.lead_score >= 3 ? 'score-high' : conv.lead_score >= 2 ? 'score-med' : 'score-low';
                                const date = conv.created_at ? conv.created_at.slice(0,10) : 'Unknown';

                                html += `
                                    <div class="conversation-item">
                                        <div class="conversation-header">
                                            <span class="conversation-date">${{date}} (${{conv.message_count}} messages)</span>
                                            <span class="conversation-score ${{scoreClass}}">Score: ${{conv.lead_score}}</span>
                                        </div>
                                `;

                                if (conv.messages && conv.messages.length > 0) {{
                                    for (const msg of conv.messages) {{
                                        const roleClass = msg.role === 'user' ? 'message-user' : 'message-assistant';
                                        const roleLabel = msg.role === 'user' ? 'User' : 'Maurice';
                                        const content = msg.content || '';
                                        html += `
                                            <div class="message ${{roleClass}}">
                                                <div class="message-role">${{roleLabel}}</div>
                                                ${{content.replace(/</g, '&lt;').replace(/>/g, '&gt;')}}
                                            </div>
                                        `;
                                    }}
                                }}

                                html += '</div>';
                            }}
                        }} else {{
                            html += '<div style="color: #666; padding: 20px; text-align: center;">No conversations yet</div>';
                        }}

                        document.getElementById('modalBody').innerHTML = html;

                    }} catch (e) {{
                        document.getElementById('modalBody').innerHTML = `<div style="color: #f66;">Error loading user: ${{e.message}}</div>`;
                    }}
                }}

                function closeModal() {{
                    document.getElementById('userModal').style.display = 'none';
                }}

                document.addEventListener('keydown', (e) => {{
                    if (e.key === 'Escape') closeModal();
                }});

                // Enter key in search
                document.getElementById('searchInput').addEventListener('keypress', (e) => {{
                    if (e.key === 'Enter') applyFilters();
                }});

                // Handle highlight parameter - scroll to and highlight user
                const highlightUserId = '{highlight or ''}';
                if (highlightUserId) {{
                    const userRow = document.querySelector(`tr.user-row[data-id="${{highlightUserId}}"]`);
                    if (userRow) {{
                        userRow.classList.add('highlighted');
                        userRow.scrollIntoView({{ behavior: 'smooth', block: 'center' }});
                        // Also open the user detail modal
                        showUserDetail(highlightUserId);
                    }}
                }}
            </script>
        </body>
        </html>
    """)


@app.get("/admin/users/{user_id}")
async def admin_user_detail(user_id: str, password: str = Query(...)):
    """Get full user profile for admin modal."""
    if password != ADMIN_PASSWORD:
        raise HTTPException(status_code=401, detail="Unauthorized")

    profile = get_user_full_profile(user_id)
    if profile is None:
        raise HTTPException(status_code=404, detail="User not found")

    # Add browsing history
    profile["browsing_history"] = get_user_page_views(user_id, limit=50)

    return profile


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


# ============================================
# Response Feedback Endpoints
# ============================================

@app.post("/admin/feedback")
async def submit_feedback(request: FeedbackRequest, password: str = Query(...)):
    """Submit feedback on a Maurice response."""
    if password != ADMIN_PASSWORD:
        raise HTTPException(status_code=401, detail="Unauthorized")

    feedback_id = save_response_feedback(
        conversation_id=request.conversation_id,
        message_index=request.message_index,
        rating=request.rating,
        feedback_type=request.feedback_type,
        notes=request.notes,
        corrected_response=request.corrected_response,
        is_exemplary=request.is_exemplary,
        is_problematic=request.is_problematic
    )

    if feedback_id is None:
        raise HTTPException(status_code=400, detail="Failed to save feedback")

    return {"status": "saved", "feedback_id": feedback_id}


@app.get("/admin/feedback/{conversation_id}")
async def get_conversation_feedback(conversation_id: int, password: str = Query(...)):
    """Get all feedback for a conversation."""
    if password != ADMIN_PASSWORD:
        raise HTTPException(status_code=401, detail="Unauthorized")

    feedback = get_response_feedback(conversation_id)
    return {"feedback": feedback}


@app.get("/admin/feedback/stats")
async def feedback_statistics(password: str = Query(...)):
    """Get aggregate feedback statistics."""
    if password != ADMIN_PASSWORD:
        raise HTTPException(status_code=401, detail="Unauthorized")

    stats = get_feedback_stats()
    return stats


@app.get("/admin/feedback/exemplary")
async def exemplary_responses(password: str = Query(...), limit: int = 100):
    """Get exemplary responses for training data."""
    if password != ADMIN_PASSWORD:
        raise HTTPException(status_code=401, detail="Unauthorized")

    responses = get_exemplary_responses(limit=limit)
    return {"responses": responses, "count": len(responses)}


@app.get("/admin/feedback/problematic")
async def problematic_responses(password: str = Query(...), limit: int = 100):
    """Get problematic responses for review."""
    if password != ADMIN_PASSWORD:
        raise HTTPException(status_code=401, detail="Unauthorized")

    responses = get_problematic_responses(limit=limit)
    return {"responses": responses, "count": len(responses)}


@app.get("/admin/feedback/export")
async def export_training_data(password: str = Query(...)):
    """Export exemplary responses as JSONL for fine-tuning."""
    if password != ADMIN_PASSWORD:
        raise HTTPException(status_code=401, detail="Unauthorized")

    responses = get_exemplary_responses(limit=1000)

    # Format as JSONL training data
    jsonl_lines = []
    for r in responses:
        if r.get("user_message") and r.get("assistant_response"):
            # Use corrected response if available, otherwise original
            response = r.get("corrected_response") or r.get("assistant_response")
            training_example = {
                "messages": [
                    {"role": "user", "content": r["user_message"]},
                    {"role": "assistant", "content": response}
                ]
            }
            jsonl_lines.append(json.dumps(training_example))

    content = "\n".join(jsonl_lines)

    return StreamingResponse(
        iter([content]),
        media_type="application/jsonl",
        headers={"Content-Disposition": "attachment; filename=training_data.jsonl"}
    )


# ============================================
# Training Data Management Endpoints
# ============================================

@app.post("/admin/training")
async def create_training_example(request: TrainingExampleRequest, password: str = Query(...)):
    """Create a new training example."""
    if password != ADMIN_PASSWORD:
        raise HTTPException(status_code=401, detail="Unauthorized")

    example_id = save_training_example(
        user_message=request.user_message,
        assistant_response=request.assistant_response,
        category=request.category,
        difficulty=request.difficulty,
        relevant_facts=request.relevant_facts,
        rag_context=request.rag_context,
        source_conversation_id=request.source_conversation_id,
        source_feedback_id=request.source_feedback_id,
        quality_score=request.quality_score,
        reviewer_notes=request.reviewer_notes,
        created_by="admin"
    )

    if example_id is None:
        raise HTTPException(status_code=400, detail="Failed to create training example")

    return {"status": "created", "id": example_id}


@app.get("/admin/training")
async def list_training_examples(
    password: str = Query(...),
    status: Optional[str] = None,
    category: Optional[str] = None,
    limit: int = 50,
    offset: int = 0
):
    """List training examples with filtering."""
    if password != ADMIN_PASSWORD:
        raise HTTPException(status_code=401, detail="Unauthorized")

    return get_training_examples(status=status, category=category, limit=limit, offset=offset)


@app.get("/admin/training/stats")
async def training_stats(password: str = Query(...)):
    """Get training data statistics."""
    if password != ADMIN_PASSWORD:
        raise HTTPException(status_code=401, detail="Unauthorized")

    return get_training_stats()


@app.get("/admin/training/candidates")
async def training_candidates(password: str = Query(...), limit: int = 50):
    """Get auto-suggested training candidates."""
    if password != ADMIN_PASSWORD:
        raise HTTPException(status_code=401, detail="Unauthorized")

    candidates = get_training_candidates(limit=limit)
    return {"candidates": candidates, "count": len(candidates)}


@app.post("/admin/training/from-feedback/{feedback_id}")
async def create_from_feedback(feedback_id: int, password: str = Query(...)):
    """Create a training example from an exemplary feedback entry."""
    if password != ADMIN_PASSWORD:
        raise HTTPException(status_code=401, detail="Unauthorized")

    example_id = create_training_example_from_feedback(feedback_id, created_by="admin")

    if example_id is None:
        raise HTTPException(status_code=400, detail="Failed to create training example from feedback")

    return {"status": "created", "id": example_id}


@app.put("/admin/training/{example_id}")
async def update_training(example_id: int, request: TrainingExampleUpdateRequest, password: str = Query(...)):
    """Update a training example."""
    if password != ADMIN_PASSWORD:
        raise HTTPException(status_code=401, detail="Unauthorized")

    success = update_training_example(
        example_id=example_id,
        user_message=request.user_message,
        assistant_response=request.assistant_response,
        category=request.category,
        difficulty=request.difficulty,
        relevant_facts=request.relevant_facts,
        rag_context=request.rag_context,
        quality_score=request.quality_score,
        reviewer_notes=request.reviewer_notes,
        status=request.status
    )

    if not success:
        raise HTTPException(status_code=400, detail="Failed to update training example")

    return {"status": "updated"}


@app.delete("/admin/training/{example_id}")
async def delete_training(example_id: int, password: str = Query(...)):
    """Delete a training example."""
    if password != ADMIN_PASSWORD:
        raise HTTPException(status_code=401, detail="Unauthorized")

    success = delete_training_example(example_id)

    if not success:
        raise HTTPException(status_code=400, detail="Failed to delete training example")

    return {"status": "deleted"}


@app.get("/admin/training/export")
async def export_training(password: str = Query(...), status: str = "approved"):
    """Export training data as JSONL file for fine-tuning."""
    if password != ADMIN_PASSWORD:
        raise HTTPException(status_code=401, detail="Unauthorized")

    data = export_training_data_jsonl(status=status)

    # Format as JSONL
    jsonl_lines = [json.dumps(entry) for entry in data]
    content = "\n".join(jsonl_lines)

    return StreamingResponse(
        iter([content]),
        media_type="application/jsonl",
        headers={"Content-Disposition": f"attachment; filename=maurice_training_{status}.jsonl"}
    )


# ============================================
# Lead Intelligence Endpoints
# ============================================

@app.get("/admin/analytics/funnel")
async def funnel_analytics(password: str = Query(...), days: int = 30):
    """Get lead funnel analytics."""
    if password != ADMIN_PASSWORD:
        raise HTTPException(status_code=401, detail="Unauthorized")

    return get_funnel_analytics(days=days)


@app.get("/admin/analytics/intent-signals")
async def intent_signals(password: str = Query(...), days: int = 30, min_mentions: int = 3):
    """Get intent signals analysis."""
    if password != ADMIN_PASSWORD:
        raise HTTPException(status_code=401, detail="Unauthorized")

    signals = get_intent_signals(days=days, min_mentions=min_mentions)
    return {"signals": signals, "days": days}


@app.get("/admin/analytics/high-intent")
async def high_intent_leads(password: str = Query(...), days: int = 7, limit: int = 10):
    """Get recent high-intent leads."""
    if password != ADMIN_PASSWORD:
        raise HTTPException(status_code=401, detail="Unauthorized")

    leads = get_recent_high_intent_leads(days=days, limit=limit)
    return {"leads": leads, "count": len(leads)}


@app.get("/admin/user/{user_id}/journey")
async def user_journey(user_id: str, password: str = Query(...)):
    """Get user journey timeline."""
    if password != ADMIN_PASSWORD:
        raise HTTPException(status_code=401, detail="Unauthorized")

    journey = get_user_journey(user_id)
    return {"journey": journey, "event_count": len(journey)}


# ============================================
# Response Quality Endpoints
# ============================================

@app.get("/admin/quality/metrics")
async def quality_metrics(password: str = Query(...), days: int = 7):
    """Get aggregated response quality metrics."""
    if password != ADMIN_PASSWORD:
        raise HTTPException(status_code=401, detail="Unauthorized")

    return get_quality_metrics(days=days)


@app.get("/admin/quality/flagged")
async def flagged_responses(password: str = Query(...), days: int = 7, limit: int = 50):
    """Get flagged responses for review."""
    if password != ADMIN_PASSWORD:
        raise HTTPException(status_code=401, detail="Unauthorized")

    responses = get_flagged_responses(days=days, limit=limit)
    return {"responses": responses, "count": len(responses)}


@app.get("/admin/quality/hallucinations")
async def hallucinations(password: str = Query(...), days: int = 30, limit: int = 20):
    """Get hallucination examples."""
    if password != ADMIN_PASSWORD:
        raise HTTPException(status_code=401, detail="Unauthorized")

    examples = get_hallucination_examples(days=days, limit=limit)
    return {"examples": examples, "count": len(examples)}


@app.post("/admin/quality/analyze")
async def analyze_single_response(password: str = Query(...), user_message: str = "", assistant_response: str = ""):
    """Analyze a single response for quality issues."""
    if password != ADMIN_PASSWORD:
        raise HTTPException(status_code=401, detail="Unauthorized")

    if not user_message or not assistant_response:
        raise HTTPException(status_code=400, detail="Both user_message and assistant_response required")

    analysis = analyze_response_quality(user_message, assistant_response)
    return analysis


# ============================================
# Lead Handoff & Agent Integration Endpoints
# ============================================

@app.post("/admin/leads/{user_id}/draft-email")
async def draft_lead_email(user_id: str, password: str = Query(...)):
    """Generate personalized cold email draft for a lead using agent platform."""
    if password != ADMIN_PASSWORD:
        raise HTTPException(status_code=401, detail="Unauthorized")

    if not agent_client.is_configured:
        raise HTTPException(status_code=503, detail="Agent platform not configured")

    # Get user context for email generation
    user_context = get_user_context(user_id)
    if not user_context:
        raise HTTPException(status_code=404, detail="User not found")

    # Get handoff package for rich context
    handoff = create_handoff_package(user_id)

    # Draft email via agent platform
    email_result = await agent_client.draft_cold_email(
        company_name=handoff.get("user", {}).get("company") or "your company",
        contact_name=handoff.get("user", {}).get("name"),
        contact_role=handoff.get("facts", {}).get("role"),
        context=f"""
Lead context:
- Interests: {', '.join(handoff.get('interests', [])) or 'Not specified'}
- Intent signals: {', '.join(handoff.get('intent_signals', [])) or 'None detected'}
- Conversation summary: {handoff.get('conversation_summary', 'No previous conversation')}
- Suggested approach: {handoff.get('suggested_approach', 'Standard follow-up')}
"""
    )

    if not email_result.get("success"):
        raise HTTPException(status_code=500, detail=f"Email draft failed: {email_result.get('error')}")

    return {
        "draft": email_result.get("email_draft") or email_result.get("draft"),
        "subject": email_result.get("subject"),
        "user_context": {
            "name": handoff.get("user", {}).get("name"),
            "company": handoff.get("user", {}).get("company"),
            "email": handoff.get("user", {}).get("email")
        }
    }


@app.get("/admin/leads/{user_id}/handoff")
async def get_lead_handoff(user_id: str, password: str = Query(...)):
    """Get comprehensive handoff package for a lead."""
    if password != ADMIN_PASSWORD:
        raise HTTPException(status_code=401, detail="Unauthorized")

    handoff = create_handoff_package(user_id)
    if handoff.get("error"):
        raise HTTPException(status_code=404, detail=handoff["error"])

    return handoff


@app.post("/admin/leads/{user_id}/notify-handoff")
async def notify_lead_handoff(
    user_id: str,
    password: str = Query(...),
    channel: str = Query("agent")  # "agent", "slack", "email"
):
    """
    Notify sales team of lead ready for handoff.

    Channels:
    - agent: Notify agent platform (default)
    - slack: Send Slack notification (if configured)
    - email: Send email notification (if configured)
    """
    if password != ADMIN_PASSWORD:
        raise HTTPException(status_code=401, detail="Unauthorized")

    handoff = create_handoff_package(user_id)
    if handoff.get("error"):
        raise HTTPException(status_code=404, detail=handoff["error"])

    notifications_sent = []

    # Notify agent platform
    if channel == "agent" and agent_client.is_configured:
        result = await agent_client.notify_lead_captured(
            user_id=user_id,
            lead_data={
                "name": handoff.get("user", {}).get("name"),
                "email": handoff.get("user", {}).get("email"),
                "phone": handoff.get("user", {}).get("phone"),
                "company": handoff.get("user", {}).get("company"),
                "interest_level": "hot" if handoff.get("lead_score", 1) >= 3 else "warm",
                "conversation_summary": handoff.get("conversation_summary"),
                "notes": handoff.get("suggested_approach")
            }
        )
        if result.get("success"):
            notifications_sent.append("agent_platform")

    # Update lead status to indicate handoff initiated
    update_lead_status(user_id, "contacted")

    return {
        "status": "handoff_initiated",
        "notifications_sent": notifications_sent,
        "handoff_summary": {
            "name": handoff.get("user", {}).get("name"),
            "company": handoff.get("user", {}).get("company"),
            "lead_score": handoff.get("lead_score"),
            "suggested_approach": handoff.get("suggested_approach")
        }
    }


@app.get("/admin/quality-dashboard")
async def admin_quality_dashboard(password: str = Query(None), days: int = Query(7)):
    """Admin page for response quality metrics."""
    if password != ADMIN_PASSWORD:
        return HTMLResponse("""
            <html>
            <head><title>Quality Dashboard - Login</title></head>
            <body style="font-family: monospace; background: #0a0a0a; color: #e0e0e0; padding: 40px;">
                <h1>Quality Dashboard</h1>
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

    # Get quality metrics
    metrics = get_quality_metrics(days=days)
    hallucinations = get_hallucination_examples(days=30, limit=10)

    # Build flagged responses rows
    flagged_rows = ""
    for resp in metrics.get("flagged_responses", [])[:15]:
        issue_tags = " ".join([
            f'<span class="issue-tag issue-{i["severity"]}">{i["type"]}</span>'
            for i in resp.get("issues", [])
        ])
        user_preview = resp.get("user_message", "")[:60]
        asst_preview = resp.get("assistant_response", "")[:60]

        flagged_rows += f"""
            <tr>
                <td style="color: {"#f66" if resp["quality_score"] < 50 else "#fd0" if resp["quality_score"] < 80 else "#888"};">{resp["quality_score"]}</td>
                <td class="truncate">{user_preview}...</td>
                <td class="truncate">{asst_preview}...</td>
                <td>{issue_tags}</td>
                <td style="color: #555;">{resp.get("created_at", "")[:10] if resp.get("created_at") else "-"}</td>
            </tr>
        """

    # Build hallucination rows
    hallucination_rows = ""
    for h in hallucinations[:10]:
        hallucination_rows += f"""
            <tr>
                <td style="color: #f66;">"{h["pattern"]}"</td>
                <td>{h["description"]}</td>
                <td class="truncate">{h["response_excerpt"][:80]}...</td>
                <td style="color: #555;">{h.get("created_at", "")[:10] if h.get("created_at") else "-"}</td>
            </tr>
        """

    # Issue breakdown
    issue_breakdown = metrics.get("issue_breakdown", {})
    issue_bars = ""
    max_issues = max(issue_breakdown.values()) if issue_breakdown else 1
    for issue_type, count in sorted(issue_breakdown.items(), key=lambda x: -x[1]):
        width = (count / max_issues) * 100
        color = "#f66" if issue_type == "hallucination" else "#fd0" if issue_type in ["too_short", "missed_lead_capture"] else "#888"
        issue_bars += f"""
            <div style="margin-bottom: 8px;">
                <div style="display: flex; justify-content: space-between; font-size: 0.8rem; margin-bottom: 3px;">
                    <span style="color: #888;">{issue_type.replace("_", " ").title()}</span>
                    <span style="color: #e0e0e0;">{count}</span>
                </div>
                <div style="background: #222; height: 6px; border-radius: 3px; overflow: hidden;">
                    <div style="background: {color}; height: 100%; width: {width}%;"></div>
                </div>
            </div>
        """

    return HTMLResponse(f"""
        <html>
        <head>
            <title>Quality Dashboard - Maurice Admin</title>
            <style>
                body {{ font-family: 'IBM Plex Mono', monospace; background: #0a0a0a; color: #e0e0e0; padding: 20px 40px; }}
                h1, h2 {{ color: #888; font-weight: normal; }}
                h2 {{ font-size: 1rem; margin-top: 30px; text-transform: uppercase; letter-spacing: 0.1em; }}
                .header {{ display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px; }}
                .actions {{ display: flex; gap: 10px; }}
                .btn {{ padding: 8px 16px; font-family: monospace; background: #333; color: #e0e0e0; border: none; cursor: pointer; border-radius: 4px; text-decoration: none; }}
                .btn:hover {{ background: #444; }}
                .stats-bar {{ display: flex; gap: 30px; padding: 20px 0; border-bottom: 1px solid #222; margin-bottom: 20px; flex-wrap: wrap; }}
                .stat {{ text-align: center; min-width: 100px; }}
                .stat-value {{ font-size: 2rem; font-weight: bold; }}
                .stat-label {{ font-size: 0.7rem; color: #666; text-transform: uppercase; }}
                .stat-good .stat-value {{ color: #6d6; }}
                .stat-warning .stat-value {{ color: #fd0; }}
                .stat-bad .stat-value {{ color: #f66; }}
                .panels {{ display: flex; gap: 20px; margin-bottom: 20px; flex-wrap: wrap; }}
                .panel {{ flex: 1; min-width: 300px; background: #111; padding: 15px; border-radius: 8px; border: 1px solid #222; }}
                .panel-title {{ font-size: 0.7rem; color: #666; text-transform: uppercase; letter-spacing: 0.1em; margin-bottom: 15px; }}
                table {{ border-collapse: collapse; width: 100%; }}
                th, td {{ padding: 8px 10px; text-align: left; border-bottom: 1px solid #222; font-size: 0.85rem; }}
                th {{ color: #666; font-weight: normal; text-transform: uppercase; font-size: 0.7rem; letter-spacing: 0.1em; }}
                tr:hover {{ background: #1a1a1a; }}
                .truncate {{ max-width: 200px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }}
                .issue-tag {{ display: inline-block; padding: 2px 6px; border-radius: 3px; font-size: 0.7rem; margin: 1px; }}
                .issue-high {{ background: #3a1a1a; color: #f66; }}
                .issue-medium {{ background: #3a3a1a; color: #fd0; }}
                .issue-low {{ background: #1a1a1a; color: #888; }}
                .filter-select {{ padding: 6px 12px; background: #1a1a1a; color: #e0e0e0; border: 1px solid #333; border-radius: 4px; font-family: monospace; }}
            </style>
        </head>
        <body>
            <div class="header">
                <h1>Response Quality Dashboard</h1>
                <div class="actions">
                    <a href="/admin?password={password}" class="btn">Leads</a>
                    <a href="/admin/users?password={password}" class="btn">Users</a>
                    <a href="/admin/traffic?password={password}" class="btn">Traffic</a>
                    <a href="/admin/quality-dashboard?password={password}" class="btn" style="background: #1a1a1a; border: 1px solid #f88; color: #f88;">Quality</a>
                    <a href="/admin/training-data?password={password}" class="btn" style="color: #fd0;">Training</a>
                </div>
            </div>

            <div style="margin-bottom: 15px;">
                <select class="filter-select" onchange="window.location.href='/admin/quality-dashboard?password={password}&days=' + this.value">
                    <option value="7" {"selected" if days == 7 else ""}>Last 7 days</option>
                    <option value="14" {"selected" if days == 14 else ""}>Last 14 days</option>
                    <option value="30" {"selected" if days == 30 else ""}>Last 30 days</option>
                </select>
            </div>

            <!-- Stats -->
            <div class="stats-bar">
                <div class="stat {"stat-good" if metrics.get("avg_quality_score", 0) >= 80 else "stat-warning" if metrics.get("avg_quality_score", 0) >= 60 else "stat-bad"}">
                    <div class="stat-value">{metrics.get("avg_quality_score", 0)}</div>
                    <div class="stat-label">Avg Quality Score</div>
                </div>
                <div class="stat">
                    <div class="stat-value">{metrics.get("total_responses", 0)}</div>
                    <div class="stat-label">Total Responses</div>
                </div>
                <div class="stat">
                    <div class="stat-value">{metrics.get("avg_response_words", 0)}</div>
                    <div class="stat-label">Avg Response Words</div>
                </div>
                <div class="stat {"stat-good" if metrics.get("personality_rate", 0) >= 80 else "stat-warning" if metrics.get("personality_rate", 0) >= 60 else "stat-bad"}">
                    <div class="stat-value">{metrics.get("personality_rate", 0)}%</div>
                    <div class="stat-label">Personality Rate</div>
                </div>
                <div class="stat {"stat-good" if metrics.get("lead_capture_rate", 0) >= 50 else "stat-warning" if metrics.get("lead_capture_rate", 0) >= 30 else "stat-bad"}">
                    <div class="stat-value">{metrics.get("lead_capture_rate", 0)}%</div>
                    <div class="stat-label">Lead Capture Rate</div>
                </div>
                <div class="stat stat-bad">
                    <div class="stat-value">{metrics.get("flagged_count", 0)}</div>
                    <div class="stat-label">Flagged Responses</div>
                </div>
            </div>

            <!-- Issue Breakdown Panel -->
            <div class="panels">
                <div class="panel">
                    <div class="panel-title">Issue Breakdown ({days} days)</div>
                    {issue_bars if issue_bars else '<div style="color: #555; text-align: center;">No issues detected</div>'}
                </div>
            </div>

            <!-- Flagged Responses -->
            <h2>🚨 Flagged Responses</h2>
            <table>
                <thead>
                    <tr>
                        <th>Score</th>
                        <th>User Message</th>
                        <th>Response</th>
                        <th>Issues</th>
                        <th>Date</th>
                    </tr>
                </thead>
                <tbody>
                    {flagged_rows if flagged_rows else '<tr><td colspan="5" style="color: #555; text-align: center;">No flagged responses</td></tr>'}
                </tbody>
            </table>

            <!-- Hallucinations -->
            <h2>⚠️ Hallucination Examples (30 days)</h2>
            <table>
                <thead>
                    <tr>
                        <th>Pattern</th>
                        <th>Description</th>
                        <th>Response Excerpt</th>
                        <th>Date</th>
                    </tr>
                </thead>
                <tbody>
                    {hallucination_rows if hallucination_rows else '<tr><td colspan="4" style="color: #6d6; text-align: center;">No hallucinations detected! 🎉</td></tr>'}
                </tbody>
            </table>
        </body>
        </html>
    """)


@app.get("/admin/training-data")
async def admin_training_data(password: str = Query(None), status_filter: str = Query(None), page: int = Query(1)):
    """Admin page for managing training data."""
    if password != ADMIN_PASSWORD:
        return HTMLResponse("""
            <html>
            <head><title>Training Data - Login</title></head>
            <body style="font-family: monospace; background: #0a0a0a; color: #e0e0e0; padding: 40px;">
                <h1>Training Data Dashboard</h1>
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

    # Get stats and data
    stats = get_training_stats()
    offset = (page - 1) * 50
    examples_data = get_training_examples(status=status_filter, limit=50, offset=offset)
    candidates = get_training_candidates(limit=20)

    # Build examples table rows
    example_rows = ""
    for ex in examples_data['examples']:
        user_preview = (ex['user_message'][:60] + '...') if len(ex['user_message']) > 60 else ex['user_message']
        asst_preview = (ex['assistant_response'][:60] + '...') if len(ex['assistant_response']) > 60 else ex['assistant_response']

        # Escape HTML
        user_preview = user_preview.replace('<', '&lt;').replace('>', '&gt;').replace('\n', ' ')
        asst_preview = asst_preview.replace('<', '&lt;').replace('>', '&gt;').replace('\n', ' ')

        status_color = {"pending": "#fd0", "approved": "#6d6", "rejected": "#f66"}.get(ex['status'], "#666")

        example_rows += f"""
            <tr class="example-row" data-id="{ex['id']}">
                <td>{ex['id']}</td>
                <td class="truncate" title="{user_preview}">{user_preview}</td>
                <td class="truncate" title="{asst_preview}">{asst_preview}</td>
                <td>{ex['category'] or '-'}</td>
                <td>{ex['quality_score'] or '-'}</td>
                <td style="color: {status_color};">{ex['status']}</td>
                <td>
                    <button class="action-btn" onclick="viewExample({ex['id']})" title="View/Edit">👁️</button>
                    <button class="action-btn" onclick="approveExample({ex['id']})" title="Approve">✓</button>
                    <button class="action-btn" onclick="rejectExample({ex['id']})" title="Reject">✗</button>
                    <button class="action-btn delete-btn" onclick="deleteExample({ex['id']})" title="Delete">🗑️</button>
                </td>
            </tr>
        """

    # Build candidates rows
    candidate_rows = ""
    for c in candidates[:10]:
        user_preview = (c['user_message'][:50] + '...') if c.get('user_message') and len(c['user_message']) > 50 else (c.get('user_message') or '')
        user_preview = user_preview.replace('<', '&lt;').replace('>', '&gt;').replace('\n', ' ')
        source = c.get('source', 'unknown')
        priority_color = {1: '#6d6', 2: '#fd0', 3: '#68d'}.get(c.get('priority', 99), '#666')

        candidate_rows += f"""
            <tr>
                <td style="color: {priority_color};">{source}</td>
                <td class="truncate">{user_preview}</td>
                <td>
                    <button class="action-btn btn-primary" onclick="addCandidate({json.dumps(c).replace('"', '&quot;')})">+ Add</button>
                </td>
            </tr>
        """

    # Pagination
    total_pages = examples_data.get('total_pages', 1)
    prev_disabled = "disabled" if page <= 1 else ""
    next_disabled = "disabled" if page >= total_pages else ""

    return HTMLResponse(f"""
        <html>
        <head>
            <title>Training Data - Maurice Admin</title>
            <style>
                body {{ font-family: 'IBM Plex Mono', monospace; background: #0a0a0a; color: #e0e0e0; padding: 20px 40px; }}
                h1, h2 {{ color: #888; font-weight: normal; }}
                h2 {{ font-size: 1rem; margin-top: 30px; text-transform: uppercase; letter-spacing: 0.1em; }}
                .header {{ display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px; }}
                .actions {{ display: flex; gap: 10px; }}
                .btn {{ padding: 8px 16px; font-family: monospace; background: #333; color: #e0e0e0; border: none; cursor: pointer; border-radius: 4px; text-decoration: none; }}
                .btn:hover {{ background: #444; }}
                .btn-primary {{ background: #2a4a2a; color: #6f6; }}
                .btn-export {{ background: #2a2a4a; color: #68f; }}
                .stats-bar {{ display: flex; gap: 30px; padding: 20px 0; border-bottom: 1px solid #222; margin-bottom: 20px; }}
                .stat {{ text-align: center; }}
                .stat-value {{ font-size: 2rem; font-weight: bold; }}
                .stat-label {{ font-size: 0.7rem; color: #666; text-transform: uppercase; }}
                .stat-approved .stat-value {{ color: #6d6; }}
                .stat-pending .stat-value {{ color: #fd0; }}
                .stat-rejected .stat-value {{ color: #f66; }}
                .filters {{ display: flex; gap: 15px; margin-bottom: 15px; align-items: center; }}
                .filter-input {{ padding: 8px 12px; font-family: monospace; background: #1a1a1a; color: #e0e0e0; border: 1px solid #333; border-radius: 4px; }}
                table {{ border-collapse: collapse; width: 100%; margin-bottom: 20px; }}
                th, td {{ padding: 10px; text-align: left; border-bottom: 1px solid #222; }}
                th {{ color: #666; font-weight: normal; text-transform: uppercase; font-size: 0.7rem; letter-spacing: 0.1em; }}
                tr:hover {{ background: #111; }}
                .truncate {{ max-width: 200px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }}
                .action-btn {{ background: none; border: 1px solid #333; color: #888; cursor: pointer; padding: 4px 8px; font-family: monospace; border-radius: 4px; margin: 0 2px; }}
                .action-btn:hover {{ background: #333; color: #fff; border-color: #555; }}
                .delete-btn:hover {{ background: #533; color: #f66; border-color: #733; }}
                .pagination {{ display: flex; justify-content: center; align-items: center; gap: 20px; padding: 20px 0; }}
                .pagination button {{ padding: 8px 16px; background: #333; border: none; color: #e0e0e0; cursor: pointer; border-radius: 4px; }}
                .pagination button:disabled {{ opacity: 0.5; cursor: not-allowed; }}
                .section {{ background: #111; padding: 20px; border-radius: 8px; margin-bottom: 20px; }}
                .modal {{ display: none; position: fixed; top: 0; left: 0; width: 100%; height: 100%; background: rgba(0,0,0,0.8); z-index: 1000; }}
                .modal-content {{ background: #1a1a1a; margin: 5% auto; padding: 30px; width: 80%; max-width: 900px; max-height: 80vh; overflow-y: auto; border-radius: 8px; border: 1px solid #333; }}
                .modal-header {{ display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px; }}
                .modal-close {{ font-size: 24px; cursor: pointer; color: #666; }}
                .modal-close:hover {{ color: #fff; }}
                .form-group {{ margin-bottom: 15px; }}
                .form-group label {{ display: block; margin-bottom: 5px; color: #888; font-size: 0.8rem; text-transform: uppercase; }}
                .form-group textarea, .form-group input, .form-group select {{ width: 100%; padding: 10px; background: #0a0a0a; border: 1px solid #333; color: #e0e0e0; font-family: monospace; border-radius: 4px; }}
                .form-group textarea {{ min-height: 100px; resize: vertical; }}
                .form-row {{ display: flex; gap: 15px; }}
                .form-row .form-group {{ flex: 1; }}
            </style>
        </head>
        <body>
            <div class="header">
                <h1>Training Data Dashboard</h1>
                <div class="actions">
                    <a href="/admin?password={password}" class="btn">Leads</a>
                    <a href="/admin/users?password={password}" class="btn">Users</a>
                    <a href="/admin/traffic?password={password}" class="btn">Traffic</a>
                    <a href="/admin/quality-dashboard?password={password}" class="btn" style="color: #f88;">Quality</a>
                    <a href="/admin/training-data?password={password}" class="btn" style="background: #1a1a1a; border: 1px solid #fd0;">Training</a>
                    <a href="/admin/training/export?password={password}&status=approved" class="btn btn-export">Export JSONL</a>
                </div>
            </div>

            <!-- Stats -->
            <div class="stats-bar">
                <div class="stat">
                    <div class="stat-value">{stats.get('total', 0)}</div>
                    <div class="stat-label">Total Examples</div>
                </div>
                <div class="stat stat-approved">
                    <div class="stat-value">{stats.get('approved', 0)}</div>
                    <div class="stat-label">Approved</div>
                </div>
                <div class="stat stat-pending">
                    <div class="stat-value">{stats.get('pending', 0)}</div>
                    <div class="stat-label">Pending</div>
                </div>
                <div class="stat stat-rejected">
                    <div class="stat-value">{stats.get('rejected', 0)}</div>
                    <div class="stat-label">Rejected</div>
                </div>
                <div class="stat">
                    <div class="stat-value">{stats.get('avg_quality_score') or '-'}</div>
                    <div class="stat-label">Avg Quality</div>
                </div>
            </div>

            <!-- Candidates Section -->
            <h2>📥 Suggested Training Candidates</h2>
            <div class="section">
                <table>
                    <thead>
                        <tr>
                            <th>Source</th>
                            <th>User Message Preview</th>
                            <th>Action</th>
                        </tr>
                    </thead>
                    <tbody>
                        {candidate_rows if candidate_rows else '<tr><td colspan="3" style="color: #666; text-align: center;">No candidates found. Mark responses as exemplary to generate candidates.</td></tr>'}
                    </tbody>
                </table>
            </div>

            <!-- Training Examples Section -->
            <h2>📚 Training Examples</h2>
            <div class="filters">
                <select class="filter-input" onchange="filterByStatus(this.value)">
                    <option value="" {"selected" if not status_filter else ""}>All Status</option>
                    <option value="pending" {"selected" if status_filter == "pending" else ""}>Pending</option>
                    <option value="approved" {"selected" if status_filter == "approved" else ""}>Approved</option>
                    <option value="rejected" {"selected" if status_filter == "rejected" else ""}>Rejected</option>
                </select>
                <button class="btn btn-primary" onclick="showCreateModal()">+ New Example</button>
            </div>

            <table>
                <thead>
                    <tr>
                        <th>ID</th>
                        <th>User Message</th>
                        <th>Assistant Response</th>
                        <th>Category</th>
                        <th>Quality</th>
                        <th>Status</th>
                        <th>Actions</th>
                    </tr>
                </thead>
                <tbody>
                    {example_rows if example_rows else '<tr><td colspan="7" style="color: #666; text-align: center;">No training examples yet.</td></tr>'}
                </tbody>
            </table>

            <div class="pagination">
                <button onclick="goToPage({page - 1})" {prev_disabled}>&lt; Prev</button>
                <span>Page {page} of {total_pages}</span>
                <button onclick="goToPage({page + 1})" {next_disabled}>Next &gt;</button>
            </div>

            <!-- Edit Modal -->
            <div id="editModal" class="modal">
                <div class="modal-content">
                    <div class="modal-header">
                        <h2 id="modalTitle">Edit Training Example</h2>
                        <span class="modal-close" onclick="closeModal()">&times;</span>
                    </div>
                    <form id="editForm">
                        <input type="hidden" id="exampleId">
                        <div class="form-group">
                            <label>User Message</label>
                            <textarea id="userMessage" required></textarea>
                        </div>
                        <div class="form-group">
                            <label>Assistant Response</label>
                            <textarea id="assistantResponse" required></textarea>
                        </div>
                        <div class="form-row">
                            <div class="form-group">
                                <label>Category</label>
                                <select id="category">
                                    <option value="">Select...</option>
                                    <option value="greeting">Greeting</option>
                                    <option value="pricing">Pricing</option>
                                    <option value="technical">Technical</option>
                                    <option value="objection_handling">Objection Handling</option>
                                    <option value="lead_capture">Lead Capture</option>
                                    <option value="company_info">Company Info</option>
                                    <option value="project_info">Project Info</option>
                                </select>
                            </div>
                            <div class="form-group">
                                <label>Difficulty</label>
                                <select id="difficulty">
                                    <option value="">Select...</option>
                                    <option value="easy">Easy</option>
                                    <option value="medium">Medium</option>
                                    <option value="hard">Hard</option>
                                </select>
                            </div>
                            <div class="form-group">
                                <label>Quality Score (1-5)</label>
                                <input type="number" id="qualityScore" min="1" max="5">
                            </div>
                        </div>
                        <div class="form-group">
                            <label>Reviewer Notes</label>
                            <textarea id="reviewerNotes"></textarea>
                        </div>
                        <div class="form-row">
                            <div class="form-group">
                                <label>Status</label>
                                <select id="status">
                                    <option value="pending">Pending</option>
                                    <option value="approved">Approved</option>
                                    <option value="rejected">Rejected</option>
                                </select>
                            </div>
                        </div>
                        <button type="submit" class="btn btn-primary">Save</button>
                        <button type="button" class="btn" onclick="closeModal()">Cancel</button>
                    </form>
                </div>
            </div>

            <script>
                const password = '{password}';

                function goToPage(p) {{
                    const status = new URLSearchParams(window.location.search).get('status_filter') || '';
                    window.location.href = `/admin/training-data?password=${{password}}&page=${{p}}${{status ? '&status_filter=' + status : ''}}`;
                }}

                function filterByStatus(status) {{
                    window.location.href = `/admin/training-data?password=${{password}}${{status ? '&status_filter=' + status : ''}}`;
                }}

                function showCreateModal() {{
                    document.getElementById('modalTitle').textContent = 'Create Training Example';
                    document.getElementById('exampleId').value = '';
                    document.getElementById('userMessage').value = '';
                    document.getElementById('assistantResponse').value = '';
                    document.getElementById('category').value = '';
                    document.getElementById('difficulty').value = '';
                    document.getElementById('qualityScore').value = '';
                    document.getElementById('reviewerNotes').value = '';
                    document.getElementById('status').value = 'pending';
                    document.getElementById('editModal').style.display = 'block';
                }}

                async function viewExample(id) {{
                    const resp = await fetch(`/admin/training?password=${{password}}&limit=1000`);
                    const data = await resp.json();
                    const ex = data.examples.find(e => e.id === id);
                    if (!ex) return alert('Example not found');

                    document.getElementById('modalTitle').textContent = 'Edit Training Example #' + id;
                    document.getElementById('exampleId').value = id;
                    document.getElementById('userMessage').value = ex.user_message;
                    document.getElementById('assistantResponse').value = ex.assistant_response;
                    document.getElementById('category').value = ex.category || '';
                    document.getElementById('difficulty').value = ex.difficulty || '';
                    document.getElementById('qualityScore').value = ex.quality_score || '';
                    document.getElementById('reviewerNotes').value = ex.reviewer_notes || '';
                    document.getElementById('status').value = ex.status || 'pending';
                    document.getElementById('editModal').style.display = 'block';
                }}

                function closeModal() {{
                    document.getElementById('editModal').style.display = 'none';
                }}

                async function approveExample(id) {{
                    if (!confirm('Approve this example?')) return;
                    const resp = await fetch(`/admin/training/${{id}}?password=${{password}}`, {{
                        method: 'PUT',
                        headers: {{ 'Content-Type': 'application/json' }},
                        body: JSON.stringify({{ status: 'approved' }})
                    }});
                    if (resp.ok) location.reload();
                    else alert('Failed to approve');
                }}

                async function rejectExample(id) {{
                    if (!confirm('Reject this example?')) return;
                    const resp = await fetch(`/admin/training/${{id}}?password=${{password}}`, {{
                        method: 'PUT',
                        headers: {{ 'Content-Type': 'application/json' }},
                        body: JSON.stringify({{ status: 'rejected' }})
                    }});
                    if (resp.ok) location.reload();
                    else alert('Failed to reject');
                }}

                async function deleteExample(id) {{
                    if (!confirm('Delete this training example? This cannot be undone.')) return;
                    const resp = await fetch(`/admin/training/${{id}}?password=${{password}}`, {{ method: 'DELETE' }});
                    if (resp.ok) location.reload();
                    else alert('Failed to delete');
                }}

                async function addCandidate(candidate) {{
                    document.getElementById('modalTitle').textContent = 'Add Training Example';
                    document.getElementById('exampleId').value = '';
                    document.getElementById('userMessage').value = candidate.user_message || '';
                    document.getElementById('assistantResponse').value = candidate.corrected_response || candidate.assistant_response || '';
                    document.getElementById('category').value = '';
                    document.getElementById('difficulty').value = '';
                    document.getElementById('qualityScore').value = candidate.rating || '';
                    document.getElementById('reviewerNotes').value = candidate.notes || '';
                    document.getElementById('status').value = 'pending';
                    document.getElementById('editModal').style.display = 'block';
                }}

                document.getElementById('editForm').addEventListener('submit', async (e) => {{
                    e.preventDefault();
                    const id = document.getElementById('exampleId').value;
                    const data = {{
                        user_message: document.getElementById('userMessage').value,
                        assistant_response: document.getElementById('assistantResponse').value,
                        category: document.getElementById('category').value || null,
                        difficulty: document.getElementById('difficulty').value || null,
                        quality_score: document.getElementById('qualityScore').value ? parseInt(document.getElementById('qualityScore').value) : null,
                        reviewer_notes: document.getElementById('reviewerNotes').value || null,
                        status: document.getElementById('status').value
                    }};

                    let resp;
                    if (id) {{
                        resp = await fetch(`/admin/training/${{id}}?password=${{password}}`, {{
                            method: 'PUT',
                            headers: {{ 'Content-Type': 'application/json' }},
                            body: JSON.stringify(data)
                        }});
                    }} else {{
                        resp = await fetch(`/admin/training?password=${{password}}`, {{
                            method: 'POST',
                            headers: {{ 'Content-Type': 'application/json' }},
                            body: JSON.stringify(data)
                        }});
                    }}

                    if (resp.ok) {{
                        closeModal();
                        location.reload();
                    }} else {{
                        alert('Failed to save');
                    }}
                }});

                window.onclick = (e) => {{
                    if (e.target === document.getElementById('editModal')) closeModal();
                }};
            </script>
        </body>
        </html>
    """)


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


class ClearRequest(BaseModel):
    user_id: Optional[str] = None


@app.post("/clear")
async def clear(request: ClearRequest = None):
    """Clear conversation history for a user."""
    if request and request.user_id and request.user_id in user_sessions:
        user_sessions[request.user_id] = []
        return {"message": f"Conversation history cleared for user {request.user_id}"}
    return {"message": "No history to clear"}


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
        "total_chunks": bot.doc_store.collection.count()
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
