"""
Experience Store

과거 성공한 코드 수정 패턴을 저장하고 재사용합니다.

기능:
- 성공한 수정 패턴 저장
- 유사 문제 자동 매칭
- 패턴 기반 빠른 수정 제안
- 학습률 향상
"""

import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any


@dataclass
class Experience:
    """경험 기록"""

    experience_id: str
    task_description: str
    error_pattern: str  # 에러 패턴 (테스트 실패 등)
    fix_pattern: str  # 수정 패턴
    file_type: str  # 파일 타입 (.py, .js 등)
    success_rate: float  # 성공률 (0.0-1.0)
    times_used: int  # 사용 횟수
    created_at: str
    updated_at: str


class ExperienceStore:
    """
    Experience Store.

    과거 성공 패턴을 저장하고 유사 문제에 재사용.
    """

    def __init__(self, store_path: str = ".experience_store.json"):
        """
        Args:
            store_path: Experience store 파일 경로
        """
        self.store_path = Path(store_path)
        self.experiences: dict[str, Experience] = {}

        # Load existing experiences
        self._load()

    def _load(self):
        """Experience store 로드"""
        if self.store_path.exists():
            try:
                data = json.loads(self.store_path.read_text())

                for exp_data in data.get("experiences", []):
                    exp = Experience(**exp_data)
                    self.experiences[exp.experience_id] = exp

            except Exception as e:
                print(f"⚠️  Experience store 로드 실패: {e}")

    def _save(self):
        """Experience store 저장"""
        try:
            data = {
                "experiences": [asdict(exp) for exp in self.experiences.values()],
                "count": len(self.experiences),
            }

            self.store_path.write_text(json.dumps(data, indent=2))

        except Exception as e:
            print(f"⚠️  Experience store 저장 실패: {e}")

    async def add_experience(
        self,
        task_description: str,
        error_pattern: str,
        fix_pattern: str,
        file_type: str = ".py",
        success: bool = True,
    ):
        """
        새로운 경험 추가.

        Args:
            task_description: Task 설명
            error_pattern: 에러 패턴 (예: "AttributeError: discount_rate")
            fix_pattern: 수정 패턴 (예: "discount = price * discount_rate")
            file_type: 파일 타입
            success: 성공 여부
        """
        # Experience ID 생성 (에러 패턴 기반 해시)
        exp_id = hashlib.md5(f"{error_pattern}:{file_type}".encode()).hexdigest()[:16]

        now = datetime.now().isoformat()

        if exp_id in self.experiences:
            # 기존 경험 업데이트
            exp = self.experiences[exp_id]
            exp.times_used += 1

            # 성공률 업데이트 (지수 이동 평균)
            if success:
                exp.success_rate = 0.9 * exp.success_rate + 0.1 * 1.0
            else:
                exp.success_rate = 0.9 * exp.success_rate + 0.1 * 0.0

            exp.updated_at = now

        else:
            # 새로운 경험 생성
            exp = Experience(
                experience_id=exp_id,
                task_description=task_description,
                error_pattern=error_pattern,
                fix_pattern=fix_pattern,
                file_type=file_type,
                success_rate=1.0 if success else 0.0,
                times_used=1,
                created_at=now,
                updated_at=now,
            )

            self.experiences[exp_id] = exp

        self._save()

    async def find_similar_experiences(
        self, error_pattern: str, file_type: str = ".py", top_k: int = 3
    ) -> list[Experience]:
        """
        유사한 경험 찾기.

        Args:
            error_pattern: 에러 패턴
            file_type: 파일 타입
            top_k: 최대 결과 수

        Returns:
            유사한 Experience 리스트
        """
        candidates = []

        for exp in self.experiences.values():
            # 파일 타입 일치
            if exp.file_type != file_type:
                continue

            # 유사도 계산 (간단한 substring matching)
            similarity = self._calculate_similarity(error_pattern, exp.error_pattern)

            if similarity > 0.3:  # 임계값
                candidates.append((similarity, exp))

        # 유사도 + 성공률 + 사용 횟수로 정렬
        candidates.sort(
            key=lambda x: (x[0] * 0.5 + x[1].success_rate * 0.3 + min(x[1].times_used / 10, 1.0) * 0.2),
            reverse=True,
        )

        return [exp for _, exp in candidates[:top_k]]

    def _calculate_similarity(self, pattern1: str, pattern2: str) -> float:
        """
        두 패턴의 유사도 계산 (간단한 Jaccard similarity).

        Returns:
            유사도 (0.0-1.0)
        """
        # 단어 집합
        words1 = set(pattern1.lower().split())
        words2 = set(pattern2.lower().split())

        if not words1 or not words2:
            return 0.0

        # Jaccard similarity
        intersection = len(words1 & words2)
        union = len(words1 | words2)

        return intersection / union if union > 0 else 0.0

    async def get_fix_suggestion(self, error_pattern: str, file_type: str = ".py") -> str | None:
        """
        에러 패턴에 대한 수정 제안 가져오기.

        Args:
            error_pattern: 에러 패턴
            file_type: 파일 타입

        Returns:
            수정 패턴 (없으면 None)
        """
        similar_exps = await self.find_similar_experiences(error_pattern, file_type, top_k=1)

        if similar_exps and similar_exps[0].success_rate > 0.5:
            return similar_exps[0].fix_pattern

        return None

    def get_statistics(self) -> dict[str, Any]:
        """Experience store 통계"""
        if not self.experiences:
            return {
                "total": 0,
                "avg_success_rate": 0.0,
                "total_uses": 0,
            }

        return {
            "total": len(self.experiences),
            "avg_success_rate": sum(exp.success_rate for exp in self.experiences.values()) / len(self.experiences),
            "total_uses": sum(exp.times_used for exp in self.experiences.values()),
            "by_file_type": self._count_by_file_type(),
        }

    def _count_by_file_type(self) -> dict[str, int]:
        """파일 타입별 경험 수"""
        counts = {}

        for exp in self.experiences.values():
            counts[exp.file_type] = counts.get(exp.file_type, 0) + 1

        return counts


# ============================================================
# ExperienceStore를 사용하는 Enhanced Services
# ============================================================


class ExperienceEnhancedGenerateService:
    """
    Experience Store를 사용하는 Generate Service.

    과거 패턴을 먼저 확인하고, 없으면 LLM 사용.
    """

    def __init__(self, llm_provider, experience_store: ExperienceStore):
        """
        Args:
            llm_provider: ILLMProvider
            experience_store: ExperienceStore
        """
        self.llm = llm_provider
        self.exp_store = experience_store

    async def generate_changes(self, task, plan):
        """
        코드 변경 생성 (Experience Store 우선).

        1. Experience Store에서 유사 패턴 검색
        2. 있으면 패턴 기반 빠른 생성
        3. 없으면 LLM으로 생성
        """
        from src.agent.domain.models import ChangeType, CodeChange

        # 1. Task description에서 에러 패턴 추출
        error_pattern = task.description  # 간단하게

        # 2. Experience Store 조회
        fix_suggestion = await self.exp_store.get_fix_suggestion(error_pattern, ".py")

        if fix_suggestion:
            print("   💡 Experience Store hit! Using past pattern...")

            # 패턴 기반 빠른 생성
            # (실제로는 더 정교하게 파싱)
            return [
                CodeChange(
                    file_path=task.context_files[0] if task.context_files else "unknown.py",
                    change_type=ChangeType.MODIFY,
                    new_lines=fix_suggestion.split("\n"),
                    start_line=22,  # 간단히
                    end_line=22,
                    rationale="Applied past successful pattern (success_rate: high)",
                )
            ]

        # 3. Experience miss → LLM으로 생성
        print("   🤖 Experience miss. Using LLM...")

        from src.agent.domain.real_services import RealGenerateService

        real_service = RealGenerateService(self.llm)
        return await real_service.generate_changes(task, plan)
