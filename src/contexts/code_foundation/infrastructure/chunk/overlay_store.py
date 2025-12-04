"""
Overlay Chunk Store

IDE 실시간 변경사항(overlay)을 저장/관리하는 저장소.
저장되지 않은 파일 변경사항을 overlay chunk로 처리.

Strategy:
- In-memory storage (Redis로 확장 가능)
- Session 기반 격리
- File path별로 overlay chunk 관리
"""

from collections import defaultdict
from typing import Any

from src.common.observability import get_logger
from src.contexts.code_foundation.infrastructure.chunk.models import Chunk

logger = get_logger(__name__)


class OverlayChunkStore:
    """
    Overlay chunk 저장소 (In-memory).

    세션별로 overlay chunk를 관리하며, 저장 시 base로 승격.
    """

    def __init__(self):
        # session_id -> file_path -> list[Chunk]
        self._overlays: dict[str, dict[str, list[Chunk]]] = defaultdict(lambda: defaultdict(list))

        # Statistics
        self._stats = {"upserts": 0, "gets": 0, "clears": 0, "promotes": 0}

    def upsert_overlay(self, session_id: str, file_path: str, chunks: list[Chunk]) -> None:
        """
        Overlay chunk 저장/업데이트.

        Args:
            session_id: IDE 세션 ID
            file_path: 파일 경로
            chunks: Overlay chunk 리스트 (is_overlay=True)
        """
        # Validate
        for chunk in chunks:
            if not chunk.is_overlay:
                raise ValueError(f"Chunk {chunk.chunk_id} is not an overlay chunk")
            if chunk.overlay_session_id != session_id:
                chunk.overlay_session_id = session_id

        # Store
        self._overlays[session_id][file_path] = chunks
        self._stats["upserts"] += 1

        logger.debug(
            "overlay_upserted",
            session_id=session_id,
            file_path=file_path,
            chunk_count=len(chunks),
        )

    def get_overlay(self, session_id: str, file_path: str | None = None) -> list[Chunk]:
        """
        Overlay chunk 조회.

        Args:
            session_id: IDE 세션 ID
            file_path: 파일 경로 (None이면 세션 전체)

        Returns:
            Overlay chunk 리스트
        """
        self._stats["gets"] += 1

        if file_path:
            return self._overlays.get(session_id, {}).get(file_path, [])

        # All files in session
        all_chunks = []
        for chunks in self._overlays.get(session_id, {}).values():
            all_chunks.extend(chunks)
        return all_chunks

    def get_all_overlays(self, session_id: str) -> dict[str, list[Chunk]]:
        """
        세션의 모든 overlay 조회 (파일별로 그룹화).

        Args:
            session_id: IDE 세션 ID

        Returns:
            file_path -> list[Chunk] 딕셔너리
        """
        return dict(self._overlays.get(session_id, {}))

    def clear_overlay(self, session_id: str, file_path: str | None = None) -> None:
        """
        Overlay chunk 삭제.

        Args:
            session_id: IDE 세션 ID
            file_path: 파일 경로 (None이면 세션 전체 삭제)
        """
        if file_path:
            if session_id in self._overlays:
                self._overlays[session_id].pop(file_path, None)
                logger.debug("overlay_cleared", session_id=session_id, file_path=file_path)
        else:
            self._overlays.pop(session_id, None)
            logger.info("overlay_session_cleared", session_id=session_id)

        self._stats["clears"] += 1

    def promote_to_base(self, session_id: str, file_path: str) -> list[Chunk]:
        """
        Overlay를 base로 승격 (저장 시).

        Overlay chunk를 반환하고 저장소에서 제거.
        호출자가 is_overlay=False로 변경하여 base에 저장.

        Args:
            session_id: IDE 세션 ID
            file_path: 파일 경로

        Returns:
            승격할 chunk 리스트 (호출자가 base로 저장)
        """
        chunks = self.get_overlay(session_id, file_path)
        self.clear_overlay(session_id, file_path)
        self._stats["promotes"] += 1

        logger.info(
            "overlay_promoted",
            session_id=session_id,
            file_path=file_path,
            chunk_count=len(chunks),
        )

        return chunks

    def get_stats(self) -> dict[str, Any]:
        """
        통계 정보 조회.

        Returns:
            통계 딕셔너리
        """
        return {
            **self._stats,
            "active_sessions": len(self._overlays),
            "total_overlays": sum(len(files) for files in self._overlays.values()),
        }

    def cleanup_session(self, session_id: str) -> None:
        """
        세션 정리 (IDE 종료 시).

        Args:
            session_id: IDE 세션 ID
        """
        self.clear_overlay(session_id)
