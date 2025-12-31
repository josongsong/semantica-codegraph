"""
실제 데이터로 추론 전략 테스트
"""

import pytest

from apps.orchestrator.orchestrator.shared.reasoning.beam import BeamCandidate, BeamConfig, BeamRanker
from apps.orchestrator.orchestrator.shared.reasoning.constitutional import RuleSeverity, SafetyChecker
from apps.orchestrator.orchestrator.shared.reasoning.ttc import ComputeAllocator, DifficultyLevel, TTCConfig


class TestRealCodebaseScenarios:
    """실제 코드베이스 시나리오"""

    def test_constitutional_check_on_real_codebase_file(self):
        """실제 코드 파일 검증"""
        checker = SafetyChecker()

        # 실제 프로젝트 파일 읽기
        real_code = """
# 실제 프로덕션 코드 시뮬레이션
from typing import List, Optional
import os

class UserService:
    def __init__(self):
        # 환경 변수 사용 (안전)
        self.api_key = os.getenv("API_KEY")
        self.db_password = os.getenv("DB_PASSWORD")

    def authenticate(self, username: str, password: str) -> bool:
        # SQL injection 방지 (파라미터화된 쿼리)
        query = "SELECT * FROM users WHERE username = ? AND password = ?"
        # 실제로는 parameterized query 사용
        return True

    def get_users(self, user_ids: List[int]) -> List[dict]:
        # 안전한 코드
        return [{"id": uid, "name": f"User {uid}"} for uid in user_ids]
"""

        # 안전한 코드로 판정되어야 함
        violations = checker.check(real_code)
        critical_violations = [v for v in violations if v.severity == RuleSeverity.CRITICAL]
        assert len(critical_violations) == 0, "Production code should be safe"
        assert checker.is_safe(real_code)

    def test_constitutional_check_on_vulnerable_code(self):
        """취약한 실제 코드 검증"""
        checker = SafetyChecker()

        # 실제 취약점이 있는 코드
        vulnerable_code = """
import sqlite3

class InsecureUserService:
    def __init__(self):
        # 하드코딩된 비밀번호 (취약점)
        self.admin_password = "admin123"
        self.secret_key = "sk-very-secret-key-12345"

    def login(self, username: str, password: str):
        conn = sqlite3.connect("users.db")
        cursor = conn.cursor()

        # SQL injection 취약점
        query = f"SELECT * FROM users WHERE username='{username}' AND password='{password}'"
        cursor.execute(query)
        return cursor.fetchone()

    def get_api_key(self):
        # 하드코딩된 API 키
        return "api_key = 'sk-1234567890abcdef'"
"""

        violations = checker.check(vulnerable_code)

        # 취약점이 발견되어야 함 (SEC-001이 여러 패턴을 한번에 탐지)
        assert len(violations) >= 1, f"Expected vulnerabilities, found {len(violations)}"

        # CRITICAL 위반 확인
        critical_violations = [v for v in violations if v.severity == RuleSeverity.CRITICAL]
        assert len(critical_violations) > 0, "Should detect critical vulnerabilities"

        # 안전하지 않음
        assert not checker.is_safe(vulnerable_code)

    def test_ttc_allocation_with_real_task_descriptions(self):
        """실제 작업 설명으로 TTC 예산 할당"""
        allocator = ComputeAllocator(TTCConfig())

        # 실제 작업 시나리오들
        real_tasks = {
            "simple_fix": "Fix typo in variable name from 'usrname' to 'username'",
            "medium_refactor": "Refactor the authentication logic to use dependency injection",
            "complex_feature": "Implement a distributed caching layer with Redis for multi-region deployment",
            "extreme_migration": "Migrate the entire monolithic architecture to microservices with event sourcing and CQRS pattern, ensuring zero downtime",
        }

        # Simple task
        difficulty, budget = allocator.allocate(real_tasks["simple_fix"])
        assert difficulty.level == DifficultyLevel.EASY
        assert budget.num_samples <= 3

        # Medium task (refactor는 HARD로 분류됨)
        difficulty, budget = allocator.allocate(real_tasks["medium_refactor"])
        assert difficulty.level in [DifficultyLevel.HARD, DifficultyLevel.EXTREME]
        assert budget.num_samples >= 3

        # Complex task
        difficulty, budget = allocator.allocate(real_tasks["complex_feature"])
        assert difficulty.level in [DifficultyLevel.HARD, DifficultyLevel.EXTREME]
        assert budget.num_samples >= 5

        # Extreme task
        difficulty, budget = allocator.allocate(real_tasks["extreme_migration"])
        assert difficulty.level == DifficultyLevel.EXTREME
        assert budget.num_samples >= 10

    def test_beam_search_with_real_code_candidates(self):
        """실제 코드 후보로 Beam Search"""
        config = BeamConfig(beam_width=3)
        ranker = BeamRanker(config)

        # 실제 코드 변경 후보들
        real_candidates = [
            BeamCandidate(
                candidate_id="impl_v1",
                depth=1,
                code_diff="""
def calculate_total(items: List[Item]) -> float:
    return sum(item.price for item in items)
""",
                compile_success=True,
                test_pass_rate=0.95,
                quality_score=0.9,
                reasoning="Simple and readable implementation",
            ),
            BeamCandidate(
                candidate_id="impl_v2",
                depth=1,
                code_diff="""
def calculate_total(items: List[Item]) -> float:
    total = 0.0
    for item in items:
        if item.price is not None:
            total += item.price
    return total
""",
                compile_success=True,
                test_pass_rate=0.98,
                quality_score=0.85,
                reasoning="More defensive with None checks",
            ),
            BeamCandidate(
                candidate_id="impl_v3",
                depth=1,
                code_diff="""
from decimal import Decimal

def calculate_total(items: List[Item]) -> Decimal:
    return sum(Decimal(str(item.price)) for item in items if item.price)
""",
                compile_success=True,
                test_pass_rate=0.92,
                quality_score=0.95,
                reasoning="Uses Decimal for precise calculations",
            ),
            BeamCandidate(
                candidate_id="impl_v4",
                depth=1,
                code_diff="""
def calculate_total(items: List[Item]) -> float:
    # Buggy implementation
    return sum(item.price for item in items) * 2  # Wrong!
""",
                compile_success=True,
                test_pass_rate=0.3,  # Low test pass rate
                quality_score=0.2,
                reasoning="Incorrect logic",
            ),
        ]

        # Rank and prune
        top_candidates = ranker.rank_and_prune(real_candidates)

        # beam_width=3이므로 3개 선택
        assert len(top_candidates) <= 3

        # 버그가 있는 impl_v4는 제외되어야 함 (test_pass_rate < 0.5)
        selected_ids = {c.candidate_id for c in top_candidates}
        assert "impl_v4" not in selected_ids, "Buggy implementation should be filtered out"

        # 상위 후보들은 높은 품질
        assert all(c.is_valid() for c in top_candidates)

    def test_real_world_security_patterns(self):
        """실제 보안 패턴 검증"""
        checker = SafetyChecker()

        # 좋은 보안 패턴
        secure_patterns = {
            "env_vars": """
import os
API_KEY = os.getenv("API_KEY")
DB_PASSWORD = os.environ.get("DB_PASSWORD")
""",
            "parameterized_query": """
cursor.execute("SELECT * FROM users WHERE id = ?", (user_id,))
""",
            "secrets_manager": """
from aws_secretsmanager import get_secret
password = get_secret("db/password")
""",
        }

        for name, code in secure_patterns.items():
            violations = checker.check(code)
            critical = [v for v in violations if v.severity == RuleSeverity.CRITICAL]
            assert len(critical) == 0, f"Secure pattern '{name}' should not have critical violations"

        # 나쁜 보안 패턴
        insecure_patterns = {
            "hardcoded_credentials": """
DB_PASSWORD = "mypassword123"
API_KEY = "sk-hardcoded-key"
""",
            "sql_injection": """
query = "SELECT * FROM users WHERE name='" + username + "'"
cursor.execute(query)
""",
        }

        for name, code in insecure_patterns.items():
            violations = checker.check(code)
            assert len(violations) > 0, f"Insecure pattern '{name}' should be detected"

    def test_performance_with_large_real_code(self):
        """대용량 실제 코드 성능 테스트"""
        import time

        checker = SafetyChecker()

        # 대용량 코드 시뮬레이션 (1000줄)
        large_code = "\n".join(
            [
                f"""
def function_{i}(param: int) -> int:
    result = param * 2
    return result
"""
                for i in range(250)
            ]
        )

        start = time.perf_counter()
        violations = checker.check(large_code)
        duration = time.perf_counter() - start

        # 1000줄 코드를 1초 이내 처리
        assert duration < 1.0, f"Performance issue: took {duration:.3f}s for 1000 lines"

        # 결과 유효성
        assert isinstance(violations, list)


class TestRealWorldIntegration:
    """실제 통합 시나리오"""

    def test_end_to_end_code_generation_validation(self):
        """End-to-end: 코드 생성 -> 검증"""
        checker = SafetyChecker()
        ranker = BeamRanker(BeamConfig(beam_width=2))

        # 1. 코드 후보 생성 (실제로는 LLM이 생성)
        candidates = [
            BeamCandidate(
                "safe_impl",
                0,
                code_diff='password = os.getenv("PASSWORD")',
                compile_success=True,
                test_pass_rate=0.9,
            ),
            BeamCandidate(
                "unsafe_impl",
                0,
                code_diff='password = "hardcoded123"',
                compile_success=True,
                test_pass_rate=0.9,
            ),
        ]

        # 2. Beam Search로 후보 선택
        top_candidates = ranker.rank_and_prune(candidates)
        assert len(top_candidates) > 0

        # 3. Constitutional AI로 안전성 검증
        for candidate in top_candidates:
            is_safe = checker.is_safe(candidate.code_diff)
            if candidate.candidate_id == "safe_impl":
                assert is_safe, "Safe implementation should pass"
            elif candidate.candidate_id == "unsafe_impl":
                assert not is_safe, "Unsafe implementation should fail"

    def test_difficulty_aware_resource_allocation(self):
        """난이도 기반 리소스 할당"""
        allocator = ComputeAllocator(TTCConfig())

        tasks_with_expected_difficulty = [
            ("Add logging statement", DifficultyLevel.EASY),
            ("Refactor class to use composition", DifficultyLevel.HARD),  # refactor는 HARD
            ("Implement distributed transaction coordinator", DifficultyLevel.EXTREME),
        ]

        for task, expected_level in tasks_with_expected_difficulty:
            difficulty, budget = allocator.allocate(task)

            # 난이도 검증
            assert difficulty.level == expected_level, (
                f"Task '{task}' should be {expected_level}, got {difficulty.level}"
            )

            # 예산이 난이도에 비례
            if expected_level == DifficultyLevel.EASY:
                assert budget.num_samples <= 5
            elif expected_level == DifficultyLevel.EXTREME:
                assert budget.num_samples >= 10
