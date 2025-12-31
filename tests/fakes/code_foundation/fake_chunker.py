"""
Fake Chunker

⚠️  TEST ONLY - DO NOT USE IN PRODUCTION ⚠️

테스트용 간단한 청커. 실제 시맨틱 청킹을 수행하지 않습니다.
프로덕션에서는 FoundationChunkerAdapter를 사용하세요.

See Also:
    - src/contexts/code_foundation/adapters/foundation_adapters.py
    - src/contexts/code_foundation/infrastructure/chunk/

Note:
    Supports both Infrastructure IRDocument (nodes) and Domain IRDocument (symbols).
    Domain IRDocument support is DEPRECATED.
"""

from typing import Any

from codegraph_engine.code_foundation.domain.models import Chunk, Language


class FakeChunker:
    """테스트용 Fake 청커 (nodes/symbols 둘 다 지원)"""

    def _get_items(self, ir_doc: Any) -> list[Any]:
        """Get nodes or symbols from IR document"""
        if hasattr(ir_doc, "nodes") and ir_doc.nodes:
            return ir_doc.nodes
        # DEPRECATED: Domain IRDocument uses 'symbols'
        if hasattr(ir_doc, "symbols"):
            return ir_doc.symbols
        return []

    def _get_file_path(self, ir_doc: Any) -> str:
        """Get file path from IR document"""
        if hasattr(ir_doc, "file_path") and ir_doc.file_path:
            return ir_doc.file_path
        if hasattr(ir_doc, "meta") and ir_doc.meta:
            return ir_doc.meta.get("file_path", "")
        return ""

    def _get_language(self, ir_doc: Any) -> Language:
        """Get language from IR document"""
        if hasattr(ir_doc, "language"):
            lang = ir_doc.language
            if isinstance(lang, Language):
                return lang
            try:
                return Language(str(lang))
            except ValueError:
                pass
        if hasattr(ir_doc, "meta") and ir_doc.meta:
            try:
                return Language(ir_doc.meta.get("language", "unknown"))
            except ValueError:
                pass
        return Language.UNKNOWN

    def chunk(self, ir_doc: Any, source_code: str) -> list[Chunk]:
        """청킹"""
        chunks = []
        file_path = self._get_file_path(ir_doc)
        language = self._get_language(ir_doc)
        lines = source_code.splitlines()

        # 노드/심볼별로 청크 생성
        for item in self._get_items(ir_doc):
            name = getattr(item, "name", "unknown")

            # Get start/end lines (Node uses span, Symbol uses direct attrs)
            if hasattr(item, "span") and item.span:
                start_line = item.span.start_line
                end_line = item.span.end_line
            else:
                start_line = getattr(item, "start_line", 1)
                end_line = getattr(item, "end_line", 1)

            # Get type/kind
            if hasattr(item, "kind"):
                kind = item.kind
                chunk_type = kind.value if hasattr(kind, "value") else str(kind)
            else:
                chunk_type = getattr(item, "type", "unknown")

            chunk_id = f"{file_path}::{name}"

            # 해당 라인의 코드 추출
            if start_line <= len(lines):
                content = lines[start_line - 1]
            else:
                content = ""

            chunks.append(
                Chunk(
                    id=chunk_id,
                    content=content,
                    file_path=file_path,
                    start_line=start_line,
                    end_line=end_line,
                    chunk_type=chunk_type,
                    language=language,
                    metadata={"symbol_name": name},
                )
            )

        # 파일 전체 청크도 추가
        if chunks:
            chunks.append(
                Chunk(
                    id=f"{file_path}::__file__",
                    content=source_code[:500],  # 처음 500자
                    file_path=file_path,
                    start_line=1,
                    end_line=len(lines),
                    chunk_type="file",
                    language=language,
                    metadata={},
                )
            )

        return chunks
