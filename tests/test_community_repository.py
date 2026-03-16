from __future__ import annotations

import asyncio

import app.community.database.repository as community_repo_mod
from app.community.database.repository import CommunityRepository


def test_community_repository_posts_comments_reactions(monkeypatch, sqlite_session_context):
    monkeypatch.setattr(community_repo_mod, "get_session_context", sqlite_session_context)

    repo = CommunityRepository()

    async def _run():
        user_id = "u-community"

        post = await repo.create_post(
            user_id=user_id,
            author_display_name="A",
            is_anonymous=True,
            mood="happy",
            content="hello world",
            tags=["t1", "t2"],
            image_urls=["https://example.com/img.png"],
            nutrition_snapshot={"kcal": 123},
        )
        post_id = str(post.id)

        assert await repo.get_post("not-a-uuid") is None
        fetched = await repo.get_post(post_id)
        assert fetched is not None and fetched.content == "hello world"

        posts = await repo.list_posts(limit=10, offset=0, tag="t1")
        assert len(posts) == 1
        assert posts[0].id == post.id

        assert await repo.count_posts(tag="t1") == 1
        assert await repo.count_posts(tag="missing") == 0

        assert await repo.increment_post_like_count(post_id=post_id, delta=1) == 1
        assert await repo.increment_post_comment_count(post_id=post_id, delta=2) == 2
        assert await repo.increment_post_like_count(post_id="bad", delta=1) is None

        comment = await repo.create_comment(
            post_id=post_id,
            user_id=user_id,
            author_display_name="A",
            is_anonymous=False,
            content="nice",
        )
        assert comment is not None
        comment_id = str(comment.id)

        assert await repo.create_comment(
            post_id="bad",
            user_id=user_id,
            author_display_name="A",
            is_anonymous=False,
            content="nope",
        ) is None

        comments = await repo.list_comments(post_id=post_id, limit=10, offset=0)
        assert len(comments) == 1
        assert comments[0].content == "nice"

        assert await repo.get_comment("bad") is None
        fetched_comment = await repo.get_comment(comment_id)
        assert fetched_comment is not None and fetched_comment.content == "nice"

        assert await repo.delete_comment(comment_id="bad") is False
        assert await repo.delete_comment(comment_id=comment_id) is True

        # Reactions
        assert await repo.has_reaction(post_id=post_id, user_id=user_id) is False
        assert await repo.create_reaction(post_id=post_id, user_id=user_id) is True
        assert await repo.has_reaction(post_id=post_id, user_id=user_id) is True

        # Duplicate should be treated as "already liked" and return False.
        assert await repo.create_reaction(post_id=post_id, user_id=user_id) is False

        liked = await repo.get_user_liked_post_ids(user_id=user_id, post_ids=[post_id, "bad"])
        assert liked == {post_id}

        assert await repo.delete_reaction(post_id=post_id, user_id=user_id) is True
        assert await repo.has_reaction(post_id=post_id, user_id=user_id) is False

        # Cascade delete should remove everything.
        assert await repo.delete_post_cascade(post_id="bad") is False
        assert await repo.delete_post_cascade(post_id=post_id) is True
        assert await repo.get_post(post_id) is None

    asyncio.run(_run())

