"""
Core chatbot logic - supports both local llama-cpp-python and cloud Together AI
"""
from config import (
    MODEL_PATH, N_GPU_LAYERS, N_THREADS, N_CTX, N_BATCH,
    MAX_TOKENS, TEMPERATURE, TOP_P, REPEAT_PENALTY, MAX_HISTORY_TURNS,
    USE_CLOUD_LLM, TOGETHER_API_KEY, TOGETHER_MODEL
)
from prompts import SYSTEM_PROMPT
from rag import DocumentStore

# Conditional imports based on mode
if USE_CLOUD_LLM:
    from together import Together
else:
    from llama_cpp import Llama
    from download_model import download_model


class BlackskyChatbot:
    """Chatbot wrapper supporting both local Llama and cloud Together AI."""

    def __init__(self, use_rag: bool = True):
        self.model = None
        self.client = None  # Together AI client
        self.conversation_history = []
        self.use_rag = use_rag
        self.doc_store = None
        self.is_cloud = USE_CLOUD_LLM

    def load_model(self):
        """Load the model - local file or cloud API client."""
        if self.is_cloud:
            # Cloud mode: Initialize Together AI client
            print("Initializing Together AI client...")
            print(f"  Model: {TOGETHER_MODEL}")
            self.client = Together(api_key=TOGETHER_API_KEY)
            print("✓ Together AI client ready!")
        else:
            # Local mode: Load GGUF model
            if not MODEL_PATH.exists():
                print("Model not found locally, downloading...")
                download_model()

            print(f"Loading model from {MODEL_PATH}...")
            print(f"  GPU layers: {N_GPU_LAYERS}")
            print(f"  Threads: {N_THREADS}")
            print(f"  Context: {N_CTX}")

            self.model = Llama(
                model_path=str(MODEL_PATH),
                n_gpu_layers=N_GPU_LAYERS,
                n_threads=N_THREADS,
                n_ctx=N_CTX,
                n_batch=N_BATCH,
                verbose=False
            )
            print("✓ Model loaded successfully!")

        # Initialize RAG if enabled (skip in cloud mode - sentence-transformers too heavy)
        if self.use_rag and not self.is_cloud:
            self.doc_store = DocumentStore()
            self.doc_store.initialize()
        elif self.is_cloud:
            print("RAG disabled in cloud mode (use Together embeddings API for cloud RAG)")
        print()

    def _build_user_context_prompt(self, user_context: dict, potential_matches: list = None) -> str:
        """Build a context string for returning users and potential matches."""
        parts = []

        # Add returning user context
        if user_context and user_context.get("is_returning"):
            if user_context.get("name"):
                parts.append(f"Returning user: {user_context['name']}")
            else:
                parts.append("Returning user (name unknown)")

            if user_context.get("last_summary"):
                parts.append(f"Previous conversation: {user_context['last_summary']}")

            if user_context.get("last_interests"):
                parts.append(f"Previous interests: {', '.join(user_context['last_interests'])}")

        # Add potential matches for verification
        if potential_matches and len(potential_matches) > 0:
            parts.append("\nPOTENTIAL MATCHES (user just provided their name - verify their identity):")
            for match in potential_matches[:3]:
                topic = match.get('last_topic', 'general questions')
                parts.append(f"  - {match.get('name')} who previously asked about: {topic}")

        # Add semantic facts about the user
        if user_context and user_context.get("facts"):
            parts.append("\nKNOWN FACTS ABOUT THIS USER:")
            for fact_type, value in user_context["facts"].items():
                # Format fact type nicely (e.g., "pain_point" -> "Pain Point")
                label = fact_type.replace("_", " ").title()
                parts.append(f"  {label}: {value}")

        if not parts:
            return ""

        return "\n\nUSER CONTEXT:\n" + "\n".join(parts)

    def _get_system_content(self, user_message: str, user_context: dict = None, potential_matches: list = None) -> str:
        """Build the system prompt with RAG and user context."""
        # Get RAG context if enabled and documents exist
        rag_context = ""
        if self.use_rag and self.doc_store and self.doc_store.collection.count() > 0:
            rag_context = self.doc_store.get_context(user_message)

        # Build system prompt with optional RAG context and user context
        system_content = SYSTEM_PROMPT
        if rag_context:
            system_content = f"{SYSTEM_PROMPT}\n\n{rag_context}"
        # Add user context and potential matches
        context_prompt = self._build_user_context_prompt(user_context, potential_matches)
        if context_prompt:
            system_content += context_prompt

        return system_content

    def _build_messages(self, user_message: str, user_context: dict = None, potential_matches: list = None) -> list:
        """Build messages array for Together AI API (OpenAI-compatible format)."""
        system_content = self._get_system_content(user_message, user_context, potential_matches)

        messages = [{"role": "system", "content": system_content}]

        # Add conversation history
        for turn in self.conversation_history[-MAX_HISTORY_TURNS:]:
            messages.append({"role": "user", "content": turn['user']})
            messages.append({"role": "assistant", "content": turn['assistant']})

        # Add current user message
        messages.append({"role": "user", "content": user_message})

        return messages

    def _build_prompt(self, user_message: str, user_context: dict = None, potential_matches: list = None) -> str:
        """
        Build the full prompt with system message and conversation history.
        Uses Llama 3.1 instruct format with special tokens (for local mode).
        """
        system_content = self._get_system_content(user_message, user_context, potential_matches)

        # Llama 3.1 format (no begin_of_text - llama.cpp adds it automatically)
        prompt = f"<|start_header_id|>system<|end_header_id|>\n\n{system_content}<|eot_id|>"

        # Add conversation history
        for turn in self.conversation_history[-MAX_HISTORY_TURNS:]:
            prompt += f"<|start_header_id|>user<|end_header_id|>\n\n{turn['user']}<|eot_id|>"
            prompt += f"<|start_header_id|>assistant<|end_header_id|>\n\n{turn['assistant']}<|eot_id|>"

        # Add current user message
        prompt += f"<|start_header_id|>user<|end_header_id|>\n\n{user_message}<|eot_id|>"
        prompt += f"<|start_header_id|>assistant<|end_header_id|>\n\n"

        return prompt
    
    def chat(self, user_message: str, user_context: dict = None, potential_matches: list = None) -> str:
        """
        Generate a response to the user's message.
        """
        if self.is_cloud:
            # Cloud mode: Use Together AI API
            if self.client is None:
                raise RuntimeError("Together AI client not initialized. Call load_model() first.")

            messages = self._build_messages(user_message, user_context, potential_matches)
            print(f"[DEBUG] Messages count: {len(messages)}")

            response_obj = self.client.chat.completions.create(
                model=TOGETHER_MODEL,
                messages=messages,
                max_tokens=MAX_TOKENS,
                temperature=TEMPERATURE,
                top_p=TOP_P,
                repetition_penalty=REPEAT_PENALTY,
                stop=["<|eot_id|>"]
            )

            response = response_obj.choices[0].message.content.strip()
        else:
            # Local mode: Use llama-cpp-python
            if self.model is None:
                raise RuntimeError("Model not loaded. Call load_model() first.")

            prompt = self._build_prompt(user_message, user_context, potential_matches)

            # Debug: log prompt size
            print(f"[DEBUG] Prompt length: {len(prompt)} chars, ~{len(prompt) // 4} tokens")

            # Generate response
            output = self.model(
                prompt,
                max_tokens=MAX_TOKENS,
                temperature=TEMPERATURE,
                top_p=TOP_P,
                repeat_penalty=REPEAT_PENALTY,
                stop=["<|eot_id|>", "<|start_header_id|>"],
                echo=False
            )

            response = output["choices"][0]["text"].strip()

        # Debug: log response
        print(f"[DEBUG] Response length: {len(response)} chars")
        print(f"[DEBUG] Response: {repr(response[:200])}")
        
        # Store in history
        self.conversation_history.append({
            "user": user_message,
            "assistant": response
        })
        
        return response
    
    def chat_stream(self, user_message: str, user_context: dict = None, potential_matches: list = None):
        """
        Generate a streaming response to the user's message.
        Yields tokens as they are generated.
        """
        full_response = ""

        if self.is_cloud:
            # Cloud mode: Use Together AI API with streaming
            if self.client is None:
                raise RuntimeError("Together AI client not initialized. Call load_model() first.")

            messages = self._build_messages(user_message, user_context, potential_matches)
            print(f"[DEBUG] Messages count: {len(messages)}")

            stream = self.client.chat.completions.create(
                model=TOGETHER_MODEL,
                messages=messages,
                max_tokens=MAX_TOKENS,
                temperature=TEMPERATURE,
                top_p=TOP_P,
                repetition_penalty=REPEAT_PENALTY,
                stop=["<|eot_id|>"],
                stream=True
            )

            for chunk in stream:
                if chunk.choices[0].delta.content:
                    token = chunk.choices[0].delta.content
                    full_response += token
                    yield token
        else:
            # Local mode: Use llama-cpp-python
            if self.model is None:
                raise RuntimeError("Model not loaded. Call load_model() first.")

            prompt = self._build_prompt(user_message, user_context, potential_matches)

            # Debug: log prompt size
            print(f"[DEBUG] Prompt length: {len(prompt)} chars, ~{len(prompt) // 4} tokens")

            # Generate response with streaming
            for output in self.model(
                prompt,
                max_tokens=MAX_TOKENS,
                temperature=TEMPERATURE,
                top_p=TOP_P,
                repeat_penalty=REPEAT_PENALTY,
                stop=["<|eot_id|>", "<|start_header_id|>"],
                echo=False,
                stream=True
            ):
                token = output["choices"][0]["text"]
                full_response += token
                yield token
        
        # Store in history after streaming completes
        self.conversation_history.append({
            "user": user_message,
            "assistant": full_response.strip()
        })
        
        print(f"[DEBUG] Response length: {len(full_response)} chars")
    
    def clear_history(self):
        """Clear conversation history."""
        self.conversation_history = []
        return "Conversation cleared. Fresh start!"
    
    def get_stats(self) -> dict:
        """Return current stats."""
        stats = {
            "history_turns": len(self.conversation_history),
            "max_history": MAX_HISTORY_TURNS,
            "rag_enabled": self.use_rag,
            "cloud_mode": self.is_cloud
        }
        if self.is_cloud:
            stats["model"] = TOGETHER_MODEL
        else:
            stats["context_size"] = N_CTX
            stats["gpu_layers"] = N_GPU_LAYERS
        if self.use_rag and self.doc_store:
            stats["indexed_chunks"] = self.doc_store.collection.count()
            stats["indexed_documents"] = len(self.doc_store.list_documents())
        return stats


# CLI interface for testing
if __name__ == "__main__":
    print("=" * 50)
    print("Blacksky Chatbot - CLI Mode")
    print("=" * 50)
    print("Commands: /clear (reset history), /stats, /docs, /quit\n")
    
    bot = BlackskyChatbot(use_rag=True)
    bot.load_model()
    
    while True:
        try:
            user_input = input("You: ").strip()
            
            if not user_input:
                continue
            elif user_input.lower() == "/quit":
                print("Goodbye!")
                break
            elif user_input.lower() == "/clear":
                print(f"Bot: {bot.clear_history()}")
                continue
            elif user_input.lower() == "/stats":
                print(f"Stats: {bot.get_stats()}")
                continue
            elif user_input.lower() == "/docs":
                if bot.doc_store:
                    docs = bot.doc_store.list_documents()
                    print(f"Indexed documents: {docs if docs else 'None'}")
                else:
                    print("RAG not enabled")
                continue
            
            response = bot.chat(user_input)
            print(f"Bot: {response}\n")
            
        except KeyboardInterrupt:
            print("\nGoodbye!")
            break
