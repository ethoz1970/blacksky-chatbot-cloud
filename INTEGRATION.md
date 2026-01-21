# Blacksky Agent Platform - Integration Guide for Maurice

## Architecture Overview

```
Maurice (Production Chatbot)
    │
    ▼ HTTP POST
┌─────────────────────────────────────────┐
│     Blacksky Agent Platform (FastAPI)    │
│         http://localhost:8001            │
├─────────────────────────────────────────┤
│  ┌─────────────┐  ┌──────────────────┐  │
│  │  Research   │  │  Email Drafter   │  │
│  │   Agent     │  │     Agent        │  │
│  └─────────────┘  └──────────────────┘  │
│  ┌─────────────┐  ┌──────────────────┐  │
│  │  BSM Docs   │  │   User Lookup    │  │
│  │   Agent     │  │     Agent        │  │
│  └─────────────┘  └──────────────────┘  │
├─────────────────────────────────────────┤
│  Shared: Claude Sonnet 4 | PostgreSQL   │
│          Pinecone Vector DB             │
└─────────────────────────────────────────┘
```

---

## Available Agents & Endpoints

### 1. Research Agent
B2B lead research with 1-10 lead scoring.

```
POST /agent/research/company
Content-Type: application/json

{
  "company_name": "Anthropic",
  "context": "Focus on their AI safety initiatives"  // optional
}
```

**Response:** Detailed company research with lead score (1-10 based on Federal Connection, AI/Tech Need, Budget Signals, Accessibility).

---

### 2. Email Drafter Agent
Generate personalized sales emails.

**Cold Outreach:**
```
POST /agent/email/cold
{
  "company_name": "Anthropic",
  "contact_name": "Dario Amodei",  // optional
  "context": "They announced AI safety funding"  // optional
}
```

**Follow-up:**
```
POST /agent/email/followup
{
  "company_name": "Anthropic",
  "contact_name": "Dario Amodei",  // optional
  "previous_context": "Had intro call last week",  // optional
  "followup_reason": "Share case study"  // optional
}
```

---

### 3. BSM Docs Agent
Search Blacksky internal documents (requires Pinecone setup).

```
POST /agent/bsm-docs
{
  "query": "What federal projects has Blacksky completed?",
  "context": "User interested in Treasury experience"  // optional
}
```

**Response:**
```json
{
  "success": true,
  "data": {
    "found": true,
    "summary": "Blacksky has completed...",
    "details": [{"topic": "Treasury", "content": "..."}],
    "confidence": "high",
    "sources": ["projects.md", "federal.md"]
  }
}
```

---

### 4. User Lookup Agent
Query PostgreSQL for user/lead information. **Most useful for Maurice.**

| Endpoint | Purpose | Request Body |
|----------|---------|--------------|
| `POST /agent/user/lookup-by-name` | Find users by name | `{"name": "Stan"}` |
| `POST /agent/user/lookup-by-email` | Find user by email | `{"email": "stan@acme.com"}` |
| `POST /agent/user/lookup-by-company` | Find all users from company | `{"company": "Acme"}` |
| `POST /agent/user/context` | Get full user context (facts, conversations) | `{"user_id": "uuid-here"}` |
| `POST /agent/user/conversations` | Get conversation history | `{"user_id": "uuid", "limit": 5}` |
| `POST /agent/user/leads` | Get high-scoring leads | `{"min_score": 4, "status": "qualified"}` |
| `POST /agent/user/search-by-fact` | Find users by characteristic | `{"fact_type": "industry", "fact_value": "fintech"}` |
| `POST /agent/user/timeline` | Get interaction timeline | `{"user_id": "uuid"}` |

**Example - Get User Context:**
```
POST /agent/user/context
{"user_id": "035c1fb0-e5f9-40ef-bde7-3d1f5373742f"}
```

**Response:**
```json
{
  "success": true,
  "data": {
    "found": true,
    "user": {
      "id": "035c1fb0...",
      "name": "Stan Felix",
      "company": "Acme Inc",
      "interest_level": "high"
    },
    "facts": {
      "decision_stage": {"value": "considering", "confidence": 0.7}
    },
    "recent_conversations": [...],
    "total_conversations": 1
  }
}
```

---

## Standard Response Format

All agents return:
```json
{
  "success": true,
  "data": { ... },
  "error": null
}
```

For Claude-based agents (Research, Email), data includes:
```json
{
  "content": [{"type": "text", "text": "..."}],
  "model": "claude-sonnet-4-20250514",
  "usage": {"input_tokens": 123, "output_tokens": 456}
}
```

---

## How Maurice Should Call These Agents

**Python example using httpx:**
```python
import httpx

AGENT_BASE_URL = "http://localhost:8001"  # or Railway URL in production

async def lookup_user_context(user_id: str) -> dict:
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{AGENT_BASE_URL}/agent/user/context",
            json={"user_id": user_id}
        )
        return response.json()

async def research_company(company_name: str, context: str = None) -> dict:
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{AGENT_BASE_URL}/agent/research/company",
            json={"company_name": company_name, "context": context},
            timeout=60.0  # Research can take time
        )
        return response.json()
```

---

## Database Schema (PostgreSQL)

Maurice writes to these tables, agents read from them:

**users**
- `id` (varchar) - UUID
- `name`, `email`, `company`, `status`
- `interest_level`, `last_seen`

**conversations**
- `id` (int), `user_id` (varchar FK)
- `summary`, `interests`, `lead_score` (1-5)
- `messages` (text), `created_at`

**user_facts**
- `id` (int), `user_id` (varchar FK)
- `fact_type` (industry, role, budget, etc.)
- `fact_value`, `confidence` (0-1)

---

## Configuration Required

**.env.local / Railway environment:**
```
ANTHROPIC_API_KEY=sk-ant-...
DATABASE_URL=postgresql://...  # Same DB as Maurice
PINECONE_API_KEY=...           # For BSM Docs (optional)
OPENAI_API_KEY=...             # For embeddings (optional)
```

---

## Key Integration Points for Maurice

1. **Before conversation:** Call `/agent/user/lookup-by-email` to check if returning user
2. **Get context:** Call `/agent/user/context` to get facts and history
3. **During conversation:** Call `/agent/research/company` when user mentions a company
4. **After qualifying lead:** Call `/agent/email/cold` to draft outreach
5. **For internal questions:** Call `/agent/bsm-docs` for Blacksky capabilities

---

## Running Locally

```bash
# FastAPI server (for API calls)
python main.py  # Runs on http://localhost:8001

# Streamlit UI (for testing)
streamlit run dev_ui.py  # Runs on http://localhost:8501
```

---

## Health Check

```
GET /health
Response: {"status": "healthy"}

GET /
Response: {
  "service": "Blacksky Agent Platform",
  "version": "1.0.0",
  "agents": ["research", "email", "bsm-docs", "user-lookup"],
  "status": "operational"
}
```
