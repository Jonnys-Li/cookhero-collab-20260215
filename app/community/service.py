"""
Community service layer.

Keeps business logic out of endpoints:
- Anonymous display name policy
- Like/comment counters update policy
- Feed enrichment with liked_by_me
- Lightweight AI suggestions (tags, empathetic reply draft)
"""

from __future__ import annotations

import json
import logging
import re
import secrets
from dataclasses import dataclass
from typing import Any, Optional

from pydantic import BaseModel, Field, ValidationError

from app.community.constants import (
    ALLOWED_MOODS,
    ALLOWED_TAGS,
    ANON_DISPLAY_PREFIX,
    REACTION_LIKE,
    SHAME_WORDS,
)
from app.community.database.repository import CommunityRepository
from app.config import settings
from app.llm import LLMProvider, llm_context

logger = logging.getLogger(__name__)


class TagSuggestResult(BaseModel):
    tags: list[str] = Field(default_factory=list, max_length=8)


class ReplySuggestResult(BaseModel):
    reply: str


class CardSuggestResult(BaseModel):
    card: str


def _make_anon_display_name() -> str:
    # 0000-9999; simple and non-identifying.
    suffix = f"{secrets.randbelow(10000):04d}"
    return f"{ANON_DISPLAY_PREFIX}{suffix}"


def _normalize_tags(tags: Optional[list[str]]) -> list[str]:
    if not tags:
        return []
    out: list[str] = []
    seen = set()
    for raw in tags:
        tag = str(raw or "").strip()
        if not tag:
            continue
        if tag in seen:
            continue
        seen.add(tag)
        out.append(tag)
        if len(out) >= 5:
            break
    return out


def _filter_allowed_tags(tags: list[str]) -> list[str]:
    allowed = set(ALLOWED_TAGS)
    return [t for t in tags if t in allowed]


def _extract_json(text: str) -> Optional[dict[str, Any]]:
    """
    Best-effort JSON extraction for LLM outputs.

    Tries:
    1) direct json.loads
    2) substring between the first '{' and the last '}'.
    """
    raw = (text or "").strip()
    if not raw:
        return None
    try:
        value = json.loads(raw)
        return value if isinstance(value, dict) else None
    except Exception:
        pass

    start = raw.find("{")
    end = raw.rfind("}")
    if start < 0 or end <= start:
        return None

    candidate = raw[start : end + 1]
    try:
        value = json.loads(candidate)
        return value if isinstance(value, dict) else None
    except Exception:
        return None


def _contains_shame_words(text: str) -> bool:
    content = (text or "").strip()
    if not content:
        return False
    for word in SHAME_WORDS:
        if word and word in content:
            return True
    return False


@dataclass
class CommunityPostDetail:
    post: dict[str, Any]
    comments: list[dict[str, Any]]


class CommunityService:
    def __init__(self, repository: Optional[CommunityRepository] = None):
        self.repository = repository or CommunityRepository()
        self._provider: Optional[LLMProvider] = None
        self._invoker = None

    # -------------------- Core CRUD --------------------

    async def create_post(
        self,
        *,
        user_id: str,
        username: Optional[str],
        is_anonymous: bool = True,
        mood: Optional[str] = None,
        content: str,
        tags: Optional[list[str]] = None,
        image_urls: Optional[list[str]] = None,
        nutrition_snapshot: Optional[dict] = None,
    ) -> dict[str, Any]:
        if mood is not None:
            mood = str(mood).strip() or None
            if mood and mood not in ALLOWED_MOODS:
                mood = None

        content = str(content or "").strip()
        if not content:
            raise ValueError("content cannot be empty")

        normalized_tags = _normalize_tags(tags)

        display_name: str
        if is_anonymous:
            display_name = _make_anon_display_name()
        else:
            display_name = str(username or "").strip() or "用户"

        post = await self.repository.create_post(
            user_id=user_id,
            author_display_name=display_name,
            is_anonymous=is_anonymous,
            mood=mood,
            content=content,
            tags=normalized_tags or None,
            image_urls=image_urls or None,
            nutrition_snapshot=nutrition_snapshot,
        )
        return post.to_dict(liked_by_me=False)

    async def get_feed(
        self,
        *,
        user_id: str,
        limit: int,
        offset: int,
        tag: Optional[str] = None,
        mood: Optional[str] = None,
    ) -> dict[str, Any]:
        posts = await self.repository.list_posts(
            limit=limit,
            offset=offset,
            tag=str(tag).strip() if tag else None,
            mood=str(mood).strip() if mood else None,
        )
        total = await self.repository.count_posts(
            tag=str(tag).strip() if tag else None,
            mood=str(mood).strip() if mood else None,
        )

        post_ids = [str(p.id) for p in posts]
        liked_set = await self.repository.get_user_liked_post_ids(
            user_id=user_id,
            post_ids=post_ids,
        )

        return {
            "posts": [p.to_dict(liked_by_me=str(p.id) in liked_set) for p in posts],
            "total": total,
        }

    async def get_post_detail(
        self,
        *,
        user_id: str,
        post_id: str,
        comment_limit: int = 50,
        comment_offset: int = 0,
    ) -> Optional[CommunityPostDetail]:
        post = await self.repository.get_post(post_id)
        if not post:
            return None
        comments = await self.repository.list_comments(
            post_id=post_id,
            limit=comment_limit,
            offset=comment_offset,
        )
        liked = await self.repository.has_reaction(
            post_id=post_id,
            user_id=user_id,
            reaction_type=REACTION_LIKE,
        )
        return CommunityPostDetail(
            post=post.to_dict(liked_by_me=liked),
            comments=[c.to_dict() for c in comments],
        )

    async def add_comment(
        self,
        *,
        user_id: str,
        username: Optional[str],
        post_id: str,
        content: str,
        is_anonymous: bool = True,
    ) -> Optional[dict[str, Any]]:
        post = await self.repository.get_post(post_id)
        if not post:
            return None

        content = str(content or "").strip()
        if not content:
            raise ValueError("content cannot be empty")

        if is_anonymous:
            display_name = _make_anon_display_name()
        else:
            display_name = str(username or "").strip() or "用户"

        comment = await self.repository.create_comment(
            post_id=post_id,
            user_id=user_id,
            author_display_name=display_name,
            is_anonymous=is_anonymous,
            content=content,
        )
        if not comment:
            return None

        await self.repository.increment_post_comment_count(post_id=post_id, delta=1)
        return comment.to_dict()

    async def toggle_like(
        self,
        *,
        user_id: str,
        post_id: str,
    ) -> Optional[dict[str, Any]]:
        post = await self.repository.get_post(post_id)
        if not post:
            return None

        liked = await self.repository.has_reaction(
            post_id=post_id,
            user_id=user_id,
            reaction_type=REACTION_LIKE,
        )

        if liked:
            deleted = await self.repository.delete_reaction(
                post_id=post_id,
                user_id=user_id,
                reaction_type=REACTION_LIKE,
            )
            if deleted:
                await self.repository.increment_post_like_count(post_id=post_id, delta=-1)
            liked = False if deleted else True
        else:
            created = await self.repository.create_reaction(
                post_id=post_id,
                user_id=user_id,
                reaction_type=REACTION_LIKE,
            )
            if created:
                await self.repository.increment_post_like_count(post_id=post_id, delta=1)
            liked = True

        refreshed = await self.repository.get_post(post_id)
        like_count = int(refreshed.like_count) if refreshed else int(post.like_count or 0)
        return {"liked": liked, "like_count": like_count}

    async def delete_post(self, *, user_id: str, post_id: str) -> bool:
        post = await self.repository.get_post(post_id)
        if not post:
            return False
        if str(post.user_id) != str(user_id):
            return False
        return await self.repository.delete_post_cascade(post_id=post_id)

    async def delete_comment(self, *, user_id: str, comment_id: str) -> bool:
        comment = await self.repository.get_comment(comment_id)
        if not comment:
            return False
        if str(comment.user_id) != str(user_id):
            return False
        deleted = await self.repository.delete_comment(comment_id=comment_id)
        if deleted:
            await self.repository.increment_post_comment_count(
                post_id=str(comment.post_id),
                delta=-1,
            )
        return deleted

    # -------------------- AI Suggestions --------------------

    def _get_invoker(self):
        if self._invoker is not None:
            return self._invoker
        self._provider = LLMProvider(settings.llm)
        self._invoker = self._provider.create_invoker(
            "fast",
            temperature=0.2,
            streaming=False,
        )
        return self._invoker

    async def suggest_tags(self, *, user_id: str, content: str) -> list[str]:
        content = str(content or "").strip()
        if not content:
            raise ValueError("content cannot be empty")

        tag_vocab = "、".join(ALLOWED_TAGS)
        system_prompt = (
            "你是一个社区内容标签助手。"
            "你只输出严格 JSON，不要解释，不要 markdown。"
        )
        user_prompt = (
            "请为这段用户打卡内容选择 3-5 个标签。"
            "标签必须从下列候选中选择，不能发明新标签：\n"
            f"{tag_vocab}\n\n"
            f"内容：{content}\n\n"
            '输出 JSON 格式：{"tags": ["标签1", "标签2", "..."]}'
        )

        invoker = self._get_invoker()
        with llm_context("community_ai", user_id=user_id):
            response = await invoker.ainvoke(
                [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                response_format={"type": "json_object"},
            )

        raw = str(getattr(response, "content", response))
        payload = _extract_json(raw)
        if not payload:
            raise ValueError("AI response is not valid JSON")

        try:
            parsed = TagSuggestResult.model_validate(payload)
        except ValidationError as exc:
            raise ValueError(f"AI tags payload invalid: {exc}") from exc

        normalized = _filter_allowed_tags(_normalize_tags(parsed.tags))
        if len(normalized) < 1:
            raise ValueError("AI tags empty after normalization")
        # Ensure at most 5 tags; keep first ones.
        return normalized[:5]

    async def suggest_reply_for_post(
        self,
        *,
        user_id: str,
        post_id: str,
        post_content_override: Optional[str] = None,
    ) -> str:
        post = await self.repository.get_post(post_id)
        if not post:
            raise ValueError("post not found")

        post_content = (
            str(post_content_override).strip()
            if post_content_override is not None
            else post.content
        )

        tag_vocab = "、".join(ALLOWED_TAGS)
        system_prompt = (
            "你是一个互助打卡广场的共情式评论助手。"
            "你的目标是用温和、非责备的语气，帮助对方降低焦虑并给出一个低风险的小行动建议。"
            "只输出严格 JSON，不要解释，不要 markdown。"
        )
        user_prompt = (
            "请为下面这条帖子生成一条共情评论建议。要求：\n"
            "1) 中文；2) 不羞辱不评判；3) 包含 1 个低风险行动建议；"
            "4) 长度尽量在 100-150 字；5) 不要提及你是 AI。\n"
            f"可用标签候选（仅用于理解，不必输出）：{tag_vocab}\n\n"
            f"帖子内容：{post_content}\n"
            f"帖子情绪(mood)：{post.mood or 'unknown'}\n"
            f"帖子标签(tags)：{post.tags or []}\n\n"
            '输出 JSON 格式：{"reply": "..." }'
        )

        invoker = self._get_invoker()
        with llm_context("community_ai", user_id=user_id):
            response = await invoker.ainvoke(
                [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                response_format={"type": "json_object"},
            )

        raw = str(getattr(response, "content", response))
        payload = _extract_json(raw)
        if not payload:
            raise ValueError("AI response is not valid JSON")

        try:
            parsed = ReplySuggestResult.model_validate(payload)
        except ValidationError as exc:
            raise ValueError(f"AI reply payload invalid: {exc}") from exc

        reply = str(parsed.reply or "").strip()
        reply = re.sub(r"\s+", " ", reply)
        if not reply:
            raise ValueError("AI reply is empty")
        if _contains_shame_words(reply):
            raise ValueError("AI reply contains shame/blame words")
        if len(reply) > 220:
            reply = reply[:220]
        return reply

    async def suggest_empathy_card_for_post(
        self,
        *,
        user_id: str,
        post_id: str,
        post_content_override: Optional[str] = None,
    ) -> str:
        """
        Generate a short "empathetic coach card" for a post.

        This is not a comment draft; it's an inline helper card for the feed UI.
        """
        post = await self.repository.get_post(post_id)
        if not post:
            raise ValueError("post not found")

        post_content = (
            str(post_content_override).strip()
            if post_content_override is not None
            else post.content
        )

        system_prompt = (
            "你是一个互助打卡广场的共情式点评助手。"
            "你的目标是用温和、非责备的语气，帮助对方降低焦虑，并给出一个低风险的小行动建议。"
            "只输出严格 JSON，不要解释，不要 markdown。"
        )
        user_prompt = (
            "请为下面这条帖子生成一段“共情点评小卡”。要求：\n"
            "1) 中文；2) 不羞辱不评判；3) 不要给医疗诊断；4) 包含 1 个低风险行动建议；\n"
            "5) 尽量 80-140 字；6) 不要提及你是 AI；7) 用一段话即可。\n\n"
            f"帖子内容：{post_content}\n"
            f"帖子情绪(mood)：{post.mood or 'unknown'}\n"
            f"帖子标签(tags)：{post.tags or []}\n\n"
            '输出 JSON 格式：{"card": "..." }'
        )

        invoker = self._get_invoker()
        with llm_context("community_ai", user_id=user_id):
            response = await invoker.ainvoke(
                [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                response_format={"type": "json_object"},
            )

        raw = str(getattr(response, "content", response))
        payload = _extract_json(raw)
        if not payload:
            raise ValueError("AI response is not valid JSON")

        try:
            parsed = CardSuggestResult.model_validate(payload)
        except ValidationError as exc:
            raise ValueError(f"AI card payload invalid: {exc}") from exc

        card = str(parsed.card or "").strip()
        card = re.sub(r"\s+", " ", card)
        if not card:
            raise ValueError("AI card is empty")
        if _contains_shame_words(card):
            raise ValueError("AI card contains shame/blame words")
        if len(card) > 240:
            card = card[:240]
        return card


community_service = CommunityService()
