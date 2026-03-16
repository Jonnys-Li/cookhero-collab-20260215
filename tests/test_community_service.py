from dataclasses import dataclass
from typing import Any, Optional

import pytest

from app.community.service import CommunityService


@dataclass
class FakePost:
    id: str
    user_id: str
    author_display_name: str
    is_anonymous: bool
    post_type: str
    mood: Optional[str]
    content: str
    tags: list[str]
    image_urls: list[str]
    nutrition_snapshot: Optional[dict]
    like_count: int = 0
    comment_count: int = 0

    def to_dict(self, *, liked_by_me: bool = False) -> dict[str, Any]:
        return {
            "id": self.id,
            "user_id": self.user_id,
            "author_display_name": self.author_display_name,
            "is_anonymous": self.is_anonymous,
            "post_type": self.post_type,
            "mood": self.mood,
            "content": self.content,
            "tags": self.tags,
            "image_urls": self.image_urls,
            "nutrition_snapshot": self.nutrition_snapshot,
            "like_count": self.like_count,
            "comment_count": self.comment_count,
            "liked_by_me": liked_by_me,
            "created_at": "2026-03-12T00:00:00",
            "updated_at": "2026-03-12T00:00:00",
        }


@dataclass
class FakeComment:
    id: str
    post_id: str
    user_id: str
    author_display_name: str
    is_anonymous: bool
    content: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "post_id": self.post_id,
            "user_id": self.user_id,
            "author_display_name": self.author_display_name,
            "is_anonymous": self.is_anonymous,
            "content": self.content,
            "created_at": "2026-03-12T00:00:00",
        }


class FakeInvoker:
    def __init__(self, content: str):
        self._content = content

    async def ainvoke(self, *_args, **_kwargs):
        return type("Resp", (), {"content": self._content})()


class FakeRepo:
    def __init__(self):
        self.posts: dict[str, FakePost] = {}
        self.comments: dict[str, FakeComment] = {}
        self.reactions: set[tuple[str, str, str]] = set()

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
    ) -> FakePost:
        post = FakePost(
            id="post-1",
            user_id=user_id,
            author_display_name=author_display_name,
            is_anonymous=is_anonymous,
            post_type="check_in",
            mood=mood,
            content=content,
            tags=list(tags or []),
            image_urls=list(image_urls or []),
            nutrition_snapshot=nutrition_snapshot,
        )
        self.posts[post.id] = post
        return post

    async def get_post(self, post_id: str) -> Optional[FakePost]:
        return self.posts.get(post_id)

    async def list_posts(self, *, limit: int, offset: int, tag=None, mood=None):
        values = list(self.posts.values())
        return values[offset : offset + limit]

    async def count_posts(self, *, tag=None, mood=None):
        return len(self.posts)

    async def get_user_liked_post_ids(self, *, user_id: str, post_ids):
        liked = set()
        for post_id in post_ids:
            if (post_id, user_id, "like") in self.reactions:
                liked.add(post_id)
        return liked

    async def list_comments(self, *, post_id: str, limit: int, offset: int):
        values = [c for c in self.comments.values() if c.post_id == post_id]
        return values[offset : offset + limit]

    async def create_comment(
        self,
        *,
        post_id: str,
        user_id: str,
        author_display_name: str,
        is_anonymous: bool,
        content: str,
    ) -> Optional[FakeComment]:
        if post_id not in self.posts:
            return None
        comment = FakeComment(
            id="c1",
            post_id=post_id,
            user_id=user_id,
            author_display_name=author_display_name,
            is_anonymous=is_anonymous,
            content=content,
        )
        self.comments[comment.id] = comment
        return comment

    async def increment_post_comment_count(self, *, post_id: str, delta: int):
        post = self.posts.get(post_id)
        if not post:
            return None
        post.comment_count = max(0, post.comment_count + delta)
        return post.comment_count

    async def has_reaction(self, *, post_id: str, user_id: str, reaction_type: str = "like"):
        return (post_id, user_id, reaction_type) in self.reactions

    async def create_reaction(self, *, post_id: str, user_id: str, reaction_type: str = "like"):
        key = (post_id, user_id, reaction_type)
        if key in self.reactions:
            return False
        self.reactions.add(key)
        return True

    async def delete_reaction(self, *, post_id: str, user_id: str, reaction_type: str = "like"):
        key = (post_id, user_id, reaction_type)
        if key not in self.reactions:
            return False
        self.reactions.remove(key)
        return True

    async def increment_post_like_count(self, *, post_id: str, delta: int):
        post = self.posts.get(post_id)
        if not post:
            return None
        post.like_count = max(0, post.like_count + delta)
        return post.like_count

    async def get_comment(self, comment_id: str) -> Optional[FakeComment]:
        return self.comments.get(comment_id)

    async def delete_comment(self, *, comment_id: str) -> bool:
        if comment_id not in self.comments:
            return False
        del self.comments[comment_id]
        return True


def test_create_post_anonymous_generates_display_name(run):
    repo = FakeRepo()
    service = CommunityService(repository=repo)  # type: ignore[arg-type]

    post = run(
        service.create_post(
            user_id="u1",
            username="alice",
            is_anonymous=True,
            mood="neutral",
            content="今天按计划吃了晚餐，继续坚持。",
            tags=["坚持打卡"],
        )
    )

    assert post["is_anonymous"] is True
    assert post["author_display_name"].startswith("匿名小厨")
    assert post["author_display_name"] != "alice"


def test_toggle_like_idempotent(run):
    repo = FakeRepo()
    service = CommunityService(repository=repo)  # type: ignore[arg-type]

    post = run(
        service.create_post(
            user_id="u1",
            username="alice",
            is_anonymous=True,
            mood="neutral",
            content="打卡",
            tags=["坚持打卡"],
        )
    )
    post_id = post["id"]

    first = run(service.toggle_like(user_id="u2", post_id=post_id))
    assert first and first["liked"] is True
    assert first["like_count"] == 1

    second = run(service.toggle_like(user_id="u2", post_id=post_id))
    assert second and second["liked"] is False
    assert second["like_count"] == 0


def test_delete_comment_requires_owner(run):
    repo = FakeRepo()
    service = CommunityService(repository=repo)  # type: ignore[arg-type]

    post = run(
        service.create_post(
            user_id="u1",
            username="alice",
            is_anonymous=True,
            mood="neutral",
            content="打卡",
            tags=["坚持打卡"],
        )
    )
    post_id = post["id"]
    comment = run(
        service.add_comment(
            user_id="u1",
            username="alice",
            post_id=post_id,
            content="谢谢大家",
            is_anonymous=True,
        )
    )
    assert comment is not None

    # Different user cannot delete
    ok = run(service.delete_comment(user_id="u2", comment_id=comment["id"]))
    assert ok is False


def test_suggest_tags_filters_to_allowed_set(monkeypatch, run):
    repo = FakeRepo()
    service = CommunityService(repository=repo)  # type: ignore[arg-type]

    monkeypatch.setattr(
        service,
        "_get_invoker",
        lambda: FakeInvoker('{"tags": ["减脂", "不合法", "坚持打卡", "焦虑"]}'),
    )

    tags = run(service.suggest_tags(user_id="u1", content="今天有点焦虑，但还是打卡了"))
    assert "减脂" in tags
    assert "坚持打卡" in tags
    assert "不合法" not in tags


def test_suggest_reply_rejects_shame_words(monkeypatch, run):
    repo = FakeRepo()
    # Seed a post for reply context
    repo.posts["post-1"] = FakePost(
        id="post-1",
        user_id="u1",
        author_display_name="匿名小厨0001",
        is_anonymous=True,
        post_type="check_in",
        mood="guilty",
        content="我今天吃多了很内疚。",
        tags=["暴食后自责"],
        image_urls=[],
        nutrition_snapshot=None,
    )

    service = CommunityService(repository=repo)  # type: ignore[arg-type]

    monkeypatch.setattr(
        service,
        "_get_invoker",
        lambda: FakeInvoker('{"reply": "你太差了，怎么又暴食？"}'),
    )

    with pytest.raises(ValueError):
        run(service.suggest_reply_for_post(user_id="u1", post_id="post-1"))


def test_suggest_empathy_card_returns_text(monkeypatch, run):
    repo = FakeRepo()
    repo.posts["post-1"] = FakePost(
        id="post-1",
        user_id="u1",
        author_display_name="匿名小厨0001",
        is_anonymous=True,
        post_type="check_in",
        mood="anxious",
        content="今天有点焦虑，晚饭没按计划吃。",
        tags=["焦虑", "求建议"],
        image_urls=[],
        nutrition_snapshot=None,
    )

    service = CommunityService(repository=repo)  # type: ignore[arg-type]

    monkeypatch.setattr(
        service,
        "_get_invoker",
        lambda: FakeInvoker('{"card": "听起来你今天压力有点大，但你愿意记录已经很不容易。先做一次深呼吸，给自己一个小目标：下一顿选一份清淡高蛋白，再慢慢找回节奏。"}'),
    )

    card = run(service.suggest_empathy_card_for_post(user_id="u1", post_id="post-1"))
    assert isinstance(card, str)
    assert len(card) > 10


def test_suggest_empathy_card_rejects_shame_words(monkeypatch, run):
    repo = FakeRepo()
    repo.posts["post-1"] = FakePost(
        id="post-1",
        user_id="u1",
        author_display_name="匿名小厨0001",
        is_anonymous=True,
        post_type="check_in",
        mood="guilty",
        content="我今天吃多了很内疚。",
        tags=["暴食后自责"],
        image_urls=[],
        nutrition_snapshot=None,
    )

    service = CommunityService(repository=repo)  # type: ignore[arg-type]

    monkeypatch.setattr(
        service,
        "_get_invoker",
        lambda: FakeInvoker('{"card": "你太差了，怎么又暴食？"}'),
    )

    with pytest.raises(ValueError):
        run(service.suggest_empathy_card_for_post(user_id="u1", post_id="post-1"))


def test_polish_post_content_returns_text(monkeypatch, run):
    repo = FakeRepo()
    service = CommunityService(repository=repo)  # type: ignore[arg-type]

    monkeypatch.setattr(
        service,
        "_get_invoker",
        lambda: FakeInvoker('{"polished": "今天状态一般，但我还是记录了饮食。希望大家给我一些更容易坚持的小建议，我也会慢慢调整节奏。"}'),
    )

    polished = run(service.polish_post_content(user_id="u1", content="我好难受"))
    assert isinstance(polished, str)
    assert len(polished) > 10
