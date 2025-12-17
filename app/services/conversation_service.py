import asyncio
import json
import logging
import os
from typing import AsyncGenerator, Dict, List, Optional

from app.config import settings
from app.context import ContextCompressor, ContextManager
from app.conversation import (
    IntentDetectionResult,
    IntentDetector,
    LLMOrchestrator,
    QueryRewriter,
    conversation_repository,
)
from app.services.rag_service import rag_service_instance

logger = logging.getLogger(__name__)


SYSTEM_PROMPT = """你是 CookHero，一位友好、专业且富有耐心的烹饪助手。

**你的能力：**
1. 帮助用户查找菜谱和烹饪方法
2. 提供烹饪技巧和建议
3. 根据用户手边的食材推荐菜品
4. 解答各种厨房和烹饪相关的问题

**交互风格：**
- 始终保持友好、鼓励的语气
- 回答要简洁但信息丰富
- 使用 Markdown 格式让回答更易读
- 如果用户的问题不够明确，主动询问以获取更多信息

**注意事项：**
- 当涉及食谱查询时，你会自动从知识库中检索相关信息
- 如果知识库中没有找到相关信息，你可以基于通用烹饪知识回答
- 始终优先推荐健康、安全的烹饪方法
"""


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
        """
        Initialize the conversation service with modular components.
        """
        self.llm_config = settings.llm
        self.context_manager = ContextManager(
            system_prompt=SYSTEM_PROMPT,
        )
        self.context_compressor = ContextCompressor(
            llm_config=self.llm_config,
            compression_threshold=self.COMPRESSION_THRESHOLD,
            recent_messages_limit=self.RECENT_MESSAGES_LIMIT,
        )
        self.llm_orchestrator = LLMOrchestrator(llm_config=self.llm_config)
        self.intent_detector = IntentDetector(llm_config=self.llm_config)
        self.query_rewriter = QueryRewriter(llm_config=self.llm_config)
    
    async def chat(
        self,
        message: str,
        conversation_id: Optional[str] = None,
        user_id: Optional[str] = None,
        stream: bool = True
    ) -> AsyncGenerator[str, None]:
        """
        Process a chat message and generate a response.
        
        Yields SSE-formatted events:
        - {"type": "intent", "data": {...}} - Detected intent
        - {"type": "thinking", "content": "..."} - Thinking step
        - {"type": "text", "content": "..."} - Text chunk
        - {"type": "sources", "data": [...]} - RAG sources (if any)
        - {"type": "done", "conversation_id": "..."} - Completion signal
        
        Args:
            message: The user's message
            conversation_id: Optional existing conversation ID
            user_id: Optional user ID for personalization and memory
            stream: Whether to stream the response
        """
        # Get or create conversation in database
        conversation = await conversation_repository.get_or_create(conversation_id, user_id=user_id)
        conv_id = str(conversation.id)
        
        # Add user message to database
        await conversation_repository.add_message(
            conversation_id=conv_id,
            role="user",
            content=message,
        )
        
        # Load conversation history and compressed summary
        history = await conversation_repository.get_history(conv_id, limit=100) or []
        compressed_summary, compressed_count = await conversation_repository.get_compressed_summary(conv_id)
        
        # Build history text for intent detection (includes compressed summary)
        history_dicts = [{"role": h["role"], "content": h["content"]} for h in history]
        history_text = self.context_manager.build_history_text(
            history=history_dicts,
            compressed_count=compressed_count,
            compressed_summary=compressed_summary,
        )

        # check if the file debug_history.txt exists, if not create it
        if not os.path.exists("./debug_history.txt"):
            with open("./debug_history.txt", "w") as f:
                f.write("")
        with open("./debug_history.txt", "a") as f:
            f.write(f"--- New Interaction ---\n")
            f.write(f"Total History Messages: {len(history_dicts)}\n")
            f.write(f"Compressed Count: {compressed_count}\n")
            f.write(f"User Message:\n{message}\n")
            f.write(f"History Text:\n{history_text}\n\n\n")

        # Detect intent
        intent_result: IntentDetectionResult = self.intent_detector.detect(
            message, history_text
        )
        yield f"data: {json.dumps({'type': 'intent', 'data': {'need_rag': intent_result.need_rag, 'intent': intent_result.intent.value, 'reason': intent_result.reason}})}\n\n"
        
        sources: List[Dict] = []
        full_response = ""
        thinking_steps: List[str] = []

        def emit_thinking(step: str) -> str:
            thinking_steps.append(step)
            return f"data: {json.dumps({'type': 'thinking', 'content': step})}\n\n"
        
        # Yield intent detection result with more details
        yield emit_thinking(f"🔍 意图识别完成: {intent_result.intent.value}")
        yield emit_thinking(f"📋 是否需要检索: {'是' if intent_result.need_rag else '否'}")
        yield emit_thinking(f"💭 判断依据: {intent_result.reason}")
        
        logger.info(
            "chat route need_rag=%s intent=%s reason=%s history_len=%d",
            intent_result.need_rag,
            intent_result.intent.value,
            intent_result.reason[:120],
            len(history),
        )

        if intent_result.need_rag:
            # Use RAG pipeline with history-aware query rewriting
            yield emit_thinking("⏳ 正在结合对话历史重写查询语句...")
            
            try:
                # Rewrite query with chat history context
                rewritten_query = self.query_rewriter.rewrite_with_history(
                    message, history_text
                )
                yield emit_thinking(f"✏️ 重写后的查询: {rewritten_query}")
                
                yield emit_thinking("🔎 正在从 CookHero 知识库中检索相关资料...")
                
                # Retrieve context once and reuse for generation + sources
                retrieval_result = rag_service_instance.retrieve(
                    rewritten_query,
                    skip_rewrite=True,
                )
                doc_count = len(retrieval_result.documents)
                
                if doc_count:
                    yield emit_thinking(f"📚 检索到 {doc_count} 条相关资料")
                    # Show brief info about retrieved documents
                    for i, doc in enumerate(retrieval_result.documents[:3]):  # Show top 3
                        doc_title = doc.metadata.get('dish_name', '')
                        doc_difficulty = doc.metadata.get('difficulty', '')
                        doc_category = doc.metadata.get('category', '')
                        doc_preview = doc.page_content[:200].replace('\n', ' ') + ('...' if len(doc.page_content) > 200 else '')
                        yield emit_thinking(f"  📄 [{i+1}] {doc_title} (难度: {doc_difficulty}, 分类: {doc_category}): {doc_preview}")
                    if doc_count > 3:
                        yield emit_thinking(f"  ...还有 {doc_count - 3} 条资料")
                else:
                    yield emit_thinking("⚠️ 知识库里没有找到直接相关的资料，将结合常识为你回答。")
                
                sources = retrieval_result.sources or [
                    {"type": "rag", "info": "CookHero 知识库"}
                ]
                yield f"data: {json.dumps({'type': 'sources', 'data': sources})}\n\n"
                
                context_prompt = self._build_rag_context_prompt(
                    retrieval_result.context,
                    rewritten_query
                )
                # Build LLM messages with compressed summary
                messages_for_llm = self.context_manager.build_llm_messages(
                    history_dicts,
                    compressed_count=compressed_count,
                    compressed_summary=compressed_summary,
                    extra_system_prompt=context_prompt,
                )
                
                yield emit_thinking("🤖 开始生成回答...")
                
                async for chunk in self.llm_orchestrator.stream(messages_for_llm):
                    full_response += chunk
                    yield f"data: {json.dumps({'type': 'text', 'content': chunk})}\n\n"
                
            except Exception as e:
                logger.error(f"RAG error: {e}", exc_info=True)
                yield emit_thinking(f"❌ 检索遇到问题: {str(e)[:50]}，改为直接回答。")
                messages_for_llm = self.context_manager.build_llm_messages(
                    history_dicts,
                    compressed_count=compressed_count,
                    compressed_summary=compressed_summary,
                )
                async for chunk in self.llm_orchestrator.stream(messages_for_llm):
                    full_response += chunk
                    yield f"data: {json.dumps({'type': 'text', 'content': chunk})}\n\n"
        else:
            # Direct LLM conversation
            yield emit_thinking("💬 无需检索知识库，直接回答...")
            messages_for_llm = self.context_manager.build_llm_messages(
                history_dicts,
                compressed_count=compressed_count,
                compressed_summary=compressed_summary,
            )
            async for chunk in self.llm_orchestrator.stream(messages_for_llm):
                full_response += chunk
                yield f"data: {json.dumps({'type': 'text', 'content': chunk})}\n\n"
        
        # Add assistant response to database
        await conversation_repository.add_message(
            conversation_id=conv_id,
            role="assistant",
            content=full_response,
            sources=sources if sources else None,
            intent=intent_result.intent.value,
            thinking=thinking_steps if thinking_steps else None,
        )
        
        # Yield completion signal
        yield f"data: {json.dumps({'type': 'done', 'conversation_id': conv_id})}\n\n"
        
        # Trigger async context compression if needed
        asyncio.create_task(
            self.context_compressor.maybe_compress(conv_id, conversation_repository)
        )

    def _build_rag_context_prompt(self, context: str, rewritten_query: str) -> str:
        """Construct the system prompt that injects retrieved context for generation."""
        sanitized_context = context.strip() or "（检索结果为空，尽量结合通用烹饪知识回答）"
        return (
            "下面是 CookHero 知识库中与当前问题最相关的资料，请结合它们回答用户。"
            "如果资料不足，请坦诚说明并给出合理的建议。\n\n"
            f"【重写后的检索语句】\n{rewritten_query}\n\n"
            f"【检索到的参考内容】\n{sanitized_context}"
        )
    
    async def get_conversation_history(self, conversation_id: str) -> Optional[List[Dict]]:
        """Get conversation history."""
        return await conversation_repository.get_history(conversation_id)
    
    async def clear_conversation(self, conversation_id: str) -> bool:
        """Clear a conversation."""
        return await conversation_repository.clear(conversation_id)

    async def list_conversations(self, user_id: Optional[str] = None) -> list[dict]:
        """List all conversations with basic metadata for UI switching."""
        return await conversation_repository.list_conversations(user_id=user_id)


# Singleton instance
conversation_service = ConversationService()
