"""
Core chatbot logic with support for local and cloud Llama providers.
"""
from llm import create_llama_provider
from config import (
    MAX_TOKENS, TEMPERATURE, TOP_P, REPEAT_PENALTY, MAX_HISTORY_TURNS, N_CTX, N_GPU_LAYERS
)
from prompts import SYSTEM_PROMPT, ADMIN_SYSTEM_PROMPT
from rag import DocumentStore


class BlackskyChatbot:
    """Chatbot wrapper with support for local and cloud Llama providers.

    This class is stateless - conversation history must be passed per request.
    """

    def __init__(self, use_rag: bool = True):
        self.llm = None
        self.use_rag = use_rag
        self.doc_store = None

    def load_model(self):
        """Load the LLM provider (local or cloud)."""
        self.llm = create_llama_provider()
        self.llm.load()
        
        # Initialize RAG if enabled
        if self.use_rag:
            self.doc_store = DocumentStore()
            self.doc_store.initialize()
        print()

    def _build_user_context_prompt(self, user_context: dict, potential_matches: list = None,
                                     panel_views: list = None) -> str:
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

        # Add panel engagement (what pages user has viewed)
        if panel_views and len(panel_views) > 0:
            # Deduplicate while preserving order
            seen = set()
            unique_views = []
            for v in panel_views:
                if v not in seen:
                    seen.add(v)
                    unique_views.append(v)
            parts.append(f"\nRECENT PAGE VIEWS: {', '.join(unique_views)}")

        if not parts:
            return ""

        return "\n\nUSER CONTEXT:\n" + "\n".join(parts)

    def _build_prompt(self, user_message: str, conversation_history: list = None,
                       user_context: dict = None, potential_matches: list = None,
                       is_admin: bool = False, panel_views: list = None) -> tuple:
        """
        Build the full prompt with system message and conversation history.
        Uses Llama 3.1 instruct format with special tokens.

        Args:
            user_message: The current user message
            conversation_history: List of {"user": ..., "assistant": ...} dicts
            user_context: Context about the user (name, facts, etc.)
            potential_matches: Potential returning user matches
            is_admin: Whether the user is in admin mode
            panel_views: List of panel titles the user has viewed

        Returns:
            Tuple of (prompt, rag_sources) where rag_sources is a list of source names
        """
        if conversation_history is None:
            conversation_history = []

        # Get RAG context if enabled and documents exist
        rag_context = ""
        rag_sources = []
        if self.use_rag and self.doc_store and self.doc_store.collection.count() > 0:
            rag_context, rag_sources = self.doc_store.get_context_with_sources(user_message)

        # Choose base prompt based on admin status
        if is_admin:
            base_prompt = ADMIN_SYSTEM_PROMPT.format(base_prompt=SYSTEM_PROMPT)
        else:
            base_prompt = SYSTEM_PROMPT

        # Build system prompt with optional RAG context and user context
        system_content = base_prompt
        if rag_context:
            system_content = f"{base_prompt}\n\n{rag_context}"
            # Add RAG source info for admin mode
            if is_admin and rag_sources:
                system_content += f"\n\n[RAG SOURCES: {', '.join(rag_sources)}]"
        # Add user context and potential matches
        context_prompt = self._build_user_context_prompt(user_context, potential_matches, panel_views)
        if context_prompt:
            system_content += context_prompt

        # Llama 3.1 format (no begin_of_text - llama.cpp adds it automatically)
        prompt = f"<|start_header_id|>system<|end_header_id|>\n\n{system_content}<|eot_id|>"

        # Add conversation history (last N turns)
        for turn in conversation_history[-MAX_HISTORY_TURNS:]:
            prompt += f"<|start_header_id|>user<|end_header_id|>\n\n{turn['user']}<|eot_id|>"
            prompt += f"<|start_header_id|>assistant<|end_header_id|>\n\n{turn['assistant']}<|eot_id|>"

        # Add current user message
        prompt += f"<|start_header_id|>user<|end_header_id|>\n\n{user_message}<|eot_id|>"
        prompt += f"<|start_header_id|>assistant<|end_header_id|>\n\n"

        return prompt, rag_sources
    
    def chat(self, user_message: str, conversation_history: list = None,
             user_context: dict = None, potential_matches: list = None,
             is_admin: bool = False) -> str:
        """
        Generate a response to the user's message.

        Args:
            user_message: The user's message
            conversation_history: Previous turns in this conversation
            user_context: Context about the user
            potential_matches: Potential returning user matches
            is_admin: Whether the user is in admin mode

        Returns:
            The assistant's response (caller should append to their history)
        """
        if self.llm is None or not self.llm.is_loaded():
            raise RuntimeError("Model not loaded. Call load_model() first.")

        prompt, _ = self._build_prompt(user_message, conversation_history, user_context, potential_matches, is_admin)

        # Debug: log prompt size
        print(f"[DEBUG] Prompt length: {len(prompt)} chars, ~{len(prompt) // 4} tokens")

        # Generate response via provider
        response = self.llm.chat(
            prompt=prompt,
            max_tokens=MAX_TOKENS,
            temperature=TEMPERATURE,
            top_p=TOP_P,
            repeat_penalty=REPEAT_PENALTY,
            stop=["<|eot_id|>", "<|start_header_id|>"]
        )

        # Debug: log response
        print(f"[DEBUG] Response length: {len(response)} chars")
        print(f"[DEBUG] Response: {repr(response[:200])}")

        return response
    
    def chat_stream(self, user_message: str, conversation_history: list = None,
                     user_context: dict = None, potential_matches: list = None,
                     is_admin: bool = False, panel_views: list = None):
        """
        Generate a streaming response to the user's message.
        Yields tokens as they are generated.

        Args:
            user_message: The user's message
            conversation_history: Previous turns in this conversation
            user_context: Context about the user
            potential_matches: Potential returning user matches
            is_admin: Whether the user is in admin mode
            panel_views: List of panel titles the user has viewed

        Yields:
            Tokens as they are generated (caller should collect and append to history)
        """
        if self.llm is None or not self.llm.is_loaded():
            raise RuntimeError("Model not loaded. Call load_model() first.")

        prompt, _ = self._build_prompt(user_message, conversation_history, user_context, potential_matches, is_admin, panel_views)

        # Debug: log prompt size
        print(f"[DEBUG] Prompt length: {len(prompt)} chars, ~{len(prompt) // 4} tokens")

        # Generate response with streaming via provider
        full_response = ""
        for token in self.llm.chat_stream(
            prompt=prompt,
            max_tokens=MAX_TOKENS,
            temperature=TEMPERATURE,
            top_p=TOP_P,
            repeat_penalty=REPEAT_PENALTY,
            stop=["<|eot_id|>", "<|start_header_id|>"]
        ):
            full_response += token
            yield token

        print(f"[DEBUG] Response length: {len(full_response)} chars")
    
    def get_stats(self) -> dict:
        """Return current stats."""
        import os
        provider = os.getenv("LLAMA_PROVIDER", "local")
        stats = {
            "max_history": MAX_HISTORY_TURNS,
            "provider": provider,
            "rag_enabled": self.use_rag
        }
        # Add local-specific stats
        if provider == "local":
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

    # Local conversation history for CLI mode
    cli_history = []

    while True:
        try:
            user_input = input("You: ").strip()

            if not user_input:
                continue
            elif user_input.lower() == "/quit":
                print("Goodbye!")
                break
            elif user_input.lower() == "/clear":
                cli_history = []
                print("Bot: Conversation history cleared.")
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

            response = bot.chat(user_input, conversation_history=cli_history)
            # Append to local CLI history
            cli_history.append({"user": user_input, "assistant": response})
            print(f"Bot: {response}\n")

        except KeyboardInterrupt:
            print("\nGoodbye!")
            break
