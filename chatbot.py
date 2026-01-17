"""
Core chatbot logic using Together AI (Llama 3.1 70B)
"""
from openai import OpenAI

import json

from config import (
    TOGETHER_API_KEY,
    TOGETHER_MODEL,
    TOGETHER_FAST_MODEL,
    TOGETHER_BASE_URL,
    MAX_TOKENS,
    MAX_HISTORY_TURNS
)
from prompts import SYSTEM_PROMPT
from rag import DocumentStore


class BlackskyChatbot:
    """Chatbot wrapper using Together AI (Llama) for inference."""

    def __init__(self, use_rag: bool = True):
        self.client = None
        self.conversation_history = []
        self.use_rag = use_rag
        self.doc_store = None
        self.session_context = {}  # Track user info learned this session

    def initialize(self):
        """Initialize Together AI client and RAG."""
        print("Initializing Blacksky Chatbot (Cloud)...")

        # Initialize Together AI client (OpenAI-compatible)
        self.client = OpenAI(
            api_key=TOGETHER_API_KEY,
            base_url=TOGETHER_BASE_URL
        )
        print("✓ Together AI (Llama 3.1 70B) client ready")
        
        # Initialize RAG if enabled
        if self.use_rag:
            self.doc_store = DocumentStore()
            self.doc_store.initialize()
        
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

            # Add lead intelligence based on previous engagement
            lead_score = user_context.get("last_lead_score", 1)
            conv_count = user_context.get("conversation_count", 1)
            has_contact = user_context.get("email") or user_context.get("phone")

            if lead_score >= 3:
                # High-value returning lead
                interests = user_context.get("last_interests", [])
                interest_str = ', '.join(interests) if interests else "your services"
                parts.append(f"\nLEAD INTELLIGENCE: This user previously showed strong interest in {interest_str}.")
                parts.append(f"They scored {lead_score}/5 on intent signals.")
                parts.append("Consider this a warm lead — be helpful but look for closing opportunities.")
            elif conv_count > 1 and not has_contact:
                # Multiple visits but no contact info
                parts.append(f"\nLEAD INTELLIGENCE: This user has visited {conv_count} times but hasn't provided contact info.")
                parts.append("Focus on understanding their needs before asking for info.")

        # Add potential matches for verification
        if potential_matches and len(potential_matches) > 0:
            parts.append("\nPOTENTIAL MATCHES (user just provided their name - verify their identity):")
            for i, match in enumerate(potential_matches[:3]):  # Max 3 matches
                topic = match.get('last_topic', 'general questions')
                parts.append(f"  - {match.get('name')} who previously asked about: {topic}")

        if not parts:
            return ""

        return "\n\nUSER CONTEXT:\n" + "\n".join(parts)

    def _extract_session_insights(self, user_message: str, assistant_response: str):
        """Extract key user info from exchange using fast model."""
        prompt = """Extract any NEW user information from this exchange. Return valid JSON only:
{"name": null, "company": null, "industry": null, "interests": [], "pain_points": []}
Only include non-null/non-empty values for info actually stated. Return {} if nothing new.

User: """ + user_message + """
Assistant: """ + assistant_response

        try:
            response = self.client.chat.completions.create(
                model=TOGETHER_FAST_MODEL,
                max_tokens=150,
                messages=[{"role": "user", "content": prompt}]
            )
            result = response.choices[0].message.content.strip()

            # Try to parse JSON from response
            # Handle cases where model wraps in markdown code blocks
            if "```" in result:
                result = result.split("```")[1]
                if result.startswith("json"):
                    result = result[4:]

            insights = json.loads(result)

            # Merge insights into session_context
            if insights.get("name"):
                self.session_context["name"] = insights["name"]
            if insights.get("company"):
                self.session_context["company"] = insights["company"]
            if insights.get("industry"):
                self.session_context["industry"] = insights["industry"]
            if insights.get("interests"):
                existing = self.session_context.get("interests", [])
                self.session_context["interests"] = list(set(existing + insights["interests"]))
            if insights.get("pain_points"):
                existing = self.session_context.get("pain_points", [])
                self.session_context["pain_points"] = list(set(existing + insights["pain_points"]))

        except Exception as e:
            # Silent fail - extraction is optional enhancement
            print(f"Session insight extraction failed: {e}")

    def _build_session_context_prompt(self) -> str:
        """Build context string from info learned this session."""
        if not self.session_context:
            return ""

        parts = ["SESSION INFO (learned this conversation):"]
        if self.session_context.get("name"):
            parts.append(f"  Name: {self.session_context['name']}")
        if self.session_context.get("company"):
            parts.append(f"  Company: {self.session_context['company']}")
        if self.session_context.get("industry"):
            parts.append(f"  Industry: {self.session_context['industry']}")
        if self.session_context.get("interests"):
            parts.append(f"  Interests: {', '.join(self.session_context['interests'])}")
        if self.session_context.get("pain_points"):
            parts.append(f"  Pain points: {', '.join(self.session_context['pain_points'])}")

        if len(parts) == 1:
            return ""

        return "\n\n" + "\n".join(parts)

    def chat(self, user_message: str, user_context: dict = None, potential_matches: list = None) -> str:
        """Generate a response to the user's message."""
        if self.client is None:
            raise RuntimeError("Client not initialized. Call initialize() first.")

        # Get RAG context if enabled (pass history for query expansion)
        rag_context = ""
        if self.use_rag and self.doc_store:
            try:
                rag_context = self.doc_store.get_context(user_message, history=self.conversation_history)
            except Exception as e:
                print(f"RAG error: {e}")

        # Build system prompt with optional RAG context and user context
        system_content = SYSTEM_PROMPT
        if rag_context:
            system_content = f"{SYSTEM_PROMPT}\n\n{rag_context}"
        # Add user context and potential matches
        context_prompt = self._build_user_context_prompt(user_context, potential_matches)
        if context_prompt:
            system_content += context_prompt

        # Add session context (info learned this conversation)
        session_prompt = self._build_session_context_prompt()
        if session_prompt:
            system_content += session_prompt

        # Build messages array (OpenAI format - system message first)
        messages = [{"role": "system", "content": system_content}]

        # Add conversation history
        for turn in self.conversation_history[-MAX_HISTORY_TURNS:]:
            messages.append({"role": "user", "content": turn["user"]})
            messages.append({"role": "assistant", "content": turn["assistant"]})

        # Add current user message
        messages.append({"role": "user", "content": user_message})

        # Call Together AI (Llama 3.1 70B)
        response = self.client.chat.completions.create(
            model=TOGETHER_MODEL,
            max_tokens=MAX_TOKENS,
            messages=messages
        )

        assistant_message = response.choices[0].message.content.strip()

        # Store in history
        self.conversation_history.append({
            "user": user_message,
            "assistant": assistant_message
        })

        # Extract insights from this exchange for future context
        self._extract_session_insights(user_message, assistant_message)

        return assistant_message

    def chat_stream(self, user_message: str, user_context: dict = None, potential_matches: list = None):
        """Generate a streaming response to the user's message."""
        if self.client is None:
            raise RuntimeError("Client not initialized. Call initialize() first.")

        # Get RAG context if enabled (pass history for query expansion)
        rag_context = ""
        if self.use_rag and self.doc_store:
            try:
                rag_context = self.doc_store.get_context(user_message, history=self.conversation_history)
            except Exception as e:
                print(f"RAG error: {e}")

        # Build system prompt with optional RAG context and user context
        system_content = SYSTEM_PROMPT
        if rag_context:
            system_content = f"{SYSTEM_PROMPT}\n\n{rag_context}"
        # Add user context and potential matches
        context_prompt = self._build_user_context_prompt(user_context, potential_matches)
        if context_prompt:
            system_content += context_prompt

        # Add session context (info learned this conversation)
        session_prompt = self._build_session_context_prompt()
        if session_prompt:
            system_content += session_prompt

        # Build messages array (OpenAI format - system message first)
        messages = [{"role": "system", "content": system_content}]

        # Add conversation history
        for turn in self.conversation_history[-MAX_HISTORY_TURNS:]:
            messages.append({"role": "user", "content": turn["user"]})
            messages.append({"role": "assistant", "content": turn["assistant"]})

        # Add current user message
        messages.append({"role": "user", "content": user_message})

        # Call Together AI with streaming
        full_response = ""
        stream = self.client.chat.completions.create(
            model=TOGETHER_MODEL,
            max_tokens=MAX_TOKENS,
            messages=messages,
            stream=True
        )
        for chunk in stream:
            if chunk.choices[0].delta.content:
                text = chunk.choices[0].delta.content
                full_response += text
                yield text

        # Store in history after streaming completes
        self.conversation_history.append({
            "user": user_message,
            "assistant": full_response.strip()
        })

        # Extract insights from this exchange for future context
        self._extract_session_insights(user_message, full_response.strip())

    def clear_history(self):
        """Clear conversation history and session context."""
        self.conversation_history = []
        self.session_context = {}
        return "Conversation cleared. Fresh start!"
    
    def get_stats(self) -> dict:
        """Return current stats."""
        stats = {
            "history_turns": len(self.conversation_history),
            "max_history": MAX_HISTORY_TURNS,
            "model": TOGETHER_MODEL,
            "rag_enabled": self.use_rag
        }
        if self.use_rag and self.doc_store:
            try:
                rag_stats = self.doc_store.get_stats()
                stats["indexed_vectors"] = rag_stats["total_vectors"]
            except Exception:
                stats["indexed_vectors"] = 0
        return stats


# CLI interface for testing
if __name__ == "__main__":
    print("=" * 50)
    print("Blacksky Chatbot (Cloud) - CLI Mode")
    print("=" * 50)
    print("Commands: /clear (reset history), /stats, /quit\n")
    
    bot = BlackskyChatbot(use_rag=True)
    bot.initialize()
    
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
            
            response = bot.chat(user_input)
            print(f"Bot: {response}\n")
            
        except KeyboardInterrupt:
            print("\nGoodbye!")
            break
