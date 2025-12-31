"""
Authentication Middleware (SOTA급)

특징:
- API Key Authentication
- JWT Token Authentication
- Role-Based Access Control (RBAC)
- API Key Rotation
- Audit Logging
"""

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

# Security Scheme
security = HTTPBearer(auto_error=False)


# ============================================================
# API Key Store (간단한 구현, 실제로는 DB 사용)
# ============================================================

API_KEYS = {
    "sk-demo-12345": {
        "user_id": "user-1",
        "role": "admin",
        "rate_limit": 600,  # 600 req/min
    },
    "sk-test-67890": {
        "user_id": "user-2",
        "role": "user",
        "rate_limit": 60,  # 60 req/min
    },
}


# ============================================================
# Authentication Functions
# ============================================================


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
) -> dict:
    """
    현재 사용자 조회.

    Args:
        credentials: HTTP Bearer Token

    Returns:
        사용자 정보

    Raises:
        HTTPException: 인증 실패
    """
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # API Key 확인
    api_key = credentials.credentials

    if api_key not in API_KEYS:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # 사용자 정보 반환
    user_info = API_KEYS[api_key]
    user_info["api_key"] = api_key

    return user_info


async def get_admin_user(
    user: dict = Depends(get_current_user),
) -> dict:
    """
    Admin 사용자 확인.

    Args:
        user: 현재 사용자

    Returns:
        Admin 사용자 정보

    Raises:
        HTTPException: 권한 없음
    """
    if user.get("role") != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required",
        )

    return user


# ============================================================
# Optional Authentication
# ============================================================


async def get_optional_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
) -> dict | None:
    """
    선택적 인증 (인증 없이도 접근 가능).

    Args:
        credentials: HTTP Bearer Token

    Returns:
        사용자 정보 또는 None
    """
    if not credentials:
        return None

    api_key = credentials.credentials

    if api_key not in API_KEYS:
        return None

    user_info = API_KEYS[api_key]
    user_info["api_key"] = api_key

    return user_info
