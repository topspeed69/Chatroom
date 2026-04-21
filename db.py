from __future__ import annotations

from datetime import datetime
from typing import List

from sqlmodel import Field, SQLModel, Session, create_engine, select

DATABASE_URL = "sqlite:///chat.db"
engine = create_engine(DATABASE_URL, echo=False, connect_args={"check_same_thread": False})


class User(SQLModel, table=True):
    name: str = Field(primary_key=True)
    joined_at: datetime = Field(default_factory=datetime.utcnow)


class Message(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    username: str
    content: str
    msg_type: str = Field(default="message")  # "message" or "image"
    extra_data: str | None = Field(default=None)  # JSON string for images (url, psnr, etc.)
    timestamp: datetime = Field(default_factory=datetime.utcnow)


def init_db() -> None:
    """Create the SQLite database and tables if they do not exist."""
    SQLModel.metadata.create_all(engine)


def get_session() -> Session:
    """Create a new database session."""
    return Session(engine)


def get_or_create_user(name: str) -> User:
    """Get an existing user or create a new one. Merges with oldest message timestamp if user is new but has history."""
    with get_session() as session:
        user = session.get(User, name)
        if user:
            return user
        
        # If user doesn't exist in User table, check if they have existing messages
        statement = select(Message).where(Message.username == name).order_by(Message.timestamp.asc()).limit(1)
        oldest_msg = session.exec(statement).first()
        
        joined_at = oldest_msg.timestamp if oldest_msg else datetime.utcnow()
        user = User(name=name, joined_at=joined_at)
        session.add(user)
        session.commit()
        session.refresh(user)
        return user


def save_message(username: str, content: str, msg_type: str = "message", extra_data: str | None = None) -> Message:
    """Insert a new chat message into the database."""
    with get_session() as session:
        message = Message(username=username, content=content, msg_type=msg_type, extra_data=extra_data)
        session.add(message)
        session.commit()
        session.refresh(message)
        return message


def save_image_message(username: str, filename: str, url: str, compression_info: dict) -> Message:
    """Insert a new image message into the database."""
    import json
    extra = {
        "url": url,
        "filename": filename,
        "compression": compression_info
    }
    return save_message(username, content=f"Uploaded image: {filename}", msg_type="image", extra_data=json.dumps(extra))


def get_messages_since(since: datetime) -> List[Message]:
    """Return all messages since a specific datetime."""
    with get_session() as session:
        statement = select(Message).where(Message.timestamp >= since).order_by(Message.timestamp.asc())
        results = session.exec(statement).all()
        return list(results)


def get_recent_messages(limit: int = 50) -> List[Message]:
    """Return the most recent messages from the database."""
    with get_session() as session:
        statement = select(Message).order_by(Message.id.desc()).limit(limit)
        results = session.exec(statement).all()
        return list(reversed(results))
