"""
Fake Search Engine

테스트용 인메모리 검색 엔진
"""

from ..domain.models import SearchHit, SearchQuery


class FakeSearchEngine:
    """테스트용 Fake 검색 엔진"""

    def __init__(self):
        """초기화"""
        self.documents: dict[str, SearchHit] = {}

    def index_document(self, doc: SearchHit) -> None:
        """문서 인덱싱 (테스트용)"""
        self.documents[doc.id] = doc

    async def search(self, query: SearchQuery) -> list[SearchHit]:
        """검색 실행"""
        # 간단한 키워드 매칭
        results = []
        for doc in self.documents.values():
            # repo_id 필터링
            if doc.metadata.get("repo_id") != query.repo_id:
                continue

            # 키워드 매칭 (대소문자 무시)
            if query.query.lower() in doc.content.lower():
                # 스코어 계산 (간단한 TF 방식)
                score = doc.content.lower().count(query.query.lower()) / len(doc.content.split())
                results.append(
                    SearchHit(
                        id=doc.id,
                        score=score,
                        content=doc.content,
                        metadata=doc.metadata,
                    )
                )

        # 스코어 순으로 정렬
        results.sort(key=lambda x: x.score, reverse=True)

        # limit 적용
        return results[: query.limit]
