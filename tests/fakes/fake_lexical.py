"""
Fake Lexical Search for Unit Testing
"""

from typing import List, Dict, Any


class FakeLexicalSearch:
    """
    LexicalSearchPort Fake 구현.

    간단한 substring matching 기반.
    """

    def __init__(self):
        self.documents: Dict[str, str] = {}

    def index(self, doc_id: str, content: str):
        """문서 인덱싱."""
        self.documents[doc_id] = content

    def search(self, query: str, limit: int = 10) -> List[Dict[str, Any]]:
        """
        Substring matching 기반 검색.

        Args:
            query: 검색 쿼리
            limit: 결과 수

        Returns:
            검색 결과
        """
        results = []

        for doc_id, content in self.documents.items():
            if query.lower() in content.lower():
                # 간단한 relevance score (매칭 횟수)
                score = content.lower().count(query.lower())
                results.append({
                    "id": doc_id,
                    "score": score,
                    "content": content,
                })

        # 점수 내림차순 정렬
        results.sort(key=lambda x: x["score"], reverse=True)
        return results[:limit]

    def delete(self, doc_id: str):
        """문서 삭제."""
        self.documents.pop(doc_id, None)

    def clear(self):
        """모든 문서 삭제."""
        self.documents.clear()
