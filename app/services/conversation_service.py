import json
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import AsyncGenerator, Dict, List, Optional

from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage

from app.config import settings
from app.conversation import IntentDetector, QueryRewriter
from app.services.rag_service import rag_service_instance

logger = logging.getLogger(__name__)


@dataclass
class Message:
    """Represents a single message in a conversation."""
    role: str  # "user" or "assistant"
    content: str
    timestamp: datetime = field(default_factory=datetime.now)
    sources: Optional[List[Dict]] = None  # RAG sources if any
    intent: Optional[str] = None  # Detected intent
    thinking: Optional[List[str]] = None  # Intermediate reasoning steps


@dataclass
class Conversation:
    """Represents a conversation session."""
    id: str
    messages: List[Message] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)


# In-memory conversation store (replace with Redis/DB for production)
_conversations: Dict[str, Conversation] = {}


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
        """Initialize the conversation service."""
        self.llm_config = settings.llm
        
        # Initialize LLM for general conversation
        self.llm = ChatOpenAI(
            model=self.llm_config.model_name,
            temperature=self.llm_config.temperature,
            max_completion_tokens=self.llm_config.max_tokens,
            api_key=self.llm_config.api_key,  # type: ignore
            base_url=self.llm_config.base_url,
            streaming=True
        )
        
        # Initialize intent detector & query rewriter with shared LLM config
        self.intent_detector = IntentDetector(llm_config=self.llm_config)
        self.query_rewriter = QueryRewriter(llm_config=self.llm_config)
        
        logger.info("ConversationService initialized.")
    
    def get_or_create_conversation(self, conversation_id: Optional[str] = None) -> Conversation:
        """Get existing conversation or create a new one."""
        if conversation_id and conversation_id in _conversations:
            return _conversations[conversation_id]
        
        new_id = conversation_id or str(uuid.uuid4())
        conversation = Conversation(id=new_id)
        _conversations[new_id] = conversation
        return conversation
    
    def _build_chat_history(self, conversation: Conversation, limit: int = 10):
        """Build chat history for LLM context."""
        from langchain_core.messages import BaseMessage
        messages: List[BaseMessage] = [SystemMessage(content=SYSTEM_PROMPT)]
        
        # Get last N messages for context
        recent_messages = conversation.messages[-limit:]
        
        for msg in recent_messages:
            if msg.role == "user":
                messages.append(HumanMessage(content=msg.content))
            else:
                messages.append(AIMessage(content=msg.content))
        
        return messages
    
    def _build_history_list(self, conversation: Conversation, limit: int = 10) -> List[Dict[str, str]]:
        """Build chat history as a simple list of dicts for query rewriting."""
        recent_messages = conversation.messages
        return [
            {"role": msg.role, "content": msg.content}
            for msg in recent_messages
        ]
    
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
        conversation = self.get_or_create_conversation(conversation_id)
        
        # Add user message to history
        user_message = Message(role="user", content=message)
        conversation.messages.append(user_message)
        conversation.updated_at = datetime.now()
        
        # Detect intent
        need_rag, intent, reason = self.intent_detector.detect(message)
        
        # Yield intent information
        yield f"data: {json.dumps({'type': 'intent', 'data': {'need_rag': need_rag, 'intent': intent.value, 'reason': reason}})}\n\n"
        
        sources: List[Dict] = []
        full_response = ""
        thinking_steps: List[str] = []

        def emit_thinking(step: str) -> str:
            thinking_steps.append(step)
            return f"data: {json.dumps({'type': 'thinking', 'content': step})}\n\n"
        
        if need_rag:
            # Use RAG pipeline with history-aware query rewriting
            logger.info(f"Using RAG for query: {message}")
            yield emit_thinking("正在分析你的问题并检索 CookHero 知识库...")
            
            try:
                # Build chat history for query rewriting
                chat_history = self._build_history_list(conversation)
                
                # Rewrite query with chat history context
                rewritten_query = self.query_rewriter.rewrite_with_history(
                    message, chat_history
                )
                
                # Retrieve context once and reuse for generation + sources
                retrieval_result = rag_service_instance.retrieve(rewritten_query)
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
                async for chunk in self._generate_llm_response(
                    conversation,
                    extra_system_prompt=context_prompt
                ):
                    full_response += chunk
                    yield f"data: {json.dumps({'type': 'text', 'content': chunk})}\n\n"
                
            except Exception as e:
                logger.error(f"RAG error: {e}", exc_info=True)
                yield emit_thinking("检索遇到问题，改为直接回答你的问题。")
                # Fallback to direct LLM
                async for chunk in self._direct_llm_response(conversation):
                    full_response += chunk
                    yield f"data: {json.dumps({'type': 'text', 'content': chunk})}\n\n"
        else:
            # Direct LLM conversation
            logger.info(f"Using direct LLM for query: {message}")
            async for chunk in self._direct_llm_response(conversation):
                full_response += chunk
                yield f"data: {json.dumps({'type': 'text', 'content': chunk})}\n\n"
        
        # Add assistant response to history
        assistant_message = Message(
            role="assistant",
            content=full_response,
            sources=sources if sources else None,
            intent=intent.value,
            thinking=thinking_steps if thinking_steps else None
        )
        conversation.messages.append(assistant_message)
        
        # Yield completion signal
        yield f"data: {json.dumps({'type': 'done', 'conversation_id': conversation.id})}\n\n"
    
    async def _direct_llm_response(
        self,
        conversation: Conversation
    ) -> AsyncGenerator[str, None]:
        """Generate a direct LLM response without RAG."""
        async for chunk in self._generate_llm_response(conversation):
            if chunk:
                yield chunk

    async def _generate_llm_response(
        self,
        conversation: Conversation,
        extra_system_prompt: Optional[str] = None
    ) -> AsyncGenerator[str, None]:
        """Stream responses from the base LLM with optional extra system guidance."""
        chat_history = self._build_chat_history(conversation)
        if extra_system_prompt:
            chat_history.append(SystemMessage(content=extra_system_prompt))
        
        async for chunk in self.llm.astream(chat_history):
            if chunk.content:
                yield str(chunk.content)

    def _build_rag_context_prompt(self, context: str, rewritten_query: str) -> str:
        """Construct the system prompt that injects retrieved context for generation."""
        sanitized_context = context.strip() or "（检索结果为空，尽量结合通用烹饪知识回答）"
        return (
            "下面是 CookHero 知识库中与当前问题最相关的资料，请结合它们回答用户。"
            "如果资料不足，请坦诚说明并给出合理的建议。\n\n"
            f"【重写后的检索语句】\n{rewritten_query}\n\n"
            f"【检索到的参考内容】\n{sanitized_context}"
        )
    
    async def _wrap_sync_generator(self, sync_gen):
        """Wrap a synchronous generator as async."""
        import asyncio
        
        def get_next():
            try:
                return next(sync_gen), False
            except StopIteration:
                return None, True
        
        loop = asyncio.get_event_loop()
        while True:
            result, done = await loop.run_in_executor(None, get_next)
            if done:
                break
            if result:
                yield result
    
    def get_conversation_history(self, conversation_id: str) -> Optional[List[Dict]]:
        """Get conversation history."""
        if conversation_id not in _conversations:
            return None
        
        conversation = _conversations[conversation_id]
        return [
            {
                "role": msg.role,
                "content": msg.content,
                "timestamp": msg.timestamp.isoformat(),
                "sources": msg.sources,
                "intent": msg.intent,
                "thinking": msg.thinking,
            }
            for msg in conversation.messages
        ]
    
    def clear_conversation(self, conversation_id: str) -> bool:
        """Clear a conversation."""
        if conversation_id in _conversations:
            del _conversations[conversation_id]
            return True
        return False

    def list_conversations(self) -> list[dict]:
        """List all conversations with basic metadata for UI switching."""
        result = []
        for conv in _conversations.values():
            result.append(
                {
                    "id": conv.id,
                    "created_at": conv.created_at.isoformat(),
                    "updated_at": conv.updated_at.isoformat(),
                    "message_count": len(conv.messages),
                    "last_message_preview": (conv.messages[-1].content[:80] if conv.messages else ""),
                }
            )
        # Sort by updated_at desc to surface recent conversations first
        return sorted(result, key=lambda x: x["updated_at"], reverse=True)


# Singleton instance
conversation_service = ConversationService()
