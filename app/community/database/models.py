"""
Community database models

MVP scope:
- Posts (check-in)
- Comments
- Reactions (like)

Notes:
- We store `user_id` as a string (JWT uid) to stay consistent with the existing
  diet module and avoid cross-table UUID FK migrations in the thesis timeframe.
- We keep tags as JSON list[str] and snapshots as JSON for flexibility.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.community.constants import DEFAULT_POST_TYPE, REACTION_LIKE
from app.database.models import Base


class CommunityPostModel(Base):
    __tablename__ = "community_posts"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)

    user_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    author_display_name: Mapped[str] = mapped_column(String(64), nullable=False)
    is_anonymous: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    post_type: Mapped[str] = mapped_column(
        String(32),
        default=DEFAULT_POST_TYPE,
        nullable=False,
        index=True,
    )
    mood: Mapped[Optional[str]] = mapped_column(String(32), nullable=True, index=True)

    content: Mapped[str] = mapped_column(Text, nullable=False)
    tags: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    image_urls: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    nutrition_snapshot: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    like_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    comment_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        nullable=False,
        index=True,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )

    __table_args__ = (
        Index("ix_community_posts_created_at_desc", created_at.desc()),
        Index("ix_community_posts_type_created", "post_type", "created_at"),
    )

    def to_dict(self, *, liked_by_me: bool = False) -> dict:
        return {
            "id": str(self.id),
            "user_id": self.user_id,
            "author_display_name": self.author_display_name,
            "is_anonymous": bool(self.is_anonymous),
            "post_type": self.post_type,
            "mood": self.mood,
            "content": self.content,
            "tags": list(self.tags or []),
            "image_urls": list(self.image_urls or []),
            "nutrition_snapshot": self.nutrition_snapshot,
            "like_count": int(self.like_count or 0),
            "comment_count": int(self.comment_count or 0),
            "liked_by_me": bool(liked_by_me),
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class CommunityCommentModel(Base):
    __tablename__ = "community_comments"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)

    post_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("community_posts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    author_display_name: Mapped[str] = mapped_column(String(64), nullable=False)
    is_anonymous: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    content: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        nullable=False,
        index=True,
    )

    __table_args__ = (
        Index("ix_community_comments_post_created", "post_id", "created_at"),
    )

    def to_dict(self) -> dict:
        return {
            "id": str(self.id),
            "post_id": str(self.post_id),
            "user_id": self.user_id,
            "author_display_name": self.author_display_name,
            "is_anonymous": bool(self.is_anonymous),
            "content": self.content,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class CommunityReactionModel(Base):
    __tablename__ = "community_reactions"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    post_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("community_posts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    reaction_type: Mapped[str] = mapped_column(
        String(20),
        default=REACTION_LIKE,
        nullable=False,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        nullable=False,
        index=True,
    )

    __table_args__ = (
        UniqueConstraint(
            "post_id",
            "user_id",
            "reaction_type",
            name="uq_community_reactions_post_user_type",
        ),
        Index("ix_community_reactions_post_user", "post_id", "user_id"),
    )

