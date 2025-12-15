from typing import Dict, List, Optional, Union

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage

from app.conversation.models import Message


class ContextManager:
    """Builds and trims conversation context for LLM consumption."""

    def __init__(
        self,
        system_prompt: str,
        chat_history_limit: int = 1000,
        history_pairs_limit: int = 1000,
        history_text_max_len: int = 8096,
    ):
        self.system_prompt = system_prompt 
        self.chat_history_limit = chat_history_limit
        self.history_pairs_limit = history_pairs_limit
        self.history_text_max_len = history_text_max_len

    def build_llm_messages(
        self,
        messages: List[Message],
        extra_system_prompt: Optional[str] = None,
    ) -> List[BaseMessage]:
        """Build LLM messages from a list of Message objects."""
        result: List[BaseMessage] = [SystemMessage(content=self.system_prompt)]
        recent_messages = messages[-self.chat_history_limit:]
        for msg in recent_messages:
            if msg.role == "user":
                result.append(HumanMessage(content=msg.content))
            else:
                result.append(AIMessage(content=msg.content))
        if extra_system_prompt:
            result.append(SystemMessage(content=extra_system_prompt))
        return result

    def build_llm_messages_from_dicts(
        self,
        history: List[Dict[str, str]],
        extra_system_prompt: Optional[str] = None,
    ) -> List[BaseMessage]:
        """Build LLM messages from a list of dicts (for DB-loaded history)."""
        result: List[BaseMessage] = [SystemMessage(content=self.system_prompt)]
        recent = history[-self.chat_history_limit:]
        for msg in recent:
            role = msg.get("role", "")
            content = msg.get("content", "")
            if role == "user":
                result.append(HumanMessage(content=content))
            else:
                result.append(AIMessage(content=content))
        if extra_system_prompt:
            result.append(SystemMessage(content=extra_system_prompt))
        return result

    def build_history_pairs(
        self, messages: List[Message], limit: Optional[int] = None
    ) -> List[Dict[str, str]]:
        """Build history pairs from Message objects."""
        recent_messages = messages[-(limit or self.history_pairs_limit):]
        return [
            {"role": msg.role, "content": msg.content}
            for msg in recent_messages
        ]

    def build_history_text(
        self,
        messages: List[Message],
        limit: Optional[int] = None,
        empty_placeholder: str = "(无历史对话)",
    ) -> str:
        """Build formatted history text from Message objects."""
        pairs = self.build_history_pairs(messages, limit=limit)
        return self._format_pairs_to_text(pairs, empty_placeholder)

    def build_history_text_from_dicts(
        self,
        history: List[Dict[str, str]],
        limit: Optional[int] = None,
        empty_placeholder: str = "(无历史对话)",
    ) -> str:
        """Build formatted history text from list of dicts (for DB-loaded history)."""
        recent = history[-(limit or self.history_pairs_limit):]
        return self._format_pairs_to_text(recent, empty_placeholder)

    def _format_pairs_to_text(
        self,
        pairs: List[Dict[str, str]],
        empty_placeholder: str = "(无历史对话)",
    ) -> str:
        """Format history pairs to text string."""
        if not pairs:
            return empty_placeholder

        history_parts: List[str] = []
        for msg in pairs:
            role = msg.get("role", "")
            content = msg.get("content", "")
            if len(content) > self.history_text_max_len:
                content = content[:self.history_text_max_len] + "..."
            history_parts.append(f"{role}: {content}")
        return "\n".join(history_parts)
