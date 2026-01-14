"""
Database models and functions for Maurice memory system.
Uses PostgreSQL in production (Railway), SQLite for local development.
"""
import os
import json
import bcrypt
from datetime import datetime
from typing import Optional
from pathlib import Path
from sqlalchemy import create_engine, Column, String, Integer, Text, DateTime, ForeignKey, Float
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship

# Use DATABASE_URL from environment (Railway PostgreSQL) or fall back to SQLite
DATABASE_URL = os.getenv("DATABASE_URL")
if DATABASE_URL and DATABASE_URL.startswith("postgres://"):
    # Railway uses postgres:// but SQLAlchemy needs postgresql://
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)
elif not DATABASE_URL:
    # Local SQLite fallback
    DATABASE_PATH = Path(__file__).parent / "maurice.db"
    DATABASE_URL = f"sqlite:///{DATABASE_PATH}"

# SQLAlchemy setup
Base = declarative_base()
engine = None
SessionLocal = None


class User(Base):
    """User model for tracking visitors."""
    __tablename__ = "users"

    id = Column(String(36), primary_key=True)  # UUID as string
    name = Column(String(255), nullable=True)
    email = Column(String(255), nullable=True)
    phone = Column(String(50), nullable=True)
    company = Column(String(255), nullable=True)
    status = Column(String(20), default="new")  # new, contacted, qualified, converted, archived
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    last_seen = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Google OAuth fields
    google_id = Column(String(255), nullable=True, unique=True, index=True)
    google_email = Column(String(255), nullable=True)
    google_name = Column(String(255), nullable=True)
    google_picture = Column(String(500), nullable=True)
    auth_method = Column(String(20), default="soft")  # "soft", "medium", or "google"

    # Medium login fields
    password_hash = Column(String(255), nullable=True)
    interest_level = Column(String(20), nullable=True)  # Gold, Silver, Bronze

    conversations = relationship("Conversation", back_populates="user")
    facts = relationship("UserFact", back_populates="user", cascade="all, delete-orphan")


class Conversation(Base):
    """Conversation model for storing chat history."""
    __tablename__ = "conversations"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String(36), ForeignKey("users.id"))
    summary = Column(Text, nullable=True)
    interests = Column(Text, nullable=True)  # JSON array as string
    lead_score = Column(Integer, default=1)
    messages = Column(Text, nullable=True)  # JSON as string
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="conversations")


class UserFact(Base):
    """Semantic facts extracted from user conversations."""
    __tablename__ = "user_facts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    fact_type = Column(String(50), nullable=False, index=True)  # role, budget, pain_point, etc.
    fact_value = Column(String(500), nullable=False)
    confidence = Column(Float, default=1.0)  # 0.0-1.0 confidence score
    source_conversation_id = Column(Integer, ForeignKey("conversations.id"), nullable=True)
    source_text = Column(Text, nullable=True)  # The original text that triggered extraction
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    user = relationship("User", back_populates="facts")


def init_db():
    """Initialize database connection and create tables."""
    global engine, SessionLocal

    try:
        engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
        SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

        # Create tables if they don't exist
        Base.metadata.create_all(bind=engine)
        print(f"SQLite database ready: {DATABASE_PATH}")
        return True
    except Exception as e:
        print(f"Database connection failed: {e}")
        return False


def get_session():
    """Get a database session."""
    if SessionLocal is None:
        return None
    return SessionLocal()


def get_or_create_user(user_id: str) -> Optional[dict]:
    """Get user by ID or create if new. Returns user dict."""
    session = get_session()
    if session is None:
        return None

    try:
        user = session.query(User).filter(User.id == user_id).first()

        if user is None:
            # Create new anonymous user with timestamp
            timestamp = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
            user = User(id=user_id, name=f"ANON[{timestamp}]")
            session.add(user)
            session.commit()
            session.refresh(user)
        else:
            # Update last_seen
            user.last_seen = datetime.utcnow()
            session.commit()

        return {
            "id": user.id,
            "name": user.name,
            "email": user.email,
            "phone": user.phone,
            "company": user.company,
            "status": user.status or "new",
            "notes": user.notes,
            "created_at": user.created_at.isoformat() if user.created_at else None,
            "last_seen": user.last_seen.isoformat() if user.last_seen else None
        }
    except Exception as e:
        print(f"Error getting/creating user: {e}")
        session.rollback()
        return None
    finally:
        session.close()


def update_user(user_id: str, name: str = None, email: str = None, phone: str = None, company: str = None) -> Optional[dict]:
    """Update user information."""
    session = get_session()
    if session is None:
        return None

    try:
        user = session.query(User).filter(User.id == user_id).first()

        if user is None:
            return None

        if name is not None:
            user.name = name
        if email is not None:
            user.email = email
        if phone is not None:
            user.phone = phone
        if company is not None:
            user.company = company

        user.last_seen = datetime.utcnow()
        session.commit()

        return {
            "id": user.id,
            "name": user.name,
            "email": user.email,
            "phone": user.phone,
            "company": user.company
        }
    except Exception as e:
        print(f"Error updating user: {e}")
        session.rollback()
        return None
    finally:
        session.close()


def save_conversation(user_id: str, messages: list, summary: str = None,
                      interests: list = None, lead_score: int = 1) -> Optional[int]:
    """Save a conversation. Returns conversation ID."""
    session = get_session()
    if session is None:
        return None

    try:
        # Convert lists to JSON strings for SQLite
        interests_json = json.dumps(interests) if interests else None
        messages_json = json.dumps(messages) if messages else None

        conversation = Conversation(
            user_id=user_id,
            messages=messages_json,
            summary=summary,
            interests=interests_json,
            lead_score=lead_score
        )
        session.add(conversation)
        session.commit()

        return conversation.id
    except Exception as e:
        print(f"Error saving conversation: {e}")
        session.rollback()
        return None
    finally:
        session.close()


def update_conversation(conversation_id: int, messages: list, summary: str = None,
                        interests: list = None, lead_score: int = None) -> bool:
    """Update an existing conversation. Returns True on success."""
    session = get_session()
    if session is None:
        return False

    try:
        conversation = session.query(Conversation).filter(Conversation.id == conversation_id).first()
        if conversation is None:
            return False

        # Update fields
        if messages is not None:
            conversation.messages = json.dumps(messages)
        if summary is not None:
            conversation.summary = summary
        if interests is not None:
            conversation.interests = json.dumps(interests)
        if lead_score is not None:
            conversation.lead_score = lead_score

        session.commit()
        return True
    except Exception as e:
        print(f"Error updating conversation: {e}")
        session.rollback()
        return False
    finally:
        session.close()


def get_user_context(user_id: str) -> Optional[dict]:
    """Get user info and last conversation summary for prompt injection."""
    session = get_session()
    if session is None:
        return None

    try:
        user = session.query(User).filter(User.id == user_id).first()

        if user is None:
            return None

        # Get the most recent conversation
        last_conversation = (
            session.query(Conversation)
            .filter(Conversation.user_id == user_id)
            .order_by(Conversation.created_at.desc())
            .first()
        )

        # Parse JSON strings back to lists
        last_interests = None
        if last_conversation and last_conversation.interests:
            try:
                last_interests = json.loads(last_conversation.interests)
            except:
                last_interests = None

        # Get semantic facts for this user
        user_facts = session.query(UserFact).filter(
            UserFact.user_id == user_id,
            UserFact.confidence >= 0.6
        ).order_by(UserFact.confidence.desc()).all()

        # Build facts dict (highest confidence for each type)
        facts_dict = {}
        for f in user_facts:
            if f.fact_type not in facts_dict:
                facts_dict[f.fact_type] = f.fact_value

        context = {
            "user_id": user.id,
            "name": user.name,
            "email": user.email,
            "phone": user.phone,
            "company": user.company,
            "auth_method": user.auth_method or "soft",
            "is_returning": last_conversation is not None,
            "last_summary": last_conversation.summary if last_conversation else None,
            "last_interests": last_interests,
            "conversation_count": session.query(Conversation).filter(Conversation.user_id == user_id).count(),
            "facts": facts_dict
        }

        return context
    except Exception as e:
        print(f"Error getting user context: {e}")
        return None
    finally:
        session.close()


def get_leads(limit: int = 50) -> list:
    """Get leads sorted by score and recency for admin dashboard."""
    session = get_session()
    if session is None:
        return []

    try:
        # Get all users, ordered by last_seen
        users = (
            session.query(User)
            .order_by(User.last_seen.desc())
            .limit(limit)
            .all()
        )

        leads = []
        for user in users:
            # Get the best conversation for this user (highest lead score)
            best_conv = (
                session.query(Conversation)
                .filter(Conversation.user_id == user.id)
                .order_by(Conversation.lead_score.desc(), Conversation.created_at.desc())
                .first()
            )

            # Parse interests JSON
            interests = []
            if best_conv and best_conv.interests:
                try:
                    interests = json.loads(best_conv.interests)
                except:
                    interests = []

            leads.append({
                "id": user.id,
                "name": user.name or "Anonymous",
                "email": user.email,
                "company": user.company,
                "status": user.status or "new",
                "notes": user.notes,
                "lead_score": best_conv.lead_score if best_conv else 1,
                "last_summary": best_conv.summary if best_conv else None,
                "interests": interests,
                "last_seen": user.last_seen.isoformat() if user.last_seen else None
            })

        # Sort by lead score descending, then last_seen
        leads.sort(key=lambda x: (-x["lead_score"], x["last_seen"] or ""), reverse=False)

        return leads
    except Exception as e:
        print(f"Error getting leads: {e}")
        import traceback
        traceback.print_exc()
        return []
    finally:
        session.close()


def lookup_users_by_name(name: str) -> list:
    """Find users by name for verification. Returns list with last conversation topic."""
    session = get_session()
    if session is None:
        return []

    try:
        # Case-insensitive name search (SQLite uses LIKE for this)
        users = (
            session.query(User)
            .filter(User.name.ilike(f"%{name}%"))
            .order_by(User.last_seen.desc())
            .limit(5)
            .all()
        )

        results = []
        for user in users:
            # Get last conversation for context
            last_conv = (
                session.query(Conversation)
                .filter(Conversation.user_id == user.id)
                .order_by(Conversation.created_at.desc())
                .first()
            )

            # Parse interests JSON
            last_interests = []
            if last_conv and last_conv.interests:
                try:
                    last_interests = json.loads(last_conv.interests)
                except:
                    last_interests = []

            results.append({
                "user_id": user.id,
                "name": user.name,
                "last_topic": last_conv.summary if last_conv else None,
                "last_interests": last_interests,
                "last_seen": user.last_seen.isoformat() if user.last_seen else None
            })

        return results
    except Exception as e:
        print(f"Error looking up users by name: {e}")
        return []
    finally:
        session.close()


def link_users(current_user_id: str, target_user_id: str) -> bool:
    """
    Link current session to an existing user.
    Moves conversations from current user to target user, then deletes current user.
    """
    session = get_session()
    if session is None:
        return False

    try:
        # Don't link to self
        if current_user_id == target_user_id:
            return True

        # Get both users
        current_user = session.query(User).filter(User.id == current_user_id).first()
        target_user = session.query(User).filter(User.id == target_user_id).first()

        if not current_user or not target_user:
            return False

        # Move all conversations from current to target
        session.query(Conversation).filter(
            Conversation.user_id == current_user_id
        ).update({"user_id": target_user_id})

        # Update target user's last_seen
        target_user.last_seen = datetime.utcnow()

        # Delete the current (anonymous) user record
        session.delete(current_user)

        session.commit()
        return True
    except Exception as e:
        print(f"Error linking users: {e}")
        session.rollback()
        return False
    finally:
        session.close()


def get_user_conversations(user_id: str) -> list:
    """Get all conversations for a user with full message history."""
    session = get_session()
    if session is None:
        return []

    try:
        conversations = (
            session.query(Conversation)
            .filter(Conversation.user_id == user_id)
            .order_by(Conversation.created_at.desc())
            .all()
        )

        results = []
        for conv in conversations:
            # Parse JSON strings
            messages = []
            if conv.messages:
                try:
                    messages = json.loads(conv.messages)
                except:
                    messages = []

            interests = []
            if conv.interests:
                try:
                    interests = json.loads(conv.interests)
                except:
                    interests = []

            results.append({
                "id": conv.id,
                "summary": conv.summary,
                "interests": interests,
                "lead_score": conv.lead_score,
                "messages": messages,
                "created_at": conv.created_at.isoformat() if conv.created_at else None
            })

        return results
    except Exception as e:
        print(f"Error getting user conversations: {e}")
        return []
    finally:
        session.close()


def get_all_exchanges(page: int = 1, per_page: int = 50) -> dict:
    """Get all Q&A exchanges with pagination.

    Parses messages JSON from all conversations and extracts
    individual user question + assistant response pairs.
    """
    session = get_session()
    if session is None:
        return {'exchanges': [], 'total': 0, 'page': page, 'per_page': per_page, 'total_pages': 0}

    try:
        # Get all conversations with user info
        conversations = (
            session.query(Conversation, User.name)
            .join(User, Conversation.user_id == User.id)
            .order_by(Conversation.created_at.desc())
            .all()
        )

        # Extract all Q&A pairs from all conversations
        all_exchanges = []
        for conv, user_name in conversations:
            if not conv.messages:
                continue

            try:
                messages = json.loads(conv.messages)
            except:
                continue

            # Extract user/assistant pairs
            i = 0
            while i < len(messages):
                if messages[i].get('role') == 'user':
                    question = messages[i].get('content', '')
                    answer = ''
                    # Look for the next assistant message
                    if i + 1 < len(messages) and messages[i + 1].get('role') == 'assistant':
                        answer = messages[i + 1].get('content', '')
                        i += 2
                    else:
                        i += 1

                    all_exchanges.append({
                        'user_name': user_name or 'Unknown',
                        'user_id': conv.user_id,
                        'question': question,
                        'answer': answer,
                        'timestamp': conv.created_at.isoformat() if conv.created_at else None,
                        'conversation_id': conv.id
                    })
                else:
                    i += 1

        # Calculate pagination
        total = len(all_exchanges)
        total_pages = (total + per_page - 1) // per_page if total > 0 else 0
        start = (page - 1) * per_page
        end = start + per_page
        paginated = all_exchanges[start:end]

        return {
            'exchanges': paginated,
            'total': total,
            'page': page,
            'per_page': per_page,
            'total_pages': total_pages
        }
    except Exception as e:
        print(f"Error getting exchanges: {e}")
        return {'exchanges': [], 'total': 0, 'page': page, 'per_page': per_page, 'total_pages': 0}
    finally:
        session.close()


def update_lead_status(user_id: str, status: str) -> bool:
    """Update a user's lead status."""
    valid_statuses = ["new", "contacted", "qualified", "converted", "archived"]
    if status not in valid_statuses:
        return False

    session = get_session()
    if session is None:
        return False

    try:
        user = session.query(User).filter(User.id == user_id).first()
        if user is None:
            return False

        user.status = status
        session.commit()
        return True
    except Exception as e:
        print(f"Error updating lead status: {e}")
        session.rollback()
        return False
    finally:
        session.close()


def update_lead_notes(user_id: str, notes: str) -> bool:
    """Update a user's notes."""
    session = get_session()
    if session is None:
        return False

    try:
        user = session.query(User).filter(User.id == user_id).first()
        if user is None:
            return False

        user.notes = notes
        session.commit()
        return True
    except Exception as e:
        print(f"Error updating lead notes: {e}")
        session.rollback()
        return False
    finally:
        session.close()


def get_lead_details(user_id: str) -> Optional[dict]:
    """Get full lead details including all conversations."""
    session = get_session()
    if session is None:
        return None

    try:
        user = session.query(User).filter(User.id == user_id).first()
        if user is None:
            return None

        conversations = get_user_conversations(user_id)

        return {
            "id": user.id,
            "name": user.name or "Anonymous",
            "email": user.email,
            "company": user.company,
            "status": user.status or "new",
            "notes": user.notes,
            "created_at": user.created_at.isoformat() if user.created_at else None,
            "last_seen": user.last_seen.isoformat() if user.last_seen else None,
            "conversations": conversations
        }
    except Exception as e:
        print(f"Error getting lead details: {e}")
        return None
    finally:
        session.close()


def delete_user(user_id: str) -> bool:
    """Delete a user and all their conversations."""
    session = get_session()
    if session is None:
        return False

    try:
        user = session.query(User).filter(User.id == user_id).first()
        if user is None:
            return False

        # Delete all conversations first (foreign key constraint)
        session.query(Conversation).filter(Conversation.user_id == user_id).delete()

        # Delete the user
        session.delete(user)
        session.commit()
        return True
    except Exception as e:
        print(f"Error deleting user: {e}")
        session.rollback()
        return False
    finally:
        session.close()


def get_analytics() -> dict:
    """Get analytics data for the admin dashboard."""
    session = get_session()
    if session is None:
        return {}

    try:
        from datetime import timedelta

        # Total leads
        total_leads = session.query(User).count()

        # Leads by status
        status_counts = {}
        for status in ["new", "contacted", "qualified", "converted", "archived"]:
            count = session.query(User).filter(User.status == status).count()
            status_counts[status] = count

        # Count users with no status as "new"
        null_status_count = session.query(User).filter(User.status == None).count()
        status_counts["new"] = status_counts.get("new", 0) + null_status_count

        # Average lead score
        conversations = session.query(Conversation).all()
        if conversations:
            scores = [c.lead_score for c in conversations if c.lead_score]
            avg_score = sum(scores) / len(scores) if scores else 0
        else:
            avg_score = 0

        # Leads this week
        week_ago = datetime.utcnow() - timedelta(days=7)
        leads_this_week = session.query(User).filter(User.created_at >= week_ago).count()

        return {
            "total_leads": total_leads,
            "status_counts": status_counts,
            "avg_score": round(avg_score, 1),
            "leads_this_week": leads_this_week
        }
    except Exception as e:
        print(f"Error getting analytics: {e}")
        return {}
    finally:
        session.close()


def get_user_dashboard(user_id: str) -> Optional[dict]:
    """Get comprehensive dashboard data for a user."""
    session = get_session()
    if session is None:
        return None

    try:
        user = session.query(User).filter(User.id == user_id).first()
        if user is None:
            return None

        # Get all conversations for this user
        conversations = (
            session.query(Conversation)
            .filter(Conversation.user_id == user_id)
            .order_by(Conversation.created_at.desc())
            .all()
        )

        # Build conversation history
        conversation_history = []
        all_interests = set()
        for conv in conversations:
            # Parse interests from JSON string
            interests = []
            if conv.interests:
                try:
                    interests = json.loads(conv.interests)
                    for interest in interests:
                        all_interests.add(interest)
                except:
                    pass

            conversation_history.append({
                "id": conv.id,
                "date": conv.created_at.isoformat() if conv.created_at else None,
                "summary": conv.summary,
                "lead_score": conv.lead_score,
                "interests": interests
            })

        return {
            "profile": {
                "id": str(user.id),
                "name": user.name,
                "email": user.email,
                "phone": user.phone,
                "company": user.company,
                "auth_method": user.auth_method,
                "google_picture": user.google_picture
            },
            "activity": {
                "conversation_count": len(conversations),
                "member_since": user.created_at.isoformat() if user.created_at else None,
                "last_active": user.last_seen.isoformat() if user.last_seen else None
            },
            "conversations": conversation_history,
            "interests": list(all_interests)
        }
    except Exception as e:
        print(f"Error getting user dashboard: {e}")
        import traceback
        traceback.print_exc()
        return None
    finally:
        session.close()


# ============================================
# Medium Login Functions
# ============================================

def get_user_by_name(name: str) -> Optional[dict]:
    """Find user by exact name match (for medium login)."""
    session = get_session()
    if session is None:
        return None

    try:
        user = session.query(User).filter(User.name == name).first()

        if user is None:
            return None

        return {
            "id": str(user.id),
            "name": user.name,
            "email": user.email,
            "auth_method": user.auth_method,
            "password_hash": user.password_hash,
            "interest_level": user.interest_level
        }
    except Exception as e:
        print(f"Error getting user by name: {e}")
        return None
    finally:
        session.close()


def create_hard_user(user_id: str, name: str, password: str, interest_level: str = None) -> Optional[dict]:
    """Create or upgrade a user with hard login (password-based)."""
    session = get_session()
    if session is None:
        return None

    try:
        # Hash the password
        password_hash = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

        # Check if user already exists (e.g., anonymous user)
        user = session.query(User).filter(User.id == user_id).first()

        if user:
            # Upgrade existing user to hard auth
            user.name = name
            user.password_hash = password_hash
            user.interest_level = interest_level
            user.auth_method = "hard"
            user.last_seen = datetime.utcnow()
        else:
            # Create new user
            user = User(
                id=user_id,
                name=name,
                password_hash=password_hash,
                interest_level=interest_level,
                auth_method="hard"
            )
            session.add(user)

        session.commit()
        session.refresh(user)

        return {
            "id": str(user.id),
            "name": user.name,
            "interest_level": user.interest_level,
            "auth_method": user.auth_method
        }
    except Exception as e:
        print(f"Error creating hard user: {e}")
        session.rollback()
        return None
    finally:
        session.close()


def verify_hard_login(name: str, password: str) -> Optional[dict]:
    """Verify hard login credentials. Returns user dict if valid."""
    session = get_session()
    if session is None:
        return None

    try:
        user = session.query(User).filter(User.name == name).first()

        if user is None or user.password_hash is None:
            return None

        # Verify password
        if bcrypt.checkpw(password.encode('utf-8'), user.password_hash.encode('utf-8')):
            # Update last_seen
            user.last_seen = datetime.utcnow()
            session.commit()

            return {
                "id": str(user.id),
                "name": user.name,
                "email": user.email,
                "interest_level": user.interest_level,
                "auth_method": user.auth_method
            }
        return None
    except Exception as e:
        print(f"Error verifying hard login: {e}")
        return None
    finally:
        session.close()


# ============================================
# Semantic Facts Functions
# ============================================

def save_user_fact(user_id: str, fact_type: str, fact_value: str,
                   confidence: float = 1.0, conversation_id: int = None,
                   source_text: str = None) -> Optional[int]:
    """Save a semantic fact about a user. Returns fact ID."""
    session = get_session()
    if session is None:
        return None

    try:
        # Check if this fact type already exists for this user
        existing = session.query(UserFact).filter(
            UserFact.user_id == user_id,
            UserFact.fact_type == fact_type
        ).first()

        if existing:
            # Update if new value has higher confidence or is different
            if confidence >= existing.confidence or fact_value != existing.fact_value:
                existing.fact_value = fact_value
                existing.confidence = max(confidence, existing.confidence)
                existing.source_conversation_id = conversation_id
                existing.source_text = source_text
                existing.updated_at = datetime.utcnow()
                session.commit()
                return existing.id
            return existing.id

        # Create new fact
        fact = UserFact(
            user_id=user_id,
            fact_type=fact_type,
            fact_value=fact_value,
            confidence=confidence,
            source_conversation_id=conversation_id,
            source_text=source_text
        )
        session.add(fact)
        session.commit()
        return fact.id
    except Exception as e:
        print(f"Error saving user fact: {e}")
        session.rollback()
        return None
    finally:
        session.close()


def save_user_facts(user_id: str, facts: list, conversation_id: int = None) -> int:
    """Save multiple facts for a user. Returns count of facts saved."""
    saved_count = 0
    for fact in facts:
        fact_type = fact.get("type")
        fact_value = fact.get("value")
        confidence = fact.get("confidence", 1.0)
        source_text = fact.get("source_text")

        if fact_type and fact_value:
            result = save_user_fact(
                user_id=user_id,
                fact_type=fact_type,
                fact_value=fact_value,
                confidence=confidence,
                conversation_id=conversation_id,
                source_text=source_text
            )
            if result:
                saved_count += 1
    return saved_count


def get_user_facts(user_id: str, min_confidence: float = 0.5) -> list:
    """Get all facts for a user above confidence threshold."""
    session = get_session()
    if session is None:
        return []

    try:
        facts = session.query(UserFact).filter(
            UserFact.user_id == user_id,
            UserFact.confidence >= min_confidence
        ).order_by(UserFact.fact_type, UserFact.confidence.desc()).all()

        return [
            {
                "id": f.id,
                "type": f.fact_type,
                "value": f.fact_value,
                "confidence": f.confidence,
                "created_at": f.created_at.isoformat() if f.created_at else None,
                "updated_at": f.updated_at.isoformat() if f.updated_at else None
            }
            for f in facts
        ]
    except Exception as e:
        print(f"Error getting user facts: {e}")
        return []
    finally:
        session.close()


def get_user_facts_dict(user_id: str, min_confidence: float = 0.6) -> dict:
    """Get facts as a dict (fact_type -> fact_value) for context injection."""
    session = get_session()
    if session is None:
        return {}

    try:
        facts = session.query(UserFact).filter(
            UserFact.user_id == user_id,
            UserFact.confidence >= min_confidence
        ).order_by(UserFact.confidence.desc()).all()

        # Return dict with highest confidence fact for each type
        facts_dict = {}
        for f in facts:
            if f.fact_type not in facts_dict:
                facts_dict[f.fact_type] = f.fact_value
        return facts_dict
    except Exception as e:
        print(f"Error getting user facts dict: {e}")
        return {}
    finally:
        session.close()


def delete_user_fact(fact_id: int) -> bool:
    """Delete a specific fact."""
    session = get_session()
    if session is None:
        return False

    try:
        fact = session.query(UserFact).filter(UserFact.id == fact_id).first()
        if fact:
            session.delete(fact)
            session.commit()
            return True
        return False
    except Exception as e:
        print(f"Error deleting user fact: {e}")
        session.rollback()
        return False
    finally:
        session.close()
