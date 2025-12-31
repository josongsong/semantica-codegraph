"""
Index Session Context

세션 단위 상태 관리 for 2-Pass Impact Reindexing.
"""

from dataclasses import dataclass, field


@dataclass
class IndexSessionContext:
    """
    인덱싱 세션 컨텍스트.

    단일 인덱싱 실행(session) 동안 유지되는 상태:
    - 처리된 파일 추적 (중복 방지)
    - Impact 재인덱싱 후보
    - Impact pass 실행 여부

    2-Pass 전략:
    1. 1st pass: 원래 change_set 처리 → processed_files에 기록
    2. Impact 분석: affected_files 계산 → impact_candidates에 저장
    3. 2nd pass: impact_candidates 중 미처리 파일만 재인덱싱

    안전장치:
    - 세션당 1회만 impact pass 실행 (impact_pass_ran)
    - 최대 파일 수 제한 (max_impact_reindex_files)
    - 재귀 방지 (2nd pass에서는 impact 분석 미실행)
    """

    # 처리 완료된 파일 경로
    processed_files: set[str] = field(default_factory=set)

    # Impact 분석 결과: 영향 받은 파일 중 미처리 파일
    impact_candidates: set[str] = field(default_factory=set)

    # Impact pass 실행 여부 (세션당 1회 제한)
    impact_pass_ran: bool = False

    # 설정
    max_impact_reindex_files: int = 200

    def mark_file_processed(self, file_path: str) -> None:
        """파일 처리 완료 마킹."""
        self.processed_files.add(file_path)

    def is_file_processed(self, file_path: str) -> bool:
        """파일이 이미 처리되었는지 확인."""
        return file_path in self.processed_files

    def set_impact_candidates(self, candidates: set[str]) -> None:
        """
        Impact 재인덱싱 후보 설정.

        Args:
            candidates: 영향 받은 파일 중 미처리 파일
        """
        # 이미 처리된 파일 제외
        self.impact_candidates = candidates - self.processed_files

    def get_impact_batch(self) -> list[str]:
        """
        Impact 재인덱싱 배치 가져오기.

        Returns:
            최대 max_impact_reindex_files개의 파일 경로
        """
        candidates = list(self.impact_candidates)
        return candidates[: self.max_impact_reindex_files]

    def mark_impact_pass_done(self) -> None:
        """Impact pass 완료 마킹."""
        self.impact_pass_ran = True

    def should_run_impact_pass(self) -> bool:
        """
        Impact pass 실행 여부 판단.

        Returns:
            True if impact pass를 실행해야 함
        """
        return not self.impact_pass_ran and len(self.impact_candidates) > 0
