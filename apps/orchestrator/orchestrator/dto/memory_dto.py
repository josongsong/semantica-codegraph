"""
Memory DTO (Data Transfer Object)

Agent ↔ session_memory Context 간 데이터 전송용.
도메인 모델 직접 의존 방지 (Hexagonal Architecture).
"""

import uuid
from dataclasses import dataclass, field
from typing import Any

# 유효한 MemoryType 값 (도메인 모델과 동기화 필수)
VALID_MEMORY_TYPES = frozenset({"working", "episodic", "semantic", "profile", "preference", "fact", "none"})

# Agent 레이어 타입 → 도메인 타입 매핑 (L11 SOTA: Immutable)
from types import MappingProxyType

MEMORY_TYPE_MAPPING = MappingProxyType(
    {
        "experience": "episodic",  # 경험 → 에피소드 메모리
        "knowledge": "semantic",  # 지식 → 시맨틱 메모리
        "context": "working",  # 컨텍스트 → 워킹 메모리
    }
)


def normalize_memory_type(memory_type: str) -> str:
    """Agent 레이어 타입을 도메인 타입으로 정규화 (모듈 레벨 함수)"""
    if not memory_type:
        return "working"
    lower = memory_type.lower()
    return MEMORY_TYPE_MAPPING.get(lower, lower)


@dataclass(frozen=True)
class MemoryDTO:
    """
    Agent 레이어용 Memory DTO.

    Immutable (frozen=True) - 안전한 전달 보장.

    Note:
        memory_type은 Agent 레이어 타입 또는 도메인 타입 모두 허용.
        Agent 타입(experience, knowledge, context)은 자동 변환됨.
    """

    session_id: str
    content: str
    memory_type: str = "working"
    metadata: dict[str, Any] = field(default_factory=dict)
    id: str = field(default_factory=lambda: str(uuid.uuid4()))

    # 정규화된 타입 캐싱 (frozen이므로 object.__setattr__ 사용)
    _normalized_type: str = field(default="", init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        """입력 검증 및 정규화 캐싱"""
        normalized = normalize_memory_type(self.memory_type)
        if normalized not in VALID_MEMORY_TYPES:
            raise ValueError(
                f"Invalid memory_type: '{self.memory_type}'. "
                f"Valid types: {sorted(VALID_MEMORY_TYPES)} or "
                f"aliases: {list(MEMORY_TYPE_MAPPING.keys())}"
            )
        # frozen dataclass에서 값 설정
        object.__setattr__(self, "_normalized_type", normalized)

    def to_domain(self) -> Any:
        """
        도메인 모델로 변환.

        Returns:
            Memory 도메인 객체

        Note:
            Lazy import로 순환 의존 방지.
            정규화는 __post_init__에서 이미 완료됨 (캐싱).
        """
        from codegraph_runtime.session_memory.domain.models import Memory, MemoryType

        return Memory(
            id=self.id,
            session_id=self.session_id,
            content=self.content,
            type=MemoryType(self._normalized_type),
            metadata=dict(self.metadata),  # 방어적 복사
        )

    @classmethod
    def from_domain(cls, memory: Any) -> "MemoryDTO":
        """
        도메인 모델에서 DTO 생성.

        Args:
            memory: Memory 도메인 객체

        Returns:
            MemoryDTO
        """
        return cls(
            id=memory.id,
            session_id=memory.session_id,
            content=memory.content,
            memory_type=memory.type.value if memory.type else "working",
            metadata=dict(memory.metadata) if memory.metadata else {},
        )
