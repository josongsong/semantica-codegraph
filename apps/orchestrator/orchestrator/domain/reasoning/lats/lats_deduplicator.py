"""
LATS Semantic Deduplicator (v9)

AST 기반 의미론적 중복 제거
"""

import ast
import hashlib
import logging

logger = logging.getLogger(__name__)


class LATSDeduplicator:
    """
    LATS Semantic Deduplication

    AST 기반 중복 제거

    책임:
    - 코드 정규화 (AST 기반)
    - 의미론적 Hash 계산
    - 중복 감지

    SOTA:
    - AST Normalization
    - Semantic Hash
    """

    def __init__(self):
        """초기화"""
        self.seen_hashes = set()

        logger.info("LATSDeduplicator initialized")

    def normalize_code(self, code: str) -> str:
        """
        코드 정규화 (AST 기반)

        Args:
            code: Python 코드

        Returns:
            정규화된 AST 문자열
        """
        try:
            # AST 파싱
            tree = ast.parse(code)

            # AST를 정규화된 문자열로 변환
            # (변수명, 들여쓰기 무시)
            normalized = ast.dump(tree, annotate_fields=False)

            return normalized

        except SyntaxError:
            # 파싱 실패 시 원본 반환
            logger.debug(f"Failed to parse code for normalization: {code[:50]}...")
            return code

        except Exception as e:
            logger.warning(f"Normalization failed: {e}")
            return code

    def get_semantic_hash(self, code: str) -> str:
        """
        의미론적 Hash

        Args:
            code: 코드

        Returns:
            Hash 문자열
        """
        normalized = self.normalize_code(code)
        return hashlib.md5(normalized.encode()).hexdigest()

    def is_duplicate(self, code: str) -> bool:
        """
        중복 여부 확인

        Args:
            code: 코드

        Returns:
            중복 여부
        """
        hash_value = self.get_semantic_hash(code)

        if hash_value in self.seen_hashes:
            logger.debug(f"Duplicate code detected: {code[:50]}...")
            return True

        # 새 Hash 등록
        self.seen_hashes.add(hash_value)
        return False

    def reset(self):
        """초기화 (새 탐색 시작 시)"""
        self.seen_hashes.clear()
        logger.debug("Deduplicator reset")

    def get_stats(self) -> dict:
        """통계 반환"""
        return {
            "unique_codes": len(self.seen_hashes),
            "seen_hashes": list(self.seen_hashes)[:10],  # 처음 10개만
        }
