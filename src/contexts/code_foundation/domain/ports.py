"""
Code Foundation Domain Ports

코드 분석 파이프라인의 포트 인터페이스
"""

from pathlib import Path
from typing import Protocol

from .models import ASTDocument, Chunk, GraphDocument, IRDocument, Language


class ParserPort(Protocol):
    """AST 파서 포트"""

    def parse_file(self, file_path: Path, language: Language) -> ASTDocument:
        """파일을 파싱하여 AST 생성"""
        ...

    def parse_code(self, code: str, language: Language) -> ASTDocument:
        """코드를 파싱하여 AST 생성"""
        ...


class IRGeneratorPort(Protocol):
    """IR 생성기 포트"""

    def generate(self, ast_doc: ASTDocument) -> IRDocument:
        """AST로부터 IR 생성"""
        ...


class GraphBuilderPort(Protocol):
    """그래프 빌더 포트"""

    def build(self, ir_doc: IRDocument) -> GraphDocument:
        """IR로부터 그래프 생성"""
        ...


class ChunkerPort(Protocol):
    """청커 포트"""

    def chunk(self, ir_doc: IRDocument, source_code: str) -> list[Chunk]:
        """IR로부터 청크 생성"""
        ...


class ChunkStorePort(Protocol):
    """청크 저장소 포트"""

    async def save_chunks(self, chunks: list[Chunk], repo_id: str) -> None:
        """청크 저장"""
        ...

    async def get_chunk(self, chunk_id: str) -> Chunk | None:
        """청크 조회"""
        ...

    async def get_chunks_by_file(self, file_path: str, repo_id: str) -> list[Chunk]:
        """파일의 모든 청크 조회"""
        ...

    async def delete_chunks(self, chunk_ids: list[str]) -> None:
        """청크 삭제"""
        ...
