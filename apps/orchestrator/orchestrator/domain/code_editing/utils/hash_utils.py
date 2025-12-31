"""
Hash Utilities (DRY)

Content hash 계산을 위한 공통 유틸리티

Usage:
    from apps.orchestrator.orchestrator.domain.code_editing.utils import compute_content_hash

    # 16자 해시
    hash_16 = compute_content_hash(content, length=16)

    # 8자 해시
    hash_8 = compute_content_hash(content, length=8)

    # 전체 해시
    hash_full = compute_content_hash(content)
"""

import hashlib
from typing import overload


@overload
def compute_content_hash(content: str, length: int | None = None) -> str: ...


@overload
def compute_content_hash(content: bytes, length: int | None = None) -> str: ...


def compute_content_hash(content: str | bytes, length: int | None = None) -> str:
    """
    Content hash 계산 (SHA256)

    Args:
        content: 해시 계산 대상 (str or bytes)
        length: 해시 길이 (None이면 전체 64자)

    Returns:
        SHA256 hex digest (length로 잘림)

    Examples:
        >>> compute_content_hash("hello")
        '2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824'

        >>> compute_content_hash("hello", length=16)
        '2cf24dba5fb0a30e'

        >>> compute_content_hash(b"hello", length=8)
        '2cf24dba'
    """
    if isinstance(content, str):
        content = content.encode("utf-8")

    hash_full = hashlib.sha256(content).hexdigest()

    if length is not None:
        return hash_full[:length]

    return hash_full


def verify_content_hash(content: str | bytes, expected_hash: str) -> bool:
    """
    Content hash 검증

    Args:
        content: 검증할 내용
        expected_hash: 예상 해시

    Returns:
        해시 일치 여부
    """
    length = len(expected_hash)
    actual_hash = compute_content_hash(content, length=length)
    return actual_hash == expected_hash
