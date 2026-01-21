# Plan: Integrate Agent Platform into Maurice

## Overview
Connect Maurice to the Blacksky Agent Platform to enhance lead intelligence with company research, user lookups, and document search.

## Agent Platform Summary

| Agent | Endpoint | Purpose |
|-------|----------|---------|
| Research | `/agent/research/company` | B2B company research with 1-10 lead scoring |
| Email Drafter | `/agent/email/cold`, `/agent/email/followup` | Generate personalized sales emails |
| BSM Docs | `/agent/bsm-docs` | Search Blacksky internal documents |
| User Lookup | `/agent/user/*` | Query PostgreSQL for user context, facts, conversations |

## Integration Strategy

### Phase 1: Agent Client Module (Foundation)
Create a reusable client to call agent endpoints.

**New file:** `agents.py`
```python
import httpx
import os

AGENT_BASE_URL = os.getenv("AGENT_PLATFORM_URL", "http://localhost:8001")

class AgentClient:
    """Client for Blacksky Agent Platform."""

    async def lookup_user_context(self, user_id: str) -> dict:
        """Get full user context from agent platform."""
        ...

    async def research_company(self, company_name: str, context: str = None) -> dict:
        """Research a company for lead qualification."""
        ...

    async def search_bsm_docs(self, query: str, context: str = None) -> dict:
        """Search Blacksky internal documents."""
        ...

    async def draft_cold_email(self, company_name: str, contact_name: str = None) -> dict:
        """Generate a cold outreach email."""
        ...
```

### Phase 2: Enhanced User Context
Call User Lookup agent to enrich Maurice's context.

**When:** On each chat request (if agent platform available)
**Where:** `server.py` in `/chat/stream` endpoint

```python
# In chat_stream endpoint, after getting local user_context:
if AGENT_PLATFORM_URL:
    agent_context = await agent_client.lookup_user_context(user_id)
    if agent_context.get("success"):
        user_context["agent_data"] = agent_context["data"]
```

**Update:** `chatbot.py` to include agent data in prompt context.

### Phase 3: Company Research (On Detection)
Research companies when Maurice detects one mentioned.

**Options:**
1. **Automatic:** Detect company names in user messages, research in background
2. **On-demand:** Maurice requests research via special token `[RESEARCH: CompanyName]`
3. **Admin-only:** Only research when in admin mode

**Recommended:** Start with on-demand via admin command, then add automatic detection.

### Phase 4: BSM Docs Integration
Use agent's Pinecone-backed search for internal docs.

**When:** Maurice needs to answer capability questions
**How:** Replace or augment local RAG with agent's BSM Docs search

---

## Files to Modify

| File | Changes |
|------|---------|
| `agents.py` (new) | Agent platform client |
| `config.py` | Add `AGENT_PLATFORM_URL` config |
| `server.py` | Call agent on chat requests |
| `chatbot.py` | Include agent data in context prompt |
| `prompts.py` | Add guidance for using agent-enriched data |

---

## Phase 1 Implementation Detail

### Task 1: Create Agent Client

**File:** `agents.py`

```python
"""
Client for Blacksky Agent Platform.
Provides access to Research, Email, BSM Docs, and User Lookup agents.
"""
import os
import httpx
from typing import Optional

AGENT_PLATFORM_URL = os.getenv("AGENT_PLATFORM_URL", "")
AGENT_TIMEOUT = 60.0  # Research can take time


class AgentClient:
    """Async client for Blacksky Agent Platform."""

    def __init__(self):
        self.base_url = AGENT_PLATFORM_URL
        self.enabled = bool(self.base_url)

    async def _post(self, endpoint: str, data: dict, timeout: float = AGENT_TIMEOUT) -> dict:
        """Make POST request to agent platform."""
        if not self.enabled:
            return {"success": False, "error": "Agent platform not configured"}

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.base_url}{endpoint}",
                    json=data,
                    timeout=timeout
                )
                return response.json()
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def health_check(self) -> bool:
        """Check if agent platform is available."""
        if not self.enabled:
            return False
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(f"{self.base_url}/health", timeout=5.0)
                return response.status_code == 200
        except:
            return False

    # User Lookup endpoints
    async def lookup_user_context(self, user_id: str) -> dict:
        """Get full user context including facts and conversations."""
        return await self._post("/agent/user/context", {"user_id": user_id})

    async def lookup_user_by_name(self, name: str) -> dict:
        """Find users by name."""
        return await self._post("/agent/user/lookup-by-name", {"name": name})

    async def lookup_user_by_company(self, company: str) -> dict:
        """Find all users from a company."""
        return await self._post("/agent/user/lookup-by-company", {"company": company})

    async def get_high_scoring_leads(self, min_score: int = 4, status: str = None) -> dict:
        """Get leads above a score threshold."""
        data = {"min_score": min_score}
        if status:
            data["status"] = status
        return await self._post("/agent/user/leads", data)

    # Research endpoints
    async def research_company(self, company_name: str, context: str = None) -> dict:
        """Research a company for lead qualification."""
        data = {"company_name": company_name}
        if context:
            data["context"] = context
        return await self._post("/agent/research/company", data)

    # BSM Docs endpoints
    async def search_bsm_docs(self, query: str, context: str = None) -> dict:
        """Search Blacksky internal documents."""
        data = {"query": query}
        if context:
            data["context"] = context
        return await self._post("/agent/bsm-docs", data)

    # Email endpoints
    async def draft_cold_email(self, company_name: str, contact_name: str = None, context: str = None) -> dict:
        """Generate a cold outreach email."""
        data = {"company_name": company_name}
        if contact_name:
            data["contact_name"] = contact_name
        if context:
            data["context"] = context
        return await self._post("/agent/email/cold", data)

    async def draft_followup_email(self, company_name: str, contact_name: str = None,
                                    previous_context: str = None, followup_reason: str = None) -> dict:
        """Generate a follow-up email."""
        data = {"company_name": company_name}
        if contact_name:
            data["contact_name"] = contact_name
        if previous_context:
            data["previous_context"] = previous_context
        if followup_reason:
            data["followup_reason"] = followup_reason
        return await self._post("/agent/email/followup", data)


# Global client instance
agent_client = AgentClient()
```

### Task 2: Add Config

**File:** `config.py`

```python
# Agent Platform URL (empty = disabled)
AGENT_PLATFORM_URL = os.getenv("AGENT_PLATFORM_URL", "")
```

### Task 3: Update .env.example

```
# Blacksky Agent Platform (optional - enhances Maurice with external agents)
AGENT_PLATFORM_URL=http://localhost:8001
```

---

## Phase 2 Implementation Detail

### Task 4: Enrich User Context in Server

**File:** `server.py`

```python
from agents import agent_client

@app.post("/chat/stream")
async def chat_stream(request: ChatRequest):
    # ... existing code ...

    # Enrich with agent platform data (if available)
    agent_data = None
    if request.user_id and agent_client.enabled:
        agent_result = await agent_client.lookup_user_context(request.user_id)
        if agent_result.get("success"):
            agent_data = agent_result.get("data")

    # Pass to chatbot
    for token in bot.chat_stream(
        message,
        conversation_history=conversation_history,
        user_context=user_context,
        potential_matches=request.potential_matches,
        is_admin=request.is_admin,
        panel_views=request.panel_views,
        agent_data=agent_data  # New parameter
    ):
```

### Task 5: Include Agent Data in Prompt

**File:** `chatbot.py`

Update `_build_user_context_prompt()`:

```python
# Add agent-enriched data
if agent_data and agent_data.get("found"):
    parts.append("\nAGENT INTELLIGENCE:")
    if agent_data.get("user"):
        user = agent_data["user"]
        if user.get("interest_level"):
            parts.append(f"  Interest Level: {user['interest_level']}")
    if agent_data.get("facts"):
        for fact_type, fact_info in agent_data["facts"].items():
            confidence = fact_info.get("confidence", 1.0)
            parts.append(f"  {fact_type.title()}: {fact_info['value']} ({int(confidence*100)}%)")
    if agent_data.get("total_conversations"):
        parts.append(f"  Total Conversations: {agent_data['total_conversations']}")
```

---

## Environment Configuration

**Local (.env):**
```
AGENT_PLATFORM_URL=http://localhost:8001
```

**Production (Railway):**
```
AGENT_PLATFORM_URL=https://your-agent-platform.up.railway.app
```

**Disabled:**
```
AGENT_PLATFORM_URL=
```

---

## Implementation Order

1. Create `agents.py` with AgentClient class
2. Add `AGENT_PLATFORM_URL` to config
3. Update `server.py` to call agent on chat requests
4. Update `chatbot.py` to include agent data in context
5. Test locally with agent platform running
6. Add admin commands for on-demand research (Phase 3)

---

## Verification

1. Start agent platform: `python main.py` (on port 8001)
2. Start Maurice: `python server.py` (on port 8000)
3. Chat with Maurice
4. In admin mode, verify agent data appears in response
5. Check agent platform logs for incoming requests

---

## Future Phases

**Phase 3:** Company research on detection
- Detect company names in messages
- Call research agent automatically or on-demand
- Show research results in admin mode

**Phase 4:** Email drafting integration
- After qualifying a lead, offer to draft email
- Admin command: `/draft-email CompanyName`

**Phase 5:** BSM Docs fallback
- When local RAG doesn't have answer, query agent's Pinecone
- Merge results from both sources

---

# Plan: Add User Browsing & Link Clicks to Admin Mode

## Overview

Add persistent tracking of user page views and link clicks, then surface this data in admin mode chat responses for better lead intelligence.

---

## Current State

**What's Already Tracked (Session Only):**
- Panel/page views stored in `panelViewHistory` array (frontend)
- Sent to backend with each chat request as `panel_views`
- Displayed in prompt as `RECENT PAGE VIEWS: [list]`

**What's Missing:**
- Persistent storage of page views across sessions
- Link click tracking (internal and external)
- Timestamps and engagement duration
- Admin-visible browsing history in chat responses

---

## Implementation Plan

### Step 1: Create Database Model for Page Views

**File:** `database.py`

Add new `PageView` model to persist browsing history:

```python
class PageView(Base):
    """Track user page/panel views and link clicks."""
    __tablename__ = "page_views"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    view_type = Column(String(20), nullable=False)  # "panel", "link", "external"
    title = Column(String(255), nullable=False)     # Panel title or link text
    url = Column(String(500), nullable=True)        # For link clicks
    panel_key = Column(String(100), nullable=True)  # For panel views
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", backref="page_views")
```

Add helper functions:
- `save_page_view(user_id, view_type, title, url=None, panel_key=None)`
- `get_user_page_views(user_id, limit=20)` - Returns recent views with timestamps
- `get_user_browsing_summary(user_id)` - Returns aggregated stats

---

### Step 2: Create API Endpoint to Log Views

**File:** `server.py`

Add endpoint to receive page view events from frontend:

```python
class PageViewRequest(BaseModel):
    user_id: str
    view_type: str  # "panel", "link", "external"
    title: str
    url: Optional[str] = None
    panel_key: Optional[str] = None

@app.post("/track/pageview")
async def track_pageview(request: PageViewRequest):
    """Log a page view or link click."""
    save_page_view(
        user_id=request.user_id,
        view_type=request.view_type,
        title=request.title,
        url=request.url,
        panel_key=request.panel_key
    )
    return {"status": "tracked"}
```

---

### Step 3: Update Frontend to Track & Send Events

**File:** `static/js/ui.js`

Modify `openPanel()` to persist views:

```javascript
function openPanel(panelData, options = {}) {
  // Existing panelViewHistory tracking...

  // Persist to backend
  fetch(`${API_HOST}/track/pageview`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      user_id: userId,
      view_type: 'panel',
      title: panelData.title,
      panel_key: options.panelKey || null
    })
  }).catch(e => console.error('Failed to track view:', e));
}
```

**File:** `static/js/chat.js` or new `static/js/tracking.js`

Add link click tracking:

```javascript
// Track clicks on links in chat messages
document.getElementById('messages').addEventListener('click', (e) => {
  const link = e.target.closest('a');
  if (link) {
    const isExternal = link.hostname !== window.location.hostname;
    fetch(`${API_HOST}/track/pageview`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        user_id: userId,
        view_type: isExternal ? 'external' : 'link',
        title: link.textContent || link.href,
        url: link.href
      })
    }).catch(e => console.error('Failed to track click:', e));
  }
});
```

---

### Step 4: Add Browsing Data to Admin Context

**File:** `chatbot.py`

Update `_build_user_context_prompt()` to include browsing history for admin mode:

```python
def _build_user_context_prompt(user_context, potential_matches=None,
                                panel_views=None, is_admin=False):
    # ... existing code ...

    # For admin mode, add detailed browsing history from database
    if is_admin and user_context:
        from database import get_user_page_views
        recent_views = get_user_page_views(user_context.get("user_id"), limit=15)

        if recent_views:
            parts.append("\nRECENT BROWSING ACTIVITY:")
            for view in recent_views:
                timestamp = view["created_at"][:16].replace("T", " ")
                if view["view_type"] == "panel":
                    parts.append(f"  [{timestamp}] Viewed: {view['title']}")
                elif view["view_type"] == "link":
                    parts.append(f"  [{timestamp}] Clicked: {view['title']}")
                elif view["view_type"] == "external":
                    parts.append(f"  [{timestamp}] External: {view['url']}")
```

---

### Step 5: Update Admin System Prompt

**File:** `prompts.py`

Add guidance for using browsing data:

```python
ADMIN_SYSTEM_PROMPT = """...

## BROWSING ACTIVITY
When RECENT BROWSING ACTIVITY is provided, note:
- Which panels/pages they viewed and when
- Any links they clicked (internal or external)
- Patterns: Are they researching specific topics? Comparing options?
- Example insight: "User viewed Treasury project 3 times, clicked case study link"

..."""
```

---

### Step 6: Show in Admin Dashboard (Optional Enhancement)

**File:** `server.py` - Admin user detail endpoint

Add browsing history to the user profile modal:

```python
@app.get("/admin/users/{user_id}")
async def admin_user_detail(user_id: str, password: str = Query(...)):
    # ... existing code ...

    # Add browsing history
    profile["browsing_history"] = get_user_page_views(user_id, limit=50)

    return profile
```

Update the admin dashboard JavaScript to display browsing history section.

---

## Files to Modify

| File | Changes |
|------|---------|
| `database.py` | Add `PageView` model and helper functions |
| `server.py` | Add `/track/pageview` endpoint, update admin user detail |
| `static/js/ui.js` | Persist panel views to backend |
| `static/js/chat.js` | Add link click tracking |
| `chatbot.py` | Include browsing history in admin context |
| `prompts.py` | Update `ADMIN_SYSTEM_PROMPT` with browsing guidance |

---

## Data Flow

```
User clicks panel/link
        │
        ▼
Frontend sends POST /track/pageview
        │
        ▼
Backend saves to page_views table
        │
        ▼
Admin sends chat message
        │
        ▼
Backend fetches user's page_views
        │
        ▼
Context includes RECENT BROWSING ACTIVITY
        │
        ▼
Maurice mentions relevant browsing in admin response
```

---

## Example Admin Response

```
[ADMIN] Lead Score: 3 (high) - mentioned "budget"
Facts: Role=CTO (95%), Company=Acme (90%)
Agent: HOT lead, status=qualified

Browsing Activity (last 24h):
  - Viewed: Treasury project (3x)
  - Viewed: LATEST menu
  - Clicked: Case study PDF link
  - External: linkedin.com/company/blacksky
---
Based on what you've been looking at, it seems like federal
project experience is important to you...
```

---

## Testing

1. Open site, click through several panels
2. Enable admin mode
3. Send a message - verify browsing history appears in response
4. Check admin dashboard user detail for browsing section
5. Verify external link clicks are tracked

---

## Implementation Order

1. Database model + migration
2. API endpoint for tracking
3. Frontend tracking code
4. Admin context injection
5. Prompt updates
6. Admin dashboard UI (optional)

---

# Plan: Enhanced Admin Mode for Maurice Intelligence

## Goal

Make admin mode a powerful tool for:
1. **Analyzing responses** - Understand what Maurice said and why
2. **Improving Maurice** - Collect training data and identify weaknesses
3. **Tracking leads** - Better intelligence on user intent and engagement

---

## Current Admin Mode Gaps

| Area | Current State | Gap |
|------|--------------|-----|
| Response Quality | No feedback mechanism | Can't identify good/bad responses |
| Training Data | All Q&A saved, but not curated | No way to mark exemplary responses |
| Response Analysis | RAG sources shown | Can't see full prompt or debug context |
| Lead Insights | Lead score 1-3 | No conversion tracking or funnel analysis |
| User Satisfaction | Not tracked | No way to know if Maurice helped |

---

## Proposed Enhancements

### Phase 1: Response Feedback System

**Goal:** Let admins rate responses to identify what's working and what needs improvement.

#### 1.1 Database: ResponseFeedback Model

```python
class ResponseFeedback(Base):
    """Admin feedback on Maurice responses."""
    __tablename__ = "response_feedback"

    id = Column(Integer, primary_key=True)
    conversation_id = Column(Integer, ForeignKey("conversations.id"))
    message_index = Column(Integer)  # Which message in conversation

    # Rating
    rating = Column(Integer)  # 1-5 stars or thumbs up/down
    feedback_type = Column(String(20))  # "accurate", "helpful", "tone", "hallucination", "off-topic"

    # Detailed feedback
    notes = Column(Text)  # Admin notes on what was wrong/right
    corrected_response = Column(Text)  # What Maurice should have said

    # Training flags
    is_exemplary = Column(Boolean, default=False)  # Good for training
    is_problematic = Column(Boolean, default=False)  # Needs review

    created_at = Column(DateTime)
    admin_id = Column(String(50))  # Who left feedback
```

#### 1.2 Admin Chat UI: Feedback Controls

Add to each Maurice response in admin mode:
- 👍 / 👎 quick rating buttons
- ⭐ "Mark as exemplary" (good training example)
- 🚩 "Flag for review" (problematic response)
- 📝 "Add notes" expandable field
- ✏️ "Suggest correction" text area

#### 1.3 API Endpoints

```python
POST /admin/feedback
{
    "conversation_id": 123,
    "message_index": 2,
    "rating": 5,
    "feedback_type": "accurate",
    "is_exemplary": true,
    "notes": "Perfect explanation of Treasury project"
}

GET /admin/feedback/stats
# Returns: rating distribution, common issues, exemplary count

GET /admin/feedback/export
# Returns: Training-ready dataset of exemplary Q&A pairs
```

---

### Phase 2: Prompt Debugger

**Goal:** See exactly what Maurice received so you can understand and improve responses.

#### 2.1 Debug Mode Toggle

In admin chat, add a "🔧 Debug Mode" toggle that shows:

```
═══════════════ PROMPT DEBUG ═══════════════
SYSTEM PROMPT: (2,450 tokens)
[Full system prompt text - collapsible]

RAG CONTEXT: (850 tokens)
[Documents retrieved with relevance scores]
  - projects.md (chunk 3): 0.89 relevance
  - services.md (chunk 1): 0.76 relevance

USER CONTEXT: (320 tokens)
[Full user context block]
  - Returning user: John Smith
  - Facts: Role=CTO, Budget=$100k
  - Browsing: Treasury (3x), AI Services

AGENT DATA: (180 tokens)
[Agent platform enrichment]
  - Interest: HOT
  - Enhanced facts: 5

CONVERSATION HISTORY: (1,200 tokens)
[Last N turns sent to model]

TOTAL PROMPT: 5,000 tokens
═══════════════════════════════════════════

[USER]: What's your experience with Treasury?

[MAURICE]: ...response...
```

#### 2.2 Save Debug Snapshots

Store full prompt context for problematic responses:
- When admin flags a response, save the complete prompt
- Allow replay/comparison of different contexts
- Identify patterns in bad responses (missing RAG? wrong facts?)

---

### Phase 3: Training Data Pipeline

**Goal:** Build a curated dataset of excellent Q&A pairs for fine-tuning.

#### 3.1 Training Dataset Table

```python
class TrainingExample(Base):
    """Curated Q&A pairs for fine-tuning."""
    __tablename__ = "training_examples"

    id = Column(Integer, primary_key=True)

    # The Q&A
    user_message = Column(Text)
    assistant_response = Column(Text)

    # Context that should be included
    relevant_facts = Column(Text)  # JSON of facts to inject
    rag_context = Column(Text)  # Relevant docs to include

    # Categorization
    category = Column(String(50))  # "greeting", "pricing", "technical", "objection_handling"
    difficulty = Column(String(20))  # "easy", "medium", "hard"

    # Source
    source_conversation_id = Column(Integer)
    was_edited = Column(Boolean, default=False)

    # Quality
    quality_score = Column(Integer)  # 1-5
    reviewer_notes = Column(Text)

    created_at = Column(DateTime)
```

#### 3.2 Training Data Dashboard

New admin page `/admin/training`:
- View all exemplary responses
- Edit/refine responses before adding to training set
- Categorize by topic (pricing, technical, lead capture, etc.)
- Export as JSONL for fine-tuning
- Track dataset growth over time

#### 3.3 Auto-Suggest Training Candidates

Flag conversations that might be good training data:
- High lead score conversations (user was engaged)
- Long conversations (deep engagement)
- Conversations with positive feedback
- Conversations that led to contact info capture

---

### Phase 4: Lead Intelligence Dashboard

**Goal:** Better understand the lead funnel and conversion patterns.

#### 4.1 Funnel Analytics

New metrics on `/admin` dashboard:

```
LEAD FUNNEL (Last 30 days)
━━━━━━━━━━━━━━━━━━━━━━━━━━━
Visitors:     1,247  ████████████████████
Engaged:        389  ██████░░░░░░░░░░░░░░  (31%)
Named:          156  ██░░░░░░░░░░░░░░░░░░  (12%)
High-Intent:     67  █░░░░░░░░░░░░░░░░░░░   (5%)
Contacted:       23  ░░░░░░░░░░░░░░░░░░░░   (2%)
Converted:        8  ░░░░░░░░░░░░░░░░░░░░   (0.6%)
```

#### 4.2 Conversion Tracking

Track key conversion events:
- Anonymous → Named (gave name)
- Named → Contact (gave email/phone)
- Contact → Call Request (asked for call)
- Call Request → Meeting (scheduled)

#### 4.3 Intent Signals Dashboard

Show what topics/questions lead to high-intent:
```
HIGH-INTENT TRIGGERS (Last 30 days)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"pricing"          23 mentions → 18 high-intent (78%)
"timeline"         19 mentions → 14 high-intent (74%)
"Treasury"         15 mentions → 11 high-intent (73%)
"budget"           12 mentions →  9 high-intent (75%)
"federal"          28 mentions → 12 high-intent (43%)
```

#### 4.4 User Journey Visualization

For each lead, show their path:
```
John Smith - CTO @ Acme Corp
━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Day 1: Browsed WHO, PROJECTS
Day 1: Asked about AI capabilities
Day 3: Returned, viewed Treasury case study
Day 3: Asked about pricing → HIGH INTENT
Day 3: Gave email address
Day 5: Asked to schedule call
```

---

### Phase 5: Response Quality Metrics

**Goal:** Automated quality signals, not just manual feedback.

#### 5.1 Automatic Quality Signals

Track for each response:
- **Length ratio**: Response length vs question length
- **Question answered**: Did response address the question?
- **Hallucination risk**: Did Maurice claim abilities it doesn't have?
- **Personality adherence**: Did Maurice stay in character?
- **Lead capture opportunity**: Did Maurice ask for info when appropriate?

#### 5.2 Quality Alerts

Flag responses that might need review:
- Very short responses to complex questions
- Responses containing "I can schedule" or "I'll send" (hallucination)
- Responses without personality markers
- Missed lead capture opportunities (high-intent, no ask for contact)

#### 5.3 Quality Dashboard

```
RESPONSE QUALITY (Last 7 days)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Avg Response Length:    145 words
Questions Answered:      94%
Personality Score:       87%
Lead Capture Rate:       34%
Flagged Responses:        3

COMMON ISSUES:
- 2x "I'll schedule a meeting" (hallucination)
- 1x Missed pricing question
```

---

## Implementation Priority

### High Priority (Phase 1-2)
1. **Response feedback buttons** - Quick wins for identifying issues
2. **Prompt debugger** - Essential for understanding behavior
3. **Exemplary response marking** - Start building training data

### Medium Priority (Phase 3)
4. **Training data export** - Enable fine-tuning workflow
5. **Conversion funnel** - Better lead intelligence

### Lower Priority (Phase 4-5)
6. **Automated quality signals** - Advanced analysis
7. **User journey visualization** - Nice to have

---

## Files to Modify

| File | Changes |
|------|---------|
| `database.py` | Add `ResponseFeedback`, `TrainingExample` models |
| `server.py` | Add feedback endpoints, debug mode, analytics endpoints |
| `chatbot.py` | Return debug info when requested |
| `static/js/chat.js` | Add feedback UI in admin mode |
| `prompts.py` | No changes needed |
| `templates/admin/` | New training data dashboard |

---

## Quick Wins (Can Implement Now)

1. **Add feedback buttons to admin chat** - 30 min
2. **Show full prompt in debug toggle** - 1 hour
3. **Add "Mark as exemplary" flag** - 30 min
4. **Export exemplary Q&A as JSONL** - 1 hour
5. **Add conversion funnel to dashboard** - 2 hours

---

## Success Metrics

After implementation, you should be able to:
- ✅ Rate any Maurice response with one click
- ✅ See exactly what context Maurice had when responding
- ✅ Build a curated training dataset from real conversations
- ✅ Identify patterns in good/bad responses
- ✅ Track lead conversion through the funnel
- ✅ Export training data for fine-tuning Maurice
