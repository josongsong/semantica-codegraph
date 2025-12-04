"""
Conversation Manager for Agent System

Manages multi-turn conversation context with:
- Context window management
- History compression via summarization
- Token counting and pruning
- Message deduplication
"""

import hashlib
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from src.infra.observability import get_logger

logger = get_logger(__name__)


class MessageRole(Enum):
    """Role of message sender."""

    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"


@dataclass
class Message:
    """Single conversation message."""

    role: MessageRole
    content: str
    timestamp: float = field(default_factory=time.time)
    metadata: dict[str, Any] = field(default_factory=dict)
    token_count: int = 0  # Estimated tokens

    @property
    def content_hash(self) -> str:
        """Hash of content for deduplication."""
        return hashlib.md5(self.content.encode()).hexdigest()[:12]

    def to_dict(self) -> dict[str, Any]:
        """Convert to API-compatible dict."""
        return {
            "role": self.role.value,
            "content": self.content,
        }


@dataclass
class ConversationSummary:
    """Compressed summary of conversation history."""

    summary: str
    message_count: int
    token_count: int
    start_time: float
    end_time: float


class ConversationManager:
    """
    Manages conversation context for multi-turn interactions.

    Features:
    - Automatic context window management
    - History compression when approaching token limit
    - Recency-weighted message retention
    - Tool result caching

    Usage:
        manager = ConversationManager(max_tokens=8000)
        manager.add_system_message("You are a helpful coding assistant.")
        manager.add_user_message("Find the User class")
        manager.add_assistant_message("I found the User class in models.py")

        # Get messages for LLM
        messages = manager.get_messages_for_llm()

        # When context is full, compress
        if manager.should_compress():
            await manager.compress_history(llm)
    """

    # Approximate tokens per character (conservative estimate)
    CHARS_PER_TOKEN = 4

    def __init__(
        self,
        max_tokens: int = 8000,
        compression_threshold: float = 0.8,  # Compress at 80% capacity
        min_recent_messages: int = 4,  # Always keep last N messages
        summarizer: Any | None = None,  # LLM for summarization
    ):
        """
        Initialize conversation manager.

        Args:
            max_tokens: Maximum tokens in context window
            compression_threshold: Trigger compression at this % of max
            min_recent_messages: Minimum recent messages to retain
            summarizer: Optional LLM for summarization
        """
        self.max_tokens = max_tokens
        self.compression_threshold = compression_threshold
        self.min_recent_messages = min_recent_messages
        self.summarizer = summarizer

        self._messages: list[Message] = []
        self._summaries: list[ConversationSummary] = []
        self._tool_cache: dict[str, Any] = {}
        self._total_tokens = 0

    def add_message(
        self,
        role: MessageRole,
        content: str,
        metadata: dict[str, Any] | None = None,
    ) -> Message:
        """
        Add message to conversation.

        Args:
            role: Message role
            content: Message content
            metadata: Optional metadata

        Returns:
            Created Message object
        """
        token_count = self._estimate_tokens(content)
        message = Message(
            role=role,
            content=content,
            metadata=metadata or {},
            token_count=token_count,
        )

        self._messages.append(message)
        self._total_tokens += token_count

        logger.debug(
            "message_added",
            role=role.value,
            tokens=token_count,
            total_tokens=self._total_tokens,
        )

        return message

    def add_system_message(self, content: str) -> Message:
        """Add system message."""
        return self.add_message(MessageRole.SYSTEM, content)

    def add_user_message(self, content: str) -> Message:
        """Add user message."""
        return self.add_message(MessageRole.USER, content)

    def add_assistant_message(self, content: str) -> Message:
        """Add assistant message."""
        return self.add_message(MessageRole.ASSISTANT, content)

    def add_tool_result(
        self,
        tool_name: str,
        result: Any,
        cache: bool = True,
    ) -> Message:
        """
        Add tool execution result.

        Args:
            tool_name: Name of the tool
            result: Tool result
            cache: Whether to cache result

        Returns:
            Created Message object
        """
        content = f"[Tool: {tool_name}]\n{result}"

        if cache:
            cache_key = f"{tool_name}:{hashlib.md5(str(result).encode()).hexdigest()[:8]}"
            self._tool_cache[cache_key] = result

        return self.add_message(
            MessageRole.TOOL,
            content,
            metadata={"tool_name": tool_name},
        )

    def get_messages_for_llm(
        self,
        include_summaries: bool = True,
    ) -> list[dict[str, str]]:
        """
        Get messages formatted for LLM API.

        Args:
            include_summaries: Whether to include compressed summaries

        Returns:
            List of message dicts with role and content
        """
        messages = []

        # Add summaries as system context
        if include_summaries and self._summaries:
            summary_content = self._format_summaries()
            messages.append(
                {
                    "role": "system",
                    "content": f"[Previous conversation summary]\n{summary_content}",
                }
            )

        # Add current messages
        for msg in self._messages:
            messages.append(msg.to_dict())

        return messages

    def should_compress(self) -> bool:
        """Check if compression is needed."""
        threshold_tokens = int(self.max_tokens * self.compression_threshold)
        return self._total_tokens > threshold_tokens

    async def compress_history(
        self,
        llm: Any | None = None,
    ) -> ConversationSummary | None:
        """
        Compress older messages into a summary.

        Args:
            llm: LLM to use for summarization (falls back to self.summarizer)

        Returns:
            Created summary or None if compression not needed
        """
        llm = llm or self.summarizer

        # Keep recent messages
        if len(self._messages) <= self.min_recent_messages:
            return None

        # Split messages: old (to compress) vs recent (to keep)
        split_idx = len(self._messages) - self.min_recent_messages
        old_messages = self._messages[:split_idx]
        recent_messages = self._messages[split_idx:]

        if not old_messages:
            return None

        # Generate summary
        if llm:
            summary_text = await self._generate_summary(old_messages, llm)
        else:
            summary_text = self._create_extractive_summary(old_messages)

        # Create summary object
        summary = ConversationSummary(
            summary=summary_text,
            message_count=len(old_messages),
            token_count=sum(m.token_count for m in old_messages),
            start_time=old_messages[0].timestamp,
            end_time=old_messages[-1].timestamp,
        )
        self._summaries.append(summary)

        # Update messages and token count
        old_tokens = sum(m.token_count for m in old_messages)
        self._messages = recent_messages
        self._total_tokens -= old_tokens
        self._total_tokens += self._estimate_tokens(summary_text)

        logger.info(
            "conversation_compressed",
            messages_compressed=len(old_messages),
            tokens_saved=old_tokens,
            new_total=self._total_tokens,
        )

        return summary

    async def _generate_summary(
        self,
        messages: list[Message],
        llm: Any,
    ) -> str:
        """Generate LLM-based summary of messages."""
        # Format messages for summarization
        content = "\n".join(
            f"[{m.role.value}]: {m.content[:500]}"  # Truncate long messages
            for m in messages
        )

        prompt = f"""Summarize the following conversation concisely,
focusing on key decisions, code changes, and important context:

{content}

Summary (2-3 sentences):"""

        try:
            if hasattr(llm, "generate"):
                return await llm.generate(prompt)
            elif callable(llm):
                return await llm(prompt)
            else:
                return self._create_extractive_summary(messages)
        except Exception as e:
            logger.warning("summary_generation_failed", error=str(e))
            return self._create_extractive_summary(messages)

    def _create_extractive_summary(self, messages: list[Message]) -> str:
        """Create simple extractive summary without LLM."""
        # Extract key information
        parts = []

        # Count by role
        user_count = sum(1 for m in messages if m.role == MessageRole.USER)
        assistant_count = sum(1 for m in messages if m.role == MessageRole.ASSISTANT)
        tool_count = sum(1 for m in messages if m.role == MessageRole.TOOL)

        parts.append(f"Conversation: {user_count} user messages, {assistant_count} assistant responses")

        if tool_count > 0:
            tool_names = {m.metadata.get("tool_name", "unknown") for m in messages if m.role == MessageRole.TOOL}
            parts.append(f"Tools used: {', '.join(tool_names)}")

        # Extract first user query and last assistant response
        user_messages = [m for m in messages if m.role == MessageRole.USER]
        assistant_messages = [m for m in messages if m.role == MessageRole.ASSISTANT]

        if user_messages:
            first_query = user_messages[0].content[:100]
            parts.append(f"Initial query: {first_query}...")

        if assistant_messages:
            last_response = assistant_messages[-1].content[:100]
            parts.append(f"Last response: {last_response}...")

        return " | ".join(parts)

    def _format_summaries(self) -> str:
        """Format all summaries as context."""
        if not self._summaries:
            return ""

        return "\n---\n".join(f"[{i + 1}] {s.summary}" for i, s in enumerate(self._summaries))

    def _estimate_tokens(self, text: str) -> int:
        """Estimate token count for text."""
        return len(text) // self.CHARS_PER_TOKEN + 1

    def clear(self) -> None:
        """Clear all messages and summaries."""
        self._messages.clear()
        self._summaries.clear()
        self._tool_cache.clear()
        self._total_tokens = 0

    def get_last_n_messages(self, n: int) -> list[Message]:
        """Get last N messages."""
        return self._messages[-n:] if n > 0 else []

    def get_messages_by_role(self, role: MessageRole) -> list[Message]:
        """Get all messages with specific role."""
        return [m for m in self._messages if m.role == role]

    @property
    def message_count(self) -> int:
        """Total message count."""
        return len(self._messages)

    @property
    def token_count(self) -> int:
        """Total token count."""
        return self._total_tokens

    @property
    def summary_count(self) -> int:
        """Number of compressed summaries."""
        return len(self._summaries)

    def get_statistics(self) -> dict[str, Any]:
        """Get conversation statistics."""
        return {
            "message_count": self.message_count,
            "token_count": self.token_count,
            "summary_count": self.summary_count,
            "max_tokens": self.max_tokens,
            "utilization": self.token_count / self.max_tokens,
            "tool_cache_size": len(self._tool_cache),
            "messages_by_role": {role.value: len(self.get_messages_by_role(role)) for role in MessageRole},
        }
