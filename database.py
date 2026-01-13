"""
Database models and functions for Maurice memory system.
Cloud version using PostgreSQL via Railway.
"""
import os
import json
from datetime import datetime
from typing import Optional
from sqlalchemy import create_engine, Column, String, Integer, Text, DateTime, ForeignKey, JSON, text, Boolean, Index
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship

# PostgreSQL database from Railway environment
DATABASE_URL = os.getenv("DATABASE_URL")

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
    auth_method = Column(String(20), default="soft")  # "soft" or "google"

    conversations = relationship("Conversation", back_populates="user")


class Conversation(Base):
    """Conversation model for storing chat history."""
    __tablename__ = "conversations"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String(36), ForeignKey("users.id"))
    summary = Column(Text, nullable=True)
    interests = Column(JSON, nullable=True)  # JSON array stored as JSONB in PostgreSQL
    lead_score = Column(Integer, default=1)
    messages = Column(JSON, nullable=True)  # JSON stored as JSONB in PostgreSQL
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="conversations")


def init_db():
    """Initialize database connection and create tables."""
    global engine, SessionLocal

    if not DATABASE_URL:
        print("DATABASE_URL not set - database disabled")
        return False

    try:
        engine = create_engine(DATABASE_URL)
        SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

        # Create tables if they don't exist
        Base.metadata.create_all(bind=engine)

        # Migrate columns to JSONB if needed (one-time migration)
        with engine.connect() as conn:
            try:
                # Convert interests and messages columns to JSONB from any type
                conn.execute(text("""
                    DO $$
                    BEGIN
                        -- Convert interests to JSONB if not already
                        IF EXISTS (
                            SELECT 1 FROM information_schema.columns
                            WHERE table_name = 'conversations' AND column_name = 'interests'
                            AND data_type != 'jsonb'
                        ) THEN
                            -- Drop and recreate the column as JSONB
                            ALTER TABLE conversations DROP COLUMN IF EXISTS interests;
                            ALTER TABLE conversations ADD COLUMN interests JSONB;
                            RAISE NOTICE 'Recreated interests column as JSONB';
                        END IF;

                        -- Convert messages to JSONB if not already
                        IF EXISTS (
                            SELECT 1 FROM information_schema.columns
                            WHERE table_name = 'conversations' AND column_name = 'messages'
                            AND data_type != 'jsonb'
                        ) THEN
                            -- Drop and recreate the column as JSONB
                            ALTER TABLE conversations DROP COLUMN IF EXISTS messages;
                            ALTER TABLE conversations ADD COLUMN messages JSONB;
                            RAISE NOTICE 'Recreated messages column as JSONB';
                        END IF;
                    END $$;
                """))
                conn.commit()
                print("Database migrations complete.")
            except Exception as e:
                print(f"Migration check: {e}")

        print("PostgreSQL database connected")
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
            "id": str(user.id),
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
            "id": str(user.id),
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


def get_user_by_google_id(google_id: str) -> Optional[dict]:
    """Find user by Google OAuth ID."""
    session = get_session()
    if session is None:
        return None

    try:
        user = session.query(User).filter(User.google_id == google_id).first()

        if user is None:
            return None

        return {
            "id": str(user.id),
            "name": user.name or user.google_name,
            "email": user.email or user.google_email,
            "phone": user.phone,
            "company": user.company,
            "google_id": user.google_id,
            "google_email": user.google_email,
            "google_name": user.google_name,
            "google_picture": user.google_picture,
            "auth_method": user.auth_method,
            "status": user.status or "new",
            "created_at": user.created_at.isoformat() if user.created_at else None,
            "last_seen": user.last_seen.isoformat() if user.last_seen else None
        }
    except Exception as e:
        print(f"Error getting user by Google ID: {e}")
        return None
    finally:
        session.close()


def create_google_user(user_id: str, google_id: str, google_email: str,
                       google_name: str, google_picture: str) -> Optional[dict]:
    """Create a new user with Google OAuth."""
    session = get_session()
    if session is None:
        return None

    try:
        user = User(
            id=user_id,
            google_id=google_id,
            google_email=google_email,
            google_name=google_name,
            google_picture=google_picture,
            name=google_name,
            email=google_email,
            auth_method="google"
        )
        session.add(user)
        session.commit()
        session.refresh(user)

        return {
            "id": str(user.id),
            "name": user.name,
            "email": user.email,
            "google_id": user.google_id,
            "google_picture": user.google_picture,
            "auth_method": user.auth_method
        }
    except Exception as e:
        print(f"Error creating Google user: {e}")
        session.rollback()
        return None
    finally:
        session.close()


def link_google_account(user_id: str, google_id: str, google_email: str,
                        google_name: str, google_picture: str) -> Optional[dict]:
    """Link Google account to existing user."""
    session = get_session()
    if session is None:
        return None

    try:
        user = session.query(User).filter(User.id == user_id).first()

        if user is None:
            return None

        user.google_id = google_id
        user.google_email = google_email
        user.google_name = google_name
        user.google_picture = google_picture
        user.auth_method = "google"

        # Update name/email if not already set
        if not user.name:
            user.name = google_name
        if not user.email:
            user.email = google_email

        user.last_seen = datetime.utcnow()
        session.commit()

        return {
            "id": str(user.id),
            "name": user.name,
            "email": user.email,
            "google_id": user.google_id,
            "google_picture": user.google_picture,
            "auth_method": user.auth_method
        }
    except Exception as e:
        print(f"Error linking Google account: {e}")
        session.rollback()
        return None
    finally:
        session.close()


def save_conversation(user_id: str, messages: list, summary: str = None,
                      interests: list = None, lead_score: int = 1) -> Optional[int]:
    """Save a conversation. Returns conversation ID."""
    print(f"[DB DEBUG] save_conversation called for user {user_id}")
    session = get_session()
    if session is None:
        print("[DB DEBUG] Session is None!")
        return None

    try:
        # JSON column type handles serialization automatically
        conversation = Conversation(
            user_id=user_id,
            messages=messages,
            summary=summary,
            interests=interests,
            lead_score=lead_score
        )
        session.add(conversation)
        session.commit()

        print(f"[DB DEBUG] Conversation saved with id {conversation.id}")
        return conversation.id
    except Exception as e:
        print(f"[DB DEBUG] Error saving conversation: {e}")
        import traceback
        traceback.print_exc()
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

        # Update fields - JSON column type handles serialization automatically
        if messages is not None:
            conversation.messages = messages
        if summary is not None:
            conversation.summary = summary
        if interests is not None:
            conversation.interests = interests
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

        # JSON column type returns Python objects directly
        last_interests = last_conversation.interests if last_conversation else None

        context = {
            "user_id": str(user.id),
            "name": user.name,
            "email": user.email,
            "phone": user.phone,
            "company": user.company,
            "is_returning": last_conversation is not None,
            "last_summary": last_conversation.summary if last_conversation else None,
            "last_interests": last_interests,
            "conversation_count": session.query(Conversation).filter(Conversation.user_id == user_id).count(),
            "auth_method": user.auth_method,
            "google_picture": user.google_picture
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

            # JSON column type returns Python objects directly
            interests = best_conv.interests if best_conv and best_conv.interests else []

            leads.append({
                "id": str(user.id),
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

            # JSON column type returns Python objects directly
            last_interests = last_conv.interests if last_conv and last_conv.interests else []

            results.append({
                "user_id": str(user.id),
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
            # JSON column type returns Python objects directly
            messages = conv.messages if conv.messages else []
            interests = conv.interests if conv.interests else []

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
            # Collect interests
            if conv.interests:
                for interest in conv.interests:
                    all_interests.add(interest)

            conversation_history.append({
                "id": conv.id,
                "date": conv.created_at.isoformat() if conv.created_at else None,
                "summary": conv.summary,
                "lead_score": conv.lead_score,
                "interests": conv.interests or []
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
