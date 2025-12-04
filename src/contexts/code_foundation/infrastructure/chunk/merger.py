"""
Chunk Merger

Base chunk와 overlay chunk를 병합.
Overlay가 base를 shadowing하는 로직 구현.

Strategy:
- Overlay chunk가 우선순위
- 같은 file_path + line range가 겹치면 overlay가 base를 가림
- 겹치지 않는 base chunk는 그대로 유지
"""

from src.common.observability import get_logger
from src.contexts.code_foundation.infrastructure.chunk.models import Chunk

logger = get_logger(__name__)


class ChunkMerger:
    """Base와 overlay chunk를 병합"""

    def merge(self, base_chunks: list[Chunk], overlay_chunks: list[Chunk]) -> list[Chunk]:
        """
        Base + overlay 병합.

        Overlay가 base를 shadowing:
        - 같은 file + line range 겹치면 overlay 우선
        - 겹치지 않는 base는 유지

        Args:
            base_chunks: Base chunk 리스트
            overlay_chunks: Overlay chunk 리스트

        Returns:
            병합된 chunk 리스트 (overlay + non-shadowed base)
        """
        if not overlay_chunks:
            return base_chunks

        # Overlay chunks by file_path for fast lookup
        overlay_by_file: dict[str, list[Chunk]] = {}
        for chunk in overlay_chunks:
            if chunk.file_path:
                overlay_by_file.setdefault(chunk.file_path, []).append(chunk)

        # Filter out shadowed base chunks
        non_shadowed_base = []
        shadowed_count = 0

        for base_chunk in base_chunks:
            if not base_chunk.file_path or base_chunk.file_path not in overlay_by_file:
                # No overlay for this file
                non_shadowed_base.append(base_chunk)
                continue

            # Check if any overlay shadows this base chunk
            is_shadowed = self._is_shadowed(base_chunk, overlay_by_file[base_chunk.file_path])

            if not is_shadowed:
                non_shadowed_base.append(base_chunk)
            else:
                shadowed_count += 1

        # Merge: overlay + non-shadowed base
        merged = overlay_chunks + non_shadowed_base

        logger.debug(
            "chunks_merged",
            base_count=len(base_chunks),
            overlay_count=len(overlay_chunks),
            shadowed_count=shadowed_count,
            merged_count=len(merged),
        )

        return merged

    def _is_shadowed(self, base_chunk: Chunk, overlays: list[Chunk]) -> bool:
        """
        Check if base chunk is shadowed by any overlay.

        Shadowing occurs when:
        1. Same file_path
        2. Line ranges overlap OR
        3. Same chunk_id (exact replacement)

        Args:
            base_chunk: Base chunk
            overlays: Overlay chunks for the same file

        Returns:
            True if shadowed
        """
        for overlay in overlays:
            # Exact replacement (same chunk ID)
            if overlay.base_chunk_id == base_chunk.chunk_id:
                return True

            # Line range overlap
            if self._ranges_overlap(base_chunk, overlay):
                return True

        return False

    def _ranges_overlap(self, chunk1: Chunk, chunk2: Chunk) -> bool:
        """
        Check if two chunks' line ranges overlap.

        Args:
            chunk1: First chunk
            chunk2: Second chunk

        Returns:
            True if ranges overlap
        """
        # Both must have line ranges
        if chunk1.start_line is None or chunk1.end_line is None:
            return False
        if chunk2.start_line is None or chunk2.end_line is None:
            return False

        # Check overlap
        return not (
            chunk1.end_line < chunk2.start_line  # chunk1 ends before chunk2 starts
            or chunk2.end_line < chunk1.start_line  # chunk2 ends before chunk1 starts
        )

    def get_shadowed_chunks(self, base_chunks: list[Chunk], overlay_chunks: list[Chunk]) -> list[Chunk]:
        """
        Get list of base chunks that are shadowed by overlays.

        Useful for debugging or diff visualization.

        Args:
            base_chunks: Base chunk 리스트
            overlay_chunks: Overlay chunk 리스트

        Returns:
            Shadowed base chunks
        """
        if not overlay_chunks:
            return []

        # Overlay chunks by file_path
        overlay_by_file: dict[str, list[Chunk]] = {}
        for chunk in overlay_chunks:
            if chunk.file_path:
                overlay_by_file.setdefault(chunk.file_path, []).append(chunk)

        # Find shadowed
        shadowed = []
        for base_chunk in base_chunks:
            if not base_chunk.file_path or base_chunk.file_path not in overlay_by_file:
                continue

            if self._is_shadowed(base_chunk, overlay_by_file[base_chunk.file_path]):
                shadowed.append(base_chunk)

        return shadowed
