"""
Community data access repository.

Implements CRUD for:
- Posts
- Comments
- Reactions (likes)
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional, Sequence

from sqlalchemy import and_, cast, delete, func, select, String

from app.community.constants import DEFAULT_POST_TYPE, REACTION_LIKE
from app.community.database.models import (
    CommunityCommentModel,
    CommunityPostModel,
    CommunityReactionModel,
)
from app.database.session import get_session_context


def _parse_uuid(value: str) -> Optional[uuid.UUID]:
    try:
        return uuid.UUID(str(value))
    except Exception:
        return None


class CommunityRepository:
    # -------------------- Posts --------------------

    async def create_post(
        self,
        *,
        user_id: str,
        author_display_name: str,
        is_anonymous: bool,
        mood: Optional[str],
        content: str,
        tags: Optional[list[str]],
        image_urls: Optional[list[str]],
        nutrition_snapshot: Optional[dict],
    ) -> CommunityPostModel:
        async with get_session_context() as session:
            post = CommunityPostModel(
                user_id=user_id,
                author_display_name=author_display_name,
                is_anonymous=is_anonymous,
                post_type=DEFAULT_POST_TYPE,
                mood=mood,
                content=content,
                tags=tags,
                image_urls=image_urls,
                nutrition_snapshot=nutrition_snapshot,
                like_count=0,
                comment_count=0,
            )
            session.add(post)
            await session.flush()
            await session.refresh(post)
            return post

    async def get_post(self, post_id: str) -> Optional[CommunityPostModel]:
        post_uuid = _parse_uuid(post_id)
        if not post_uuid:
            return None
        async with get_session_context() as session:
            stmt = select(CommunityPostModel).where(CommunityPostModel.id == post_uuid)
            result = await session.execute(stmt)
            return result.scalar_one_or_none()

    async def list_posts(
        self,
        *,
        limit: int,
        offset: int,
        tag: Optional[str] = None,
        mood: Optional[str] = None,
        sort: Optional[str] = None,
    ) -> list[CommunityPostModel]:
        sort_value = (sort or "latest").strip().lower()
        allowed_sorts = {"latest", "need_support", "hot"}
        if sort_value not in allowed_sorts:
            sort_value = "latest"

        need_support_tags = {
            "焦虑",
            "想放弃",
            "暴食后自责",
            "求建议",
        }

        async with get_session_context() as session:
            stmt = select(CommunityPostModel).where(
                CommunityPostModel.post_type == DEFAULT_POST_TYPE
            )

            if mood:
                stmt = stmt.where(CommunityPostModel.mood == mood)

            if tag:
                # Cross-dialect best-effort filter: cast JSON -> text and do an exact
                # string match against JSON-encoded list items: ["tag", ...]
                like_pat = f'%"{tag}"%'
                stmt = stmt.where(cast(CommunityPostModel.tags, String).like(like_pat))

            if sort_value == "hot":
                stmt = (
                    stmt.order_by(
                        CommunityPostModel.like_count.desc(),
                        CommunityPostModel.comment_count.desc(),
                        CommunityPostModel.created_at.desc(),
                    )
                    .limit(limit)
                    .offset(offset)
                )
                result = await session.execute(stmt)
                return list(result.scalars().all())

            if sort_value == "need_support":
                # Cross-dialect and explainable sorting:
                # 1) comment_count asc (prioritize zero replies)
                # 2) help-seeking tags boosted
                # 3) created_at desc
                #
                # We do a bounded over-fetch and then a Python sort to keep
                # behavior consistent across SQLite/Postgres without JSON
                # operator differences.
                fetch_size = min(500, max(int(limit) * 5 + int(offset), int(limit) + int(offset)))
                stmt = (
                    stmt.order_by(
                        CommunityPostModel.comment_count.asc(),
                        CommunityPostModel.created_at.desc(),
                    )
                    .limit(fetch_size)
                    .offset(0)
                )
                result = await session.execute(stmt)
                posts = list(result.scalars().all())

                def _has_need_support_tag(post: CommunityPostModel) -> bool:
                    tags = post.tags or []
                    if not isinstance(tags, list):
                        return False
                    for raw in tags:
                        tag_text = str(raw or "").strip()
                        if tag_text in need_support_tags:
                            return True
                    return False

                def _created_key(post: CommunityPostModel) -> float:
                    created_at = post.created_at or datetime.min
                    try:
                        return created_at.timestamp()
                    except Exception:
                        return 0.0

                posts.sort(
                    key=lambda p: (
                        int(p.comment_count or 0),
                        0 if _has_need_support_tag(p) else 1,
                        -_created_key(p),
                    )
                )
                start = max(0, int(offset))
                end = start + int(limit)
                return posts[start:end]

            # latest (default)
            stmt = (
                stmt.order_by(CommunityPostModel.created_at.desc())
                .limit(limit)
                .offset(offset)
            )
            result = await session.execute(stmt)
            return list(result.scalars().all())

    async def count_posts(
        self,
        *,
        tag: Optional[str] = None,
        mood: Optional[str] = None,
    ) -> int:
        async with get_session_context() as session:
            stmt = select(func.count()).select_from(CommunityPostModel).where(
                CommunityPostModel.post_type == DEFAULT_POST_TYPE
            )

            if mood:
                stmt = stmt.where(CommunityPostModel.mood == mood)

            if tag:
                like_pat = f'%"{tag}"%'
                stmt = stmt.where(cast(CommunityPostModel.tags, String).like(like_pat))

            result = await session.execute(stmt)
            return int(result.scalar() or 0)

    async def increment_post_like_count(
        self,
        *,
        post_id: str,
        delta: int,
    ) -> Optional[int]:
        post_uuid = _parse_uuid(post_id)
        if not post_uuid:
            return None
        async with get_session_context() as session:
            stmt = select(CommunityPostModel).where(CommunityPostModel.id == post_uuid)
            result = await session.execute(stmt)
            post = result.scalar_one_or_none()
            if not post:
                return None
            next_value = int(post.like_count or 0) + int(delta)
            post.like_count = max(0, next_value)
            await session.flush()
            await session.refresh(post)
            return int(post.like_count or 0)

    async def increment_post_comment_count(
        self,
        *,
        post_id: str,
        delta: int,
    ) -> Optional[int]:
        post_uuid = _parse_uuid(post_id)
        if not post_uuid:
            return None
        async with get_session_context() as session:
            stmt = select(CommunityPostModel).where(CommunityPostModel.id == post_uuid)
            result = await session.execute(stmt)
            post = result.scalar_one_or_none()
            if not post:
                return None
            next_value = int(post.comment_count or 0) + int(delta)
            post.comment_count = max(0, next_value)
            await session.flush()
            await session.refresh(post)
            return int(post.comment_count or 0)

    async def delete_post_cascade(self, *, post_id: str) -> bool:
        post_uuid = _parse_uuid(post_id)
        if not post_uuid:
            return False
        async with get_session_context() as session:
            # Explicit cascade for safety across dialects and FK settings.
            await session.execute(
                delete(CommunityReactionModel).where(
                    CommunityReactionModel.post_id == post_uuid
                )
            )
            await session.execute(
                delete(CommunityCommentModel).where(CommunityCommentModel.post_id == post_uuid)
            )
            result = await session.execute(
                delete(CommunityPostModel).where(CommunityPostModel.id == post_uuid)
            )
            return bool(result.rowcount and result.rowcount > 0)

    # -------------------- Comments --------------------

    async def list_comments(
        self,
        *,
        post_id: str,
        limit: int,
        offset: int,
    ) -> list[CommunityCommentModel]:
        post_uuid = _parse_uuid(post_id)
        if not post_uuid:
            return []
        async with get_session_context() as session:
            stmt = (
                select(CommunityCommentModel)
                .where(CommunityCommentModel.post_id == post_uuid)
                .order_by(CommunityCommentModel.created_at.asc())
                .limit(limit)
                .offset(offset)
            )
            result = await session.execute(stmt)
            return list(result.scalars().all())

    async def create_comment(
        self,
        *,
        post_id: str,
        user_id: str,
        author_display_name: str,
        is_anonymous: bool,
        content: str,
    ) -> Optional[CommunityCommentModel]:
        post_uuid = _parse_uuid(post_id)
        if not post_uuid:
            return None
        async with get_session_context() as session:
            comment = CommunityCommentModel(
                post_id=post_uuid,
                user_id=user_id,
                author_display_name=author_display_name,
                is_anonymous=is_anonymous,
                content=content,
            )
            session.add(comment)
            await session.flush()
            await session.refresh(comment)
            return comment

    async def get_comment(self, comment_id: str) -> Optional[CommunityCommentModel]:
        comment_uuid = _parse_uuid(comment_id)
        if not comment_uuid:
            return None
        async with get_session_context() as session:
            stmt = select(CommunityCommentModel).where(CommunityCommentModel.id == comment_uuid)
            result = await session.execute(stmt)
            return result.scalar_one_or_none()

    async def delete_comment(self, *, comment_id: str) -> bool:
        comment_uuid = _parse_uuid(comment_id)
        if not comment_uuid:
            return False
        async with get_session_context() as session:
            result = await session.execute(
                delete(CommunityCommentModel).where(CommunityCommentModel.id == comment_uuid)
            )
            return bool(result.rowcount and result.rowcount > 0)

    # -------------------- Reactions --------------------

    async def has_reaction(
        self,
        *,
        post_id: str,
        user_id: str,
        reaction_type: str = REACTION_LIKE,
    ) -> bool:
        post_uuid = _parse_uuid(post_id)
        if not post_uuid:
            return False
        async with get_session_context() as session:
            stmt = select(func.count()).select_from(CommunityReactionModel).where(
                and_(
                    CommunityReactionModel.post_id == post_uuid,
                    CommunityReactionModel.user_id == user_id,
                    CommunityReactionModel.reaction_type == reaction_type,
                )
            )
            result = await session.execute(stmt)
            return int(result.scalar() or 0) > 0

    async def create_reaction(
        self,
        *,
        post_id: str,
        user_id: str,
        reaction_type: str = REACTION_LIKE,
    ) -> bool:
        post_uuid = _parse_uuid(post_id)
        if not post_uuid:
            return False
        async with get_session_context() as session:
            reaction = CommunityReactionModel(
                post_id=post_uuid,
                user_id=user_id,
                reaction_type=reaction_type,
            )
            session.add(reaction)
            try:
                await session.flush()
            except Exception:
                # Uniqueness constraint might be violated under concurrent requests.
                # Treat as "already liked".
                #
                # Important: a failed flush leaves the session in a pending-rollback
                # state. We must rollback here because the exception is swallowed and
                # our session context manager will otherwise attempt to commit.
                await session.rollback()
                return False
            return True

    async def delete_reaction(
        self,
        *,
        post_id: str,
        user_id: str,
        reaction_type: str = REACTION_LIKE,
    ) -> bool:
        post_uuid = _parse_uuid(post_id)
        if not post_uuid:
            return False
        async with get_session_context() as session:
            result = await session.execute(
                delete(CommunityReactionModel).where(
                    and_(
                        CommunityReactionModel.post_id == post_uuid,
                        CommunityReactionModel.user_id == user_id,
                        CommunityReactionModel.reaction_type == reaction_type,
                    )
                )
            )
            return bool(result.rowcount and result.rowcount > 0)

    async def get_user_liked_post_ids(
        self,
        *,
        user_id: str,
        post_ids: Sequence[str],
    ) -> set[str]:
        post_uuids: list[uuid.UUID] = []
        for pid in post_ids:
            parsed = _parse_uuid(pid)
            if parsed:
                post_uuids.append(parsed)
        if not post_uuids:
            return set()
        async with get_session_context() as session:
            stmt = (
                select(CommunityReactionModel.post_id)
                .where(
                    and_(
                        CommunityReactionModel.user_id == user_id,
                        CommunityReactionModel.reaction_type == REACTION_LIKE,
                        CommunityReactionModel.post_id.in_(post_uuids),
                    )
                )
            )
            result = await session.execute(stmt)
            return {str(pid) for pid in result.scalars().all()}
