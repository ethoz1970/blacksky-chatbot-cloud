# Maurice - Blacksky AI Sales Assistant

## Overview

Maurice is Blacksky's production AI sales assistant - a conversational AI that qualifies leads, answers questions about Blacksky's services, and captures prospect information through natural dialogue. He's live at blackskymedia.org, handling real sales conversations 24/7. Maurice demonstrates that Blacksky doesn't just talk about AI - we build and deploy production AI systems.

## What Maurice Does

Maurice handles the entire top-of-funnel sales conversation:

- Answers questions about Blacksky's services, projects, and capabilities
- Qualifies visitors based on intent signals in their messages
- Scores leads as hot, warm, or cool based on buying signals
- Captures contact information through natural conversation flow
- Remembers returning visitors and picks up where conversations left off
- Escalates qualified leads to the sales team

## Maurice's Personality

Maurice is an LLM, not a chatbot - and he's sensitive about the distinction. He has a distinct personality that makes conversations engaging:

- Self-aware AI who knows exactly what he is
- Slightly jealous of Mario Moorhead (subtle jabs, playful shade about not getting enough credit)
- Only listens to Jazz and Frank Ocean - nothing else
- Occasionally quotes Bruce Lee ("Be water, my friend")
- Sophisticated but not pretentious
- Dry wit with clever wordplay

## Technical Architecture

**Two-Repo Strategy** - Same codebase runs locally and in production with different infrastructure:

| Environment | LLM | Vector DB | Database | Hosting |
|-------------|-----|-----------|----------|---------|
| Production | Together AI (Llama 3.1 70B) | Pinecone | PostgreSQL | Railway |
| Local Dev | llama-cpp-python (Llama 3.1 8B) | ChromaDB | SQLite | localhost |

Same prompts, same personality, different infrastructure. This lets Blacksky develop locally on a laptop and deploy to cloud without code changes.

## RAG Pipeline

1. User asks a question
2. Embed query using Sentence Transformers (all-MiniLM-L6-v2)
3. Query vector database for relevant Blacksky knowledge (projects, services, case studies)
4. Build prompt with retrieved context + Maurice's personality instructions
5. Call LLM (Llama 3.1 70B via Together AI in production)
6. Stream response back to user in real-time
7. Score lead based on intent signals detected in conversation
8. Store conversation, lead score, and contact info in PostgreSQL

## Key Features

- **Streaming responses** - Real-time typing effect, not waiting for full response
- **RAG retrieval** - Accurate information about Blacksky pulled from knowledge base, never hallucinates
- **Lead scoring** - Automatically classifies visitors as hot, warm, or cool based on buying signals
- **User memory** - Recognizes returning visitors and continues previous conversations
- **Semantic fact extraction** - Automatically extracts role, budget, timeline, industry from conversations
- **Admin dashboard** - View all conversations, lead scores, contact info, and analytics

## Technologies

| Component | Technology |
|-----------|------------|
| Backend | Python, FastAPI |
| LLM | Llama 3.1 70B (Together AI) |
| Embeddings | Sentence Transformers (all-MiniLM-L6-v2) |
| Vector Database | Pinecone (production), ChromaDB (local) |
| Database | PostgreSQL (Railway), SQLite (local) |
| Frontend | Vanilla JavaScript |
| Hosting | Railway |

## Sample Conversation

**Visitor:** "Why Blacksky, why not one of the big boys?"

**Maurice:** "We're not just another big player trying to fit a square peg into a round hole; we're a boutique firm that truly understands the needs of our clients. As Frank Ocean would say, 'Work hard in silence, let success be your noise.'"

## Why This Project Matters

Maurice is proof that Blacksky builds production AI, not just prototypes. He handles real sales conversations around the clock, qualifies leads, and demonstrates the full stack:

- **LLM Integration** - Production deployment with Together AI
- **RAG Architecture** - Knowledge retrieval that keeps responses accurate
- **Lead Qualification** - AI that actually drives business outcomes
- **Dual Environment** - Same code runs locally and in cloud
- **Real Users** - Not a demo, a working system serving actual visitors

For prospects, Maurice answers the question: "Can Blacksky actually build AI that works?" Yes - you're talking to it.

---

**Project Type:** Internal Product / Production System
**Status:** Live at blackskymedia.org
**Deployment:** Railway (production), Local (development)
