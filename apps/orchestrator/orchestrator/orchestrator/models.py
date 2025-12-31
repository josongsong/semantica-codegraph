"""V8 Agent Request/Response Models (Type-safe)"""

from dataclasses import dataclass
from enum import Enum
from typing import Any, NotRequired, TypedDict

from apps.orchestrator.orchestrator.errors import ValidationError


class ReasoningStrategy(str, Enum):
    """V8 추론 전략 (SOTA Multi-Candidate Generation)

    Attributes:
        AUTO: 자동 선택 (complexity/risk 기반)
        TOT: Tree-of-Thought (3 strategies, reflection)
        BEAM: Beam Search (5+ candidates, diversity)
        O1: o1-style Deep Reasoning (verification loop)
        DEBATE: Multi-Agent Debate (3 proposers, 2 critics)
        ALPHACODE: AlphaCode Sampling (100+ samples, clustering) - Phase 1.5

    Usage:
        >>> request = DeepReasoningRequest(task=task, strategy=ReasoningStrategy.BEAM)
        >>> # Or use backward compatible alias V8AgentRequest
        >>> request = V8AgentRequest(task=task, strategy="beam")
    """

    AUTO = "auto"
    TOT = "tot"
    BEAM = "beam"
    O1 = "o1"
    DEBATE = "debate"
    ALPHACODE = "alphacode"  # Phase 1.5


class V8Config(TypedDict, total=False):
    """V8 Agent 설정 (Type-safe)

    모든 필드는 optional이며, 기본값이 사용됩니다.

    Attributes:
        max_iterations: 최대 반복 횟수 (기본: 3)
        timeout_seconds: 작업 타임아웃 (기본: 300.0)
        temperature: LLM temperature (기본: 0.7)
        enable_reflection: Self-reflection 활성화 (기본: True)
        enable_tot: Tree-of-Thought 활성화 (기본: True)
        system_2_threshold: System 2 전환 임계값 (기본: 0.7)

        # Strategy-specific configs (RFC-016 Phase 1)
        beam_width: Beam Search 너비 (기본: 5, 범위: 3-10)
        max_depth: Beam Search 깊이 (기본: 2, 범위: 1-5)
        o1_max_attempts: o1 최대 시도 횟수 (기본: 5, 범위: 1-10)
        o1_verification_threshold: o1 검증 임계값 (기본: 0.7, 범위: 0.5-1.0)
        num_proposers: Debate proposer 수 (기본: 3, 범위: 2-5)
        num_critics: Debate critic 수 (기본: 2, 범위: 1-5)
        max_rounds: Debate 최대 라운드 (기본: 1, 범위: 1-3)

    Example:
        >>> config: V8Config = {
        ...     "max_iterations": 5,
        ...     "timeout_seconds": 600.0,
        ...     "temperature": 0.5,
        ...     "beam_width": 7,
        ... }
        >>> request = DeepReasoningRequest(task=task, config=config, strategy="beam")

    Validation Rules:
        - max_iterations: > 0, <= 10
        - timeout_seconds: > 0, <= 3600
        - temperature: >= 0.0, <= 2.0
        - system_2_threshold: >= 0.0, <= 1.0
        - beam_width: 3-10
        - max_depth: 1-5
        - o1_max_attempts: 1-10
        - o1_verification_threshold: 0.5-1.0
        - num_proposers: 2-5
        - num_critics: 1-5
        - max_rounds: 1-3
        - alphacode_num_samples: 50-200
        - alphacode_temperature: 0.5-1.0
        - alphacode_num_clusters: 5-20
    """

    max_iterations: NotRequired[int]
    timeout_seconds: NotRequired[float]
    temperature: NotRequired[float]
    enable_reflection: NotRequired[bool]
    enable_tot: NotRequired[bool]
    system_2_threshold: NotRequired[float]

    # RFC-016 Phase 1: Strategy-specific configs
    beam_width: NotRequired[int]
    max_depth: NotRequired[int]
    o1_max_attempts: NotRequired[int]
    o1_verification_threshold: NotRequired[float]
    num_proposers: NotRequired[int]
    num_critics: NotRequired[int]
    max_rounds: NotRequired[int]

    # RFC-016 Phase 1.5: AlphaCode configs
    alphacode_num_samples: NotRequired[int]  # 샘플 개수 (기본: 100, 범위: 50-200)
    alphacode_temperature: NotRequired[float]  # Temperature (기본: 0.8, 범위: 0.5-1.0)
    alphacode_num_clusters: NotRequired[int]  # 클러스터 개수 (기본: 10, 범위: 5-20)
    alphacode_parallel_workers: NotRequired[int]  # 병렬 평가 worker 수 (기본: 10, 범위: 1-50)
    alphacode_use_real_pytest: NotRequired[bool]  # 실제 pytest 실행 여부 (기본: False)
    alphacode_pytest_timeout: NotRequired[int]  # Pytest timeout (기본: 30, 범위: 10-300 초)
    alphacode_use_semantic_embedding: NotRequired[bool]  # Semantic embedding 클러스터링 (기본: False)
    alphacode_embedding_cache: NotRequired[bool]  # Embedding cache 사용 (기본: True)


def validate_v8_config(config: V8Config | None) -> None:
    """V8Config 검증

    Args:
        config: 검증할 설정

    Raises:
        ValueError: 설정값이 유효하지 않은 경우

    Example:
        >>> config: V8Config = {"max_iterations": 5}
        >>> validate_v8_config(config)  # OK
        >>>
        >>> bad_config: V8Config = {"max_iterations": -1}
        >>> validate_v8_config(bad_config)  # ValueError
    """
    if config is None:
        return

    if "max_iterations" in config:
        val = config["max_iterations"]
        if not isinstance(val, int) or val <= 0 or val > 10:
            raise ValidationError(
                f"max_iterations must be 1-10, got {val}. This controls how many times the agent retries failed tasks.",
                {"field": "max_iterations", "value": val, "expected": "1-10"},
            )

    if "timeout_seconds" in config:
        val = config["timeout_seconds"]
        if not isinstance(val, (int, float)) or val <= 0 or val > 3600:
            raise ValidationError(
                f"timeout_seconds must be 0-3600 (1 hour), got {val}. Set higher for complex tasks.",
                {"field": "timeout_seconds", "value": val, "expected": "0-3600"},
            )

    if "temperature" in config:
        val = config["temperature"]
        if not isinstance(val, (int, float)) or val < 0.0 or val > 2.0:
            raise ValidationError(
                f"temperature must be 0.0-2.0, got {val}. Lower = deterministic, higher = creative.",
                {"field": "temperature", "value": val, "expected": "0.0-2.0"},
            )

    if "system_2_threshold" in config:
        val = config["system_2_threshold"]
        if not isinstance(val, (int, float)) or val < 0.0 or val > 1.0:
            raise ValidationError(
                f"system_2_threshold must be 0.0-1.0, got {val}. Higher = more likely to use System 2 (ToT).",
                {"field": "system_2_threshold", "value": val, "expected": "0.0-1.0"},
            )

    # RFC-016 Phase 1: Strategy-specific validation
    if "beam_width" in config:
        val = config["beam_width"]
        if not isinstance(val, int) or val < 3 or val > 10:
            raise ValidationError(
                f"beam_width must be 3-10, got {val}. Higher = more candidates but more cost.",
                {"field": "beam_width", "value": val, "expected": "3-10"},
            )

    if "max_depth" in config:
        val = config["max_depth"]
        if not isinstance(val, int) or val < 1 or val > 5:
            raise ValidationError(
                f"max_depth must be 1-5, got {val}. Higher = more exploration but more cost.",
                {"field": "max_depth", "value": val, "expected": "1-5"},
            )

    if "o1_max_attempts" in config:
        val = config["o1_max_attempts"]
        if not isinstance(val, int) or val < 1 or val > 10:
            raise ValidationError(
                f"o1_max_attempts must be 1-10, got {val}. Higher = more verification iterations.",
                {"field": "o1_max_attempts", "value": val, "expected": "1-10"},
            )

    if "o1_verification_threshold" in config:
        val = config["o1_verification_threshold"]
        if not isinstance(val, (int, float)) or val < 0.5 or val > 1.0:
            raise ValidationError(
                f"o1_verification_threshold must be 0.5-1.0, got {val}. Higher = stricter verification.",
                {"field": "o1_verification_threshold", "value": val, "expected": "0.5-1.0"},
            )

    if "num_proposers" in config:
        val = config["num_proposers"]
        if not isinstance(val, int) or val < 2 or val > 5:
            raise ValidationError(
                f"num_proposers must be 2-5, got {val}. Higher = more diverse debate positions.",
                {"field": "num_proposers", "value": val, "expected": "2-5"},
            )

    if "num_critics" in config:
        val = config["num_critics"]
        if not isinstance(val, int) or val < 1 or val > 5:
            raise ValidationError(
                f"num_critics must be 1-5, got {val}. Higher = more thorough critique.",
                {"field": "num_critics", "value": val, "expected": "1-5"},
            )

    if "max_rounds" in config:
        val = config["max_rounds"]
        if not isinstance(val, int) or val < 1 or val > 3:
            raise ValidationError(
                f"max_rounds must be 1-3, got {val}. Higher = more debate iterations.",
                {"field": "max_rounds", "value": val, "expected": "1-3"},
            )

    # RFC-016 Phase 1.5: AlphaCode validation
    if "alphacode_num_samples" in config:
        val = config["alphacode_num_samples"]
        if not isinstance(val, int) or val < 50 or val > 200:
            raise ValidationError(
                f"alphacode_num_samples must be 50-200, got {val}. Higher = more diversity but more cost.",
                {"field": "alphacode_num_samples", "value": val, "expected": "50-200"},
            )

    if "alphacode_temperature" in config:
        val = config["alphacode_temperature"]
        if not isinstance(val, (int, float)) or val < 0.5 or val > 1.0:
            raise ValidationError(
                f"alphacode_temperature must be 0.5-1.0, got {val}. Higher = more diverse samples.",
                {"field": "alphacode_temperature", "value": val, "expected": "0.5-1.0"},
            )

    if "alphacode_num_clusters" in config:
        val = config["alphacode_num_clusters"]
        if not isinstance(val, int) or val < 5 or val > 20:
            raise ValidationError(
                f"alphacode_num_clusters must be 5-20, got {val}. Higher = finer-grained clustering.",
                {"field": "alphacode_num_clusters", "value": val, "expected": "5-20"},
            )

    # RFC-017 Phase 1: Parallel evaluation
    if "alphacode_parallel_workers" in config:
        val = config["alphacode_parallel_workers"]
        if not isinstance(val, int) or val < 1 or val > 50:
            raise ValidationError(
                f"alphacode_parallel_workers must be 1-50, got {val}. "
                "Higher = faster evaluation but more memory. Default: 10.",
                {"field": "alphacode_parallel_workers", "value": val, "expected": "1-50"},
            )

    # RFC-017 Phase 2: Real pytest execution
    if "alphacode_use_real_pytest" in config:
        val = config["alphacode_use_real_pytest"]
        if not isinstance(val, bool):
            raise ValidationError(
                f"alphacode_use_real_pytest must be bool, got {type(val).__name__}. "
                "True = real pytest (accurate), False = heuristic (fast). Default: False.",
                {"field": "alphacode_use_real_pytest", "value": val, "expected": "bool"},
            )

    if "alphacode_pytest_timeout" in config:
        val = config["alphacode_pytest_timeout"]
        if not isinstance(val, int) or val < 10 or val > 300:
            raise ValidationError(
                f"alphacode_pytest_timeout must be 10-300 seconds, got {val}. "
                "Higher = more time for complex tests. Default: 30.",
                {"field": "alphacode_pytest_timeout", "value": val, "expected": "10-300"},
            )

    # RFC-017 Phase 3: Semantic embedding clustering
    if "alphacode_use_semantic_embedding" in config:
        val = config["alphacode_use_semantic_embedding"]
        if not isinstance(val, bool):
            raise ValidationError(
                f"alphacode_use_semantic_embedding must be bool, got {type(val).__name__}. "
                "True = AST+LLM embedding (95% quality), False = string similarity (70%). Default: False.",
                {"field": "alphacode_use_semantic_embedding", "value": val, "expected": "bool"},
            )

    if "alphacode_embedding_cache" in config:
        val = config["alphacode_embedding_cache"]
        if not isinstance(val, bool):
            raise ValidationError(
                f"alphacode_embedding_cache must be bool, got {type(val).__name__}. "
                "True = cache embeddings (fast), False = recompute (slow). Default: True.",
                {"field": "alphacode_embedding_cache", "value": val, "expected": "bool"},
            )


# ============================================================================
# Legacy Models (Backward Compatibility)
# ============================================================================


class ExecutionStatus(str, Enum):
    """실행 상태 (Legacy)"""

    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"


@dataclass
class ExecutionContext:
    """실행 컨텍스트 (Legacy)"""

    task_id: str
    repo_id: str
    snapshot_id: str | None = None
    metadata: dict[str, Any] | None = None


@dataclass
class AgentResult:
    """Agent 실행 결과 (Legacy)"""

    success: bool
    message: str
    changes: list[str] | None = None
    errors: list[str] | None = None


@dataclass
class OrchestratorConfig:
    """Orchestrator 설정 (Legacy)"""

    max_iterations: int = 3
    timeout_seconds: float = 300.0
