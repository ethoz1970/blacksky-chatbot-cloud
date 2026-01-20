"""
Tests for user linking functionality.
Verifies that link_users() properly migrates facts and preserves names.
"""
import sys
import uuid
from pathlib import Path
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from database import (
    init_db, get_or_create_user, update_user, link_users,
    save_user_fact, get_user_facts, get_user_facts_dict, get_session, User
)


class TestLinkUsersFactMigration:
    """Tests for fact migration during user linking."""

    @pytest.fixture(autouse=True)
    def setup_db(self):
        """Initialize database and create test users."""
        init_db()
        self.current_user_id = str(uuid.uuid4())
        self.target_user_id = str(uuid.uuid4())
        get_or_create_user(self.current_user_id)
        get_or_create_user(self.target_user_id)
        yield

    def test_migrates_facts_to_target_user(self):
        """Facts from current user are migrated to target user."""
        save_user_fact(self.current_user_id, "role", "CTO", confidence=0.9)
        save_user_fact(self.current_user_id, "industry", "Healthcare", confidence=0.8)

        link_users(self.current_user_id, self.target_user_id)

        target_facts = get_user_facts_dict(self.target_user_id)
        assert target_facts.get("role") == "CTO"
        assert target_facts.get("industry") == "Healthcare"

    def test_higher_confidence_fact_wins(self):
        """When both users have same fact type, higher confidence wins."""
        # Target has low confidence role
        save_user_fact(self.target_user_id, "role", "Developer", confidence=0.5)
        # Current has high confidence role
        save_user_fact(self.current_user_id, "role", "CTO", confidence=0.9)

        link_users(self.current_user_id, self.target_user_id)

        target_facts = get_user_facts(self.target_user_id)
        role_fact = next(f for f in target_facts if f["type"] == "role")
        assert role_fact["value"] == "CTO"
        assert role_fact["confidence"] == 0.9

    def test_lower_confidence_fact_does_not_overwrite(self):
        """When current user has lower confidence, target fact preserved."""
        # Target has high confidence role
        save_user_fact(self.target_user_id, "role", "CTO", confidence=0.95)
        # Current has low confidence role
        save_user_fact(self.current_user_id, "role", "Developer", confidence=0.5)

        link_users(self.current_user_id, self.target_user_id)

        target_facts = get_user_facts(self.target_user_id)
        role_fact = next(f for f in target_facts if f["type"] == "role")
        assert role_fact["value"] == "CTO"
        assert role_fact["confidence"] == 0.95

    def test_new_fact_types_added(self):
        """Fact types only on current user are added to target."""
        save_user_fact(self.target_user_id, "role", "CTO", confidence=0.9)
        save_user_fact(self.current_user_id, "budget", "$100k", confidence=0.8)
        save_user_fact(self.current_user_id, "timeline", "Q2 2025", confidence=0.7)

        link_users(self.current_user_id, self.target_user_id)

        target_facts = get_user_facts_dict(self.target_user_id)
        assert target_facts.get("role") == "CTO"  # Original preserved
        assert target_facts.get("budget") == "$100k"  # New fact added
        assert target_facts.get("timeline") == "Q2 2025"  # New fact added

    def test_current_user_facts_deleted(self):
        """Current user's facts are cleaned up after migration."""
        save_user_fact(self.current_user_id, "role", "CTO", confidence=0.9)

        link_users(self.current_user_id, self.target_user_id)

        # Current user should be deleted, so facts should not exist
        current_facts = get_user_facts(self.current_user_id)
        assert len(current_facts) == 0


class TestLinkUsersNamePreservation:
    """Tests for name preservation during user linking."""

    @pytest.fixture(autouse=True)
    def setup_db(self):
        """Initialize database and create test users."""
        init_db()
        self.current_user_id = str(uuid.uuid4())
        self.target_user_id = str(uuid.uuid4())
        get_or_create_user(self.current_user_id)
        get_or_create_user(self.target_user_id)
        yield

    def test_name_copied_to_target(self):
        """Current user's name is copied to target user."""
        update_user(self.current_user_id, name="Sam Goody")

        link_users(self.current_user_id, self.target_user_id)

        session = get_session()
        target = session.query(User).filter(User.id == self.target_user_id).first()
        session.close()
        assert target.name == "Sam Goody"

    def test_anon_name_not_copied(self):
        """ANON[timestamp] names are not copied to target."""
        # Current user has default ANON name (not updated)
        # Target has a real name
        update_user(self.target_user_id, name="Existing User")

        link_users(self.current_user_id, self.target_user_id)

        session = get_session()
        target = session.query(User).filter(User.id == self.target_user_id).first()
        session.close()
        assert target.name == "Existing User"  # Not overwritten by ANON

    def test_current_name_overwrites_target(self):
        """Current user's real name overwrites target's name."""
        update_user(self.current_user_id, name="New Name")
        update_user(self.target_user_id, name="Old Name")

        link_users(self.current_user_id, self.target_user_id)

        session = get_session()
        target = session.query(User).filter(User.id == self.target_user_id).first()
        session.close()
        assert target.name == "New Name"


class TestLinkUsersIntegration:
    """Integration tests for full user linking flow."""

    @pytest.fixture(autouse=True)
    def setup_db(self):
        """Initialize database."""
        init_db()
        self.current_user_id = str(uuid.uuid4())
        self.target_user_id = str(uuid.uuid4())
        get_or_create_user(self.current_user_id)
        get_or_create_user(self.target_user_id)
        yield

    def test_full_linking_scenario(self):
        """
        Simulate: Anonymous user shares facts, gives name,
        links to existing user - all facts and name preserved.
        """
        # Current session: anonymous user shares info
        update_user(self.current_user_id, name="Sam Goody")
        save_user_fact(self.current_user_id, "role", "CTO", confidence=0.9)
        save_user_fact(self.current_user_id, "company_size", "50 employees", confidence=0.8)

        # Target user: existing record with some facts
        save_user_fact(self.target_user_id, "industry", "Healthcare", confidence=0.85)

        # Link users
        result = link_users(self.current_user_id, self.target_user_id)
        assert result is True

        # Verify target has all facts
        target_facts = get_user_facts_dict(self.target_user_id)
        assert target_facts.get("role") == "CTO"
        assert target_facts.get("company_size") == "50 employees"
        assert target_facts.get("industry") == "Healthcare"

        # Verify name is updated
        session = get_session()
        target = session.query(User).filter(User.id == self.target_user_id).first()
        session.close()
        assert target.name == "Sam Goody"

    def test_link_to_self_is_noop(self):
        """Linking user to self returns True without error."""
        save_user_fact(self.current_user_id, "role", "CTO", confidence=0.9)

        result = link_users(self.current_user_id, self.current_user_id)

        assert result is True
        # Facts should still exist
        facts = get_user_facts(self.current_user_id)
        assert len(facts) == 1
