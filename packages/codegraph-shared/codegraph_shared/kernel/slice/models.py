"""
Slice Models - Pure Data Classes

Extracted from: reasoning_engine/infrastructure/slicer/slicer.py
Purpose: Shared models for program slicing
"""

from dataclasses import dataclass, field
from typing import Any, Literal


@dataclass
class SliceConfig:
    """슬라이싱 설정"""

    max_depth: int = 100
    """최대 dependency depth (무한 루프 방지)"""

    include_control: bool = True
    """Control dependency 포함 여부"""

    include_data: bool = True
    """Data dependency 포함 여부"""

    interprocedural: bool = True
    """함수 경계 넘는 슬라이싱 (caller/callee 추적)"""

    max_function_depth: int = 3
    """Interprocedural slicing 시 최대 함수 호출 깊이"""

    strict_mode: bool = False
    """Strict mode: Node not found 시 exception raise (default: False)"""


@dataclass
class CodeFragment:
    """코드 조각"""

    file_path: str
    """파일 경로"""

    start_line: int
    """시작 라인"""

    end_line: int
    """끝 라인"""

    code: str
    """실제 코드"""

    node_id: str
    """PDG node ID"""

    relevance_score: float = 1.0
    """관련도 점수 (0.0-1.0)"""


@dataclass
class SliceResult:
    """슬라이싱 결과"""

    target_variable: str
    """Target 변수/노드"""

    slice_type: Literal["backward", "forward", "hybrid"]
    """슬라이스 타입"""

    slice_nodes: set[str] = field(default_factory=set)
    """포함된 PDG node IDs"""

    code_fragments: list[CodeFragment] = field(default_factory=list)
    """실제 코드 조각들"""

    control_context: list[str] = field(default_factory=list)
    """Control flow 설명"""

    total_tokens: int = 0
    """총 토큰 수 (추정)"""

    confidence: float = 1.0
    """슬라이스 정확도 (0.0-1.0)"""

    metadata: dict[str, Any] = field(default_factory=dict)
    """추가 메타데이터"""

    def get_total_lines(self) -> int:
        """총 라인 수"""
        return sum(frag.end_line - frag.start_line + 1 for frag in self.code_fragments)

    def estimate_tokens(self) -> int:
        """토큰 수 추정 (1 line ≈ 10 tokens)"""
        return self.get_total_lines() * 10

    def to_dict(self) -> dict[str, Any]:
        """딕셔너리로 변환"""
        return {
            "target_variable": self.target_variable,
            "slice_type": self.slice_type,
            "node_count": len(self.slice_nodes),
            "fragment_count": len(self.code_fragments),
            "total_lines": self.get_total_lines(),
            "total_tokens": self.total_tokens or self.estimate_tokens(),
            "confidence": self.confidence,
            "control_context_count": len(self.control_context),
        }
