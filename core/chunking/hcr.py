from dataclasses import dataclass

import numpy as np


@dataclass
class Chunk:
    """코드 청크"""

    content: str
    start_line: int
    end_line: int
    file_path: str
    level: int = 0
    embedding: np.ndarray = None
    metadata: dict = None

    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}


class HCRChunker:
    """HCR (Hierarchical Code Representation) 기반 계층적 코드 청킹"""

    def __init__(self, chunk_size: int = 512, overlap: int = 50):
        self.chunk_size = chunk_size
        self.overlap = overlap

    def chunk_code(self, content: str, file_path: str) -> list[Chunk]:
        """코드를 청크로 분할"""
        lines = content.split("\n")
        chunks = []
        start = 0

        while start < len(lines):
            end = min(start + self.chunk_size, len(lines))
            chunk_content = "\n".join(lines[start:end])

            chunk = Chunk(
                content=chunk_content,
                start_line=start + 1,
                end_line=end,
                file_path=file_path,
                level=0,
            )
            chunks.append(chunk)

            start = end - self.overlap if end < len(lines) else end

        return chunks

    def build_hierarchical_chunks(self, chunks: list[Chunk]) -> list[Chunk]:
        """계층적 청크 구성"""
        all_chunks = chunks.copy()
        current_level = chunks

        level = 1
        while len(current_level) > 1:
            next_level = []
            for i in range(0, len(current_level), 2):
                if i + 1 < len(current_level):
                    merged = self._merge_chunks(current_level[i], current_level[i + 1], level)
                else:
                    merged = Chunk(
                        content=current_level[i].content,
                        start_line=current_level[i].start_line,
                        end_line=current_level[i].end_line,
                        file_path=current_level[i].file_path,
                        level=level,
                    )
                next_level.append(merged)
                all_chunks.append(merged)

            current_level = next_level
            level += 1

        return all_chunks

    def _merge_chunks(self, chunk1: Chunk, chunk2: Chunk, level: int) -> Chunk:
        """두 청크를 병합"""
        return Chunk(
            content=f"{chunk1.content}\n{chunk2.content}",
            start_line=chunk1.start_line,
            end_line=chunk2.end_line,
            file_path=chunk1.file_path,
            level=level,
        )
