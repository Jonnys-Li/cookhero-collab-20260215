# app/database/models.py
"""
SQLAlchemy ORM models for CookHero.
Defines database schema for conversations, messages, user profiles,
long-term memory, and conversation summaries.
"""

import uuid
from datetime import datetime
from typing import List, Optional

from sqlalchemy import (
    Column,
    DateTime,
    Enum as SQLEnum,
    ForeignKey,
    Index,
    JSON,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    """Base class for all ORM models."""
    pass


# ==================== User Model ====================

class UserModel(Base):
    """ORM model for application users."""

    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    username: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    occupation: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    bio: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )

    __table_args__ = (
        Index("ix_users_username", "username", unique=True),
    )

    def to_dict(self) -> dict:
        return {
            "id": str(self.id),
            "username": self.username,
            "occupation": self.occupation,
            "bio": self.bio,
            "created_at": self.created_at.isoformat(),
        }


class ConversationModel(Base):
    """ORM model for conversation sessions."""

    __tablename__ = "conversations"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )
    # Optional user identifier for multi-user support
    user_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, index=True)
    # Optional title/summary for the conversation
    title: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    # Metadata for extensibility (e.g., tags, preferences)
    metadata_: Mapped[Optional[dict]] = mapped_column("metadata", JSON, nullable=True)
    
    # Compressed context summary for older messages
    compressed_summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # Number of messages included in the compressed summary
    compressed_message_count: Mapped[int] = mapped_column(default=0, nullable=False)

    # Relationship to messages
    messages: Mapped[List["MessageModel"]] = relationship(
        "MessageModel",
        back_populates="conversation",
        cascade="all, delete-orphan",
        order_by="MessageModel.created_at",
    )

    __table_args__ = (
        Index("ix_conversations_user_updated", "user_id", "updated_at"),
    )

    def to_dict(self) -> dict:
        """Serialize conversation to dict for API responses."""
        return {
            "id": str(self.id),
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "user_id": self.user_id,
            "title": self.title,
            "message_count": len(self.messages) if self.messages else 0,
            "last_message_preview": (
                self.messages[-1].content[:80] if self.messages else None
            ),
            "compressed_summary": self.compressed_summary,
            "compressed_message_count": self.compressed_message_count,
        }


class MessageModel(Base):
    """ORM model for individual messages in a conversation."""

    __tablename__ = "messages"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("conversations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    role: Mapped[str] = mapped_column(
        String(20), nullable=False  # "user" or "assistant"
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )
    # Optional fields for RAG metadata
    sources: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    intent: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    thinking: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)

    # Relationship to conversation
    conversation: Mapped["ConversationModel"] = relationship(
        "ConversationModel", back_populates="messages"
    )

    __table_args__ = (
        Index("ix_messages_conv_created", "conversation_id", "created_at"),
    )

    def to_dict(self) -> dict:
        """Serialize message to dict for API responses."""
        return {
            "id": str(self.id),
            "role": self.role,
            "content": self.content,
            "timestamp": self.created_at.isoformat(),
            "sources": self.sources,
            "intent": self.intent,
            "thinking": self.thinking,
        }


class KnowledgeDocumentModel(Base):
    """
    Unified knowledge document model for all document types.
    Stores both public documents (HowToCook recipes/tips) and personal documents.
    For public documents, user_id is NULL.
    """

    __tablename__ = "knowledge_documents"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    # NULL for public documents (GLOBAL), actual user_id for personal documents
    user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=True
    )
    dish_name: Mapped[str] = mapped_column(String(255), nullable=False)
    category: Mapped[str] = mapped_column(String(100), nullable=False)
    difficulty: Mapped[str] = mapped_column(String(50), nullable=False)
    # "recipes" for public recipes/tips, "personal" for user-owned documents
    data_source: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    # "recipes", "tips", "personal" - more specific type
    source_type: Mapped[str] = mapped_column(String(32), nullable=False)
    # Original file path or identifier
    source: Mapped[str] = mapped_column(String(512), nullable=False)
    # Whether this is a dish index document
    is_dish_index: Mapped[bool] = mapped_column(default=False, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.now, onupdate=datetime.now, nullable=False
    )

    __table_args__ = (
        Index("ix_knowledge_docs_user_category", "user_id", "category"),
        Index("ix_knowledge_docs_data_source", "data_source"),
        Index("ix_knowledge_docs_source_type", "source_type"),
    )

    def to_dict(self) -> dict:
        return {
            "id": str(self.id),
            "user_id": str(self.user_id) if self.user_id else "GLOBAL",
            "dish_name": self.dish_name,
            "category": self.category,
            "difficulty": self.difficulty,
            "data_source": self.data_source,
            "source_type": self.source_type,
            "source": self.source,
            "is_dish_index": self.is_dish_index,
            "content": self.content,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }

    def to_metadata(self) -> dict:
        """Convert to metadata dict for vector store."""
        return {
            "source": self.source,
            "parent_id": None,  # Will be set when creating chunks
            "dish_name": self.dish_name,
            "category": self.category,
            "difficulty": self.difficulty,
            "is_dish_index": self.is_dish_index,
            "data_source": self.data_source,
            "user_id": str(self.user_id) if self.user_id else "GLOBAL",
            "source_type": self.source_type,
        }
