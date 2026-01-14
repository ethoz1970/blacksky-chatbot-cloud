"""
Tests for authentication system - Anonymous, Soft Login, and Hard Login.

User tiers:
- Anonymous: UUID cookie only, name is "ANON[timestamp]"
- Soft login: Maurice extracted name/email/company/phone from conversation
- Hard login: User registered with name + password
"""
import pytest
import uuid
import sys
from pathlib import Path
from datetime import datetime, timedelta

sys.path.insert(0, str(Path(__file__).parent.parent))

from database import (
    init_db, get_session, User, get_or_create_user, update_user,
    create_hard_user, verify_hard_login, get_user_by_name,
    save_conversation, get_user_conversations
)
from server import app, create_auth_token, decode_auth_token
from fastapi.testclient import TestClient


# ============================================
# Test Anonymous Users
# ============================================

class TestAnonymousUser:
    """Tests for anonymous user creation and state."""

    @pytest.fixture(autouse=True)
    def setup(self):
        init_db()
        self.test_user_id = str(uuid.uuid4())
        yield

    def test_anonymous_user_created(self):
        """New UUID creates user with ANON name."""
        user = get_or_create_user(self.test_user_id)

        assert user is not None
        assert user['id'] == self.test_user_id
        assert user['name'].startswith('ANON[')

    def test_anonymous_user_has_soft_auth_method(self):
        """Anonymous user has auth_method = 'soft'."""
        get_or_create_user(self.test_user_id)

        # Check auth_method directly in database
        session = get_session()
        user = session.query(User).filter(User.id == self.test_user_id).first()
        session.close()

        assert user.auth_method == 'soft'

    def test_anonymous_user_context_empty(self):
        """Anonymous user has no name/email/phone/company."""
        user = get_or_create_user(self.test_user_id)

        # Name is ANON[timestamp], not a real name
        assert user['name'].startswith('ANON[')
        assert user.get('email') is None
        assert user.get('phone') is None
        assert user.get('company') is None


# ============================================
# Test Soft Login (Info Extraction)
# ============================================

class TestSoftLogin:
    """Tests for soft login - info extracted from conversation."""

    @pytest.fixture(autouse=True)
    def setup(self):
        init_db()
        self.test_user_id = str(uuid.uuid4())
        # Create anonymous user first
        get_or_create_user(self.test_user_id)
        yield

    def test_soft_login_name_extracted(self):
        """Name saved from conversation upgrades to soft login."""
        result = update_user(self.test_user_id, name="John Smith")

        assert result is not None
        assert result['name'] == "John Smith"

    def test_soft_login_email_extracted(self):
        """Email saved from conversation."""
        result = update_user(self.test_user_id, email="john@example.com")

        assert result is not None
        assert result['email'] == "john@example.com"

    def test_soft_login_phone_extracted(self):
        """Phone saved from conversation."""
        result = update_user(self.test_user_id, phone="5551234567")

        assert result is not None
        assert result['phone'] == "5551234567"

    def test_soft_login_company_extracted(self):
        """Company saved from conversation."""
        result = update_user(self.test_user_id, company="Acme Inc")

        assert result is not None
        assert result['company'] == "Acme Inc"

    def test_soft_login_preserves_user_id(self):
        """Same UUID after info extraction."""
        update_user(self.test_user_id, name="Jane Doe", email="jane@test.com")
        user = get_or_create_user(self.test_user_id)

        assert user['id'] == self.test_user_id
        assert user['name'] == "Jane Doe"


# ============================================
# Test Hard Login Registration
# ============================================

class TestHardLoginRegistration:
    """Tests for hard login registration (name + password)."""

    @pytest.fixture(autouse=True)
    def setup(self):
        init_db()
        self.client = TestClient(app)
        self.test_user_id = str(uuid.uuid4())
        self.test_name = f"testuser_{uuid.uuid4().hex[:8]}"
        self.test_password = "testpass123"
        yield

    def test_register_new_user(self):
        """Create account with name/password."""
        response = self.client.post("/auth/hard/register", json={
            "name": self.test_name,
            "password": self.test_password
        })

        assert response.status_code == 200
        data = response.json()
        assert data['success'] is True
        assert data['name'] == self.test_name
        assert data['auth_method'] == 'hard'

    def test_register_with_interest_level(self):
        """Registration includes optional interest level."""
        response = self.client.post("/auth/hard/register", json={
            "name": self.test_name,
            "password": self.test_password,
            "interest_level": "Gold"
        })

        assert response.status_code == 200
        data = response.json()
        assert data['interest_level'] == "Gold"

    def test_register_upgrade_anonymous_user(self):
        """Convert anonymous user to hard login."""
        # Create anonymous user first
        get_or_create_user(self.test_user_id)

        response = self.client.post("/auth/hard/register", json={
            "name": self.test_name,
            "password": self.test_password,
            "user_id": self.test_user_id
        })

        assert response.status_code == 200
        data = response.json()
        assert data['user_id'] == self.test_user_id

    def test_register_upgrade_soft_user(self):
        """Convert soft login user to hard login."""
        # Create soft login user (anonymous with extracted info)
        get_or_create_user(self.test_user_id)
        update_user(self.test_user_id, name="Soft User", email="soft@test.com")

        response = self.client.post("/auth/hard/register", json={
            "name": self.test_name,
            "password": self.test_password,
            "user_id": self.test_user_id
        })

        assert response.status_code == 200
        data = response.json()
        assert data['user_id'] == self.test_user_id

    def test_register_duplicate_name_rejected(self):
        """400 error for existing registered name."""
        # Register first user
        self.client.post("/auth/hard/register", json={
            "name": self.test_name,
            "password": self.test_password
        })

        # Try to register same name
        response = self.client.post("/auth/hard/register", json={
            "name": self.test_name,
            "password": "different_pass"
        })

        assert response.status_code == 400
        assert "already registered" in response.json()['detail'].lower()

    def test_register_returns_valid_token(self):
        """Registration returns valid JWT token."""
        response = self.client.post("/auth/hard/register", json={
            "name": self.test_name,
            "password": self.test_password
        })

        assert response.status_code == 200
        token = response.json()['token']
        payload = decode_auth_token(token)

        assert payload is not None
        assert 'user_id' in payload

    def test_register_password_hashed(self):
        """Password stored as bcrypt hash, not plaintext."""
        self.client.post("/auth/hard/register", json={
            "name": self.test_name,
            "password": self.test_password
        })

        session = get_session()
        user = session.query(User).filter(User.name == self.test_name).first()
        session.close()

        assert user is not None
        assert user.password_hash is not None
        assert user.password_hash != self.test_password
        assert user.password_hash.startswith('$2b$')  # bcrypt prefix


# ============================================
# Test Hard Login
# ============================================

class TestHardLogin:
    """Tests for hard login (authentication with credentials)."""

    @pytest.fixture(autouse=True)
    def setup(self):
        init_db()
        self.client = TestClient(app)
        self.test_name = f"testuser_{uuid.uuid4().hex[:8]}"
        self.test_password = "testpass123"

        # Register user for login tests
        self.client.post("/auth/hard/register", json={
            "name": self.test_name,
            "password": self.test_password
        })
        yield

    def test_login_success(self):
        """Valid credentials return token."""
        response = self.client.post("/auth/hard/login", json={
            "name": self.test_name,
            "password": self.test_password
        })

        assert response.status_code == 200
        data = response.json()
        assert data['success'] is True
        assert 'token' in data
        assert data['name'] == self.test_name

    def test_login_wrong_password(self):
        """401 for incorrect password."""
        response = self.client.post("/auth/hard/login", json={
            "name": self.test_name,
            "password": "wrong_password"
        })

        assert response.status_code == 401

    def test_login_nonexistent_user(self):
        """401 for unknown user."""
        response = self.client.post("/auth/hard/login", json={
            "name": "nonexistent_user_12345",
            "password": self.test_password
        })

        assert response.status_code == 401

    def test_login_updates_last_seen(self):
        """Timestamp updated on login."""
        # Get initial last_seen
        session = get_session()
        user_before = session.query(User).filter(User.name == self.test_name).first()
        last_seen_before = user_before.last_seen
        session.close()

        # Login
        self.client.post("/auth/hard/login", json={
            "name": self.test_name,
            "password": self.test_password
        })

        # Check last_seen updated
        session = get_session()
        user_after = session.query(User).filter(User.name == self.test_name).first()
        last_seen_after = user_after.last_seen
        session.close()

        assert last_seen_after >= last_seen_before


# ============================================
# Test Token Verification
# ============================================

class TestTokenVerification:
    """Tests for JWT token verification."""

    @pytest.fixture(autouse=True)
    def setup(self):
        init_db()
        self.client = TestClient(app)
        self.test_user_id = str(uuid.uuid4())
        get_or_create_user(self.test_user_id)
        self.valid_token = create_auth_token(self.test_user_id)
        yield

    def test_verify_valid_token(self):
        """Valid token returns user info."""
        response = self.client.post("/auth/verify", json={
            "token": self.valid_token
        })

        assert response.status_code == 200
        data = response.json()
        assert data['valid'] is True
        assert data['user_id'] == self.test_user_id

    def test_verify_invalid_token(self):
        """401 for malformed tokens."""
        response = self.client.post("/auth/verify", json={
            "token": "invalid.token.here"
        })

        assert response.status_code == 401

    def test_verify_tampered_token(self):
        """401 for tampered tokens."""
        # Modify the token payload
        tampered = self.valid_token[:-5] + "XXXXX"

        response = self.client.post("/auth/verify", json={
            "token": tampered
        })

        assert response.status_code == 401


# ============================================
# Test Logout
# ============================================

class TestLogout:
    """Tests for logout endpoint."""

    @pytest.fixture(autouse=True)
    def setup(self):
        init_db()
        self.client = TestClient(app)
        yield

    def test_logout_returns_success(self):
        """Logout returns success status."""
        response = self.client.post("/auth/logout")

        assert response.status_code == 200
        assert response.json()['status'] == 'logged_out'


# ============================================
# Test Auth Progression
# ============================================

class TestAuthProgression:
    """Tests for user progression through auth tiers."""

    @pytest.fixture(autouse=True)
    def setup(self):
        init_db()
        self.client = TestClient(app)
        self.test_user_id = str(uuid.uuid4())
        yield

    def test_anonymous_to_soft_to_hard(self):
        """Full user progression through all tiers."""
        # Start as anonymous
        user = get_or_create_user(self.test_user_id)
        assert user['name'].startswith('ANON[')

        # Check auth_method in database
        session = get_session()
        db_user = session.query(User).filter(User.id == self.test_user_id).first()
        assert db_user.auth_method == 'soft'
        session.close()

        # Upgrade to soft login (Maurice extracts info)
        update_user(self.test_user_id, name="John Doe", email="john@test.com")
        user = get_or_create_user(self.test_user_id)
        assert user['name'] == "John Doe"
        assert user['email'] == "john@test.com"

        # Upgrade to hard login (user registers)
        test_name = f"john_{uuid.uuid4().hex[:8]}"
        response = self.client.post("/auth/hard/register", json={
            "name": test_name,
            "password": "secure123",
            "user_id": self.test_user_id
        })
        assert response.status_code == 200
        data = response.json()
        assert data['auth_method'] == 'hard'
        assert data['user_id'] == self.test_user_id

    def test_user_id_preserved_through_upgrades(self):
        """Same UUID throughout all upgrades."""
        original_id = self.test_user_id

        # Anonymous
        user = get_or_create_user(original_id)
        assert user['id'] == original_id

        # Soft login
        update_user(original_id, name="Test User")
        user = get_or_create_user(original_id)
        assert user['id'] == original_id

        # Hard login
        test_name = f"preserved_{uuid.uuid4().hex[:8]}"
        response = self.client.post("/auth/hard/register", json={
            "name": test_name,
            "password": "test123",
            "user_id": original_id
        })
        assert response.json()['user_id'] == original_id


# ============================================
# Test Conversation Persistence Through Upgrades
# ============================================

class TestConversationPersistence:
    """Tests that conversations persist through auth upgrades."""

    @pytest.fixture(autouse=True)
    def setup(self):
        init_db()
        self.client = TestClient(app)
        self.test_user_id = str(uuid.uuid4())
        yield

    def test_conversations_persist_anonymous_to_soft(self):
        """Conversations saved as anonymous persist after soft login."""
        # Create anonymous user and save conversation
        get_or_create_user(self.test_user_id)
        messages = [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi there!"}
        ]
        conv_id = save_conversation(self.test_user_id, messages, summary="Test chat")
        assert conv_id is not None

        # Upgrade to soft login
        update_user(self.test_user_id, name="John Doe", email="john@test.com")

        # Verify conversation still accessible
        conversations = get_user_conversations(self.test_user_id)
        assert len(conversations) == 1
        assert conversations[0]['id'] == conv_id

    def test_conversations_persist_soft_to_hard(self):
        """Conversations saved as soft login persist after hard login."""
        # Create soft login user and save conversation
        get_or_create_user(self.test_user_id)
        update_user(self.test_user_id, name="Jane Doe")
        messages = [
            {"role": "user", "content": "I need help"},
            {"role": "assistant", "content": "How can I help?"}
        ]
        conv_id = save_conversation(self.test_user_id, messages, summary="Help request")
        assert conv_id is not None

        # Upgrade to hard login
        test_name = f"jane_{uuid.uuid4().hex[:8]}"
        self.client.post("/auth/hard/register", json={
            "name": test_name,
            "password": "secure123",
            "user_id": self.test_user_id
        })

        # Verify conversation still accessible
        conversations = get_user_conversations(self.test_user_id)
        assert len(conversations) == 1
        assert conversations[0]['id'] == conv_id

    def test_multiple_conversations_persist_through_all_upgrades(self):
        """Multiple conversations from different stages all persist."""
        # Stage 1: Anonymous - save first conversation
        get_or_create_user(self.test_user_id)
        conv1_id = save_conversation(
            self.test_user_id,
            [{"role": "user", "content": "First chat"}],
            summary="Anonymous conversation"
        )

        # Stage 2: Soft login - save second conversation
        update_user(self.test_user_id, name="Test User")
        conv2_id = save_conversation(
            self.test_user_id,
            [{"role": "user", "content": "Second chat"}],
            summary="Soft login conversation"
        )

        # Stage 3: Hard login - save third conversation
        test_name = f"test_{uuid.uuid4().hex[:8]}"
        self.client.post("/auth/hard/register", json={
            "name": test_name,
            "password": "pass123",
            "user_id": self.test_user_id
        })
        conv3_id = save_conversation(
            self.test_user_id,
            [{"role": "user", "content": "Third chat"}],
            summary="Hard login conversation"
        )

        # Verify ALL conversations accessible
        conversations = get_user_conversations(self.test_user_id)
        assert len(conversations) == 3

        conv_ids = [c['id'] for c in conversations]
        assert conv1_id in conv_ids
        assert conv2_id in conv_ids
        assert conv3_id in conv_ids

    def test_user_id_unchanged_through_full_conversion(self):
        """User ID remains constant through anonymous → soft → hard."""
        original_id = self.test_user_id

        # Anonymous
        user = get_or_create_user(original_id)
        assert user['id'] == original_id

        # Save conversation as anonymous
        save_conversation(original_id, [{"role": "user", "content": "Hi"}])

        # Soft login
        update_user(original_id, name="Full Test", email="full@test.com")

        # Verify ID unchanged
        session = get_session()
        db_user = session.query(User).filter(User.id == original_id).first()
        assert db_user.id == original_id
        assert db_user.name == "Full Test"
        session.close()

        # Hard login
        test_name = f"full_{uuid.uuid4().hex[:8]}"
        response = self.client.post("/auth/hard/register", json={
            "name": test_name,
            "password": "test123",
            "user_id": original_id
        })
        assert response.json()['user_id'] == original_id

        # Verify ID still unchanged and conversations accessible
        conversations = get_user_conversations(original_id)
        assert len(conversations) == 1
