"""Tantivy Adapter - tantivy-py 바인딩 연동."""

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import tantivy

from codegraph_shared.infra.observability import get_logger

logger = get_logger(__name__)


@dataclass
class TantivyDocument:
    """Tantivy 문서.

    Attributes:
        file_path: 파일 경로
        content: 파일 내용
        repo_id: 저장소 ID
        indexed_at: 인덱싱 시각
    """

    file_path: str
    content: str
    repo_id: str
    indexed_at: str


@dataclass
class TantivySearchResult:
    """Tantivy 검색 결과.

    Attributes:
        file_path: 파일 경로
        score: BM25 점수
        snippet: 코드 스니펫
    """

    file_path: str
    score: float
    snippet: str


class TantivyAdapter:
    """Tantivy Python 바인딩 어댑터.

    tantivy-py를 사용하여 Delta Index를 관리합니다.
    """

    def __init__(
        self,
        index_dir: Path,
    ):
        """
        Args:
            index_dir: Tantivy 인덱스 디렉토리
        """
        self.index_dir = Path(index_dir)
        self.index_dir.mkdir(parents=True, exist_ok=True)

        # Schema 및 Index 초기화
        self.schema = self._build_schema()
        self.index = self._get_or_create_index()

    def _build_schema(self) -> tantivy.Schema:
        """Tantivy schema 빌드."""
        schema_builder = tantivy.SchemaBuilder()

        schema_builder.add_text_field("file_path", stored=True, tokenizer_name="raw")
        schema_builder.add_text_field("content", stored=True, tokenizer_name="default")
        schema_builder.add_text_field("repo_id", stored=True, tokenizer_name="raw")
        schema_builder.add_date_field("indexed_at", stored=True)

        return schema_builder.build()

    def _get_or_create_index(self) -> tantivy.Index:
        """Index 생성 또는 로드."""
        try:
            # 기존 인덱스 로드 시도
            return tantivy.Index.open(str(self.index_dir))
        except Exception:
            # 없으면 새로 생성
            logger.info(f"Creating new Tantivy index: {self.index_dir}")
            return tantivy.Index(self.schema, path=str(self.index_dir))

    async def index_document(self, doc: TantivyDocument) -> bool:
        """문서 인덱싱.

        Args:
            doc: TantivyDocument

        Returns:
            성공 여부
        """
        try:
            writer = self.index.writer()

            # datetime 파싱
            indexed_at = datetime.fromisoformat(doc.indexed_at)

            # Document 생성
            tantivy_doc = tantivy.Document()
            tantivy_doc.add_text(self.schema.get_field("file_path"), doc.file_path)
            tantivy_doc.add_text(self.schema.get_field("content"), doc.content)
            tantivy_doc.add_text(self.schema.get_field("repo_id"), doc.repo_id)
            tantivy_doc.add_date(self.schema.get_field("indexed_at"), indexed_at)

            writer.add_document(tantivy_doc)
            writer.commit()

            logger.debug(f"Indexed document: {doc.file_path}")
            return True

        except Exception as e:
            logger.error(f"Tantivy index error: {e}", extra={"file_path": doc.file_path})
            return False

    async def search(
        self,
        query: str,
        repo_id: str,
        limit: int = 50,
    ) -> list[TantivySearchResult]:
        """검색.

        Args:
            query: 검색 쿼리
            repo_id: 저장소 ID
            limit: 최대 결과 수

        Returns:
            TantivySearchResult 리스트
        """
        try:
            searcher = self.index.searcher()

            # 쿼리 파싱: repo_id 필터 + content 검색
            query_parser = tantivy.QueryParser.for_index(self.index, [self.schema.get_field("content")])

            # Tantivy 쿼리 생성
            parsed_query = query_parser.parse_query(f'repo_id:"{repo_id}" AND content:{query}')

            # 검색 실행
            top_docs = searcher.search(parsed_query, limit)

            results = []
            for score, doc_address in top_docs:
                doc = searcher.doc(doc_address)

                file_path = doc.get_first(self.schema.get_field("file_path"))
                content = doc.get_first(self.schema.get_field("content"))

                # 스니펫 생성 (간단히 첫 200자)
                snippet = content[:200] if content else ""

                results.append(
                    TantivySearchResult(
                        file_path=file_path or "",
                        score=float(score),
                        snippet=snippet,
                    )
                )

            return results

        except Exception as e:
            logger.error(f"Tantivy search error: {e}", extra={"query": query})
            return []

    async def delete_document(self, file_path: str, repo_id: str) -> bool:
        """문서 삭제.

        Args:
            file_path: 파일 경로
            repo_id: 저장소 ID

        Returns:
            성공 여부
        """
        try:
            writer = self.index.writer()

            # file_path로 삭제
            term = tantivy.Term.from_field_text(self.schema.get_field("file_path"), file_path)
            writer.delete_documents("file_path", file_path)
            writer.commit()

            logger.debug(f"Deleted document: {file_path}")
            return True

        except Exception as e:
            logger.error(f"Tantivy delete error: {e}", extra={"file_path": file_path})
            return False

    async def clear_all(self, repo_id: str) -> bool:
        """저장소의 모든 문서 삭제.

        Args:
            repo_id: 저장소 ID

        Returns:
            성공 여부
        """
        try:
            writer = self.index.writer()

            # repo_id로 모든 문서 삭제
            writer.delete_documents("repo_id", repo_id)
            writer.commit()

            logger.info(f"Cleared Tantivy index: {repo_id}")
            return True

        except Exception as e:
            logger.error(f"Tantivy clear error: {e}", extra={"repo_id": repo_id})
            return False
