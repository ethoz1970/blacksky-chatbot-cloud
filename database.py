"""
Database models and functions for Maurice memory system.
Uses PostgreSQL via SQLAlchemy.
"""
import os
from datetime import datetime
from typing import Optional
from sqlalchemy import create_engine, Column, String, Integer, Text, DateTime, ARRAY, ForeignKey
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
import uuid

# Database URL from environment
DATABASE_URL = os.getenv("DATABASE_URL")

# SQLAlchemy setup
Base = declarative_base()
engine = None
SessionLocal = None


class User(Base):
    """User model for tracking visitors."""
    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(255), nullable=True)
    email = Column(String(255), nullable=True)
    company = Column(String(255), nullable=True)
    status = Column(String(20), default="new")  # new, contacted, qualified, converted, archived
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    last_seen = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    conversations = relationship("Conversation", back_populates="user")


class Conversation(Base):
    """Conversation model for storing chat history."""
    __tablename__ = "conversations"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"))
    summary = Column(Text, nullable=True)
    interests = Column(ARRAY(String), nullable=True)
    lead_score = Column(Integer, default=1)
    messages = Column(JSONB, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="conversations")


def init_db():
    """Initialize database connection and create tables."""
    global engine, SessionLocal

    if not DATABASE_URL:
        print("Warning: DATABASE_URL not set. Memory features disabled.")
        return False

    try:
        # Handle Railway's postgres:// vs postgresql:// URL format
        db_url = DATABASE_URL
        if db_url.startswith("postgres://"):
            db_url = db_url.replace("postgres://", "postgresql://", 1)

        engine = create_engine(db_url)
        SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

        # Create tables if they don't exist
        Base.metadata.create_all(bind=engine)
        print("Database connected and tables created.")
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
        user_uuid = uuid.UUID(user_id)
        user = session.query(User).filter(User.id == user_uuid).first()

        if user is None:
            # Create new user
            user = User(id=user_uuid)
            session.add(user)
            session.commit()
            session.refresh(user)
        else:
            # Update last_seen
            user.last_seen = datetime.utcnow()
            session.commit()

        return {
            "id": str(user.id),
            "name": user.name,
            "email": user.email,
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


def update_user(user_id: str, name: str = None, email: str = None, company: str = None) -> Optional[dict]:
    """Update user information."""
    session = get_session()
    if session is None:
        return None

    try:
        user_uuid = uuid.UUID(user_id)
        user = session.query(User).filter(User.id == user_uuid).first()

        if user is None:
            return None

        if name is not None:
            user.name = name
        if email is not None:
            user.email = email
        if company is not None:
            user.company = company

        user.last_seen = datetime.utcnow()
        session.commit()

        return {
            "id": str(user.id),
            "name": user.name,
            "email": user.email,
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
        user_uuid = uuid.UUID(user_id)

        conversation = Conversation(
            user_id=user_uuid,
            messages=messages,
            summary=summary,
            interests=interests,
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


def get_user_context(user_id: str) -> Optional[dict]:
    """Get user info and last conversation summary for prompt injection."""
    session = get_session()
    if session is None:
        return None

    try:
        user_uuid = uuid.UUID(user_id)
        user = session.query(User).filter(User.id == user_uuid).first()

        if user is None:
            return None

        # Get the most recent conversation
        last_conversation = (
            session.query(Conversation)
            .filter(Conversation.user_id == user_uuid)
            .order_by(Conversation.created_at.desc())
            .first()
        )

        context = {
            "user_id": str(user.id),
            "name": user.name,
            "email": user.email,
            "company": user.company,
            "is_returning": last_conversation is not None,
            "last_summary": last_conversation.summary if last_conversation else None,
            "last_interests": last_conversation.interests if last_conversation else None,
            "conversation_count": session.query(Conversation).filter(Conversation.user_id == user_uuid).count()
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

            leads.append({
                "id": str(user.id),
                "name": user.name or "Anonymous",
                "email": user.email,
                "company": user.company,
                "status": user.status or "new",
                "notes": user.notes,
                "lead_score": best_conv.lead_score if best_conv else 1,
                "last_summary": best_conv.summary if best_conv else None,
                "interests": best_conv.interests if best_conv else [],
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
        # Case-insensitive name search
        users = (
            session.query(User)
            .filter(User.name.ilike(name))
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

            results.append({
                "user_id": str(user.id),
                "name": user.name,
                "last_topic": last_conv.summary if last_conv else None,
                "last_interests": last_conv.interests if last_conv else [],
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
        current_uuid = uuid.UUID(current_user_id)
        target_uuid = uuid.UUID(target_user_id)

        # Don't link to self
        if current_uuid == target_uuid:
            return True

        # Get both users
        current_user = session.query(User).filter(User.id == current_uuid).first()
        target_user = session.query(User).filter(User.id == target_uuid).first()

        if not current_user or not target_user:
            return False

        # Move all conversations from current to target
        session.query(Conversation).filter(
            Conversation.user_id == current_uuid
        ).update({"user_id": target_uuid})

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
        user_uuid = uuid.UUID(user_id)
        conversations = (
            session.query(Conversation)
            .filter(Conversation.user_id == user_uuid)
            .order_by(Conversation.created_at.desc())
            .all()
        )

        results = []
        for conv in conversations:
            results.append({
                "id": conv.id,
                "summary": conv.summary,
                "interests": conv.interests or [],
                "lead_score": conv.lead_score,
                "messages": conv.messages or [],
                "created_at": conv.created_at.isoformat() if conv.created_at else None
            })

        return results
    except Exception as e:
        print(f"Error getting user conversations: {e}")
        return []
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
        user_uuid = uuid.UUID(user_id)
        user = session.query(User).filter(User.id == user_uuid).first()
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
        user_uuid = uuid.UUID(user_id)
        user = session.query(User).filter(User.id == user_uuid).first()
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
        user_uuid = uuid.UUID(user_id)
        user = session.query(User).filter(User.id == user_uuid).first()
        if user is None:
            return None

        conversations = get_user_conversations(user_id)

        return {
            "id": str(user.id),
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
        user_uuid = uuid.UUID(user_id)
        user = session.query(User).filter(User.id == user_uuid).first()
        if user is None:
            return False

        # Delete all conversations first (foreign key constraint)
        session.query(Conversation).filter(Conversation.user_id == user_uuid).delete()

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
