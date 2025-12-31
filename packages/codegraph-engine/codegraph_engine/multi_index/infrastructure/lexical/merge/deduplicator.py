"""Deduplicator - Base+Delta 중복 제거."""

from codegraph_shared.infra.observability import get_logger

logger = get_logger(__name__)


class Deduplicator:
    """중복 제거기.

    Base와 Delta에 동일 파일이 있으면 Delta가 우선합니다.
    """

    @staticmethod
    def deduplicate(
        base_results: list[dict],
        delta_results: list[dict],
        tombstones: set[str],
    ) -> list[dict]:
        """Base+Delta 중복 제거.

        SOTA 규칙:
        1. Delta가 Base를 override
        2. Tombstone은 제외

        Args:
            base_results: Base 검색 결과
            delta_results: Delta 검색 결과
            tombstones: 삭제된 파일 경로 집합

        Returns:
            중복 제거된 결과
        """
        # Delta 파일 집합
        delta_files = {r["file_path"] for r in delta_results}

        # Base 필터링 (Delta에 있거나 Tombstone이면 제외)
        filtered_base = [
            r for r in base_results if r["file_path"] not in delta_files and r["file_path"] not in tombstones
        ]

        # Delta + filtered Base
        merged = list(delta_results) + filtered_base

        logger.info(
            f"Deduplicated: delta={len(delta_results)}, "
            f"base={len(base_results)} → {len(filtered_base)} (after filter), "
            f"total={len(merged)}",
            extra={
                "delta_count": len(delta_results),
                "base_count": len(base_results),
                "filtered_base": len(filtered_base),
                "tombstones": len(tombstones),
            },
        )

        return merged
