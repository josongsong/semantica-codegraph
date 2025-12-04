"""
Database Session

DB 세션 관리
"""

from contextlib import asynccontextmanager


@asynccontextmanager
async def get_db_session():
    """
    DB 세션 가져오기

    사용 예시:
        async with get_db_session() as session:
            await session.execute(...)
    """
    from src.container import container

    # 기존 PostgreSQL adapter 사용
    try:
        yield container.postgres
    except Exception:
        # 에러 시 롤백은 caller에서 처리
        raise
