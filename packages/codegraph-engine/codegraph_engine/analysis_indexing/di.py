"""
Analysis Indexing DI Container

NOTE: 실제 프로덕션 인덱싱은 src/container.py를 사용.
이 모듈은 Bounded Context 레벨의 간단한 접근점 제공.
"""


class AnalysisIndexingContainer:
    """
    Analysis Indexing BC의 DI Container.

    NOTE: 실제 프로덕션 인덱싱은 src/container.py의 IndexingContainer를 사용.
    이 컨테이너는 하위 호환성을 위해 유지.
    """

    pass


# 전역 싱글톤 (하위 호환성)
analysis_indexing_container = AnalysisIndexingContainer()
