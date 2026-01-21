"""
Database models and functions for Maurice memory system.
Supports SQLite (local) and PostgreSQL (production).
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

# Database URL from environment (Railway provides DATABASE_URL for PostgreSQL)
# Falls back to local SQLite for development
DATABASE_PATH = Path(__file__).parent / "maurice.db"
DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{DATABASE_PATH}")

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


class PageView(Base):
    """Track user page/panel views and link clicks."""
    __tablename__ = "page_views"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    view_type = Column(String(20), nullable=False)  # "panel", "link", "external"
    title = Column(String(255), nullable=False)     # Panel title or link text
    url = Column(String(500), nullable=True)        # For link clicks
    panel_key = Column(String(100), nullable=True)  # For panel views
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", backref="page_views")


class ResponseFeedback(Base):
    """Admin feedback on Maurice responses for quality tracking and training."""
    __tablename__ = "response_feedback"

    id = Column(Integer, primary_key=True, autoincrement=True)
    conversation_id = Column(Integer, ForeignKey("conversations.id"), nullable=False, index=True)
    message_index = Column(Integer, nullable=False)  # Which message pair in conversation (0-indexed)

    # Rating (1-5 stars, or use 1=bad, 5=great)
    rating = Column(Integer, nullable=True)

    # Feedback categorization
    feedback_type = Column(String(30), nullable=True)  # "accurate", "helpful", "tone", "hallucination", "off-topic", "missed-opportunity"

    # Detailed feedback
    notes = Column(Text, nullable=True)  # Admin notes on what was wrong/right
    corrected_response = Column(Text, nullable=True)  # What Maurice should have said

    # Training flags
    is_exemplary = Column(Integer, default=0)  # 1 = good training example
    is_problematic = Column(Integer, default=0)  # 1 = needs review/fix

    # Metadata
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    admin_id = Column(String(50), nullable=True)  # Who left feedback

    conversation = relationship("Conversation", backref="feedback")


class TrainingExample(Base):
    """Curated Q&A pairs for fine-tuning Maurice."""
    __tablename__ = "training_examples"

    id = Column(Integer, primary_key=True, autoincrement=True)

    # The Q&A pair
    user_message = Column(Text, nullable=False)
    assistant_response = Column(Text, nullable=False)

    # Context that should be included during training
    relevant_facts = Column(Text, nullable=True)  # JSON of facts to inject
    rag_context = Column(Text, nullable=True)  # Relevant docs context

    # Categorization
    category = Column(String(50), nullable=True)  # greeting, pricing, technical, objection_handling, lead_capture
    difficulty = Column(String(20), nullable=True)  # easy, medium, hard

    # Source tracking
    source_conversation_id = Column(Integer, ForeignKey("conversations.id"), nullable=True)
    source_feedback_id = Column(Integer, ForeignKey("response_feedback.id"), nullable=True)
    was_edited = Column(Integer, default=0)  # 1 if response was modified from original

    # Quality
    quality_score = Column(Integer, nullable=True)  # 1-5
    reviewer_notes = Column(Text, nullable=True)

    # Status
    status = Column(String(20), default="pending")  # pending, approved, rejected

    # Metadata
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    created_by = Column(String(50), nullable=True)  # Admin who created


def init_db():
    """Initialize database connection and create tables."""
    global engine, SessionLocal

    try:
        # SQLite needs check_same_thread=False, PostgreSQL needs pooling
        if DATABASE_URL.startswith("sqlite"):
            engine = create_engine(
                DATABASE_URL,
                connect_args={"check_same_thread": False}
            )
            db_type = "SQLite"
            db_location = str(DATABASE_PATH)
        else:
            # PostgreSQL or other production database
            engine = create_engine(
                DATABASE_URL,
                pool_size=5,
                max_overflow=10,
                pool_pre_ping=True  # Verify connections before use
            )
            db_type = "PostgreSQL"
            db_location = DATABASE_URL.split("@")[-1].split("/")[0] if "@" in DATABASE_URL else "remote"

        SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

        # Create tables if they don't exist
        Base.metadata.create_all(bind=engine)
        print(f"{db_type} database ready: {db_location}")
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

        # Migrate user facts from current user to target user
        # For each fact type, keep the one with higher confidence
        current_facts = session.query(UserFact).filter(
            UserFact.user_id == current_user_id
        ).all()

        for fact in current_facts:
            existing = session.query(UserFact).filter(
                UserFact.user_id == target_user_id,
                UserFact.fact_type == fact.fact_type
            ).first()

            if existing:
                # Update if current fact has higher confidence
                if fact.confidence > existing.confidence:
                    existing.fact_value = fact.fact_value
                    existing.confidence = fact.confidence
                    existing.source_text = fact.source_text
            else:
                # Create new fact for target user
                new_fact = UserFact(
                    user_id=target_user_id,
                    fact_type=fact.fact_type,
                    fact_value=fact.fact_value,
                    confidence=fact.confidence,
                    source_text=fact.source_text
                )
                session.add(new_fact)

        # Delete current user facts explicitly (before cascade delete)
        session.query(UserFact).filter(UserFact.user_id == current_user_id).delete()

        # Preserve name - prefer current user's name (more recent)
        if current_user.name and not current_user.name.startswith("ANON["):
            target_user.name = current_user.name

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


# ============================================
# Page View Tracking Functions
# ============================================

def save_page_view(user_id: str, view_type: str, title: str,
                   url: str = None, panel_key: str = None) -> Optional[int]:
    """Save a page view or link click. Returns view ID."""
    session = get_session()
    if session is None:
        return None

    try:
        view = PageView(
            user_id=user_id,
            view_type=view_type,
            title=title,
            url=url,
            panel_key=panel_key
        )
        session.add(view)
        session.commit()
        return view.id
    except Exception as e:
        print(f"Error saving page view: {e}")
        session.rollback()
        return None
    finally:
        session.close()


def get_user_page_views(user_id: str, limit: int = 20) -> list:
    """Get recent page views for a user."""
    session = get_session()
    if session is None:
        return []

    try:
        views = session.query(PageView).filter(
            PageView.user_id == user_id
        ).order_by(PageView.created_at.desc()).limit(limit).all()

        return [
            {
                "id": v.id,
                "view_type": v.view_type,
                "title": v.title,
                "url": v.url,
                "panel_key": v.panel_key,
                "created_at": v.created_at.isoformat() if v.created_at else None
            }
            for v in views
        ]
    except Exception as e:
        print(f"Error getting page views: {e}")
        return []
    finally:
        session.close()


def get_user_browsing_summary(user_id: str) -> dict:
    """Get aggregated browsing stats for a user."""
    session = get_session()
    if session is None:
        return {}

    try:
        from sqlalchemy import func

        # Count by view type
        type_counts = session.query(
            PageView.view_type,
            func.count(PageView.id)
        ).filter(
            PageView.user_id == user_id
        ).group_by(PageView.view_type).all()

        # Most viewed panels
        top_panels = session.query(
            PageView.title,
            func.count(PageView.id).label('count')
        ).filter(
            PageView.user_id == user_id,
            PageView.view_type == 'panel'
        ).group_by(PageView.title).order_by(
            func.count(PageView.id).desc()
        ).limit(5).all()

        return {
            "total_views": sum(count for _, count in type_counts),
            "by_type": {vtype: count for vtype, count in type_counts},
            "top_panels": [{"title": title, "count": count} for title, count in top_panels]
        }
    except Exception as e:
        print(f"Error getting browsing summary: {e}")
        return {}
    finally:
        session.close()


# ============================================
# Response Feedback Functions
# ============================================

def save_response_feedback(
    conversation_id: int,
    message_index: int,
    rating: int = None,
    feedback_type: str = None,
    notes: str = None,
    corrected_response: str = None,
    is_exemplary: bool = False,
    is_problematic: bool = False,
    admin_id: str = None
) -> Optional[int]:
    """Save or update feedback on a response. Returns feedback ID."""
    session = get_session()
    if session is None:
        return None

    try:
        # Check if feedback already exists for this message
        existing = session.query(ResponseFeedback).filter(
            ResponseFeedback.conversation_id == conversation_id,
            ResponseFeedback.message_index == message_index
        ).first()

        if existing:
            # Update existing feedback
            if rating is not None:
                existing.rating = rating
            if feedback_type is not None:
                existing.feedback_type = feedback_type
            if notes is not None:
                existing.notes = notes
            if corrected_response is not None:
                existing.corrected_response = corrected_response
            existing.is_exemplary = 1 if is_exemplary else 0
            existing.is_problematic = 1 if is_problematic else 0
            if admin_id:
                existing.admin_id = admin_id
            existing.updated_at = datetime.utcnow()
            session.commit()
            return existing.id
        else:
            # Create new feedback
            feedback = ResponseFeedback(
                conversation_id=conversation_id,
                message_index=message_index,
                rating=rating,
                feedback_type=feedback_type,
                notes=notes,
                corrected_response=corrected_response,
                is_exemplary=1 if is_exemplary else 0,
                is_problematic=1 if is_problematic else 0,
                admin_id=admin_id
            )
            session.add(feedback)
            session.commit()
            return feedback.id
    except Exception as e:
        print(f"Error saving response feedback: {e}")
        session.rollback()
        return None
    finally:
        session.close()


def get_response_feedback(conversation_id: int, message_index: int = None) -> list:
    """Get feedback for a conversation, optionally for a specific message."""
    session = get_session()
    if session is None:
        return []

    try:
        query = session.query(ResponseFeedback).filter(
            ResponseFeedback.conversation_id == conversation_id
        )
        if message_index is not None:
            query = query.filter(ResponseFeedback.message_index == message_index)

        feedback_list = query.order_by(ResponseFeedback.message_index).all()

        return [
            {
                "id": f.id,
                "conversation_id": f.conversation_id,
                "message_index": f.message_index,
                "rating": f.rating,
                "feedback_type": f.feedback_type,
                "notes": f.notes,
                "corrected_response": f.corrected_response,
                "is_exemplary": bool(f.is_exemplary),
                "is_problematic": bool(f.is_problematic),
                "admin_id": f.admin_id,
                "created_at": f.created_at.isoformat() if f.created_at else None,
                "updated_at": f.updated_at.isoformat() if f.updated_at else None
            }
            for f in feedback_list
        ]
    except Exception as e:
        print(f"Error getting response feedback: {e}")
        return []
    finally:
        session.close()


def get_feedback_stats() -> dict:
    """Get aggregate statistics on response feedback."""
    session = get_session()
    if session is None:
        return {}

    try:
        from sqlalchemy import func

        total = session.query(ResponseFeedback).count()
        exemplary = session.query(ResponseFeedback).filter(
            ResponseFeedback.is_exemplary == 1
        ).count()
        problematic = session.query(ResponseFeedback).filter(
            ResponseFeedback.is_problematic == 1
        ).count()

        # Rating distribution
        rating_dist = session.query(
            ResponseFeedback.rating,
            func.count(ResponseFeedback.id)
        ).filter(
            ResponseFeedback.rating.isnot(None)
        ).group_by(ResponseFeedback.rating).all()

        # Feedback type distribution
        type_dist = session.query(
            ResponseFeedback.feedback_type,
            func.count(ResponseFeedback.id)
        ).filter(
            ResponseFeedback.feedback_type.isnot(None)
        ).group_by(ResponseFeedback.feedback_type).all()

        # Average rating
        avg_rating = session.query(func.avg(ResponseFeedback.rating)).filter(
            ResponseFeedback.rating.isnot(None)
        ).scalar()

        return {
            "total_feedback": total,
            "exemplary_count": exemplary,
            "problematic_count": problematic,
            "avg_rating": round(float(avg_rating), 2) if avg_rating else None,
            "rating_distribution": {str(r): c for r, c in rating_dist if r is not None},
            "type_distribution": {t: c for t, c in type_dist if t is not None}
        }
    except Exception as e:
        print(f"Error getting feedback stats: {e}")
        return {}
    finally:
        session.close()


def get_exemplary_responses(limit: int = 100) -> list:
    """Get exemplary responses for training data export."""
    session = get_session()
    if session is None:
        return []

    try:
        feedback_list = session.query(ResponseFeedback).filter(
            ResponseFeedback.is_exemplary == 1
        ).order_by(ResponseFeedback.created_at.desc()).limit(limit).all()

        results = []
        for f in feedback_list:
            # Get the conversation to extract the actual Q&A
            conv = session.query(Conversation).filter(
                Conversation.id == f.conversation_id
            ).first()

            if conv and conv.messages:
                try:
                    messages = json.loads(conv.messages)
                    # Get the Q&A pair at message_index
                    # message_index is the assistant response index (0-indexed among assistant messages)
                    user_msgs = [m for m in messages if m.get("role") == "user"]
                    asst_msgs = [m for m in messages if m.get("role") == "assistant"]

                    if f.message_index < len(asst_msgs):
                        user_msg = user_msgs[f.message_index] if f.message_index < len(user_msgs) else None
                        asst_msg = asst_msgs[f.message_index]

                        results.append({
                            "id": f.id,
                            "user_message": user_msg.get("content") if user_msg else "",
                            "assistant_response": asst_msg.get("content"),
                            "corrected_response": f.corrected_response,
                            "rating": f.rating,
                            "feedback_type": f.feedback_type,
                            "notes": f.notes,
                            "conversation_id": f.conversation_id,
                            "created_at": f.created_at.isoformat() if f.created_at else None
                        })
                except json.JSONDecodeError:
                    pass

        return results
    except Exception as e:
        print(f"Error getting exemplary responses: {e}")
        return []
    finally:
        session.close()


def get_problematic_responses(limit: int = 100) -> list:
    """Get problematic responses for review."""
    session = get_session()
    if session is None:
        return []

    try:
        feedback_list = session.query(ResponseFeedback).filter(
            ResponseFeedback.is_problematic == 1
        ).order_by(ResponseFeedback.created_at.desc()).limit(limit).all()

        results = []
        for f in feedback_list:
            conv = session.query(Conversation).filter(
                Conversation.id == f.conversation_id
            ).first()

            if conv and conv.messages:
                try:
                    messages = json.loads(conv.messages)
                    user_msgs = [m for m in messages if m.get("role") == "user"]
                    asst_msgs = [m for m in messages if m.get("role") == "assistant"]

                    if f.message_index < len(asst_msgs):
                        user_msg = user_msgs[f.message_index] if f.message_index < len(user_msgs) else None
                        asst_msg = asst_msgs[f.message_index]

                        results.append({
                            "id": f.id,
                            "user_message": user_msg.get("content") if user_msg else "",
                            "assistant_response": asst_msg.get("content"),
                            "corrected_response": f.corrected_response,
                            "rating": f.rating,
                            "feedback_type": f.feedback_type,
                            "notes": f.notes,
                            "conversation_id": f.conversation_id,
                            "created_at": f.created_at.isoformat() if f.created_at else None
                        })
                except json.JSONDecodeError:
                    pass

        return results
    except Exception as e:
        print(f"Error getting problematic responses: {e}")
        return []
    finally:
        session.close()


# ============================================
# Training Data Functions
# ============================================

def save_training_example(
    user_message: str,
    assistant_response: str,
    category: str = None,
    difficulty: str = None,
    relevant_facts: dict = None,
    rag_context: str = None,
    source_conversation_id: int = None,
    source_feedback_id: int = None,
    was_edited: bool = False,
    quality_score: int = None,
    reviewer_notes: str = None,
    created_by: str = None
) -> Optional[int]:
    """Save a training example. Returns example ID."""
    session = get_session()
    if session is None:
        return None

    try:
        example = TrainingExample(
            user_message=user_message,
            assistant_response=assistant_response,
            category=category,
            difficulty=difficulty,
            relevant_facts=json.dumps(relevant_facts) if relevant_facts else None,
            rag_context=rag_context,
            source_conversation_id=source_conversation_id,
            source_feedback_id=source_feedback_id,
            was_edited=1 if was_edited else 0,
            quality_score=quality_score,
            reviewer_notes=reviewer_notes,
            status="pending",
            created_by=created_by
        )
        session.add(example)
        session.commit()
        return example.id
    except Exception as e:
        print(f"Error saving training example: {e}")
        session.rollback()
        return None
    finally:
        session.close()


def get_training_examples(
    status: str = None,
    category: str = None,
    limit: int = 100,
    offset: int = 0
) -> dict:
    """Get training examples with filtering and pagination."""
    session = get_session()
    if session is None:
        return {"examples": [], "total": 0, "page": 1, "total_pages": 0}

    try:
        from sqlalchemy import desc

        query = session.query(TrainingExample)

        if status:
            query = query.filter(TrainingExample.status == status)
        if category:
            query = query.filter(TrainingExample.category == category)

        total = query.count()
        examples = query.order_by(desc(TrainingExample.created_at)).offset(offset).limit(limit).all()

        results = []
        for ex in examples:
            results.append({
                "id": ex.id,
                "user_message": ex.user_message,
                "assistant_response": ex.assistant_response,
                "category": ex.category,
                "difficulty": ex.difficulty,
                "relevant_facts": json.loads(ex.relevant_facts) if ex.relevant_facts else None,
                "rag_context": ex.rag_context,
                "source_conversation_id": ex.source_conversation_id,
                "source_feedback_id": ex.source_feedback_id,
                "was_edited": bool(ex.was_edited),
                "quality_score": ex.quality_score,
                "reviewer_notes": ex.reviewer_notes,
                "status": ex.status,
                "created_at": ex.created_at.isoformat() if ex.created_at else None,
                "created_by": ex.created_by
            })

        total_pages = (total + limit - 1) // limit if limit > 0 else 1
        current_page = (offset // limit) + 1 if limit > 0 else 1

        return {
            "examples": results,
            "total": total,
            "page": current_page,
            "total_pages": total_pages
        }
    except Exception as e:
        print(f"Error getting training examples: {e}")
        return {"examples": [], "total": 0, "page": 1, "total_pages": 0}
    finally:
        session.close()


def update_training_example(
    example_id: int,
    user_message: str = None,
    assistant_response: str = None,
    category: str = None,
    difficulty: str = None,
    relevant_facts: dict = None,
    rag_context: str = None,
    quality_score: int = None,
    reviewer_notes: str = None,
    status: str = None
) -> bool:
    """Update a training example. Returns True on success."""
    session = get_session()
    if session is None:
        return False

    try:
        example = session.query(TrainingExample).filter(TrainingExample.id == example_id).first()
        if example is None:
            return False

        if user_message is not None:
            example.user_message = user_message
            example.was_edited = 1
        if assistant_response is not None:
            example.assistant_response = assistant_response
            example.was_edited = 1
        if category is not None:
            example.category = category
        if difficulty is not None:
            example.difficulty = difficulty
        if relevant_facts is not None:
            example.relevant_facts = json.dumps(relevant_facts)
        if rag_context is not None:
            example.rag_context = rag_context
        if quality_score is not None:
            example.quality_score = quality_score
        if reviewer_notes is not None:
            example.reviewer_notes = reviewer_notes
        if status is not None:
            example.status = status

        example.updated_at = datetime.utcnow()
        session.commit()
        return True
    except Exception as e:
        print(f"Error updating training example: {e}")
        session.rollback()
        return False
    finally:
        session.close()


def delete_training_example(example_id: int) -> bool:
    """Delete a training example."""
    session = get_session()
    if session is None:
        return False

    try:
        example = session.query(TrainingExample).filter(TrainingExample.id == example_id).first()
        if example:
            session.delete(example)
            session.commit()
            return True
        return False
    except Exception as e:
        print(f"Error deleting training example: {e}")
        session.rollback()
        return False
    finally:
        session.close()


def get_training_stats() -> dict:
    """Get statistics about training data."""
    session = get_session()
    if session is None:
        return {}

    try:
        from sqlalchemy import func

        total = session.query(TrainingExample).count()
        approved = session.query(TrainingExample).filter(TrainingExample.status == "approved").count()
        pending = session.query(TrainingExample).filter(TrainingExample.status == "pending").count()
        rejected = session.query(TrainingExample).filter(TrainingExample.status == "rejected").count()

        # Category distribution
        category_dist = session.query(
            TrainingExample.category,
            func.count(TrainingExample.id)
        ).filter(
            TrainingExample.status == "approved"
        ).group_by(TrainingExample.category).all()

        # Difficulty distribution
        difficulty_dist = session.query(
            TrainingExample.difficulty,
            func.count(TrainingExample.id)
        ).filter(
            TrainingExample.status == "approved"
        ).group_by(TrainingExample.difficulty).all()

        # Average quality score
        avg_quality = session.query(func.avg(TrainingExample.quality_score)).filter(
            TrainingExample.quality_score.isnot(None),
            TrainingExample.status == "approved"
        ).scalar()

        return {
            "total": total,
            "approved": approved,
            "pending": pending,
            "rejected": rejected,
            "category_distribution": {c or "uncategorized": count for c, count in category_dist},
            "difficulty_distribution": {d or "unset": count for d, count in difficulty_dist},
            "avg_quality_score": round(float(avg_quality), 2) if avg_quality else None
        }
    except Exception as e:
        print(f"Error getting training stats: {e}")
        return {}
    finally:
        session.close()


def export_training_data_jsonl(status: str = "approved") -> list:
    """
    Export training examples as JSONL-ready dicts for fine-tuning.
    Returns list of dicts with 'messages' field in OpenAI format.
    """
    session = get_session()
    if session is None:
        return []

    try:
        examples = session.query(TrainingExample).filter(
            TrainingExample.status == status
        ).order_by(TrainingExample.created_at).all()

        jsonl_data = []
        for ex in examples:
            # Build system prompt with context if available
            system_content = "You are Maurice, the Blacksky AI assistant."
            if ex.relevant_facts:
                try:
                    facts = json.loads(ex.relevant_facts)
                    if facts:
                        facts_str = ", ".join([f"{k}: {v}" for k, v in facts.items()])
                        system_content += f"\n\nUser context: {facts_str}"
                except:
                    pass
            if ex.rag_context:
                system_content += f"\n\nRelevant information:\n{ex.rag_context}"

            # Create training example in chat format
            entry = {
                "messages": [
                    {"role": "system", "content": system_content},
                    {"role": "user", "content": ex.user_message},
                    {"role": "assistant", "content": ex.assistant_response}
                ]
            }

            # Add metadata as separate field (not sent to model)
            entry["_metadata"] = {
                "id": ex.id,
                "category": ex.category,
                "difficulty": ex.difficulty,
                "quality_score": ex.quality_score,
                "was_edited": bool(ex.was_edited)
            }

            jsonl_data.append(entry)

        return jsonl_data
    except Exception as e:
        print(f"Error exporting training data: {e}")
        return []
    finally:
        session.close()


def get_training_candidates(limit: int = 50) -> list:
    """
    Auto-suggest training candidates based on:
    - Exemplary feedback responses
    - High-engagement conversations (long, multiple turns)
    - Conversations with high lead scores
    - Conversations that captured contact info

    Returns conversations that might make good training examples.
    """
    session = get_session()
    if session is None:
        return []

    try:
        from sqlalchemy import func, desc

        candidates = []

        # 1. Get exemplary responses not yet in training set
        exemplary_feedback = session.query(ResponseFeedback).filter(
            ResponseFeedback.is_exemplary == 1
        ).all()

        existing_feedback_ids = session.query(TrainingExample.source_feedback_id).filter(
            TrainingExample.source_feedback_id.isnot(None)
        ).all()
        existing_feedback_ids = {id[0] for id in existing_feedback_ids}

        for fb in exemplary_feedback:
            if fb.id in existing_feedback_ids:
                continue

            conv = session.query(Conversation).filter(
                Conversation.id == fb.conversation_id
            ).first()

            if conv and conv.messages:
                try:
                    messages = json.loads(conv.messages)
                    user_msgs = [m for m in messages if m.get("role") == "user"]
                    asst_msgs = [m for m in messages if m.get("role") == "assistant"]

                    if fb.message_index < len(asst_msgs) and fb.message_index < len(user_msgs):
                        candidates.append({
                            "source": "exemplary_feedback",
                            "feedback_id": fb.id,
                            "conversation_id": conv.id,
                            "user_message": user_msgs[fb.message_index].get("content"),
                            "assistant_response": asst_msgs[fb.message_index].get("content"),
                            "corrected_response": fb.corrected_response,
                            "rating": fb.rating,
                            "notes": fb.notes,
                            "priority": 1  # Highest priority
                        })
                except:
                    pass

        # 2. Get high lead score conversations not in training set
        existing_conv_ids = session.query(TrainingExample.source_conversation_id).filter(
            TrainingExample.source_conversation_id.isnot(None)
        ).all()
        existing_conv_ids = {id[0] for id in existing_conv_ids}

        high_score_convs = session.query(Conversation).filter(
            Conversation.lead_score >= 3,
            ~Conversation.id.in_(existing_conv_ids)
        ).order_by(desc(Conversation.lead_score), desc(Conversation.created_at)).limit(20).all()

        for conv in high_score_convs:
            if conv.messages:
                try:
                    messages = json.loads(conv.messages)
                    # Take the last meaningful exchange
                    user_msgs = [m for m in messages if m.get("role") == "user"]
                    asst_msgs = [m for m in messages if m.get("role") == "assistant"]

                    if user_msgs and asst_msgs:
                        # Get the exchange with the longest assistant response (likely most substantive)
                        best_idx = max(range(min(len(user_msgs), len(asst_msgs))),
                                       key=lambda i: len(asst_msgs[i].get("content", "")))

                        candidates.append({
                            "source": "high_lead_score",
                            "conversation_id": conv.id,
                            "user_message": user_msgs[best_idx].get("content"),
                            "assistant_response": asst_msgs[best_idx].get("content"),
                            "lead_score": conv.lead_score,
                            "summary": conv.summary,
                            "priority": 2
                        })
                except:
                    pass

        # 3. Get conversations with captured contact info
        users_with_contact = session.query(User.id).filter(
            (User.email.isnot(None)) | (User.phone.isnot(None))
        ).all()
        user_ids_with_contact = {u[0] for u in users_with_contact}

        contact_convs = session.query(Conversation).filter(
            Conversation.user_id.in_(user_ids_with_contact),
            ~Conversation.id.in_(existing_conv_ids)
        ).order_by(desc(Conversation.created_at)).limit(20).all()

        for conv in contact_convs:
            if conv.messages and conv.id not in [c.get("conversation_id") for c in candidates]:
                try:
                    messages = json.loads(conv.messages)
                    user_msgs = [m for m in messages if m.get("role") == "user"]
                    asst_msgs = [m for m in messages if m.get("role") == "assistant"]

                    if user_msgs and asst_msgs:
                        # Find exchanges where user shared contact info
                        for i, um in enumerate(user_msgs):
                            content = um.get("content", "").lower()
                            if "@" in content or any(c.isdigit() for c in content[-10:]):
                                if i < len(asst_msgs):
                                    candidates.append({
                                        "source": "contact_captured",
                                        "conversation_id": conv.id,
                                        "user_message": um.get("content"),
                                        "assistant_response": asst_msgs[i].get("content"),
                                        "priority": 3
                                    })
                                    break
                except:
                    pass

        # Sort by priority and limit
        candidates.sort(key=lambda x: x.get("priority", 99))
        return candidates[:limit]

    except Exception as e:
        print(f"Error getting training candidates: {e}")
        import traceback
        traceback.print_exc()
        return []
    finally:
        session.close()


def create_training_example_from_feedback(feedback_id: int, created_by: str = None) -> Optional[int]:
    """Create a training example from an exemplary feedback entry."""
    session = get_session()
    if session is None:
        return None

    try:
        fb = session.query(ResponseFeedback).filter(ResponseFeedback.id == feedback_id).first()
        if not fb:
            return None

        conv = session.query(Conversation).filter(Conversation.id == fb.conversation_id).first()
        if not conv or not conv.messages:
            return None

        messages = json.loads(conv.messages)
        user_msgs = [m for m in messages if m.get("role") == "user"]
        asst_msgs = [m for m in messages if m.get("role") == "assistant"]

        if fb.message_index >= len(user_msgs) or fb.message_index >= len(asst_msgs):
            return None

        user_message = user_msgs[fb.message_index].get("content")
        # Use corrected response if available, otherwise original
        assistant_response = fb.corrected_response or asst_msgs[fb.message_index].get("content")

        # Get user facts for context
        user_facts = get_user_facts_dict(conv.user_id)

        example = TrainingExample(
            user_message=user_message,
            assistant_response=assistant_response,
            relevant_facts=json.dumps(user_facts) if user_facts else None,
            source_conversation_id=conv.id,
            source_feedback_id=fb.id,
            was_edited=1 if fb.corrected_response else 0,
            quality_score=fb.rating,
            reviewer_notes=fb.notes,
            status="pending",
            created_by=created_by
        )
        session.add(example)
        session.commit()
        return example.id

    except Exception as e:
        print(f"Error creating training example from feedback: {e}")
        session.rollback()
        return None
    finally:
        session.close()


# ============================================
# Admin Users Dashboard Functions
# ============================================

def get_all_users(
    auth_method: str = None,
    status: str = None,
    search: str = None,
    sort_by: str = 'last_seen',
    sort_order: str = 'desc',
    limit: int = 100,
    offset: int = 0
) -> dict:
    """
    Get all users with filtering, sorting, and pagination for admin dashboard.

    Args:
        auth_method: Filter by 'soft', 'medium', 'google', or None for all
        status: Filter by user status
        search: Search in name, email, company
        sort_by: 'last_seen', 'created_at', 'name', 'conversations'
        sort_order: 'asc' or 'desc'
        limit: Max results per page
        offset: Skip first N results

    Returns:
        Dict with users list, total count, and pagination info
    """
    from sqlalchemy import func, desc, asc

    session = get_session()
    if session is None:
        return {"users": [], "total": 0, "page": 1, "total_pages": 0}

    try:
        # Build base query for users
        query = session.query(User)

        # Apply filters
        if auth_method:
            if auth_method == 'anonymous':
                query = query.filter(User.name.like('ANON[%'))
            else:
                query = query.filter(User.auth_method == auth_method)

        if status:
            query = query.filter(User.status == status)

        if search:
            search_pattern = f"%{search}%"
            query = query.filter(
                (User.name.ilike(search_pattern)) |
                (User.email.ilike(search_pattern)) |
                (User.company.ilike(search_pattern))
            )

        # Get total count before pagination
        total = query.count()

        # Apply sorting
        sort_func = desc if sort_order == 'desc' else asc
        if sort_by == 'name':
            query = query.order_by(sort_func(User.name))
        elif sort_by == 'created_at':
            query = query.order_by(sort_func(User.created_at))
        elif sort_by == 'conversations':
            # For conversation sorting, we need a subquery
            conv_count = session.query(
                Conversation.user_id,
                func.count(Conversation.id).label('conv_count')
            ).group_by(Conversation.user_id).subquery()
            query = query.outerjoin(conv_count, User.id == conv_count.c.user_id)
            query = query.order_by(sort_func(func.coalesce(conv_count.c.conv_count, 0)))
        else:  # default: last_seen
            query = query.order_by(sort_func(User.last_seen))

        # Apply pagination
        query = query.offset(offset).limit(limit)

        users_list = query.all()

        # Get conversation and fact counts for each user
        user_ids = [u.id for u in users_list]

        # Batch query for conversation counts
        conv_counts = {}
        if user_ids:
            conv_results = session.query(
                Conversation.user_id,
                func.count(Conversation.id)
            ).filter(Conversation.user_id.in_(user_ids)).group_by(Conversation.user_id).all()
            conv_counts = {uid: count for uid, count in conv_results}

        # Batch query for fact counts
        fact_counts = {}
        if user_ids:
            fact_results = session.query(
                UserFact.user_id,
                func.count(UserFact.id)
            ).filter(UserFact.user_id.in_(user_ids)).group_by(UserFact.user_id).all()
            fact_counts = {uid: count for uid, count in fact_results}

        # Build results
        results = []
        for user in users_list:
            results.append((user, conv_counts.get(user.id, 0), fact_counts.get(user.id, 0)))

        users = []
        for user, conv_count, fact_count in results:
            users.append({
                "id": user.id,
                "name": user.name,
                "email": user.email,
                "phone": user.phone,
                "company": user.company,
                "auth_method": user.auth_method,
                "status": user.status or "new",
                "interest_level": user.interest_level,
                "notes": user.notes,
                "created_at": user.created_at.isoformat() if user.created_at else None,
                "last_seen": user.last_seen.isoformat() if user.last_seen else None,
                "conversation_count": conv_count,
                "fact_count": fact_count
            })

        total_pages = (total + limit - 1) // limit if limit > 0 else 1
        current_page = (offset // limit) + 1 if limit > 0 else 1

        return {
            "users": users,
            "total": total,
            "page": current_page,
            "total_pages": total_pages
        }

    except Exception as e:
        print(f"Error getting all users: {e}")
        return {"users": [], "total": 0, "page": 1, "total_pages": 0}
    finally:
        session.close()


def get_user_full_profile(user_id: str) -> dict:
    """
    Get complete user profile with all facts and conversations for admin view.

    Returns:
        Dict with user info, facts, conversations, and stats
    """
    session = get_session()
    if session is None:
        return None

    try:
        user = session.query(User).filter(User.id == user_id).first()
        if not user:
            return None

        # Get all facts
        facts = session.query(UserFact).filter(
            UserFact.user_id == user_id
        ).order_by(UserFact.confidence.desc()).all()

        # Get all conversations with messages
        conversations = session.query(Conversation).filter(
            Conversation.user_id == user_id
        ).order_by(Conversation.created_at.desc()).all()

        # Build response
        facts_list = [
            {
                "type": f.fact_type,
                "value": f.fact_value,
                "confidence": f.confidence,
                "source_text": f.source_text[:100] + "..." if f.source_text and len(f.source_text) > 100 else f.source_text,
                "created_at": f.created_at.isoformat() if f.created_at else None
            }
            for f in facts
        ]

        conversations_list = []
        total_messages = 0
        lead_scores = []

        for conv in conversations:
            messages = []
            if conv.messages:
                try:
                    messages = json.loads(conv.messages)
                except:
                    messages = []

            total_messages += len(messages)
            if conv.lead_score:
                lead_scores.append(conv.lead_score)

            conversations_list.append({
                "id": conv.id,
                "created_at": conv.created_at.isoformat() if conv.created_at else None,
                "summary": conv.summary,
                "lead_score": conv.lead_score,
                "message_count": len(messages),
                "messages": messages
            })

        # Calculate stats
        avg_lead_score = sum(lead_scores) / len(lead_scores) if lead_scores else 0
        first_contact = user.created_at
        days_since_first = (datetime.utcnow() - first_contact).days if first_contact else 0

        return {
            "user": {
                "id": user.id,
                "name": user.name,
                "email": user.email,
                "phone": user.phone,
                "company": user.company,
                "auth_method": user.auth_method,
                "status": user.status or "new",
                "interest_level": user.interest_level,
                "notes": user.notes,
                "created_at": user.created_at.isoformat() if user.created_at else None,
                "last_seen": user.last_seen.isoformat() if user.last_seen else None
            },
            "facts": facts_list,
            "conversations": conversations_list,
            "stats": {
                "total_conversations": len(conversations_list),
                "total_messages": total_messages,
                "avg_lead_score": round(avg_lead_score, 1),
                "first_contact": first_contact.isoformat() if first_contact else None,
                "days_since_first_contact": days_since_first
            }
        }

    except Exception as e:
        print(f"Error getting user full profile: {e}")
        return None
    finally:
        session.close()


# ============================================
# Lead Intelligence Functions
# ============================================

def get_funnel_analytics(days: int = 30) -> dict:
    """
    Get lead funnel analytics for the specified time period.

    Funnel stages:
    - Visitors: Total unique users
    - Engaged: Users with at least 2 messages
    - Named: Users who provided their name (not ANON)
    - Contact: Users who provided email or phone
    - High-Intent: Users with lead score >= 3
    - Contacted: Users with status 'contacted' or beyond
    - Converted: Users with status 'converted'
    """
    from datetime import timedelta
    from sqlalchemy import func, and_, or_

    session = get_session()
    if session is None:
        return {}

    try:
        cutoff = datetime.utcnow() - timedelta(days=days)

        # Total visitors in period
        visitors = session.query(User).filter(
            User.created_at >= cutoff
        ).count()

        # Engaged: Users with conversations that have multiple messages
        engaged_query = session.query(User.id).join(Conversation).filter(
            User.created_at >= cutoff
        ).group_by(User.id).having(
            func.sum(func.length(Conversation.messages) - func.length(func.replace(Conversation.messages, '"role"', ''))) >= 4
        )
        engaged = engaged_query.count()

        # Named: Users with a real name (not ANON)
        named = session.query(User).filter(
            User.created_at >= cutoff,
            User.name.isnot(None),
            ~User.name.like('ANON[%')
        ).count()

        # Contact: Users with email or phone
        contact = session.query(User).filter(
            User.created_at >= cutoff,
            or_(User.email.isnot(None), User.phone.isnot(None))
        ).count()

        # High-Intent: Users with lead score >= 3
        high_intent_users = session.query(User.id).join(Conversation).filter(
            User.created_at >= cutoff,
            Conversation.lead_score >= 3
        ).distinct().count()

        # Contacted: Users with status contacted, qualified, or converted
        contacted = session.query(User).filter(
            User.created_at >= cutoff,
            User.status.in_(['contacted', 'qualified', 'converted'])
        ).count()

        # Converted: Users with status converted
        converted = session.query(User).filter(
            User.created_at >= cutoff,
            User.status == 'converted'
        ).count()

        # Calculate percentages
        def pct(n, total):
            return round((n / total) * 100, 1) if total > 0 else 0

        return {
            "days": days,
            "funnel": [
                {"stage": "Visitors", "count": visitors, "pct": 100},
                {"stage": "Engaged", "count": engaged, "pct": pct(engaged, visitors)},
                {"stage": "Named", "count": named, "pct": pct(named, visitors)},
                {"stage": "Contact Info", "count": contact, "pct": pct(contact, visitors)},
                {"stage": "High-Intent", "count": high_intent_users, "pct": pct(high_intent_users, visitors)},
                {"stage": "Contacted", "count": contacted, "pct": pct(contacted, visitors)},
                {"stage": "Converted", "count": converted, "pct": pct(converted, visitors)},
            ],
            "conversion_rates": {
                "visitor_to_engaged": pct(engaged, visitors),
                "engaged_to_named": pct(named, engaged) if engaged > 0 else 0,
                "named_to_contact": pct(contact, named) if named > 0 else 0,
                "contact_to_high_intent": pct(high_intent_users, contact) if contact > 0 else 0,
                "high_intent_to_contacted": pct(contacted, high_intent_users) if high_intent_users > 0 else 0,
                "contacted_to_converted": pct(converted, contacted) if contacted > 0 else 0,
            }
        }
    except Exception as e:
        print(f"Error getting funnel analytics: {e}")
        import traceback
        traceback.print_exc()
        return {}
    finally:
        session.close()


def get_intent_signals(days: int = 30, min_mentions: int = 3) -> list:
    """
    Analyze which topics/keywords correlate with high-intent users.

    Returns list of keywords with their intent correlation.
    """
    from datetime import timedelta
    from collections import defaultdict

    session = get_session()
    if session is None:
        return []

    try:
        cutoff = datetime.utcnow() - timedelta(days=days)

        # Keywords to track
        intent_keywords = [
            "pricing", "price", "cost", "budget",
            "timeline", "deadline", "when", "schedule",
            "treasury", "federal", "government",
            "ai", "automation", "machine learning",
            "demo", "trial", "pilot",
            "team", "hire", "partner",
            "security", "compliance", "hipaa",
            "integration", "api", "custom"
        ]

        # Get all conversations from the period
        conversations = session.query(Conversation, User).join(User).filter(
            Conversation.created_at >= cutoff,
            Conversation.messages.isnot(None)
        ).all()

        # Track keyword mentions and high-intent correlation
        keyword_stats = defaultdict(lambda: {"mentions": 0, "high_intent": 0, "users": set()})

        for conv, user in conversations:
            if not conv.messages:
                continue

            try:
                messages = json.loads(conv.messages)
                user_messages = " ".join([
                    m.get("content", "").lower()
                    for m in messages
                    if m.get("role") == "user"
                ])

                is_high_intent = (conv.lead_score and conv.lead_score >= 3) or \
                                 (user.email is not None) or \
                                 (user.phone is not None)

                for keyword in intent_keywords:
                    if keyword in user_messages:
                        keyword_stats[keyword]["mentions"] += 1
                        keyword_stats[keyword]["users"].add(user.id)
                        if is_high_intent:
                            keyword_stats[keyword]["high_intent"] += 1

            except json.JSONDecodeError:
                continue

        # Build results
        results = []
        for keyword, stats in keyword_stats.items():
            if stats["mentions"] >= min_mentions:
                intent_rate = round((stats["high_intent"] / stats["mentions"]) * 100) if stats["mentions"] > 0 else 0
                results.append({
                    "keyword": keyword,
                    "mentions": stats["mentions"],
                    "high_intent": stats["high_intent"],
                    "intent_rate": intent_rate,
                    "unique_users": len(stats["users"])
                })

        # Sort by intent rate descending
        results.sort(key=lambda x: (-x["intent_rate"], -x["mentions"]))

        return results

    except Exception as e:
        print(f"Error getting intent signals: {e}")
        import traceback
        traceback.print_exc()
        return []
    finally:
        session.close()


def get_user_journey(user_id: str) -> list:
    """
    Get a chronological journey of user actions and milestones.

    Returns list of events with timestamps and descriptions.
    """
    session = get_session()
    if session is None:
        return []

    try:
        events = []

        # Get user info
        user = session.query(User).filter(User.id == user_id).first()
        if not user:
            return []

        # Event: User created
        if user.created_at:
            events.append({
                "timestamp": user.created_at.isoformat(),
                "type": "milestone",
                "event": "First Visit",
                "details": None
            })

        # Get page views
        page_views = session.query(PageView).filter(
            PageView.user_id == user_id
        ).order_by(PageView.created_at).all()

        for pv in page_views:
            events.append({
                "timestamp": pv.created_at.isoformat() if pv.created_at else None,
                "type": "browse",
                "event": f"Viewed {pv.title}",
                "details": pv.view_type
            })

        # Get conversations and extract key moments
        conversations = session.query(Conversation).filter(
            Conversation.user_id == user_id
        ).order_by(Conversation.created_at).all()

        for conv in conversations:
            # Conversation start
            if conv.created_at:
                events.append({
                    "timestamp": conv.created_at.isoformat(),
                    "type": "conversation",
                    "event": "Started conversation",
                    "details": conv.summary[:50] + "..." if conv.summary and len(conv.summary) > 50 else conv.summary
                })

            # High intent marker
            if conv.lead_score and conv.lead_score >= 3:
                events.append({
                    "timestamp": conv.created_at.isoformat() if conv.created_at else None,
                    "type": "milestone",
                    "event": "HIGH INTENT",
                    "details": f"Lead score: {conv.lead_score}"
                })

            # Parse messages for key moments
            if conv.messages:
                try:
                    messages = json.loads(conv.messages)
                    for msg in messages:
                        content = msg.get("content", "").lower()
                        if msg.get("role") == "user":
                            # Check for contact info sharing
                            if "@" in content and "." in content:
                                events.append({
                                    "timestamp": conv.created_at.isoformat() if conv.created_at else None,
                                    "type": "milestone",
                                    "event": "Shared email",
                                    "details": None
                                })
                            # Check for call requests
                            if any(phrase in content for phrase in ["schedule", "call", "meeting", "talk to", "speak with"]):
                                events.append({
                                    "timestamp": conv.created_at.isoformat() if conv.created_at else None,
                                    "type": "intent",
                                    "event": "Requested contact/call",
                                    "details": None
                                })
                except json.JSONDecodeError:
                    pass

        # Check for name milestone
        if user.name and not user.name.startswith("ANON["):
            events.append({
                "timestamp": user.last_seen.isoformat() if user.last_seen else None,
                "type": "milestone",
                "event": "Provided name",
                "details": user.name
            })

        # Check for contact info milestone
        if user.email:
            events.append({
                "timestamp": user.last_seen.isoformat() if user.last_seen else None,
                "type": "milestone",
                "event": "Provided email",
                "details": user.email
            })

        if user.phone:
            events.append({
                "timestamp": user.last_seen.isoformat() if user.last_seen else None,
                "type": "milestone",
                "event": "Provided phone",
                "details": user.phone
            })

        # Status changes
        if user.status and user.status != "new":
            events.append({
                "timestamp": user.last_seen.isoformat() if user.last_seen else None,
                "type": "status",
                "event": f"Status: {user.status.upper()}",
                "details": None
            })

        # Sort by timestamp and deduplicate
        events.sort(key=lambda x: x["timestamp"] or "")

        # Deduplicate consecutive similar events
        deduped = []
        for event in events:
            if not deduped or event["event"] != deduped[-1]["event"]:
                deduped.append(event)

        return deduped

    except Exception as e:
        print(f"Error getting user journey: {e}")
        import traceback
        traceback.print_exc()
        return []
    finally:
        session.close()


def get_recent_high_intent_leads(days: int = 7, limit: int = 10) -> list:
    """
    Get recent leads showing high-intent signals.
    """
    from datetime import timedelta
    from sqlalchemy import or_, desc

    session = get_session()
    if session is None:
        return []

    try:
        cutoff = datetime.utcnow() - timedelta(days=days)

        # Find users with high lead scores or contact info, recent activity
        high_intent_users = session.query(User).outerjoin(Conversation).filter(
            User.last_seen >= cutoff,
            or_(
                Conversation.lead_score >= 3,
                User.email.isnot(None),
                User.phone.isnot(None)
            )
        ).order_by(desc(User.last_seen)).limit(limit).all()

        results = []
        for user in high_intent_users:
            # Get best conversation
            best_conv = session.query(Conversation).filter(
                Conversation.user_id == user.id
            ).order_by(desc(Conversation.lead_score), desc(Conversation.created_at)).first()

            # Get user facts
            facts = session.query(UserFact).filter(
                UserFact.user_id == user.id,
                UserFact.confidence >= 0.6
            ).all()
            facts_dict = {f.fact_type: f.fact_value for f in facts}

            results.append({
                "id": user.id,
                "name": user.name,
                "email": user.email,
                "phone": user.phone,
                "company": user.company or facts_dict.get("company"),
                "role": facts_dict.get("role"),
                "lead_score": best_conv.lead_score if best_conv else 1,
                "last_topic": best_conv.summary if best_conv else None,
                "status": user.status or "new",
                "last_seen": user.last_seen.isoformat() if user.last_seen else None
            })

        return results

    except Exception as e:
        print(f"Error getting high intent leads: {e}")
        return []
    finally:
        session.close()


# ============================================
# Response Quality Analysis Functions
# ============================================

# Hallucination patterns - things Maurice should NOT claim to do
HALLUCINATION_PATTERNS = [
    ("i can schedule", "Claims to schedule meetings"),
    ("i'll schedule", "Claims to schedule meetings"),
    ("i will schedule", "Claims to schedule meetings"),
    ("i can send", "Claims to send emails/invites"),
    ("i'll send", "Claims to send emails/invites"),
    ("i will send", "Claims to send emails/invites"),
    ("i've scheduled", "Claims to have scheduled"),
    ("i have scheduled", "Claims to have scheduled"),
    ("i've sent", "Claims to have sent"),
    ("i have sent", "Claims to have sent"),
    ("calendar invite", "References calendar invites"),
    ("booking confirmed", "Claims booking confirmation"),
    ("meeting is set", "Claims meeting is set"),
    ("i'll have mario call", "Claims control over Mario's actions"),
    ("i'll make sure mario", "Claims control over Mario's actions"),
]

# Personality markers Maurice should use
PERSONALITY_MARKERS = [
    "blacksky",
    "mario",
    "we",
    "our",
    "treasury",
]

# Lead capture phrases
LEAD_CAPTURE_PHRASES = [
    "email",
    "contact",
    "reach you",
    "get in touch",
    "phone",
    "number",
    "best way to reach",
    "follow up",
]

# High-intent indicators in user messages
HIGH_INTENT_INDICATORS = [
    "pricing",
    "price",
    "cost",
    "budget",
    "timeline",
    "when can",
    "schedule",
    "demo",
    "trial",
    "call",
    "meeting",
    "speak with",
    "talk to",
]


def analyze_response_quality(user_message: str, assistant_response: str) -> dict:
    """
    Analyze a single response for quality signals.

    Returns dict with quality metrics and any issues detected.
    """
    user_lower = user_message.lower()
    response_lower = assistant_response.lower()

    # Calculate basic metrics
    user_words = len(user_message.split())
    response_words = len(assistant_response.split())
    length_ratio = response_words / max(user_words, 1)

    # Check for hallucinations
    hallucinations = []
    for pattern, description in HALLUCINATION_PATTERNS:
        if pattern in response_lower:
            hallucinations.append({
                "pattern": pattern,
                "description": description
            })

    # Check personality markers
    personality_count = sum(1 for marker in PERSONALITY_MARKERS if marker in response_lower)
    has_personality = personality_count >= 1

    # Check if response is too short for a complex question
    is_complex_question = user_words > 15 or "?" in user_message
    is_short_response = response_words < 20
    too_short = is_complex_question and is_short_response

    # Check for high-intent signals in user message
    user_high_intent = any(indicator in user_lower for indicator in HIGH_INTENT_INDICATORS)

    # Check if Maurice asked for contact info when appropriate
    asked_for_contact = any(phrase in response_lower for phrase in LEAD_CAPTURE_PHRASES)
    missed_lead_capture = user_high_intent and not asked_for_contact and response_words > 30

    # Calculate overall quality score (0-100)
    quality_score = 100

    # Deductions
    if hallucinations:
        quality_score -= 30 * len(hallucinations)
    if too_short:
        quality_score -= 20
    if not has_personality:
        quality_score -= 10
    if missed_lead_capture:
        quality_score -= 15

    quality_score = max(0, min(100, quality_score))

    # Build issues list
    issues = []
    if hallucinations:
        for h in hallucinations:
            issues.append({
                "type": "hallucination",
                "severity": "high",
                "description": h["description"],
                "pattern": h["pattern"]
            })
    if too_short:
        issues.append({
            "type": "too_short",
            "severity": "medium",
            "description": f"Short response ({response_words} words) to complex question ({user_words} words)"
        })
    if not has_personality:
        issues.append({
            "type": "no_personality",
            "severity": "low",
            "description": "Response lacks Blacksky personality markers"
        })
    if missed_lead_capture:
        issues.append({
            "type": "missed_lead_capture",
            "severity": "medium",
            "description": "High-intent user but no ask for contact info"
        })

    return {
        "quality_score": quality_score,
        "metrics": {
            "user_words": user_words,
            "response_words": response_words,
            "length_ratio": round(length_ratio, 2),
            "personality_markers": personality_count,
            "has_personality": has_personality,
            "user_high_intent": user_high_intent,
            "asked_for_contact": asked_for_contact
        },
        "issues": issues,
        "issue_count": len(issues),
        "has_hallucination": len(hallucinations) > 0,
        "is_flagged": len(issues) > 0 and any(i["severity"] in ["high", "medium"] for i in issues)
    }


def get_quality_metrics(days: int = 7) -> dict:
    """
    Get aggregated quality metrics for responses in the specified period.
    """
    from datetime import timedelta
    from collections import defaultdict

    session = get_session()
    if session is None:
        return {}

    try:
        cutoff = datetime.utcnow() - timedelta(days=days)

        # Get all conversations from the period
        conversations = session.query(Conversation).filter(
            Conversation.created_at >= cutoff,
            Conversation.messages.isnot(None)
        ).all()

        # Analyze all responses
        total_responses = 0
        total_quality_score = 0
        total_response_words = 0
        total_user_words = 0
        personality_count = 0
        lead_capture_count = 0
        high_intent_count = 0
        flagged_responses = []
        issue_counts = defaultdict(int)

        for conv in conversations:
            if not conv.messages:
                continue

            try:
                messages = json.loads(conv.messages)
            except json.JSONDecodeError:
                continue

            # Pair up user/assistant messages
            user_msgs = [m for m in messages if m.get("role") == "user"]
            asst_msgs = [m for m in messages if m.get("role") == "assistant"]

            for i in range(min(len(user_msgs), len(asst_msgs))):
                user_msg = user_msgs[i].get("content", "")
                asst_msg = asst_msgs[i].get("content", "")

                if not user_msg or not asst_msg:
                    continue

                analysis = analyze_response_quality(user_msg, asst_msg)
                total_responses += 1
                total_quality_score += analysis["quality_score"]
                total_response_words += analysis["metrics"]["response_words"]
                total_user_words += analysis["metrics"]["user_words"]

                if analysis["metrics"]["has_personality"]:
                    personality_count += 1
                if analysis["metrics"]["asked_for_contact"]:
                    lead_capture_count += 1
                if analysis["metrics"]["user_high_intent"]:
                    high_intent_count += 1

                # Count issues
                for issue in analysis["issues"]:
                    issue_counts[issue["type"]] += 1

                # Track flagged responses
                if analysis["is_flagged"]:
                    flagged_responses.append({
                        "conversation_id": conv.id,
                        "message_index": i,
                        "user_message": user_msg[:100] + "..." if len(user_msg) > 100 else user_msg,
                        "assistant_response": asst_msg[:100] + "..." if len(asst_msg) > 100 else asst_msg,
                        "quality_score": analysis["quality_score"],
                        "issues": analysis["issues"],
                        "created_at": conv.created_at.isoformat() if conv.created_at else None
                    })

        # Calculate averages
        avg_quality = round(total_quality_score / total_responses, 1) if total_responses > 0 else 0
        avg_response_words = round(total_response_words / total_responses, 1) if total_responses > 0 else 0
        personality_rate = round((personality_count / total_responses) * 100, 1) if total_responses > 0 else 0
        lead_capture_rate = round((lead_capture_count / high_intent_count) * 100, 1) if high_intent_count > 0 else 0

        return {
            "days": days,
            "total_responses": total_responses,
            "avg_quality_score": avg_quality,
            "avg_response_words": avg_response_words,
            "personality_rate": personality_rate,
            "lead_capture_rate": lead_capture_rate,
            "high_intent_responses": high_intent_count,
            "flagged_count": len(flagged_responses),
            "issue_breakdown": dict(issue_counts),
            "flagged_responses": flagged_responses[:20]  # Top 20 flagged
        }

    except Exception as e:
        print(f"Error getting quality metrics: {e}")
        import traceback
        traceback.print_exc()
        return {}
    finally:
        session.close()


def get_flagged_responses(days: int = 7, limit: int = 50) -> list:
    """
    Get responses flagged for quality issues.
    """
    from datetime import timedelta

    session = get_session()
    if session is None:
        return []

    try:
        cutoff = datetime.utcnow() - timedelta(days=days)

        conversations = session.query(Conversation).filter(
            Conversation.created_at >= cutoff,
            Conversation.messages.isnot(None)
        ).order_by(Conversation.created_at.desc()).all()

        flagged = []

        for conv in conversations:
            if len(flagged) >= limit:
                break

            if not conv.messages:
                continue

            try:
                messages = json.loads(conv.messages)
            except json.JSONDecodeError:
                continue

            user_msgs = [m for m in messages if m.get("role") == "user"]
            asst_msgs = [m for m in messages if m.get("role") == "assistant"]

            for i in range(min(len(user_msgs), len(asst_msgs))):
                if len(flagged) >= limit:
                    break

                user_msg = user_msgs[i].get("content", "")
                asst_msg = asst_msgs[i].get("content", "")

                if not user_msg or not asst_msg:
                    continue

                analysis = analyze_response_quality(user_msg, asst_msg)

                if analysis["is_flagged"]:
                    # Get user info
                    user = session.query(User).filter(User.id == conv.user_id).first()

                    flagged.append({
                        "conversation_id": conv.id,
                        "message_index": i,
                        "user_id": conv.user_id,
                        "user_name": user.name if user else "Unknown",
                        "user_message": user_msg,
                        "assistant_response": asst_msg,
                        "quality_score": analysis["quality_score"],
                        "issues": analysis["issues"],
                        "created_at": conv.created_at.isoformat() if conv.created_at else None
                    })

        return flagged

    except Exception as e:
        print(f"Error getting flagged responses: {e}")
        return []
    finally:
        session.close()


def get_hallucination_examples(days: int = 30, limit: int = 20) -> list:
    """
    Get specific examples of hallucinations for review.
    """
    from datetime import timedelta

    session = get_session()
    if session is None:
        return []

    try:
        cutoff = datetime.utcnow() - timedelta(days=days)

        conversations = session.query(Conversation).filter(
            Conversation.created_at >= cutoff,
            Conversation.messages.isnot(None)
        ).order_by(Conversation.created_at.desc()).all()

        hallucinations = []

        for conv in conversations:
            if len(hallucinations) >= limit:
                break

            if not conv.messages:
                continue

            try:
                messages = json.loads(conv.messages)
            except json.JSONDecodeError:
                continue

            asst_msgs = [m for m in messages if m.get("role") == "assistant"]

            for i, msg in enumerate(asst_msgs):
                if len(hallucinations) >= limit:
                    break

                content = msg.get("content", "").lower()

                for pattern, description in HALLUCINATION_PATTERNS:
                    if pattern in content:
                        hallucinations.append({
                            "conversation_id": conv.id,
                            "message_index": i,
                            "pattern": pattern,
                            "description": description,
                            "response_excerpt": msg.get("content", "")[:200],
                            "created_at": conv.created_at.isoformat() if conv.created_at else None
                        })
                        break  # Only report first hallucination per message

        return hallucinations

    except Exception as e:
        print(f"Error getting hallucination examples: {e}")
        return []
    finally:
        session.close()


# ============================================
# Handoff Package Functions
# ============================================

def create_handoff_package(user_id: str) -> dict:
    """
    Create comprehensive handoff package for sales team (Mario).

    Consolidates all user context for warm handoff:
    - Basic user info (name, email, phone, company)
    - Extracted facts from conversations
    - User journey timeline
    - Conversation summary
    - Intent signals
    - Suggested approach based on interests

    Returns dict with all handoff context.
    """
    session = get_session()
    if session is None:
        return {"error": "Database unavailable"}

    try:
        # Get user
        user = session.query(User).filter(User.id == user_id).first()
        if not user:
            return {"error": "User not found"}

        # Get user facts
        facts = session.query(UserFact).filter(
            UserFact.user_id == user_id,
            UserFact.confidence >= 0.6
        ).all()
        facts_dict = {f.fact_type: f.fact_value for f in facts}

        # Get most recent conversation with high score
        best_conversation = (
            session.query(Conversation)
            .filter(Conversation.user_id == user_id)
            .order_by(Conversation.lead_score.desc(), Conversation.created_at.desc())
            .first()
        )

        conversation_summary = None
        lead_score = 1
        interests = []
        if best_conversation:
            conversation_summary = best_conversation.summary
            lead_score = best_conversation.lead_score or 1
            if best_conversation.interests:
                try:
                    interests = json.loads(best_conversation.interests)
                except json.JSONDecodeError:
                    interests = []

        # Get intent signals from user's conversations
        user_intent_signals = []
        conversations = session.query(Conversation).filter(
            Conversation.user_id == user_id,
            Conversation.messages.isnot(None)
        ).all()

        for conv in conversations:
            try:
                messages = json.loads(conv.messages)
                for msg in messages:
                    if msg.get("role") == "user":
                        content = msg.get("content", "").lower()
                        for indicator in HIGH_INTENT_INDICATORS:
                            if indicator in content:
                                if indicator not in user_intent_signals:
                                    user_intent_signals.append(indicator)
            except json.JSONDecodeError:
                continue

        # Generate suggested approach based on available data
        suggested_approach = _generate_approach_recommendation(
            name=user.name,
            company=user.company or facts_dict.get("company"),
            role=facts_dict.get("role"),
            interests=interests,
            intent_signals=user_intent_signals,
            lead_score=lead_score
        )

        return {
            "user": {
                "id": user.id,
                "name": user.name,
                "email": user.email,
                "phone": user.phone,
                "company": user.company or facts_dict.get("company"),
                "status": user.status or "new",
                "first_seen": user.created_at.isoformat() if user.created_at else None,
                "last_seen": user.last_seen.isoformat() if user.last_seen else None
            },
            "facts": facts_dict,
            "journey": get_user_journey(user_id),
            "conversation_summary": conversation_summary,
            "lead_score": lead_score,
            "interests": interests,
            "intent_signals": user_intent_signals,
            "suggested_approach": suggested_approach
        }

    except Exception as e:
        print(f"Error creating handoff package: {e}")
        import traceback
        traceback.print_exc()
        return {"error": str(e)}
    finally:
        session.close()


def _generate_approach_recommendation(
    name: str = None,
    company: str = None,
    role: str = None,
    interests: list = None,
    intent_signals: list = None,
    lead_score: int = 1
) -> str:
    """
    Generate a human-readable approach recommendation for sales.
    """
    parts = []

    # Opener based on lead score
    if lead_score >= 3:
        parts.append("HIGH PRIORITY LEAD.")
    elif lead_score >= 2:
        parts.append("Warm lead with moderate interest.")
    else:
        parts.append("Early-stage contact.")

    # Personalization
    if name and company:
        parts.append(f"Reach out to {name} at {company}.")
    elif name:
        parts.append(f"Follow up with {name}.")
    elif company:
        parts.append(f"Contact at {company}.")

    # Role-based approach
    if role:
        role_lower = role.lower()
        if any(x in role_lower for x in ["cto", "ceo", "founder", "owner", "president"]):
            parts.append("Executive - focus on strategic value and ROI.")
        elif any(x in role_lower for x in ["engineer", "developer", "architect"]):
            parts.append("Technical role - emphasize capabilities and integration.")
        elif any(x in role_lower for x in ["manager", "director", "lead"]):
            parts.append("Management - discuss team efficiency and timelines.")

    # Intent-based suggestions
    if intent_signals:
        if "pricing" in intent_signals or "cost" in intent_signals:
            parts.append("Asked about pricing - prepare quote or pricing discussion.")
        if "demo" in intent_signals or "trial" in intent_signals:
            parts.append("Interested in demo - offer walkthrough.")
        if "timeline" in intent_signals or "schedule" in intent_signals:
            parts.append("Asking about timelines - has potential project in mind.")

    # Interest-based suggestions
    if interests:
        if any("treasury" in i.lower() for i in interests if i):
            parts.append("Treasury focus - highlight federal/government experience.")
        if any("ai" in i.lower() or "automation" in i.lower() for i in interests if i):
            parts.append("AI/automation interest - show relevant case studies.")

    return " ".join(parts) if parts else "Standard follow-up approach."


def get_intent_signals_for_user(user_id: str) -> list:
    """
    Get intent signals specific to a user from their conversations.
    """
    session = get_session()
    if session is None:
        return []

    try:
        signals = []
        conversations = session.query(Conversation).filter(
            Conversation.user_id == user_id,
            Conversation.messages.isnot(None)
        ).all()

        for conv in conversations:
            try:
                messages = json.loads(conv.messages)
                for msg in messages:
                    if msg.get("role") == "user":
                        content = msg.get("content", "").lower()
                        for indicator in HIGH_INTENT_INDICATORS:
                            if indicator in content and indicator not in signals:
                                signals.append(indicator)
            except json.JSONDecodeError:
                continue

        return signals

    except Exception as e:
        print(f"Error getting intent signals for user: {e}")
        return []
    finally:
        session.close()
