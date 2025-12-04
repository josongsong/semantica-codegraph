"""
MemGPT-style Self-Editing Memory Tools

Implements LLM-callable tools for memory management:
- core_memory_append: Add to core/working memory
- core_memory_replace: Update core memory
- archival_memory_insert: Store long-term memory
- archival_memory_search: Retrieve from long-term
- conversation_search: Search conversation history

Based on patterns from:
- MemGPT: LLM as OS with self-editing memory
- Function calling paradigm for memory operations
"""

import json
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Protocol

from src.common.observability import get_logger

from .models import (
    MemoryType,
    MemoryUnit,
)

logger = get_logger(__name__)
# ============================================================
# Tool Definitions (OpenAI Function Calling format)
# ============================================================

MEMORY_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "core_memory_append",
            "description": "Append information to core memory. "
            "Use for important facts about the user, project, or preferences.",
            "parameters": {
                "type": "object",
                "properties": {
                    "section": {
                        "type": "string",
                        "enum": ["profile", "preferences", "project", "facts"],
                        "description": "Which section of core memory to append to",
                    },
                    "content": {
                        "type": "string",
                        "description": "The content to append",
                    },
                },
                "required": ["section", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "core_memory_replace",
            "description": "Replace content in core memory. Use to update outdated information.",
            "parameters": {
                "type": "object",
                "properties": {
                    "section": {
                        "type": "string",
                        "enum": ["profile", "preferences", "project", "facts"],
                        "description": "Which section of core memory to update",
                    },
                    "old_content": {
                        "type": "string",
                        "description": "The content to replace (must match exactly)",
                    },
                    "new_content": {
                        "type": "string",
                        "description": "The new content",
                    },
                },
                "required": ["section", "old_content", "new_content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "archival_memory_insert",
            "description": "Insert content into archival (long-term) memory. "
            "Use for information that might be useful later.",
            "parameters": {
                "type": "object",
                "properties": {
                    "content": {
                        "type": "string",
                        "description": "The content to store",
                    },
                    "tags": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Tags for categorization and retrieval",
                    },
                },
                "required": ["content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "archival_memory_search",
            "description": "Search archival memory for relevant information.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "The search query",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum number of results",
                        "default": 5,
                    },
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "conversation_search",
            "description": "Search past conversation history for relevant context.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "The search query",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum number of results",
                        "default": 5,
                    },
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "recall_memory",
            "description": "Recall relevant memories based on current context. "
            "Use when you need to remember past experiences.",
            "parameters": {
                "type": "object",
                "properties": {
                    "context": {
                        "type": "string",
                        "description": "Current task context to match against memories",
                    },
                    "memory_types": {
                        "type": "array",
                        "items": {
                            "type": "string",
                            "enum": ["episodic", "semantic", "fact", "all"],
                        },
                        "description": "Types of memory to search",
                        "default": ["all"],
                    },
                },
                "required": ["context"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "learn_fact",
            "description": "Store a learned fact for future reference. "
            "Use when discovering new information about the codebase.",
            "parameters": {
                "type": "object",
                "properties": {
                    "fact": {
                        "type": "string",
                        "description": "The fact to remember",
                    },
                    "importance": {
                        "type": "string",
                        "enum": ["low", "medium", "high", "critical"],
                        "description": "Importance level of the fact",
                        "default": "medium",
                    },
                    "category": {
                        "type": "string",
                        "description": "Category for the fact (e.g., 'api', 'architecture', 'bug')",
                    },
                },
                "required": ["fact"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "forget_memory",
            "description": "Remove outdated or incorrect memory. Use sparingly.",
            "parameters": {
                "type": "object",
                "properties": {
                    "memory_id": {
                        "type": "string",
                        "description": "ID of the memory to forget",
                    },
                    "reason": {
                        "type": "string",
                        "description": "Reason for forgetting (for audit)",
                    },
                },
                "required": ["memory_id", "reason"],
            },
        },
    },
]

# ============================================================
# Core Memory (Working Memory)
# ============================================================


@dataclass
class CoreMemorySection:
    """A section of core memory."""

    name: str
    content: str
    max_length: int = 2000
    last_updated: datetime = field(default_factory=datetime.now)


@dataclass
class CoreMemory:
    """
    MemGPT-style Core Memory.

    Fixed-size, always-visible memory for critical context.
    """

    profile: CoreMemorySection = field(default_factory=lambda: CoreMemorySection(name="profile", content=""))
    preferences: CoreMemorySection = field(default_factory=lambda: CoreMemorySection(name="preferences", content=""))
    project: CoreMemorySection = field(default_factory=lambda: CoreMemorySection(name="project", content=""))
    facts: CoreMemorySection = field(default_factory=lambda: CoreMemorySection(name="facts", content=""))

    def get_section(self, name: str) -> CoreMemorySection | None:
        """Get section by name."""
        return getattr(self, name, None)

    def append(self, section: str, content: str) -> tuple[bool, str]:
        """
        Append content to a section.

        Returns: (success, message)
        """
        sec = self.get_section(section)
        if not sec:
            return False, f"Unknown section: {section}"

        # Check length
        new_content = sec.content + ("\n" if sec.content else "") + content
        if len(new_content) > sec.max_length:
            return False, f"Content exceeds max length ({sec.max_length})"

        sec.content = new_content
        sec.last_updated = datetime.now()
        return True, f"Appended to {section}"

    def replace(self, section: str, old: str, new: str) -> tuple[bool, str]:
        """
        Replace content in a section.

        Returns: (success, message)
        """
        sec = self.get_section(section)
        if not sec:
            return False, f"Unknown section: {section}"

        if old not in sec.content:
            return False, f"Content '{old[:50]}...' not found in {section}"

        new_content = sec.content.replace(old, new)
        if len(new_content) > sec.max_length:
            return False, f"New content exceeds max length ({sec.max_length})"

        sec.content = new_content
        sec.last_updated = datetime.now()
        return True, f"Replaced in {section}"

    def to_system_prompt(self) -> str:
        """Format core memory for system prompt injection."""
        parts = []

        if self.profile.content:
            parts.append(f"<profile>\n{self.profile.content}\n</profile>")

        if self.preferences.content:
            parts.append(f"<preferences>\n{self.preferences.content}\n</preferences>")

        if self.project.content:
            parts.append(f"<project>\n{self.project.content}\n</project>")

        if self.facts.content:
            parts.append(f"<facts>\n{self.facts.content}\n</facts>")

        return "\n\n".join(parts)

    def to_dict(self) -> dict[str, Any]:
        """Serialize core memory."""
        return {
            "profile": {
                "content": self.profile.content,
                "last_updated": self.profile.last_updated.isoformat(),
            },
            "preferences": {
                "content": self.preferences.content,
                "last_updated": self.preferences.last_updated.isoformat(),
            },
            "project": {
                "content": self.project.content,
                "last_updated": self.project.last_updated.isoformat(),
            },
            "facts": {
                "content": self.facts.content,
                "last_updated": self.facts.last_updated.isoformat(),
            },
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "CoreMemory":
        """Deserialize core memory."""
        mem = cls()

        for section_name in ["profile", "preferences", "project", "facts"]:
            if section_name in data:
                sec = mem.get_section(section_name)
                if sec:
                    sec.content = data[section_name].get("content", "")
                    if "last_updated" in data[section_name]:
                        sec.last_updated = datetime.fromisoformat(data[section_name]["last_updated"])

        return mem


# ============================================================
# Memory Tool Executor
# ============================================================


class MemoryBackend(Protocol):
    """Protocol for memory storage backend."""

    async def search(
        self,
        query: str,
        memory_types: list[MemoryType],
        limit: int,
    ) -> list[MemoryUnit]:
        """Search memories."""
        ...

    async def insert(
        self,
        content: str,
        memory_type: MemoryType,
        metadata: dict[str, Any],
    ) -> str:
        """Insert memory, return ID."""
        ...

    async def delete(self, memory_id: str) -> bool:
        """Delete memory."""
        ...

    async def search_conversations(
        self,
        query: str,
        limit: int,
    ) -> list[dict[str, Any]]:
        """Search conversation history."""
        ...


@dataclass
class ToolResult:
    """Result of tool execution."""

    success: bool
    message: str
    data: Any = None


class MemoryToolExecutor:
    """
    Executes memory tools called by LLM.

    Handles all MemGPT-style memory operations.
    """

    def __init__(
        self,
        backend: MemoryBackend,
        core_memory: CoreMemory | None = None,
        project_id: str = "default",
        user_id: str = "default",
    ):
        """
        Initialize tool executor.

        Args:
            backend: Memory storage backend
            core_memory: Core memory instance (creates new if None)
            project_id: Project ID for scoping
            user_id: User ID for scoping
        """
        self.backend = backend
        self.core = core_memory or CoreMemory()
        self.project_id = project_id
        self.user_id = user_id

        # Register tool handlers
        self._handlers: dict[str, Callable] = {
            "core_memory_append": self._handle_core_append,
            "core_memory_replace": self._handle_core_replace,
            "archival_memory_insert": self._handle_archival_insert,
            "archival_memory_search": self._handle_archival_search,
            "conversation_search": self._handle_conversation_search,
            "recall_memory": self._handle_recall,
            "learn_fact": self._handle_learn_fact,
            "forget_memory": self._handle_forget,
        }

    async def execute(self, tool_name: str, arguments: dict[str, Any]) -> ToolResult:
        """
        Execute a memory tool.

        Args:
            tool_name: Name of the tool to execute
            arguments: Tool arguments

        Returns:
            ToolResult with execution outcome
        """
        handler = self._handlers.get(tool_name)
        if not handler:
            return ToolResult(
                success=False,
                message=f"Unknown tool: {tool_name}",
            )

        try:
            return await handler(arguments)
        except Exception as e:
            logger.error(f"Tool execution failed: {tool_name} - {e}")
            return ToolResult(
                success=False,
                message=f"Tool execution failed: {str(e)}",
            )

    async def execute_function_call(
        self,
        function_call: dict[str, Any],
    ) -> ToolResult:
        """
        Execute from OpenAI function call format.

        Args:
            function_call: OpenAI function call object

        Returns:
            ToolResult
        """
        name = function_call.get("name", "")
        args_str = function_call.get("arguments", "{}")

        try:
            arguments = json.loads(args_str)
        except json.JSONDecodeError:
            return ToolResult(
                success=False,
                message=f"Invalid JSON arguments: {args_str}",
            )

        return await self.execute(name, arguments)

    # ============================================================
    # Tool Handlers
    # ============================================================

    async def _handle_core_append(self, args: dict[str, Any]) -> ToolResult:
        """Handle core_memory_append."""
        section = args.get("section", "")
        content = args.get("content", "")

        success, message = self.core.append(section, content)
        return ToolResult(success=success, message=message)

    async def _handle_core_replace(self, args: dict[str, Any]) -> ToolResult:
        """Handle core_memory_replace."""
        section = args.get("section", "")
        old_content = args.get("old_content", "")
        new_content = args.get("new_content", "")

        success, message = self.core.replace(section, old_content, new_content)
        return ToolResult(success=success, message=message)

    async def _handle_archival_insert(self, args: dict[str, Any]) -> ToolResult:
        """Handle archival_memory_insert."""
        content = args.get("content", "")
        tags = args.get("tags", [])

        memory_id = await self.backend.insert(
            content=content,
            memory_type=MemoryType.FACT,
            metadata={
                "tags": tags,
                "project_id": self.project_id,
                "user_id": self.user_id,
            },
        )

        return ToolResult(
            success=True,
            message="Inserted into archival memory",
            data={"memory_id": memory_id},
        )

    async def _handle_archival_search(self, args: dict[str, Any]) -> ToolResult:
        """Handle archival_memory_search."""
        query = args.get("query", "")
        limit = args.get("limit", 5)

        memories = await self.backend.search(
            query=query,
            memory_types=[MemoryType.FACT, MemoryType.SEMANTIC],
            limit=limit,
        )

        return ToolResult(
            success=True,
            message=f"Found {len(memories)} memories",
            data={"memories": [{"id": m.id, "content": m.content, "importance": m.importance} for m in memories]},
        )

    async def _handle_conversation_search(self, args: dict[str, Any]) -> ToolResult:
        """Handle conversation_search."""
        query = args.get("query", "")
        limit = args.get("limit", 5)

        conversations = await self.backend.search_conversations(
            query=query,
            limit=limit,
        )

        return ToolResult(
            success=True,
            message=f"Found {len(conversations)} conversation segments",
            data={"conversations": conversations},
        )

    async def _handle_recall(self, args: dict[str, Any]) -> ToolResult:
        """Handle recall_memory."""
        context = args.get("context", "")
        memory_types_raw = args.get("memory_types", ["all"])

        # Map to MemoryType
        if "all" in memory_types_raw:
            memory_types = [MemoryType.EPISODIC, MemoryType.SEMANTIC, MemoryType.FACT]
        else:
            type_map = {
                "episodic": MemoryType.EPISODIC,
                "semantic": MemoryType.SEMANTIC,
                "fact": MemoryType.FACT,
            }
            memory_types = [type_map[t] for t in memory_types_raw if t in type_map]

        memories = await self.backend.search(
            query=context,
            memory_types=memory_types,
            limit=10,
        )

        return ToolResult(
            success=True,
            message=f"Recalled {len(memories)} relevant memories",
            data={
                "memories": [
                    {
                        "id": m.id,
                        "content": m.content,
                        "type": m.memory_type.value,
                        "importance": m.importance,
                    }
                    for m in memories
                ]
            },
        )

    async def _handle_learn_fact(self, args: dict[str, Any]) -> ToolResult:
        """Handle learn_fact."""
        fact = args.get("fact", "")
        importance_str = args.get("importance", "medium")
        category = args.get("category", "general")

        # Map importance string to score
        importance_map = {
            "low": 0.3,
            "medium": 0.5,
            "high": 0.7,
            "critical": 0.9,
        }
        importance = importance_map.get(importance_str, 0.5)

        memory_id = await self.backend.insert(
            content=fact,
            memory_type=MemoryType.FACT,
            metadata={
                "importance": importance,
                "category": category,
                "project_id": self.project_id,
                "user_id": self.user_id,
            },
        )

        return ToolResult(
            success=True,
            message=f"Learned fact with importance={importance_str}",
            data={"memory_id": memory_id},
        )

    async def _handle_forget(self, args: dict[str, Any]) -> ToolResult:
        """Handle forget_memory."""
        memory_id = args.get("memory_id", "")
        reason = args.get("reason", "")

        logger.info(f"Forgetting memory {memory_id}: {reason}")

        success = await self.backend.delete(memory_id)

        if success:
            return ToolResult(
                success=True,
                message=f"Forgot memory {memory_id}",
            )
        else:
            return ToolResult(
                success=False,
                message=f"Failed to forget memory {memory_id}",
            )


# ============================================================
# Memory-Aware Agent Wrapper
# ============================================================


class MemoryAwareAgent:
    """
    Wrapper that adds memory tools to an agent.

    Intercepts tool calls and handles memory operations.
    """

    def __init__(
        self,
        tool_executor: MemoryToolExecutor,
    ):
        """
        Initialize memory-aware agent.

        Args:
            tool_executor: Memory tool executor
        """
        self.executor = tool_executor

    def get_system_prompt_injection(self) -> str:
        """
        Get system prompt injection with core memory.

        Returns:
            String to inject into system prompt
        """
        core_content = self.executor.core.to_system_prompt()

        return f"""<core_memory>
{core_content}
</core_memory>

You have access to memory tools to manage your knowledge:
- Use core_memory_append to add important facts to your active memory
- Use core_memory_replace to update outdated information
- Use archival_memory_insert to store information for later
- Use archival_memory_search to find stored information
- Use recall_memory to retrieve relevant past experiences
- Use learn_fact to remember discovered facts
- Use forget_memory to remove incorrect information

Actively manage your memory to improve over time."""

    def get_tools(self) -> list[dict[str, Any]]:
        """Get memory tool definitions."""
        return MEMORY_TOOLS

    async def process_tool_call(
        self,
        tool_call: dict[str, Any],
    ) -> ToolResult | None:
        """
        Process a potential memory tool call.

        Args:
            tool_call: Tool call from LLM

        Returns:
            ToolResult if memory tool, None otherwise
        """
        name = tool_call.get("function", {}).get("name", "")

        # Check if this is a memory tool
        memory_tool_names = {t["function"]["name"] for t in MEMORY_TOOLS}
        if name not in memory_tool_names:
            return None

        # Execute memory tool
        return await self.executor.execute_function_call(tool_call.get("function", {}))


# ============================================================
# Factory Functions
# ============================================================


def create_memory_tools(
    backend: MemoryBackend,
    project_id: str = "default",
    user_id: str = "default",
) -> tuple[MemoryToolExecutor, list[dict[str, Any]]]:
    """
    Create memory tool executor and tool definitions.

    Args:
        backend: Memory storage backend
        project_id: Project ID
        user_id: User ID

    Returns:
        Tuple of (executor, tool_definitions)
    """
    executor = MemoryToolExecutor(
        backend=backend,
        project_id=project_id,
        user_id=user_id,
    )

    return executor, MEMORY_TOOLS


def create_memory_aware_agent(
    backend: MemoryBackend,
    project_id: str = "default",
    user_id: str = "default",
    core_memory: CoreMemory | None = None,
) -> MemoryAwareAgent:
    """
    Create memory-aware agent wrapper.

    Args:
        backend: Memory storage backend
        project_id: Project ID
        user_id: User ID
        core_memory: Optional existing core memory

    Returns:
        MemoryAwareAgent
    """
    executor = MemoryToolExecutor(
        backend=backend,
        core_memory=core_memory,
        project_id=project_id,
        user_id=user_id,
    )

    return MemoryAwareAgent(executor)
