"""
Tests for semantic memory system (UserFact model, fact extraction, CRUD operations).
Run with: pytest tests/test_semantic_memory.py -v
"""
import sys
import uuid
from pathlib import Path

import pytest

# Add parent directory to path so we can import from project modules
sys.path.insert(0, str(Path(__file__).parent.parent))

from database import (
    init_db,
    save_user_fact,
    save_user_facts,
    get_user_facts,
    get_user_facts_dict,
    delete_user_fact,
    get_user_context,
    get_or_create_user
)
from server import extract_semantic_facts


# ============================================================
# extract_semantic_facts tests
# ============================================================

class TestExtractSemanticFacts:
    """Tests for extract_semantic_facts function."""

    def test_extracts_role_cto(self):
        messages = [{"role": "user", "content": "I'm the CTO at a startup"}]
        facts = extract_semantic_facts(messages)
        assert any(f["type"] == "role" and "CTO" in f["value"] for f in facts)

    def test_extracts_role_developer(self):
        messages = [{"role": "user", "content": "I work as a Senior Developer"}]
        facts = extract_semantic_facts(messages)
        assert any(f["type"] == "role" for f in facts)

    def test_extracts_budget_range(self):
        messages = [{"role": "user", "content": "We have a budget of $50k-$100k"}]
        facts = extract_semantic_facts(messages)
        assert any(f["type"] == "budget" for f in facts)

    def test_extracts_budget_single(self):
        messages = [{"role": "user", "content": "Our budget is $75k"}]
        facts = extract_semantic_facts(messages)
        assert any(f["type"] == "budget" for f in facts)

    def test_extracts_timeline_quarter(self):
        messages = [{"role": "user", "content": "We need this by Q2 2025"}]
        facts = extract_semantic_facts(messages)
        assert any(f["type"] == "timeline" for f in facts)

    def test_extracts_timeline_asap(self):
        messages = [{"role": "user", "content": "We need this ASAP"}]
        facts = extract_semantic_facts(messages)
        assert any(f["type"] == "timeline" for f in facts)

    def test_extracts_company_size_employees(self):
        messages = [{"role": "user", "content": "We have about 50 employees"}]
        facts = extract_semantic_facts(messages)
        assert any(f["type"] == "company_size" for f in facts)

    def test_extracts_company_size_startup(self):
        messages = [{"role": "user", "content": "We're a small startup"}]
        facts = extract_semantic_facts(messages)
        assert any(f["type"] == "company_size" for f in facts)

    def test_extracts_industry(self):
        messages = [{"role": "user", "content": "We're in the healthcare industry"}]
        facts = extract_semantic_facts(messages)
        assert any(f["type"] == "industry" for f in facts)

    def test_extracts_project_type(self):
        messages = [{"role": "user", "content": "We need a mobile app built"}]
        facts = extract_semantic_facts(messages)
        assert any(f["type"] == "project_type" for f in facts)

    def test_ignores_assistant_messages(self):
        messages = [{"role": "assistant", "content": "I'm the CTO here at Blacksky"}]
        facts = extract_semantic_facts(messages)
        assert len(facts) == 0

    def test_multiple_facts_from_conversation(self):
        messages = [
            {"role": "user", "content": "Hi, I'm the CTO at a healthcare startup"},
            {"role": "assistant", "content": "Nice to meet you! How can I help?"},
            {"role": "user", "content": "We have a budget of $50k-$100k"}
        ]
        facts = extract_semantic_facts(messages)
        types = [f["type"] for f in facts]
        assert "role" in types
        assert "company_size" in types  # "startup" triggers company_size

    def test_facts_have_confidence_scores(self):
        messages = [{"role": "user", "content": "I'm the CTO"}]
        facts = extract_semantic_facts(messages)
        assert len(facts) > 0
        for fact in facts:
            assert "confidence" in fact
            assert 0.0 <= fact["confidence"] <= 1.0

    def test_facts_have_source_text(self):
        messages = [{"role": "user", "content": "I'm the CTO at Acme Corp"}]
        facts = extract_semantic_facts(messages)
        assert len(facts) > 0
        for fact in facts:
            assert "source_text" in fact

    def test_empty_messages_returns_empty(self):
        facts = extract_semantic_facts([])
        assert facts == []

    def test_no_facts_found(self):
        messages = [{"role": "user", "content": "Hello, how are you today?"}]
        facts = extract_semantic_facts(messages)
        assert facts == []


# ============================================================
# UserFact CRUD tests
# ============================================================

class TestUserFactCRUD:
    """Tests for UserFact database operations."""

    @pytest.fixture(autouse=True)
    def setup_db(self):
        """Initialize database before each test."""
        init_db()
        self.test_user_id = str(uuid.uuid4())
        yield

    def test_save_single_fact(self):
        fact_id = save_user_fact(
            self.test_user_id,
            "role",
            "CTO",
            confidence=0.9,
            source_text="I am the CTO"
        )
        assert fact_id is not None
        assert isinstance(fact_id, int)

    def test_save_fact_without_optional_fields(self):
        fact_id = save_user_fact(self.test_user_id, "role", "Developer")
        assert fact_id is not None

    def test_save_multiple_facts(self):
        facts = [
            {"type": "role", "value": "CTO", "confidence": 0.9},
            {"type": "budget", "value": "$50k", "confidence": 0.8}
        ]
        count = save_user_facts(self.test_user_id, facts)
        assert count == 2

    def test_save_multiple_facts_with_source_text(self):
        facts = [
            {"type": "role", "value": "CTO", "confidence": 0.9, "source_text": "I'm the CTO"},
            {"type": "budget", "value": "$50k", "confidence": 0.8, "source_text": "Budget is 50k"}
        ]
        count = save_user_facts(self.test_user_id, facts)
        assert count == 2

    def test_get_facts_returns_saved(self):
        save_user_fact(self.test_user_id, "role", "Developer", confidence=0.9)
        facts = get_user_facts(self.test_user_id)
        assert len(facts) == 1
        assert facts[0]["type"] == "role"
        assert facts[0]["value"] == "Developer"

    def test_get_facts_includes_all_fields(self):
        save_user_fact(
            self.test_user_id,
            "role",
            "CTO",
            confidence=0.9,
            source_text="I am the CTO"
        )
        facts = get_user_facts(self.test_user_id)
        assert len(facts) == 1
        fact = facts[0]
        assert "id" in fact
        assert "type" in fact
        assert "value" in fact
        assert "confidence" in fact
        assert "created_at" in fact

    def test_get_facts_dict(self):
        save_user_fact(self.test_user_id, "role", "CTO", confidence=0.9)
        save_user_fact(self.test_user_id, "budget", "$100k", confidence=0.8)
        facts_dict = get_user_facts_dict(self.test_user_id)
        assert facts_dict["role"] == "CTO"
        assert facts_dict["budget"] == "$100k"

    def test_get_facts_dict_empty_user(self):
        facts_dict = get_user_facts_dict(self.test_user_id)
        assert facts_dict == {}

    def test_update_fact_with_higher_confidence(self):
        save_user_fact(self.test_user_id, "role", "Developer", confidence=0.7)
        save_user_fact(self.test_user_id, "role", "Senior Developer", confidence=0.9)
        facts = get_user_facts(self.test_user_id)
        # Should only have one fact (updated)
        assert len(facts) == 1
        assert facts[0]["value"] == "Senior Developer"
        assert facts[0]["confidence"] == 0.9

    def test_update_fact_keeps_max_confidence(self):
        # First save with high confidence
        save_user_fact(self.test_user_id, "role", "CTO", confidence=0.9)
        # Update with lower confidence - value changes but confidence stays max
        save_user_fact(self.test_user_id, "role", "Manager", confidence=0.5)
        facts = get_user_facts(self.test_user_id)
        assert len(facts) == 1
        assert facts[0]["value"] == "Manager"  # Value updates
        assert facts[0]["confidence"] == 0.9   # Confidence stays at max

    def test_respects_confidence_threshold(self):
        save_user_fact(self.test_user_id, "role", "Intern", confidence=0.3)
        facts = get_user_facts(self.test_user_id, min_confidence=0.5)
        assert len(facts) == 0

    def test_respects_confidence_threshold_mixed(self):
        save_user_fact(self.test_user_id, "role", "CTO", confidence=0.9)
        save_user_fact(self.test_user_id, "budget", "$10k", confidence=0.4)
        facts = get_user_facts(self.test_user_id, min_confidence=0.5)
        assert len(facts) == 1
        assert facts[0]["type"] == "role"

    def test_delete_fact(self):
        fact_id = save_user_fact(self.test_user_id, "role", "CTO", confidence=0.9)
        result = delete_user_fact(fact_id)
        assert result is True
        facts = get_user_facts(self.test_user_id)
        assert len(facts) == 0

    def test_delete_nonexistent_fact(self):
        result = delete_user_fact(99999)
        assert result is False

    def test_multiple_fact_types(self):
        save_user_fact(self.test_user_id, "role", "CTO", confidence=0.9)
        save_user_fact(self.test_user_id, "budget", "$100k", confidence=0.85)
        save_user_fact(self.test_user_id, "timeline", "Q2 2025", confidence=0.8)
        save_user_fact(self.test_user_id, "industry", "Healthcare", confidence=0.9)

        facts = get_user_facts(self.test_user_id)
        assert len(facts) == 4
        types = {f["type"] for f in facts}
        assert types == {"role", "budget", "timeline", "industry"}


# ============================================================
# Context injection tests
# ============================================================

class TestFactContextInjection:
    """Tests for facts being included in user context."""

    @pytest.fixture(autouse=True)
    def setup_db(self):
        """Initialize database before each test."""
        init_db()
        self.test_user_id = str(uuid.uuid4())
        # Create the user so get_user_context returns a result
        get_or_create_user(self.test_user_id)
        yield

    def test_get_user_context_includes_facts(self):
        # Save a fact
        save_user_fact(self.test_user_id, "role", "CTO", confidence=0.9)

        # Get user context
        context = get_user_context(self.test_user_id)

        assert context is not None
        assert "facts" in context
        assert context["facts"].get("role") == "CTO"

    def test_get_user_context_multiple_facts(self):
        save_user_fact(self.test_user_id, "role", "CTO", confidence=0.9)
        save_user_fact(self.test_user_id, "budget", "$100k", confidence=0.85)

        context = get_user_context(self.test_user_id)

        assert context["facts"].get("role") == "CTO"
        assert context["facts"].get("budget") == "$100k"

    def test_get_user_context_filters_low_confidence(self):
        save_user_fact(self.test_user_id, "role", "CTO", confidence=0.9)
        save_user_fact(self.test_user_id, "budget", "$10k", confidence=0.4)

        context = get_user_context(self.test_user_id)

        # High confidence fact should be there
        assert context["facts"].get("role") == "CTO"
        # Low confidence fact should be filtered (default threshold is 0.6)
        assert "budget" not in context["facts"]

    def test_get_user_context_no_facts(self):
        context = get_user_context(self.test_user_id)

        # Should still have facts key, just empty
        assert context is not None
        assert "facts" in context
        assert context["facts"] == {}
