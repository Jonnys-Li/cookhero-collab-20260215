from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import HTTPException


def _build_anon_request():
    return SimpleNamespace(state=SimpleNamespace())


@pytest.fixture
def patch_community_sqlite(monkeypatch, sqlite_session_context):
    import app.community.database.repository as community_repo_module

    monkeypatch.setattr(community_repo_module, "get_session_context", sqlite_session_context)
    return community_repo_module


def test_create_post_runs_security_check_and_uses_sanitized_content(
    run,
    build_request,
    monkeypatch,
    patch_community_sqlite,
):
    import app.api.v1.endpoints.community as community_endpoint
    from app.community.database.repository import CommunityRepository

    async def _fake_check_message_security(message: str, request):
        assert message == "raw-content"
        return "sanitized-content"

    monkeypatch.setattr(community_endpoint, "check_message_security", _fake_check_message_security)

    request = build_request(user_id="u_comm_1")
    created = run(
        community_endpoint.create_post(
            community_endpoint.CreatePostRequest(
                content="raw-content",
                is_anonymous=True,
                tags=["焦虑"],
            ),
            request,
        )
    )
    assert created["content"] == "sanitized-content"

    repo = CommunityRepository()
    stored = run(repo.get_post(created["id"]))
    assert stored is not None
    assert stored.content == "sanitized-content"


def test_create_post_blocked_by_security_check_does_not_persist(
    run,
    build_request,
    monkeypatch,
    patch_community_sqlite,
):
    import app.api.v1.endpoints.community as community_endpoint
    from app.community.database.repository import CommunityRepository

    async def _fake_check_message_security(message: str, request):
        raise HTTPException(status_code=400, detail="blocked")

    monkeypatch.setattr(community_endpoint, "check_message_security", _fake_check_message_security)

    repo = CommunityRepository()
    before = run(repo.count_posts())

    request = build_request(user_id="u_comm_2")
    with pytest.raises(HTTPException) as exc:
        run(
            community_endpoint.create_post(
                community_endpoint.CreatePostRequest(
                    content="bad",
                    is_anonymous=True,
                ),
                request,
            )
    )
    assert exc.value.status_code == 400

    total = run(repo.count_posts())
    assert total == before


def test_add_comment_runs_security_check_and_uses_sanitized_content(
    run,
    build_request,
    monkeypatch,
    patch_community_sqlite,
):
    import app.api.v1.endpoints.community as community_endpoint
    from app.community.database.repository import CommunityRepository

    repo = CommunityRepository()
    post = run(
        repo.create_post(
            user_id="u_comm_3",
            author_display_name="anon",
            is_anonymous=True,
            mood=None,
            content="post",
            tags=None,
            image_urls=None,
            nutrition_snapshot=None,
        )
    )

    async def _fake_check_message_security(message: str, request):
        assert message == "raw-comment"
        return "sanitized-comment"

    monkeypatch.setattr(community_endpoint, "check_message_security", _fake_check_message_security)

    request = build_request(user_id="u_comm_3")
    created = run(
        community_endpoint.add_comment(
            str(post.id),
            community_endpoint.CreateCommentRequest(content="raw-comment", is_anonymous=True),
            request,
        )
    )
    assert created["content"] == "sanitized-comment"

    comments = run(repo.list_comments(post_id=str(post.id), limit=10, offset=0))
    assert len(comments) == 1
    assert comments[0].content == "sanitized-comment"


def test_add_comment_blocked_by_security_check_does_not_persist(
    run,
    build_request,
    monkeypatch,
    patch_community_sqlite,
):
    import app.api.v1.endpoints.community as community_endpoint
    from app.community.database.repository import CommunityRepository

    repo = CommunityRepository()
    post = run(
        repo.create_post(
            user_id="u_comm_4",
            author_display_name="anon",
            is_anonymous=True,
            mood=None,
            content="post",
            tags=None,
            image_urls=None,
            nutrition_snapshot=None,
        )
    )

    async def _fake_check_message_security(message: str, request):
        raise HTTPException(status_code=400, detail="blocked")

    monkeypatch.setattr(community_endpoint, "check_message_security", _fake_check_message_security)

    request = build_request(user_id="u_comm_4")
    with pytest.raises(HTTPException) as exc:
        run(
            community_endpoint.add_comment(
                str(post.id),
                community_endpoint.CreateCommentRequest(content="bad", is_anonymous=True),
                request,
            )
        )
    assert exc.value.status_code == 400

    comments = run(repo.list_comments(post_id=str(post.id), limit=10, offset=0))
    assert comments == []

    refreshed = run(repo.get_post(str(post.id)))
    assert refreshed is not None
    assert int(refreshed.comment_count or 0) == 0


def test_feed_sort_need_support_prioritizes_zero_comment_posts(
    run,
    build_request,
    patch_community_sqlite,
):
    import app.api.v1.endpoints.community as community_endpoint
    from app.community.database.repository import CommunityRepository
    from app.community import community_service

    repo = CommunityRepository()
    p0 = run(
        repo.create_post(
            user_id="u_comm_5",
            author_display_name="anon",
            is_anonymous=True,
            mood=None,
            content="need support",
            tags=["焦虑"],
            image_urls=None,
            nutrition_snapshot=None,
        )
    )
    p1 = run(
        repo.create_post(
            user_id="u_comm_5",
            author_display_name="anon",
            is_anonymous=True,
            mood=None,
            content="has comment",
            tags=None,
            image_urls=None,
            nutrition_snapshot=None,
        )
    )
    # Add 1 comment to p1 so its comment_count becomes 1.
    _ = run(
        community_service.add_comment(
            user_id="u_comm_5",
            username=None,
            post_id=str(p1.id),
            content="ok",
            is_anonymous=True,
        )
    )

    request = build_request(user_id="u_comm_5")
    feed = run(
        community_endpoint.get_feed(
            request,
            limit=10,
            offset=0,
            tag=None,
            mood=None,
            sort="need_support",
        )
    )
    posts = feed.get("posts") or []
    assert len(posts) >= 2
    assert posts[0]["id"] == str(p0.id)
