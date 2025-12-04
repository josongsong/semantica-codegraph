"""
Zoekt Client

Zoekt 검색 엔진 클라이언트
"""

import httpx


class ZoektClient:
    """Zoekt 클라이언트 래퍼"""

    def __init__(self, base_url: str):
        """
        초기화

        Args:
            base_url: Zoekt 서버 URL
        """
        self.base_url = base_url

    async def search(self, query: str, repo_id: str, limit: int = 10) -> list[dict]:
        """검색 실행"""
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.base_url}/search",
                params={"q": f"{query} r:{repo_id}", "num": limit},
                timeout=30.0,
            )
            response.raise_for_status()
            return response.json().get("Result", {}).get("Files", [])

    async def health_check(self) -> bool:
        """헬스 체크"""
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(f"{self.base_url}/", timeout=5.0)
                return response.status_code == 200
        except Exception:
            return False
