# app/context/compress.py
"""
Context Compressor for CookHero.
Responsible for compressing older conversation history into summaries.

Key responsibilities:
1. Determine when compression is needed
2. Generate summaries of older messages via LLM
3. Support incremental/rolling compression
4. Persist compressed summaries to database

Compression rule:
- When uncompressed messages >= COMPRESSION_THRESHOLD + RECENT_MESSAGES_LIMIT:
  - Compress the first COMPRESSION_THRESHOLD messages from uncompressed ones
  - This ensures uncompressed count stays in range [COMPRESSION_THRESHOLD, COMPRESSION_THRESHOLD + RECENT_MESSAGES_LIMIT)
"""

import logging
from typing import TYPE_CHECKING, Dict, List, Optional

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from app.config import LLMProviderConfig

from app.conversation.repository import ConversationRepository

logger = logging.getLogger(__name__)


COMPRESSION_SYSTEM_PROMPT = """你是一个对话摘要助手。你的任务是将对话历史压缩成简洁但信息完整的摘要。

摘要要求：
1. 保留关键信息：用户的核心问题、偏好、提到的食材/菜品等
2. 保留重要上下文：用户的烹饪水平、饮食限制、人数等
3. 忽略闲聊和重复内容
4. 使用第三人称描述（如"用户询问了..."）
5. 摘要长度控制在 200-500 字

如果提供了之前的摘要，请将新的对话内容与之前的摘要整合，生成一个更新后的综合摘要。
"""


class ContextCompressor:
    """
    Compresses conversation history into summaries using LLM.
    
    Compression strategy:
    - Triggered when: uncompressed_count >= compression_threshold + recent_messages_limit
    - Compresses: first compression_threshold messages from uncompressed ones
    - Result: uncompressed_count reduced by compression_threshold
    - Invariant: every message is either compressed (in summary) or in context (original)
    """

    def __init__(
        self,
        llm_config: LLMProviderConfig,
        compression_threshold: int = 6,
        recent_messages_limit: int = 10,
        max_messages_per_compression: int = 200,
        history_text_max_len: int = 8096
    ):
        """
        Initialize ContextCompressor.
        
        Args:
            llm_config: LLM configuration for summary generation
            compression_threshold: Number of messages to compress each time
            recent_messages_limit: Number of recent uncompressed messages to keep
            max_messages_per_compression: Max messages to compress in one call
        """
        self.llm_config = llm_config
        self.compression_threshold = compression_threshold
        self.recent_messages_limit = recent_messages_limit
        self.max_messages_per_compression = max_messages_per_compression
        self.history_text_max_len = history_text_max_len
        
        self._llm = ChatOpenAI(
            model=llm_config.model_name,
            api_key=llm_config.api_key,  # type: ignore
            base_url=llm_config.base_url,
            max_completion_tokens=llm_config.max_tokens,
            temperature=0.3,  # Lower temperature for more consistent summaries
        )

    async def maybe_compress(
        self,
        conversation_id: str,
        repository: ConversationRepository,
    ) -> bool:
        """
        Check if compression is needed and perform it if so.
        
        This is the main entry point for compression logic.
        Handles: decision making, compression, and persistence.
        
        Compression rule:
        - When uncompressed_count >= compression_threshold + recent_messages_limit:
          - Compress first compression_threshold messages from uncompressed ones
        
        Args:
            conversation_id: The conversation ID
            repository: ConversationRepository for data access and persistence
            
        Returns:
            True if compression was performed, False otherwise
        """
        try:
            # Get current state
            total_count = await repository.get_message_count(conversation_id)
            existing_summary, compressed_count = await repository.get_compressed_summary(
                conversation_id
            )
            
            # Calculate uncompressed count
            uncompressed_count = total_count - compressed_count
            
            # Check if compression is needed
            trigger_threshold = self.compression_threshold + self.recent_messages_limit
            if uncompressed_count < trigger_threshold:
                logger.debug(
                    "Compression not needed for %s: uncompressed=%d, threshold=%d",
                    conversation_id,
                    uncompressed_count,
                    trigger_threshold,
                )
                return False
            
            logger.info(
                "Triggering compression for %s: total=%d, compressed=%d, uncompressed=%d",
                conversation_id,
                total_count,
                compressed_count,
                uncompressed_count,
            )
            
            # Get full history for compression
            full_history = await repository.get_history(conversation_id, limit=1000) or []
            history_dicts = [{"role": h["role"], "content": h["content"]} for h in full_history]
            
            # Get messages to compress (first COMPRESSION_THRESHOLD from uncompressed)
            uncompressed_messages = history_dicts[compressed_count:]
            messages_to_compress = uncompressed_messages[:self.compression_threshold]
            
            if not messages_to_compress:
                return False
            
            # Perform compression
            new_summary = await self._compress(
                messages_to_compress,
                existing_summary=existing_summary,
            )
            
            if new_summary:
                # Update compressed count
                new_compressed_count = compressed_count + len(messages_to_compress)
                
                # Persist
                await repository.update_compressed_summary(
                    conversation_id,
                    new_summary,
                    new_compressed_count,
                )
                
                logger.info(
                    "Compressed %d messages for %s, new compressed_count=%d",
                    len(messages_to_compress),
                    conversation_id,
                    new_compressed_count,
                )
                return True
            
            return False
            
        except Exception as e:
            logger.error(
                "Failed to compress context for %s: %s",
                conversation_id,
                e,
                exc_info=True,
            )
            return False

    async def _compress(
        self,
        messages: List[Dict[str, str]],
        existing_summary: Optional[str] = None,
    ) -> str:
        """
        Compress messages into a summary (internal method).
        
        If existing_summary is provided, performs incremental compression
        by integrating new messages with the existing summary.
        
        Args:
            messages: List of message dicts to compress
            existing_summary: Optional existing summary to build upon
            
        Returns:
            Compressed summary string
        """
        if not messages:
            return existing_summary or ""
        
        # Limit messages per compression to avoid context overflow
        messages_to_process = messages[-self.max_messages_per_compression:]
        
        # Format messages for compression
        messages_text = self._format_messages_for_compression(messages_to_process)
        
        # Build compression prompt
        if existing_summary:
            user_prompt = (
                f"【之前的对话摘要】\n{existing_summary}\n\n"
                f"【新增的对话内容】\n{messages_text}\n\n"
                "请将新增的对话内容与之前的摘要整合，生成一个更新后的综合摘要。"
            )
        else:
            user_prompt = (
                f"【对话内容】\n{messages_text}\n\n"
                "请为上述对话生成一个简洁的摘要。"
            )
        
        try:
            response = await self._llm.ainvoke([
                SystemMessage(content=COMPRESSION_SYSTEM_PROMPT),
                HumanMessage(content=user_prompt),
            ])
            
            # Extract content from response
            content = response.content
            if isinstance(content, str):
                summary = content.strip()
            else:
                # Handle case where content might be a list
                summary = str(content).strip()
            
            logger.info(
                "Compressed %d messages into summary (len=%d)",
                len(messages_to_process),
                len(summary),
            )
            return summary
            
        except Exception as e:
            logger.error("Failed to compress messages: %s", e, exc_info=True)
            # Return existing summary on failure, or empty string
            return existing_summary or ""

    def _format_messages_for_compression(
        self,
        messages: List[Dict[str, str]],
    ) -> str:
        """Format messages as text for compression prompt."""
        parts = []
        for msg in messages:
            role = msg.get("role", "unknown")
            content = msg.get("content", "")
            # Truncate very long messages
            if len(content) > self.history_text_max_len:
                content = content[:self.history_text_max_len] + "..."
            role_label = "用户" if role == "user" else "助手"
            parts.append(f"{role_label}: {content}")
        return "\n".join(parts)
