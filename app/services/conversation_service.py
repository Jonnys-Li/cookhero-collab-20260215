import json
import logging
from typing import AsyncGenerator, Dict, List, Optional

from app.config import settings
from app.conversation import (
    ContextManager,
    IntentDetectionResult,
    IntentDetector,
    LLMOrchestrator,
    Message,
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
    """
    
    def __init__(self):
        """Initialize the conversation service with modular components."""
        self.llm_config = settings.llm
        self.context_manager = ContextManager(system_prompt=SYSTEM_PROMPT)
        self.llm_orchestrator = LLMOrchestrator(llm_config=self.llm_config)
        self.intent_detector = IntentDetector(llm_config=self.llm_config)
        self.query_rewriter = QueryRewriter(llm_config=self.llm_config)
    
    async def chat(
        self,
        message: str,
        conversation_id: Optional[str] = None,
        stream: bool = True
    ) -> AsyncGenerator[str, None]:
        """
        Process a chat message and generate a response.
        
        Yields SSE-formatted events:
        - {"type": "intent", "data": {...}} - Detected intent
        - {"type": "text", "content": "..."} - Text chunk
        - {"type": "sources", "data": [...]} - RAG sources (if any)
        - {"type": "done", "conversation_id": "..."} - Completion signal
        """
        # Get or create conversation in database
        conversation = await conversation_repository.get_or_create(conversation_id)
        conv_id = str(conversation.id)
        
        # Add user message to database
        await conversation_repository.add_message(
            conversation_id=conv_id,
            role="user",
            content=message,
        )
        
        # Load recent history from database for context
        history = await conversation_repository.get_history(conv_id, limit=100) or []
        
        # Detect intent using preformatted history
        history_text = self.context_manager.build_history_text_from_dicts(history)
        intent_result: IntentDetectionResult = self.intent_detector.detect(
            message, history_text
        )
        
        # Yield intent information
        yield f"data: {json.dumps({'type': 'intent', 'data': {'need_rag': intent_result.need_rag, 'intent': intent_result.intent.value, 'reason': intent_result.reason}})}\n\n"
        
        sources: List[Dict] = []
        full_response = ""
        thinking_steps: List[str] = []

        def emit_thinking(step: str) -> str:
            thinking_steps.append(step)
            return f"data: {json.dumps({'type': 'thinking', 'content': step})}\n\n"
        
        logger.info(
            "chat route need_rag=%s intent=%s reason=%s history_len=%d",
            intent_result.need_rag,
            intent_result.intent.value,
            intent_result.reason[:120],
            len(history),
        )

        if intent_result.need_rag:
            # Use RAG pipeline with history-aware query rewriting
            yield emit_thinking("正在分析你的问题并检索 CookHero 知识库...")
            
            try:
                # Rewrite query with chat history context
                rewritten_query = self.query_rewriter.rewrite_with_history(
                    message, history_text
                )
                
                # Retrieve context once and reuse for generation + sources
                retrieval_result = rag_service_instance.retrieve(
                    rewritten_query,
                    skip_rewrite=True,
                )
                doc_count = len(retrieval_result.documents)
                if doc_count:
                    yield emit_thinking(f"从知识库中找到 {doc_count} 条相关资料，正在组织回答...")
                else:
                    yield emit_thinking("知识库里没有找到直接相关的资料，将结合常识为你回答。")
                
                sources = retrieval_result.sources or [
                    {"type": "rag", "info": "CookHero 知识库"}
                ]
                yield f"data: {json.dumps({'type': 'sources', 'data': sources})}\n\n"
                
                context_prompt = self._build_rag_context_prompt(
                    retrieval_result.context,
                    rewritten_query
                )
                messages_for_llm = self.context_manager.build_llm_messages_from_dicts(
                    history, extra_system_prompt=context_prompt
                )
                async for chunk in self.llm_orchestrator.stream(messages_for_llm):
                    full_response += chunk
                    yield f"data: {json.dumps({'type': 'text', 'content': chunk})}\n\n"
                
            except Exception as e:
                logger.error(f"RAG error: {e}", exc_info=True)
                yield emit_thinking("检索遇到问题，改为直接回答你的问题。")
                # Fallback to direct LLM
                messages_for_llm = self.context_manager.build_llm_messages_from_dicts(history)
                async for chunk in self.llm_orchestrator.stream(messages_for_llm):
                    full_response += chunk
                    yield f"data: {json.dumps({'type': 'text', 'content': chunk})}\n\n"
        else:
            # Direct LLM conversation
            messages_for_llm = self.context_manager.build_llm_messages_from_dicts(history)
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
