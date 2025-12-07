"""
Get Session Query

세션 조회 쿼리 (CQRS Query)
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class GetSessionQuery:
    """세션 조회 쿼리"""

    session_id: str


@dataclass(frozen=True)
class GetSessionsByRepoQuery:
    """리포지토리별 세션 조회 쿼리"""

    repo_id: str
