"""
Analysis Indexing Domain Ports

인덱싱 도메인의 포트 인터페이스 (헥사고날 아키텍처)
"""

from typing import Any, Protocol

from .models import FileToIndex


class FileProcessorPort(Protocol):
    """파일 처리 포트"""

    def detect_language(self, file_path: str) -> str | None:
        """파일 언어 감지"""
        ...

    def parse_file(self, file: FileToIndex) -> Any:
        """파일 파싱 (AST 생성)"""
        ...


class IRGeneratorPort(Protocol):
    """IR 생성 포트"""

    def generate_ir(self, ast: Any, file_path: str, language: str) -> Any:
        """AST로부터 IR 생성"""
        ...

    def generate_semantic_ir(self, ir: Any) -> Any:
        """Semantic IR 생성"""
        ...


class GraphBuilderPort(Protocol):
    """그래프 빌더 포트"""

    def build_graph(self, ir: Any, semantic_ir: Any | None = None) -> Any:
        """IR로부터 그래프 생성"""
        ...


class ChunkBuilderPort(Protocol):
    """청크 빌더 포트"""

    def build_chunks(self, ir: Any, graph: Any, file_content: str) -> list[Any]:
        """IR과 그래프로부터 청크 생성"""
        ...


class GraphStoragePort(Protocol):
    """그래프 저장소 포트"""

    async def save_graph(self, repo_id: str, graph: Any) -> None:
        """그래프 저장"""
        ...

    async def delete_graph_nodes(self, repo_id: str, node_ids: list[str]) -> None:
        """그래프 노드 삭제"""
        ...


class ChunkStoragePort(Protocol):
    """청크 저장소 포트"""

    async def save_chunks(self, repo_id: str, chunks: list[Any]) -> None:
        """청크 저장"""
        ...

    async def delete_chunks(self, repo_id: str, chunk_ids: list[str]) -> None:
        """청크 삭제"""
        ...


class LexicalIndexPort(Protocol):
    """렉시컬 인덱스 포트"""

    async def index_chunks(self, repo_id: str, chunks: list[Any]) -> None:
        """청크 인덱싱"""
        ...

    async def delete_chunks(self, repo_id: str, chunk_ids: list[str]) -> None:
        """청크 삭제"""
        ...


class VectorIndexPort(Protocol):
    """벡터 인덱스 포트"""

    async def index_chunks(self, repo_id: str, chunks: list[Any]) -> None:
        """청크 인덱싱"""
        ...

    async def delete_chunks(self, repo_id: str, chunk_ids: list[str]) -> None:
        """청크 삭제"""
        ...


class ProgressCallbackPort(Protocol):
    """진행 상황 콜백 포트"""

    def on_progress(self, current: int, total: int, message: str = "") -> None:
        """진행 상황 보고"""
        ...


class MetadataStoragePort(Protocol):
    """메타데이터 저장소 포트"""

    async def save_indexing_metadata(
        self,
        repo_id: str,
        snapshot_id: str,
        metadata: dict[str, Any],
    ) -> None:
        """인덱싱 메타데이터 저장"""
        ...

    async def get_indexing_metadata(self, repo_id: str, snapshot_id: str) -> dict[str, Any] | None:
        """인덱싱 메타데이터 조회"""
        ...
