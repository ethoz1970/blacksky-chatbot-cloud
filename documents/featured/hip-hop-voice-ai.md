# Hip-Hop Voice AI - Cultural Voice Preservation

## Overview

Blacksky built a voice-cloned conversational AI that preserves the voice, personality, and cultural knowledge of a legendary hip-hop figure. The project combines RAG (Retrieval-Augmented Generation) with voice synthesis to create an interactive experience that honors hip-hop cultural heritage. This proof of concept demonstrates Blacksky's full LLM stack capabilities - from data pipeline to voice output.

## The Challenge

When influential cultural figures pass away, decades of knowledge, perspective, and lived experience go with them. Hip-hop has lost many of its pioneering voices - attorneys who represented artists, journalists who broke stories, podcast hosts who interviewed legends. Traditional archives preserve recordings, but they're passive. The question Blacksky asked: **What if AI could create an interactive archive - a way for future generations to engage with these perspectives directly?**

The goal wasn't to replace or imitate anyone, but to build technology that could preserve cultural voices as living, conversational knowledge bases.

## Blacksky's Approach

Blacksky designed a three-node architecture that separates concerns cleanly:

**Brain Node** - Handles knowledge retrieval and response generation using Llama 3 with RAG. The knowledge base was built from podcast transcriptions, creating a searchable archive of conversations, interviews, and commentary.

**Bridge Node** - Custom middleware that orchestrates requests, injects personality characteristics, and ensures responses stay true to the subject's speech patterns, humor, and cultural references.

**Voice Node** - Coqui XTTS v2 voice cloning that synthesizes responses in the subject's actual voice, trained on clean audio samples from original recordings.

A critical architectural decision was **100% local deployment**. Everything runs on a MacBook Pro M3 - no cloud APIs, no data leaving the machine, no ongoing costs. This proves the technology is accessible, not just for enterprises with cloud budgets.

## Key Accomplishments

- **Complete data pipeline**: Podcast audio ingested, transcribed via OpenAI Whisper, chunked semantically, embedded as vectors, and stored in LanceDB for retrieval

- **Local LLM deployment**: Llama 3 running via Ollama on Apple Silicon, proving enterprise-grade AI can run on consumer hardware

- **Voice cloning**: Coqui XTTS v2 trained on audio samples to reproduce the subject's voice with natural speech patterns

- **Hybrid CPU/GPU strategy**: Solved Apple Silicon MPS compatibility issues by running embeddings on CPU and inference on GPU

- **Personality tuning**: System prompts carefully calibrated to capture speech patterns and cultural references without caricature

## Technologies

| Component | Technology | Why This Choice |
|-----------|------------|-----------------|
| LLM | Llama 3 via Ollama | Open source, runs locally on Apple Silicon |
| RAG Framework | AnythingLLM | Flexible RAG orchestration |
| Vector Database | LanceDB | Lightweight, no server required, fast |
| Voice Synthesis | Coqui XTTS v2 | Best open-source voice cloning available |
| Transcription | OpenAI Whisper | Industry-leading accuracy for speech-to-text |
| Backend | Python, FastAPI | Fast API development, async support |

## Results & Impact

The proof of concept is fully functional - a user can have a voice conversation with an AI that speaks in the subject's voice and draws on their actual recorded knowledge. This demonstrates:

- **Full LLM stack mastery**: Data pipeline, embeddings, RAG, inference, voice synthesis - end to end
- **Edge deployment**: Enterprise AI capabilities on a laptop, no cloud required
- **Cultural technology**: AI serving communities often left out of tech innovation

## Why This Project Matters

This project showcases Blacksky's depth across the entire AI stack. Most consultancies can call an API. Blacksky built every layer:

1. **Data Engineering** - Audio ingestion, transcription, chunking, embedding
2. **LLM Infrastructure** - Local deployment, RAG configuration, prompt engineering
3. **Voice AI** - Model training, synthesis, quality optimization
4. **System Architecture** - Three-node design, middleware orchestration

It also reflects Blacksky's commitment to non-European narratives in technology - using AI as a tool for cultural archiving and preservation, not just commercial applications.

**For prospects this demonstrates**: If you need AI that goes beyond chatbots - custom pipelines, voice interfaces, edge deployment, or culturally-specific applications - Blacksky has built it from scratch.

---

**Project Type:** Internal R&D / Proof of Concept
**Timeline:** 2024-2025
**Deployment:** Local (Apple Silicon M3)
**Status:** Complete - functional proof of concept
