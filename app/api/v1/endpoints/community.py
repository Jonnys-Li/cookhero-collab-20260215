"""
Community API endpoints.

MVP: 打卡互助广场
- Feed (posts)
- Create post (optional images)
- Post detail + comments
- Add comment
- Like toggle
- Delete (author-only)
- Lightweight AI suggestions (tags, reply draft)
"""

from __future__ import annotations

import base64
import logging
from typing import Any, Literal, Optional

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field, field_validator, model_validator

from app.community import community_service
from app.community.constants import ALLOWED_TAGS
from app.config import settings
from app.security.dependencies import check_message_security
from app.utils.image_storage import upload_to_imgbb

logger = logging.getLogger(__name__)
router = APIRouter()

MAX_IMAGE_SIZE_MB = 10.0
SUPPORTED_IMAGE_FORMATS = ["image/jpeg", "image/png", "image/gif", "image/webp"]


def _get_user_id(request: Request) -> str:
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        raise HTTPException(status_code=401, detail="需要登录")
    return str(user_id)


def _get_username(request: Request) -> Optional[str]:
    username = getattr(request.state, "username", None)
    return str(username) if username else None


class ImageData(BaseModel):
    """Image data for community posts."""

    data: str
    mime_type: str = "image/jpeg"

    @field_validator("mime_type")
    @classmethod
    def validate_mime_type(cls, v: str) -> str:
        if v not in SUPPORTED_IMAGE_FORMATS:
            raise ValueError(
                f"不支持的图片格式: {v}。支持的格式: {SUPPORTED_IMAGE_FORMATS}"
            )
        return v

    @field_validator("data")
    @classmethod
    def validate_data(cls, v: str) -> str:
        try:
            decoded_size = len(base64.b64decode(v))
            max_size = MAX_IMAGE_SIZE_MB * 1024 * 1024
            if decoded_size > max_size:
                raise ValueError(f"图片大小超过限制 ({MAX_IMAGE_SIZE_MB}MB)")
        except Exception as e:
            if "图片大小超过限制" in str(e):
                raise
            raise ValueError("无效的 base64 图片数据")
        return v


class CreatePostRequest(BaseModel):
    is_anonymous: bool = True
    post_type: Optional[str] = None  # reserved for future; MVP always check_in
    mood: Optional[str] = Field(None, max_length=32)
    content: str = Field(..., min_length=1, max_length=800)
    tags: Optional[list[str]] = Field(default=None, max_length=5)
    images: Optional[list[ImageData]] = Field(default=None, max_length=4)
    nutrition_snapshot: Optional[dict[str, Any]] = None

    @field_validator("tags")
    @classmethod
    def validate_tags(cls, v: Optional[list[str]]) -> Optional[list[str]]:
        if not v:
            return v
        allowed = set(ALLOWED_TAGS)
        out: list[str] = []
        seen = set()
        for raw in v:
            tag = str(raw or "").strip()
            if not tag or tag in seen:
                continue
            if tag not in allowed:
                raise ValueError(f"不支持的标签: {tag}")
            seen.add(tag)
            out.append(tag)
        return out[:5]


class CreateCommentRequest(BaseModel):
    content: str = Field(..., min_length=1, max_length=300)
    is_anonymous: bool = True


class ToggleReactionResponse(BaseModel):
    liked: bool
    like_count: int


class DeleteResponse(BaseModel):
    message: str


class AISuggestRequest(BaseModel):
    mode: Literal["tags", "reply", "card"]
    content: Optional[str] = Field(None, max_length=800)
    post_id: Optional[str] = None

    @model_validator(mode="after")
    def validate_mode_payload(self):
        if self.mode == "tags":
            if not (self.content and str(self.content).strip()):
                raise ValueError("content is required for tags mode")
        if self.mode == "reply":
            if not (self.post_id and str(self.post_id).strip()):
                raise ValueError("post_id is required for reply mode")
        if self.mode == "card":
            if not (self.post_id and str(self.post_id).strip()):
                raise ValueError("post_id is required for card mode")
        return self


# -------------------- Feed --------------------


@router.get("/community/feed")
async def get_feed(
    request: Request,
    limit: int = Query(20, ge=1, le=50),
    offset: int = Query(0, ge=0, le=10000),
    tag: Optional[str] = Query(None, max_length=30),
    mood: Optional[str] = Query(None, max_length=32),
) -> dict[str, Any]:
    user_id = _get_user_id(request)
    return await community_service.get_feed(
        user_id=user_id,
        limit=limit,
        offset=offset,
        tag=tag,
        mood=mood,
    )


# -------------------- Posts --------------------


@router.post("/community/posts", status_code=201)
async def create_post(payload: CreatePostRequest, request: Request) -> dict[str, Any]:
    user_id = _get_user_id(request)
    username = _get_username(request)

    image_urls: Optional[list[str]] = None
    if payload.images:
        storage_config = settings.image_storage
        if not storage_config.enabled or not storage_config.api_key:
            raise HTTPException(
                status_code=503,
                detail="图片上传未配置，请设置 IMGBB_STORAGE_API_KEY 或关闭带图发帖。",
            )

        image_urls = []
        for img in payload.images:
            upload_result = await upload_to_imgbb(img.data, img.mime_type)
            if not upload_result:
                raise HTTPException(status_code=502, detail="图片上传失败，请重试")
            image_urls.append(
                str(upload_result.get("display_url") or upload_result.get("url") or "").strip()
            )

        if any(not u for u in image_urls):
            raise HTTPException(status_code=502, detail="图片上传失败，请重试")

    try:
        post = await community_service.create_post(
            user_id=user_id,
            username=username,
            is_anonymous=payload.is_anonymous,
            mood=payload.mood,
            content=payload.content,
            tags=payload.tags,
            image_urls=image_urls,
            nutrition_snapshot=payload.nutrition_snapshot,
        )
        return post
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/community/posts/{post_id}")
async def get_post_detail(
    post_id: str,
    request: Request,
    comment_limit: int = Query(50, ge=1, le=50),
    comment_offset: int = Query(0, ge=0, le=10000),
) -> dict[str, Any]:
    user_id = _get_user_id(request)
    detail = await community_service.get_post_detail(
        user_id=user_id,
        post_id=post_id,
        comment_limit=comment_limit,
        comment_offset=comment_offset,
    )
    if not detail:
        raise HTTPException(status_code=404, detail="帖子不存在")
    return {"post": detail.post, "comments": detail.comments}


@router.delete("/community/posts/{post_id}", response_model=DeleteResponse)
async def delete_post(post_id: str, request: Request) -> DeleteResponse:
    user_id = _get_user_id(request)
    post = await community_service.repository.get_post(post_id)
    if not post:
        raise HTTPException(status_code=404, detail="帖子不存在")
    if str(post.user_id) != str(user_id):
        raise HTTPException(status_code=403, detail="无权删除该帖子")
    ok = await community_service.repository.delete_post_cascade(post_id=post_id)
    if not ok:
        raise HTTPException(status_code=404, detail="帖子不存在")
    return DeleteResponse(message="帖子已删除")


# -------------------- Comments --------------------


@router.post("/community/posts/{post_id}/comments", status_code=201)
async def add_comment(
    post_id: str,
    payload: CreateCommentRequest,
    request: Request,
) -> dict[str, Any]:
    user_id = _get_user_id(request)
    username = _get_username(request)

    try:
        comment = await community_service.add_comment(
            user_id=user_id,
            username=username,
            post_id=post_id,
            content=payload.content,
            is_anonymous=payload.is_anonymous,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    if not comment:
        raise HTTPException(status_code=404, detail="帖子不存在")
    return comment


@router.delete("/community/comments/{comment_id}", response_model=DeleteResponse)
async def delete_comment(comment_id: str, request: Request) -> DeleteResponse:
    user_id = _get_user_id(request)
    comment = await community_service.repository.get_comment(comment_id)
    if not comment:
        raise HTTPException(status_code=404, detail="评论不存在")
    if str(comment.user_id) != str(user_id):
        raise HTTPException(status_code=403, detail="无权删除该评论")

    ok = await community_service.delete_comment(user_id=user_id, comment_id=comment_id)
    if not ok:
        raise HTTPException(status_code=404, detail="评论不存在")
    return DeleteResponse(message="评论已删除")


# -------------------- Reactions --------------------


@router.post(
    "/community/posts/{post_id}/reactions/toggle",
    response_model=ToggleReactionResponse,
)
async def toggle_reaction(post_id: str, request: Request) -> ToggleReactionResponse:
    user_id = _get_user_id(request)
    result = await community_service.toggle_like(user_id=user_id, post_id=post_id)
    if not result:
        raise HTTPException(status_code=404, detail="帖子不存在")
    return ToggleReactionResponse(**result)


# -------------------- AI Suggest --------------------


@router.post("/community/ai/suggest")
async def ai_suggest(payload: AISuggestRequest, request: Request) -> dict[str, Any]:
    user_id = _get_user_id(request)

    try:
        if payload.mode == "tags":
            secured = await check_message_security(payload.content or "", request)
            tags = await community_service.suggest_tags(user_id=user_id, content=secured)
            return {"tags": tags}

        if payload.mode == "card":
            post = await community_service.repository.get_post(payload.post_id or "")
            if not post:
                raise HTTPException(status_code=404, detail="帖子不存在")
            secured_post_content = await check_message_security(post.content, request)
            card = await community_service.suggest_empathy_card_for_post(
                user_id=user_id,
                post_id=payload.post_id or "",
                post_content_override=secured_post_content,
            )
            return {"card": card}

        # mode == "reply"
        # Fetch post content and run security check before sending to LLM.
        post = await community_service.repository.get_post(payload.post_id or "")
        if not post:
            raise HTTPException(status_code=404, detail="帖子不存在")
        secured_post_content = await check_message_security(post.content, request)

        reply = await community_service.suggest_reply_for_post(
            user_id=user_id,
            post_id=payload.post_id or "",
            post_content_override=secured_post_content,
        )
        return {"reply": reply}
    except HTTPException:
        raise
    except Exception as exc:
        logger.warning("community ai suggest failed: %s", exc)
        raise HTTPException(status_code=503, detail="AI 建议暂不可用，请稍后重试")
