# Maurice: Blacksky's AI Sales Assistant

## What Is This?

Maurice is an AI-powered chatbot and lead generation system for Blacksky LLC. It serves as an interactive portfolio showcase that can:
- Answer questions about Blacksky's capabilities and past projects
- Capture and qualify leads through natural conversation
- Remember returning visitors and personalize interactions
- Display project case studies via interactive slideout panels

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                        CLOUD (Production)                        │
│                     bsm-chatbot-cloud repo                       │
│                                                                  │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────────┐  │
│  │   FastAPI    │───▶│  Together AI │    │   PostgreSQL     │  │
│  │   Server     │    │  (Llama 3.1  │    │   (Railway)      │  │
│  │  (Railway)   │    │   70B API)   │    │                  │  │
│  └──────────────┘    └──────────────┘    │  - Users         │  │
│         │                                 │  - Conversations │  │
│         ▼                                 │  - Lead Scores   │  │
│  ┌──────────────┐    ┌──────────────┐    └──────────────────┘  │
│  │   Pinecone   │    │   demo.html  │                          │
│  │  (Vector DB) │    │  (Frontend)  │                          │
│  │    for RAG   │    └──────────────┘                          │
│  └──────────────┘                                               │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│                        LOCAL (Development)                       │
│                       bsm-chatbot repo                           │
│                                                                  │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────────┐  │
│  │   FastAPI    │───▶│  llama.cpp   │    │     SQLite       │  │
│  │   Server     │    │  (Llama 3.1  │    │   (maurice.db)   │  │
│  │ (localhost)  │    │   8B local)  │    │                  │  │
│  └──────────────┘    └──────────────┘    └──────────────────┘  │
│         │                                                        │
│         ▼                                                        │
│  ┌──────────────┐    ┌──────────────┐                          │
│  │   ChromaDB   │    │   demo.html  │                          │
│  │  (Local RAG) │    │  (Frontend)  │                          │
│  └──────────────┘    └──────────────┘                          │
└─────────────────────────────────────────────────────────────────┘

                              ▲
                              │
                    ┌─────────┴─────────┐
                    │   Sync Scripts    │
                    │                   │
                    │ sync-to-local.sh  │
                    │ sync-from-local.sh│
                    └───────────────────┘
```

---

## Key Components

### Frontend (`demo.html`)
- Dark-themed chat interface
- Streaming responses (Server-Sent Events)
- Interactive slideout panels for project case studies
- **Entity linking**: Project names in responses become clickable links
- Cookie-based user tracking
- Mobile-responsive with sticky input

### Backend (`server.py`)
- FastAPI with streaming SSE support
- User session management
- Lead scoring based on intent keywords
- Admin dashboard for viewing leads
- RAG integration for document retrieval

### Database
- **Cloud**: PostgreSQL on Railway (users, conversations, lead_score)
- **Local**: SQLite file for development testing

### AI/LLM
- **Cloud**: Together AI API → Llama 3.1 70B (fast, scalable)
- **Local**: llama-cpp-python → Llama 3.1 8B (offline, private)

### RAG (Retrieval-Augmented Generation)
- **Cloud**: Pinecone vector database
- **Local**: ChromaDB (embedded)
- Indexes Blacksky documents for accurate project information

---

## Shared vs Repo-Specific Files

### Shared (synced between repos)
| File | Purpose |
|------|---------|
| `prompts.py` | Maurice's personality and system prompt |
| `static/demo.html` | Frontend UI |
| `static/panels.js` | Slideout panel logic |
| `static/panels.json` | Panel content data |
| `static/images/*` | Client logos |

### Repo-Specific (different implementations)
| File | Cloud | Local |
|------|-------|-------|
| `chatbot.py` | Together AI client | llama-cpp-python |
| `rag.py` | Pinecone | ChromaDB |
| `database.py` | PostgreSQL | SQLite |
| `config.py` | Railway env vars | Local paths |

---

## Lead Generation Features

1. **User Tracking**: Cookie-based session persistence
2. **Name Extraction**: Parses "My name is X" from conversation
3. **Lead Scoring**:
   - Score 3 (Hot): pricing, quote, hire, contract
   - Score 2 (Warm): project, help, interested
   - Score 1 (Cool): general browsing
4. **User Verification**: When a name matches existing user, Maurice asks verification questions
5. **Session Linking**: Links returning users across devices

---

## Admin Dashboard

Access at `/admin` with password authentication.

Shows:
- All leads sorted by score and recency
- Name, email, company (if provided)
- Last conversation topic
- Lead score indicator

---

## Deployment

**Cloud (Production)**
- Hosted on Railway
- Auto-deploys from git push
- Environment variables for secrets
- PostgreSQL addon

**Local (Development)**
- Run `python server.py`
- Requires ~8GB RAM for local LLM
- SQLite database (delete `maurice.db` to reset)

---

## Sync Workflow

```bash
# After making changes in cloud repo
./scripts/sync-to-local.sh

# After prototyping locally
./scripts/sync-from-local.sh
```

---

## Tech Stack Summary

| Layer | Cloud | Local |
|-------|-------|-------|
| Hosting | Railway | localhost:8000 |
| LLM | Together AI (Llama 70B) | llama-cpp-python (Llama 8B) |
| Vector DB | Pinecone | ChromaDB |
| Database | PostgreSQL | SQLite |
| Frontend | Same demo.html | Same demo.html |
| API | FastAPI + SSE | FastAPI + SSE |

---

## URLs

- **Production**: https://[your-railway-url]/demo
- **Admin**: https://[your-railway-url]/admin
- **Local**: http://localhost:8000/demo
- **Local Admin**: http://localhost:8000/admin (password: localdev)
