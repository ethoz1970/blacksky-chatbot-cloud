# Ife - Internal Coding Intelligence

## Overview

Ife is Blacksky's internal coding intelligence system - a private RAG-based assistant that provides Claude/Gemini-level guidance while keeping proprietary code secure within Blacksky's infrastructure. Ife knows Blacksky's codebase, conventions, and architecture, helping developers without ever sending proprietary code to external APIs.

## The Name

Ife (ee-feh) is Yoruba for "clarity." The name reflects Blacksky's commitment to non-European narratives in technology.

The philosophical foundation comes from Malcolm X's 1964 Oxford Union speech about breaking from restrictive systems. Applied to Ife: breaking from "black-box" public models toward open, collaborative, clear internal tooling. Data sovereignty as a technical and cultural value.

## The Problem

Public AI coding assistants like GitHub Copilot and ChatGPT require sending your code to external servers. For proprietary work, that's a problem:

- Client code could be exposed to third-party training data
- Compliance requirements may prohibit external data sharing
- No guarantee of data deletion or privacy
- Dependency on external API availability and pricing

Ife provides the same intelligence level while keeping code private - productivity without compromise.

## What Ife Does

- **Contextual coding assistance** trained on Blacksky's actual codebase
- **Institutional knowledge** about documentation, conventions, and best practices
- **Project intelligence** that understands internal architecture and patterns
- **Developer support** without external API calls for core functionality

Ife isn't a chatbot - it's a senior knowledge architect that understands Blacksky's specific context.

## Technical Architecture

| Component | Technology |
|-----------|------------|
| LLM | Local deployment (Llama-based) |
| RAG | Custom pipeline on Blacksky codebase |
| Vector Database | ChromaDB |
| Backend | Python |

The RAG pipeline continuously indexes Blacksky's repositories, documentation, and internal resources. When a developer asks a question, Ife retrieves relevant context from the codebase before generating a response - answers grounded in actual Blacksky code, not generic patterns.

## Key Differentiators

- **Private** - Code never leaves Blacksky infrastructure
- **Contextual** - Knows our stack (FastAPI, Next.js, Drupal, Python, etc.)
- **Current** - RAG updates as codebase evolves
- **Secure** - No external API dependencies for core functionality
- **Culturally grounded** - Named and designed with intention

## Why This Project Matters

Ife demonstrates Blacksky's approach to AI tooling:

1. **Build, don't just buy** - Instead of depending on external AI services, build internal capabilities
2. **Data sovereignty** - Keep proprietary information private while still leveraging AI
3. **Contextual intelligence** - Generic AI is useful; AI that knows your specific codebase is transformative
4. **Cultural intention** - Technology reflects values, including whose narratives are centered

For clients concerned about AI and data privacy, Ife proves Blacksky understands the challenge - because we solved it for ourselves first.

---

**Project Type:** Internal Tool
**Status:** In development - internal use at Blacksky
**Deployment:** Local infrastructure
