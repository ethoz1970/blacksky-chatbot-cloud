# Plan: Local + Together.ai Llama Support

## Goal
Run Llama models either locally (llama-cpp-python) or via Together.ai API based on one environment variable.

---

## Together.ai Details

- **Model**: `meta-llama/Llama-3.1-8B-Instruct-Turbo`
- **Cost**: ~$0.18 per 1M tokens (very cheap)
- **API**: OpenAI-compatible (uses `openai` Python package)
- **Signup**: https://together.ai

---

## Architecture

```
LLAMA_PROVIDER=local     → llama-cpp-python (current)
LLAMA_PROVIDER=together  → Together.ai API
```

```
llm/
├── __init__.py          # create_llama_provider() factory
├── base.py              # Abstract LlamaProvider class
├── local_provider.py    # Current llama-cpp implementation
└── together_provider.py # Together.ai API client
```

---

## Implementation Steps

### Step 1: Create `llm/base.py`
Abstract base class defining the interface.

### Step 2: Create `llm/local_provider.py`
Move current llama-cpp code from `chatbot.py`.

### Step 3: Create `llm/together_provider.py`
Together.ai client using OpenAI-compatible API.

### Step 4: Create `llm/__init__.py`
Factory function that reads `LLAMA_PROVIDER` env var.

### Step 5: Update `chatbot.py`
Replace direct llama-cpp usage with provider abstraction.

### Step 6: Update `config.py`
Add `LLAMA_PROVIDER` and `TOGETHER_API_KEY` settings.

### Step 7: Add `openai` to requirements.txt
Needed for Together.ai's OpenAI-compatible API.

---

## File Changes

| File | Action |
|------|--------|
| `llm/__init__.py` | Create |
| `llm/base.py` | Create |
| `llm/local_provider.py` | Create |
| `llm/together_provider.py` | Create |
| `chatbot.py` | Modify |
| `config.py` | Modify |
| `requirements.txt` | Add `openai` |

---

## Usage After Implementation

**Local (current behavior):**
```env
LLAMA_PROVIDER=local
```

**Together.ai cloud:**
```env
LLAMA_PROVIDER=together
TOGETHER_API_KEY=your_key_here
```
