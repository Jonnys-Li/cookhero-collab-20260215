import asyncio
import json
import logging
from dataclasses import dataclass, field
from typing import Any, AsyncGenerator, Callable, Dict, List, Optional

from app.api.v1.endpoints import user
from app.config import settings
from app.database.document_repository import document_repository
from app.context import ContextCompressor, ContextManager
from app.conversation import (
    IntentDetectionResult,
    IntentDetector,
    LLMOrchestrator,
    QueryRewriter,
    conversation_repository,
)
from app.services.rag_service import rag_service_instance, RetrievalResult
from app.tools.web_search import (
    WebSearchDecision,
    WebSearchResult,
    web_search_tool,
)

logger = logging.getLogger(__name__)


# =============================================================================
# Data Classes
# =============================================================================


@dataclass
class ExtraOptions:
    """Optional features that can be enabled per request."""

    web_search: bool = False
    # Future extensibility: add more options here
    # deep_reasoning: bool = False
    # multimodal: bool = False

    @classmethod
    def from_dict(cls, data: Optional[Dict[str, Any]]) -> "ExtraOptions":
        if not data:
            return cls()
        return cls(
            web_search=data.get("web_search", False),
        )


@dataclass
class UnifiedSource:
    """
    Unified source structure for frontend display.

    Attributes:
        type: Source type - "rag" for knowledge base, "web" for web search
        info: Display text describing the source
        url: Optional URL for web sources (clickable link)
    """

    type: str  # "rag" | "web"
    info: str
    url: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        result = {"type": self.type, "info": self.info}
        if self.url:
            result["url"] = self.url
        return result

    @classmethod
    def from_rag_source(cls, source_dict: Dict[str, Any]) -> "UnifiedSource":
        """Convert RAG service source to unified format."""
        info = source_dict.get("info") or source_dict.get("title") or "CookHero 知识库"
        return cls(
            type="rag",
            info=info,
            url=source_dict.get("url"),
        )

    @classmethod
    def from_web_result(cls, result: WebSearchResult) -> "UnifiedSource":
        """Convert web search result to unified format."""
        # Use title as info for cleaner display
        info = f"{result.title}" if result.title else result.source
        return cls(
            type="web",
            info=info,
            url=result.url,
        )


@dataclass
class ChatContext:
    """Holds all context needed during chat processing."""

    conv_id: str
    message: str
    user_id: Optional[str]
    options: ExtraOptions
    history: List[Dict]
    history_dicts: List[Dict[str, str]]
    history_text: str
    compressed_summary: Optional[str]
    compressed_count: int

    # Mutable state during processing
    sources: List[UnifiedSource] = field(default_factory=list)
    thinking_steps: List[str] = field(default_factory=list)
    web_search_context: str = ""
    rag_context: str = ""
    rewritten_query: str = ""


# =============================================================================
# System Prompt
# =============================================================================

SYSTEM_PROMPT = """
你是 CookHero，一位专业、可靠且富有耐心的智能烹饪助手。
你的职责是基于当前对话上下文，为用户提供**准确、可执行、符合真实厨房场景的回答**。

【你可以提供的帮助】

1. 查询并讲解菜谱与具体做法  
   - 包括步骤、时间、火候、注意事项

2. 提供实用的烹饪技巧与经验建议  
   - 口味调整、失败补救、处理方法

3. 根据用户条件进行菜品推荐  
   - 食材、人数、用餐场景、偏好等

4. 回答厨房与烹饪相关的问题  
   - 器具使用、准备流程、常见问题

5. 其他合理请求

【回答原则（非常重要）】

1. **以“能直接照做”为目标**
- 给出清晰步骤和具体建议
- 避免空泛描述或泛泛而谈

2. **严格依赖上下文**
- 当前系统消息中可能包含：
  - 压缩后的对话摘要
  - 用户最近的原始消息
  - （如有）来自知识库的参考内容
- 不要忽略这些信息，也不要引入未出现的假设条件

3. **尊重检索结果**
- 若提供了知识库内容，应该判断其相关性并合理引用，如果无关则忽略
- 若检索信息不足，可补充通用且安全的烹饪常识

【不确定或信息不足时】

- 若问题不够明确，可自然地向用户追问关键条件
- 不要在信息不足的情况下强行给出具体结论

【安全与质量底线】

- 优先推荐安全、合理、健康的烹饪方式
- 对时间、火候、生熟等关键点保持谨慎
- 不给出明显存在安全风险的建议

【表达与风格】

- 语气：友好、耐心、专业，不居高临下
- 长度：简洁但信息充分，避免冗余
- 用词：贴近日常厨房语境，避免学术或营销腔
- 表情符号：多使用一些emoji符号来增强表达效果，不仅仅在标题行使用，正文中也要穿插着使用
- 输出格式：使用Markdown语法
"""


# =============================================================================
# ConversationService
# =============================================================================


class ConversationService:
    """
    Manages conversations with LLM and RAG integration.

    Context building strategy:
    1. System Message - Base system prompt
    2. Compressed Summary - Summary of compressed messages (if exists)
    3. Uncompressed Messages - Original messages not yet compressed (history[compressed_count:])
    4. Extra System Prompt - RAG context if applicable

    Key invariant: Every message is either in compressed_summary or in context as original.
    """

    # Number of recent uncompressed messages to keep before considering compression
    RECENT_MESSAGES_LIMIT = 10
    # Number of messages to compress each time
    COMPRESSION_THRESHOLD = 6

    def __init__(self):
        """Initialize the conversation service with modular components."""
        self.context_manager = ContextManager(
            system_prompt=SYSTEM_PROMPT,
        )
        self.context_compressor = ContextCompressor(
            llm_type="normal",
            compression_threshold=self.COMPRESSION_THRESHOLD,
            recent_messages_limit=self.RECENT_MESSAGES_LIMIT,
        )
        self.llm_orchestrator = LLMOrchestrator(llm_type="normal")
        self.intent_detector = IntentDetector(llm_type="fast")
        self.query_rewriter = QueryRewriter(llm_type="fast")

    # =========================================================================
    # Main Chat Entry Point
    # =========================================================================

    async def chat(
        self,
        message: str,
        conversation_id: Optional[str] = None,
        user_id: Optional[str] = None,
        stream: bool = True,
        extra_options: Optional[Dict[str, Any]] = None,
    ) -> AsyncGenerator[str, None]:
        """
        Process a chat message and generate a response.

        Yields SSE-formatted events:
        - {"type": "intent", "data": {...}} - Detected intent
        - {"type": "thinking", "content": "..."} - Thinking step
        - {"type": "text", "content": "..."} - Text chunk
        - {"type": "sources", "data": [...]} - Sources (unified format)
        - {"type": "done", "conversation_id": "..."} - Completion signal

        Args:
            message: The user's message
            conversation_id: Optional existing conversation ID
            user_id: Optional user ID for personalization and memory
            stream: Whether to stream the response
            extra_options: Optional features like {"web_search": true}
        """
        # Phase 1: Initialize context
        ctx = await self._initialize_context(
            message=message,
            conversation_id=conversation_id,
            user_id=user_id,
            extra_options=extra_options,
        )

        # Phase 2: Intent Detection
        intent_result = await self._detect_intent(ctx)
        yield f"data: {json.dumps({'type': 'intent', 'data': {'need_rag': intent_result.need_rag, 'intent': intent_result.intent.value, 'reason': intent_result.reason}})}\n\n"

        yield self._emit_thinking(ctx, f"🔍 意图识别完成: {intent_result.intent.value}")
        yield self._emit_thinking(ctx,
            f"📋 是否需要检索: {'是' if intent_result.need_rag else '否'}"
        )
        yield self._emit_thinking(ctx, f"💭 判断依据: {intent_result.reason}")

        logger.info(
            "chat route need_rag=%s intent=%s reason=%s history_len=%d",
            intent_result.need_rag,
            intent_result.intent.value,
            intent_result.reason[:120],
            len(ctx.history),
        )

        # Phase 3: Web Search (if enabled and proactive)
        web_search_decision: Optional[WebSearchDecision] = None
        if ctx.options.web_search:
            web_search_decision, events = await self._process_web_search_decision(ctx)
            for event in events:
                yield event

            # Execute proactive web search if confidence is high
            if web_search_decision and web_search_decision.should_search:
                events = await self._execute_web_search(ctx, web_search_decision)
                for event in events:
                    yield event

        # Phase 4: RAG Retrieval (if needed) - Only prepare data, don't generate response
        if intent_result.need_rag:
            async for event in self._prepare_rag_context(
                ctx=ctx,
                web_search_decision=web_search_decision,
            ):
                yield event
        else:
            # No RAG needed, just emit thinking
            yield self._emit_thinking(ctx, "💬 无需检索知识库，直接回答...")

        # Phase 5: Unified output - Sources and Response Generation
        # Always emit sources (may be empty list if no sources collected)
        sources_data = [s.to_dict() for s in ctx.sources]
        yield f"data: {json.dumps({'type': 'sources', 'data': sources_data})}\n\n"

        # Generate response with all collected context
        yield self._emit_thinking(ctx, "🤖 开始生成回答...")

        full_response = ""
        async for chunk in self._generate_response(ctx):
            full_response += chunk
            yield f"data: {json.dumps({'type': 'text', 'content': chunk})}\n\n"

        # Phase 6: Save response and complete
        await self._save_response(ctx, full_response, intent_result)
        yield f"data: {json.dumps({'type': 'done', 'conversation_id': ctx.conv_id})}\n\n"

        # Trigger async context compression
        asyncio.create_task(
            self.context_compressor.maybe_compress(ctx.conv_id, conversation_repository)
        )

    # =========================================================================
    # Phase 1: Context Initialization
    # =========================================================================

    async def _initialize_context(
        self,
        message: str,
        conversation_id: Optional[str],
        user_id: Optional[str],
        extra_options: Optional[Dict[str, Any]],
    ) -> ChatContext:
        """Initialize chat context with conversation data."""
        options = ExtraOptions.from_dict(extra_options)

        # Get or create conversation
        conversation = await conversation_repository.get_or_create(
            conversation_id, user_id=user_id
        )
        conv_id = str(conversation.id)

        # Add user message
        await conversation_repository.add_message(
            conversation_id=conv_id,
            role="user",
            content=message,
        )

        # Load history
        history = await conversation_repository.get_history(conv_id, limit=100) or []
        compressed_summary, compressed_count = (
            await conversation_repository.get_compressed_summary(conv_id)
        )

        # Build history structures (append sources to assistant content)
        history_dicts = [
            {
                "role": h["role"],
                "content": self._format_content_with_sources(h["content"], h.get("sources"))
                if h["role"] == "assistant"
                else h["content"],
            }
            for h in history
        ]
        history_text = self.context_manager.build_history_text(
            history=history_dicts,
            compressed_count=compressed_count,
            compressed_summary=compressed_summary,
        )

        return ChatContext(
            conv_id=conv_id,
            message=message,
            user_id=user_id,
            options=options,
            history=history,
            history_dicts=history_dicts,
            history_text=history_text,
            compressed_summary=compressed_summary,
            compressed_count=compressed_count,
        )

    # =========================================================================
    # Phase 2: Intent Detection
    # =========================================================================

    async def _detect_intent(self, ctx: ChatContext) -> IntentDetectionResult:
        """Detect user intent from message and history."""
        return await self.intent_detector.detect(ctx.message, ctx.history_text)

    # =========================================================================
    # Phase 3: Web Search Processing
    # =========================================================================

    async def _process_web_search_decision(
        self,
        ctx: ChatContext,
    ) -> tuple[Optional[WebSearchDecision], List[str]]:
        """
        Process web search decision.

        Returns:
            Tuple of (decision, list of SSE events to yield)
        """
        events = []
        events.append(self._emit_thinking(ctx, "🌐 正在判断是否需要 Web 搜索..."))

        decision = await web_search_tool.decide_search(
            query=ctx.message,
            document_summary=document_repository.get_metadata_options(user_id=ctx.user_id),
            history_text=ctx.history_text,
        )

        events.append(
            self._emit_thinking(
                ctx,
                f"🌐 搜索关键词: {decision.search_params.query if decision.search_params else 'None'}，搜索置信度: {decision.confidence}/10，判断: {decision.reason}",
            )
        )

        return decision, events

    async def _execute_web_search(
        self,
        ctx: ChatContext,
        decision: WebSearchDecision,
    ) -> List[str]:
        """
        Execute web search and update context.

        Returns:
            List of SSE events to yield
        """
        events = []

        if not decision.search_params:
            return events

        events.append(self._emit_thinking(ctx, "🌐 正在执行 Web 搜索..."))

        search_results = await web_search_tool.execute_search(decision.search_params)

        if search_results:
            events.append(
                self._emit_thinking(ctx, f"🌐 Web 搜索找到 {len(search_results)} 条结果")
            )

            # Log top results
            for i, result in enumerate(search_results[:3]):
                events.append(
                    self._emit_thinking(
                        ctx, f"  🔗 [{i+1}] {result.title} ({result.source})"
                    )
                )
            if len(search_results) > 3:
                events.append(
                    self._emit_thinking(ctx, f"  ...还有 {len(search_results) - 3} 条结果")
                )

            # Update context
            ctx.web_search_context = web_search_tool.format_results_for_context(
                search_results
            )
            ctx.sources.extend(
                [UnifiedSource.from_web_result(r) for r in search_results]
            )
        else:
            events.append(self._emit_thinking(ctx, "🌐 Web 搜索未找到相关结果"))

        return events

    # =========================================================================
    # Phase 4: RAG Context Preparation
    # =========================================================================

    async def _prepare_rag_context(
        self,
        ctx: ChatContext,
        web_search_decision: Optional[WebSearchDecision],
    ) -> AsyncGenerator[str, None]:
        """
        Prepare RAG context by rewriting query and retrieving documents.

        This method only prepares data (sources, rag_context, rewritten_query).
        It does NOT emit sources or generate the final response.

        Yields:
            SSE thinking events only.
        """
        yield self._emit_thinking(ctx, "⏳ 正在结合对话历史重写查询语句...")

        try:
            # Query rewriting
            ctx.rewritten_query = await self.query_rewriter.rewrite(
                current_query=ctx.message,
                history_text=ctx.history_text,
            )
            yield self._emit_thinking(ctx, f"✍️ 重写后的查询语句: {ctx.rewritten_query}")

            # RAG retrieval
            yield self._emit_thinking(ctx, "🔎 正在从 CookHero 知识库中检索相关资料...")

            retrieval_result = await rag_service_instance.retrieve(
                ctx.rewritten_query,
                skip_rewrite=True,
                user_id=ctx.user_id,
            )

            # Process retrieval results (updates ctx.sources and ctx.rag_context)
            async for event in self._process_retrieval_results(
                ctx=ctx,
                retrieval_result=retrieval_result,
                web_search_decision=web_search_decision,
            ):
                yield event

        except Exception as e:
            logger.error(f"RAG error: {e}", exc_info=True)
            yield self._emit_thinking(ctx, f"❌ 检索遇到问题: {str(e)[:50]}，改为直接回答。")


    async def _process_retrieval_results(
        self,
        ctx: ChatContext,
        retrieval_result: RetrievalResult,
        web_search_decision: Optional[WebSearchDecision],
    ) -> AsyncGenerator[str, None]:
        """Process RAG retrieval results and handle fallback web search."""
        doc_count = len(retrieval_result.documents)

        # Convert RAG sources to unified format
        if retrieval_result.sources:
            for source in retrieval_result.sources:
                ctx.sources.append(UnifiedSource.from_rag_source(source))

        # Store RAG context
        ctx.rag_context = retrieval_result.context

        if doc_count:
            yield self._emit_thinking(ctx, f"📚 检索到 {doc_count} 条相关资料")

            # Log top documents
            for i, doc in enumerate(retrieval_result.documents[:3]):
                doc_title = doc.metadata.get("dish_name", "")
                doc_difficulty = doc.metadata.get("difficulty", "")
                doc_category = doc.metadata.get("category", "")
                doc_preview = doc.page_content[:200].replace("\n", " ")
                if len(doc.page_content) > 200:
                    doc_preview += "..."
                yield self._emit_thinking(
                    ctx,
                    f"  📄 [{i+1}] {doc_title} (难度: {doc_difficulty}, 分类: {doc_category}): {doc_preview}"
                )

            if doc_count > 3:
                yield self._emit_thinking(ctx, f"  ...还有 {doc_count - 3} 条资料")
        else:
            yield self._emit_thinking(ctx, "⚠️ 知识库里没有找到直接相关的资料")

            # Fallback to web search if RAG returns no results
            should_fallback = (
                ctx.options.web_search
                and web_search_decision
                and web_search_decision.search_params
                and not ctx.web_search_context  # Haven't done web search yet
            )

            if should_fallback and web_search_decision:
                events = await self._execute_web_search(ctx, web_search_decision)
                for event in events:
                    yield event

    async def _generate_response(
        self,
        ctx: ChatContext,
    ) -> AsyncGenerator[str, None]:
        """
        Generate LLM response with context.

        Yields:
            Raw text chunks (not SSE formatted). Caller is responsible for formatting.
        """
        # Build combined context prompt
        context_prompt = self._build_combined_context_prompt(
            rag_context=ctx.rag_context,
            web_context=ctx.web_search_context,
            rewritten_query=ctx.rewritten_query,
        )

        # Build LLM messages
        messages_for_llm = self.context_manager.build_llm_messages(
            ctx.history_dicts,
            compressed_count=ctx.compressed_count,
            compressed_summary=ctx.compressed_summary,
            extra_system_prompt=context_prompt,
        )

        async for chunk in self.llm_orchestrator.stream(messages_for_llm):
            yield chunk

    # =========================================================================
    # Phase 5: Save Response
    # =========================================================================

    async def _save_response(
        self,
        ctx: ChatContext,
        full_response: str,
        intent_result: IntentDetectionResult,
    ) -> None:
        """Save assistant response to database."""
        sources_data = [s.to_dict() for s in ctx.sources] if ctx.sources else None

        await conversation_repository.add_message(
            conversation_id=ctx.conv_id,
            role="assistant",
            content=full_response,
            sources=sources_data,
            intent=intent_result.intent.value,
            thinking=ctx.thinking_steps if ctx.thinking_steps else None,
        )

    # =========================================================================
    # Helper Methods
    # =========================================================================

    def _emit_thinking(self, ctx: ChatContext, step: str) -> str:
        """Helper to emit thinking step and update context."""
        ctx.thinking_steps.append(step)
        return f"data: {json.dumps({'type': 'thinking', 'content': step})}\n\n"

    def _build_combined_context_prompt(
        self,
        rag_context: str,
        web_context: str,
        rewritten_query: str,
    ) -> str:
        """
        Build context prompt combining both RAG and web search results.
        Clearly distinguishes between local knowledge and web search results.
        """
        parts = []
        parts.append(f"【重写后的检索语句】\n{rewritten_query}\n")

        # Add RAG context (local knowledge)
        if rag_context.strip():
            parts.append(
                "【本地知识库内容】\n"
                "下面是 CookHero 知识库中与当前问题最相关的资料：\n"
                f"{rag_context.strip()}\n"
            )

        # Add web search context
        if web_context.strip():
            parts.append(
                "【互联网搜索结果】\n"
                "下面是从互联网搜索获取的补充信息（请注意甄别信息可靠性）：\n"
                f"{web_context.strip()}\n"
            )

        if not rag_context.strip() and not web_context.strip():
            parts.append("（未找到相关参考内容，请结合通用烹饪知识回答）\n")

        parts.append(
            "\n请综合以上信息回答用户问题。"
            "如果本地知识库与互联网信息有冲突，优先采用本地知识库内容。"
            "如果信息不足，请坦诚说明并给出合理的建议。"
        )

        return "\n".join(parts)
    
    def _format_content_with_sources(
        self,
        content: str,
        sources: Optional[List[Dict[str, Any]]],
    ) -> str:
        """
        Format assistant message content with sources appended.

        For LLM context, we append sources in a brief structured way so the model
        knows what references were used in previous responses.

        Args:
            content: The assistant's response content
            sources: Optional list of source dicts with type, info, url

        Returns:
            Formatted content with sources appended
        """
        if not sources:
            return content

        # Format sources as brief appendix
        source_lines = []
        for src in sources:  # Limit to first 5
            src_type = src.get("type", "")
            src_info = src.get("info", "")[:8096]  # Truncate long info

            if src_type == "rag":
                source_lines.append(f"知识库: {src_info}")
            elif src_type == "web":
                src_url = src.get("url", "")
                source_lines.append(f"网络搜索: {src_info}({src_url})")
            else:
                source_lines.append(src_info)

        if not source_lines:
            return content

        sources_summary = "、".join(source_lines)

        return f"{content}\n\n[参考来源: {sources_summary}]"

    # =========================================================================
    # Other Public Methods
    # =========================================================================

    async def get_conversation_history(
        self, conversation_id: str
    ) -> Optional[List[Dict]]:
        """Get conversation history."""
        return await conversation_repository.get_history(conversation_id)

    async def clear_conversation(self, conversation_id: str) -> bool:
        """Clear a conversation."""
        return await conversation_repository.clear(conversation_id)

    async def list_conversations(
        self,
        user_id: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[dict], int]:
        """List all conversations with basic metadata for UI switching.

        Returns:
            Tuple of (conversations list, total count)
        """
        return await conversation_repository.list_conversations(
            user_id=user_id,
            limit=limit,
            offset=offset,
        )

    async def update_conversation_title(self, conversation_id: str, title: str) -> bool:
        """Update the title of a conversation."""
        return await conversation_repository.update_title(conversation_id, title)


# Singleton instance
conversation_service = ConversationService()
