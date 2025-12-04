"""
Fake Chunker

테스트용 간단한 청커
"""

from ..domain.models import Chunk, IRDocument


class FakeChunker:
    """테스트용 Fake 청커"""

    def chunk(self, ir_doc: IRDocument, source_code: str) -> list[Chunk]:
        """청킹"""
        chunks = []

        # 심볼별로 청크 생성
        for symbol in ir_doc.symbols:
            chunk_id = f"{ir_doc.file_path}::{symbol.name}"

            # 해당 라인의 코드 추출
            lines = source_code.splitlines()
            if symbol.start_line <= len(lines):
                content = lines[symbol.start_line - 1]
            else:
                content = ""

            chunks.append(
                Chunk(
                    id=chunk_id,
                    content=content,
                    file_path=ir_doc.file_path,
                    start_line=symbol.start_line,
                    end_line=symbol.end_line,
                    chunk_type=symbol.type,
                    language=ir_doc.language,
                    metadata={"symbol_name": symbol.name},
                )
            )

        # 파일 전체 청크도 추가
        if chunks:
            chunks.append(
                Chunk(
                    id=f"{ir_doc.file_path}::__file__",
                    content=source_code[:500],  # 처음 500자
                    file_path=ir_doc.file_path,
                    start_line=1,
                    end_line=len(source_code.splitlines()),
                    chunk_type="file",
                    language=ir_doc.language,
                    metadata={},
                )
            )

        return chunks
