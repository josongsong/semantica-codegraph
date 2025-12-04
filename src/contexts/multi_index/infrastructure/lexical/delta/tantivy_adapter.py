"""Tantivy Adapter - Tantivy subprocess 연동."""

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path

from src.infra.observability import get_logger

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
    """Tantivy subprocess 어댑터.

    Tantivy CLI를 subprocess로 실행하여
    Delta Index를 관리합니다.
    """

    def __init__(
        self,
        index_dir: Path,
        tantivy_bin: str = "tantivy",
    ):
        """
        Args:
            index_dir: Tantivy 인덱스 디렉토리
            tantivy_bin: Tantivy 바이너리 경로
        """
        self.index_dir = Path(index_dir)
        self.tantivy_bin = tantivy_bin

        # 인덱스 디렉토리 생성
        self.index_dir.mkdir(parents=True, exist_ok=True)

        # Schema 초기화 (최초 1회)
        self._init_schema_if_needed()

    def _init_schema_if_needed(self) -> None:
        """Tantivy schema 초기화 (index가 없을 때만)."""
        schema_file = self.index_dir / "meta.json"
        if schema_file.exists():
            logger.debug("Tantivy schema already exists")
            return

        # Tantivy schema 정의
        schema = {
            "fields": [
                {
                    "name": "file_path",
                    "type": "text",
                    "options": {
                        "indexing": {"record": "basic", "tokenizer": "raw"},
                        "stored": True,
                    },
                },
                {
                    "name": "content",
                    "type": "text",
                    "options": {
                        "indexing": {
                            "record": "position",
                            "tokenizer": "code_tokenizer",  # Custom
                        },
                        "stored": True,
                    },
                },
                {
                    "name": "repo_id",
                    "type": "text",
                    "options": {
                        "indexing": {"record": "basic", "tokenizer": "raw"},
                        "stored": True,
                    },
                },
                {
                    "name": "indexed_at",
                    "type": "date",
                    "options": {"stored": True, "indexed": True},
                },
            ]
        }

        # Schema 파일 작성
        schema_file.write_text(json.dumps(schema, indent=2))
        logger.info(f"Created Tantivy schema: {schema_file}")

    async def index_document(self, doc: TantivyDocument) -> bool:
        """문서 인덱싱.

        Args:
            doc: TantivyDocument

        Returns:
            성공 여부
        """
        # JSON 형식으로 문서 준비
        doc_json = {
            "file_path": doc.file_path,
            "content": doc.content,
            "repo_id": doc.repo_id,
            "indexed_at": doc.indexed_at,
        }

        try:
            # Tantivy CLI로 인덱싱 (stdin으로 JSON 전달)
            cmd = [self.tantivy_bin, "index", "--index", str(self.index_dir)]

            proc = subprocess.run(
                cmd,
                input=json.dumps(doc_json).encode(),
                capture_output=True,
                timeout=30,
            )

            if proc.returncode == 0:
                logger.debug(f"Indexed document: {doc.file_path}")
                return True
            else:
                logger.error(
                    f"Tantivy index failed: {doc.file_path}",
                    extra={"stderr": proc.stderr.decode()},
                )
                return False

        except FileNotFoundError:
            logger.error("Tantivy binary not found. Install tantivy-cli.")
            return False
        except subprocess.TimeoutExpired:
            logger.error(f"Tantivy timeout: {doc.file_path}")
            return False
        except Exception as e:
            logger.error(f"Tantivy error: {e}")
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
            # Tantivy 검색 쿼리
            tantivy_query = f"repo_id:{repo_id} AND content:{query}"

            cmd = [
                self.tantivy_bin,
                "search",
                "--index",
                str(self.index_dir),
                "--query",
                tantivy_query,
                "--num-hits",
                str(limit),
            ]

            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=10,
            )

            if proc.returncode != 0:
                logger.error(
                    f"Tantivy search failed: {query}",
                    extra={"stderr": proc.stderr},
                )
                return []

            # 결과 파싱 (JSON 형식)
            results = []
            for line in proc.stdout.strip().split("\n"):
                if not line:
                    continue
                try:
                    result = json.loads(line)
                    results.append(
                        TantivySearchResult(
                            file_path=result.get("file_path", ""),
                            score=result.get("score", 0.0),
                            snippet=result.get("snippet", ""),
                        )
                    )
                except json.JSONDecodeError:
                    continue

            return results

        except FileNotFoundError:
            logger.error("Tantivy binary not found")
            return []
        except subprocess.TimeoutExpired:
            logger.error(f"Tantivy search timeout: {query}")
            return []
        except Exception as e:
            logger.error(f"Tantivy search error: {e}")
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
            # Tantivy delete (file_path로 삭제)
            cmd = [
                self.tantivy_bin,
                "delete",
                str(self.index_dir),
                "-f",
                "file_path",
                "-v",
                file_path,
            ]

            proc = subprocess.run(cmd, capture_output=True, timeout=10)

            if proc.returncode == 0:
                logger.debug(f"Deleted document: {file_path}")
                return True
            else:
                logger.error(f"Tantivy delete failed: {file_path}")
                return False

        except Exception as e:
            logger.error(f"Tantivy delete error: {e}")
            return False

    async def clear_all(self, repo_id: str) -> bool:
        """저장소의 모든 문서 삭제.

        Args:
            repo_id: 저장소 ID

        Returns:
            성공 여부
        """
        try:
            # Tantivy clear (repo_id로 필터링하여 삭제)
            cmd = [
                self.tantivy_bin,
                "delete",
                str(self.index_dir),
                "-f",
                "repo_id",
                "-v",
                repo_id,
            ]

            proc = subprocess.run(cmd, capture_output=True, timeout=30)

            if proc.returncode == 0:
                logger.info(f"Cleared Tantivy index: {repo_id}")
                return True
            else:
                logger.error(f"Tantivy clear failed: {repo_id}")
                return False

        except Exception as e:
            logger.error(f"Tantivy clear error: {e}")
            return False
