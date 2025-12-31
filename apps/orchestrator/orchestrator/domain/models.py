"""
Agent Domain Models

비즈니스 로직을 포함한 Domain Model.
❌ Pydantic으로 Domain Model 대체 금지
✅ @dataclass + 메서드로 비즈니스 규칙 표현
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any

# ============================================================
# Enums
# ============================================================


class ChangeType(str, Enum):
    """코드 변경 타입"""

    CREATE = "create"
    MODIFY = "modify"
    DELETE = "delete"


class WorkflowStepType(str, Enum):
    """Workflow 단계"""

    ANALYZE = "analyze"
    PLAN = "plan"
    GENERATE = "generate"
    CRITIC = "critic"
    TEST = "test"
    HEAL = "heal"


class ExecutionStatus(str, Enum):
    """실행 상태"""

    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    TIMEOUT = "timeout"


# ============================================================
# Core Domain Models
# ============================================================


@dataclass
class AgentTask:
    """
    Agent Task Domain Model.

    비즈니스 로직:
    - 복잡도 추정
    - 명확화 필요 여부 판단
    - 우선순위 계산
    """

    task_id: str
    description: str
    repo_id: str
    snapshot_id: str
    context_files: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.now)

    def __post_init__(self):
        """데이터 검증"""
        # task_id 검증
        if not self.task_id or not self.task_id.strip():
            raise ValueError("task_id는 빈 문자열일 수 없습니다")

        # repo_id 검증
        if not self.repo_id or not self.repo_id.strip():
            raise ValueError("repo_id는 빈 문자열일 수 없습니다")

        # snapshot_id 검증
        if not self.snapshot_id or not self.snapshot_id.strip():
            raise ValueError("snapshot_id는 빈 문자열일 수 없습니다")

    def estimate_complexity(self) -> int:
        """
        복잡도 추정 (비즈니스 로직).

        Returns:
            1-10 스케일 복잡도 점수
            - 1-3: 단순 (단일 파일, 단일 함수)
            - 4-7: 중간 (멀티 파일, 로직 변경)
            - 8-10: 복잡 (아키텍처 변경, 멀티 모듈)
        """
        score = 1

        # 파일 개수 기준
        if len(self.context_files) > 10:
            score += 4
        elif len(self.context_files) > 3:
            score += 2

        # 설명 길이 기준
        word_count = len(self.description.split())
        if word_count > 50:
            score += 3
        elif word_count >= 20:  # >= 로 수정 (20단어도 포함)
            score += 1

        # 키워드 기준
        complex_keywords = [
            "refactor",
            "architecture",
            "migrate",
            "redesign",
            "multiple",
        ]
        if any(keyword in self.description.lower() for keyword in complex_keywords):
            score += 3

        return min(score, 10)

    def requires_clarification(self) -> bool:
        """
        명확화 필요 여부 판단.

        Returns:
            True면 사용자에게 질문 필요
        """
        # 물음표가 있으면 애매한 요청
        if "?" in self.description:
            return True

        # 설명이 너무 짧으면 불명확
        if len(self.description.split()) < 5:
            return True

        # 모호한 키워드
        ambiguous_keywords = ["maybe", "probably", "perhaps", "could", "might"]
        if any(keyword in self.description.lower() for keyword in ambiguous_keywords):
            return True

        return False

    def calculate_priority(self) -> int:
        """
        우선순위 계산.

        Returns:
            1-10 스케일 우선순위 (높을수록 우선)
        """
        priority = 5  # 기본

        # 긴급 키워드
        urgent_keywords = ["urgent", "critical", "asap", "hotfix", "production"]
        if any(keyword in self.description.lower() for keyword in urgent_keywords):
            priority += 4

        # 버그 수정은 우선순위 높음
        if "bug" in self.description.lower() or "fix" in self.description.lower():
            priority += 2

        return min(priority, 10)


@dataclass
class CodeChange:
    """
    Code Change Domain Model.

    비즈니스 로직:
    - 영향도 점수 계산
    - Breaking change 여부 판단
    - 리뷰 필요 여부
    """

    file_path: str
    change_type: ChangeType
    original_lines: list[str] = field(default_factory=list)
    new_lines: list[str] = field(default_factory=list)
    start_line: int | None = None
    end_line: int | None = None
    rationale: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        """데이터 검증"""
        # file_path 검증
        if not self.file_path or not self.file_path.strip():
            raise ValueError("file_path는 빈 문자열일 수 없습니다")

        # Directory traversal 방지
        if ".." in self.file_path:
            raise ValueError(f"file_path에 '..'는 허용되지 않습니다: {self.file_path}")

        # 절대 경로 방지 (보안)
        if self.file_path.startswith("/"):
            raise ValueError(f"file_path는 상대 경로여야 합니다: {self.file_path}")

        # Line number 검증
        if self.start_line is not None and self.start_line < 0:
            raise ValueError(f"start_line은 0 이상이어야 합니다: {self.start_line}")

        if self.end_line is not None and self.end_line < 0:
            raise ValueError(f"end_line은 0 이상이어야 합니다: {self.end_line}")

        if self.start_line is not None and self.end_line is not None and self.start_line > self.end_line:
            raise ValueError(f"start_line({self.start_line})은 end_line({self.end_line})보다 작거나 같아야 합니다")

    def calculate_impact_score(self) -> float:
        """
        영향도 점수 계산 (0.0 ~ 1.0).

        Returns:
            0.0: 영향 없음
            0.5: 중간 영향
            1.0: 큰 영향
        """
        if self.change_type == ChangeType.DELETE:
            return 0.8  # 삭제는 높은 영향

        if self.change_type == ChangeType.CREATE:
            return 0.3  # 새로 만드는 건 기존 코드 영향 적음

        # MODIFY
        if not self.original_lines or not self.new_lines:
            return 0.5

        # 변경된 라인 비율
        changed_ratio = len(self.new_lines) / max(len(self.original_lines), 1)

        # 1줄 수정 vs 전체 재작성
        if changed_ratio < 0.2:
            return 0.2
        elif changed_ratio < 0.5:
            return 0.5
        else:
            return 0.8

    def is_breaking_change(self) -> bool:
        """
        Breaking change 여부 판단.

        Returns:
            True면 API 호환성 깨짐
        """
        # Internal 파일은 breaking change 아님 (우선순위 높음)
        if "internal" in self.file_path or "private" in self.file_path or "_internal" in self.file_path:
            return False

        # Public API 파일인지 체크
        is_public_api = any(
            pattern in self.file_path for pattern in ["__init__.py", "/api/", "/interface/", "/public/"]
        )

        if not is_public_api:
            return False

        # 삭제는 무조건 breaking
        if self.change_type == ChangeType.DELETE:
            return True

        # 함수 시그니처 변경 체크 (간단한 휴리스틱)
        breaking_patterns = [
            "def ",  # 함수 정의
            "class ",  # 클래스 정의
            "async def ",  # async 함수
        ]

        original_defs = [line for line in self.original_lines if any(pattern in line for pattern in breaking_patterns)]
        new_defs = [line for line in self.new_lines if any(pattern in line for pattern in breaking_patterns)]

        # 정의가 달라졌으면 breaking
        if set(original_defs) != set(new_defs):
            return True

        return False

    def needs_review(self) -> bool:
        """
        코드 리뷰 필요 여부.

        Returns:
            True면 사람 리뷰 필요
        """
        # Breaking change는 무조건 리뷰
        if self.is_breaking_change():
            return True

        # 영향도 큼
        if self.calculate_impact_score() > 0.7:
            return True

        # 변경 라인이 많음
        if len(self.new_lines) > 100:
            return True

        return False

    def get_loc_delta(self) -> int:
        """
        LOC 변화량.

        Returns:
            양수: 증가, 음수: 감소
        """
        return len(self.new_lines) - len(self.original_lines)


@dataclass
class WorkflowState:
    """
    Workflow 상태 Domain Model.

    비즈니스 로직:
    - 상태 전이 가능 여부 판단
    - 재계획 필요 여부
    - Early exit 조건
    """

    task: AgentTask
    current_step: WorkflowStepType
    changes: list[CodeChange] = field(default_factory=list)
    test_results: list["ExecutionResult"] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    iteration: int = 0
    max_iterations: int = 5
    metadata: dict[str, Any] = field(default_factory=dict)
    started_at: datetime = field(default_factory=datetime.now)

    def __post_init__(self):
        """데이터 검증"""
        # iteration 검증
        if self.iteration < 0:
            raise ValueError(f"iteration은 0 이상이어야 합니다: {self.iteration}")

        # max_iterations 검증
        if self.max_iterations <= 0:
            raise ValueError(f"max_iterations는 1 이상이어야 합니다: {self.max_iterations}")

        # iteration이 max_iterations를 초과하면 경고 (허용은 하되 로그)
        if self.iteration > self.max_iterations:
            import logging

            logging.warning(f"iteration({self.iteration})이 max_iterations({self.max_iterations})를 초과했습니다")

    def can_transition_to(self, next_step: WorkflowStepType) -> bool:
        """
        다음 단계로 전이 가능 여부 (비즈니스 규칙).

        Args:
            next_step: 전이하려는 다음 단계

        Returns:
            True면 전이 가능
        """
        # Test 단계는 코드 변경이 있어야 함
        if next_step == WorkflowStepType.TEST and not self.changes:
            return False

        # Max iteration 초과
        if self.iteration >= self.max_iterations:
            return False

        # 에러가 너무 많으면 중단
        if len(self.errors) > 10:
            return False

        return True

    def should_replan(self) -> bool:
        """
        재계획 필요 여부.

        Returns:
            True면 Plan 단계로 돌아가야 함
        """
        # 에러가 3개 이상이면 접근 방식 변경
        if len(self.errors) >= 3:
            return True

        # 테스트 실패가 반복되면
        failed_tests = [r for r in self.test_results if r.exit_code != 0]
        if len(failed_tests) > 2:
            return True

        return False

    def should_exit_early(self) -> bool:
        """
        Early exit 조건 (성공).

        Returns:
            True면 workflow 종료
        """
        # 코드 변경 없으면 실패
        if not self.changes:
            return False

        # 테스트 모두 성공
        if self.test_results and all(r.exit_code == 0 for r in self.test_results):
            return True

        # Critic 통과 + 테스트 없는 경우 (Phase 1)
        if self.current_step == WorkflowStepType.CRITIC and not self.errors:
            return True

        return False

    def get_total_loc_delta(self) -> int:
        """전체 LOC 변화량"""
        return sum(change.get_loc_delta() for change in self.changes)

    def get_affected_files(self) -> set[str]:
        """영향받은 파일 목록"""
        return {change.file_path for change in self.changes}


# ============================================================
# Result Models
# ============================================================


@dataclass
class AnalysisResult:
    """분석 결과"""

    summary: str
    complexity: int
    requires_clarification: bool
    suggested_approach: str
    estimated_time_minutes: int
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ExecutionResult:
    """코드 실행 결과"""

    stdout: str
    stderr: str
    exit_code: int
    execution_time_ms: int
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        """데이터 검증"""
        # exit_code 범위 검증 (UNIX 표준: 0-255)
        if not 0 <= self.exit_code <= 255:
            raise ValueError(f"exit_code는 0-255 범위여야 합니다: {self.exit_code}")

        # execution_time_ms 검증
        if self.execution_time_ms < 0:
            raise ValueError(f"execution_time_ms는 0 이상이어야 합니다: {self.execution_time_ms}")

    def is_success(self) -> bool:
        """실행 성공 여부"""
        return self.exit_code == 0


@dataclass
class SandboxHandle:
    """Sandbox 핸들"""

    sandbox_id: str
    sandbox_type: str  # "local" | "e2b" | "docker"
    created_at: datetime = field(default_factory=datetime.now)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class Screenshot:
    """스크린샷"""

    image_data: bytes
    width: int
    height: int
    url: str
    captured_at: datetime = field(default_factory=datetime.now)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ValidationResult:
    """검증 결과"""

    valid: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class CommitResult:
    """커밋 결과"""

    commit_sha: str
    branch_name: str
    changed_files: list[str] = field(default_factory=list)
    timestamp: datetime = field(default_factory=datetime.now)


@dataclass
class PRResult:
    """PR 결과"""

    pr_number: int
    pr_url: str
    title: str
    body: str


@dataclass
class MergeConflict:
    """Merge 충돌"""

    file_path: str
    conflict_content: str
    base_content: str
    ours_content: str
    theirs_content: str


@dataclass
class ConflictResolution:
    """충돌 해결"""

    resolved: bool
    resolution_code: str
    strategy: str  # "llm" | "ours" | "theirs"


@dataclass
class VisualDiff:
    """시각적 차이"""

    has_difference: bool
    diff_description: str
    diff_score: float  # 0.0 ~ 1.0
    diff_regions: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class WorkflowResult:
    """Workflow 최종 결과"""

    success: bool
    final_state: WorkflowState
    total_iterations: int
    total_time_seconds: float
    changes: list[CodeChange]
    test_results: list[ExecutionResult]
    errors: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
