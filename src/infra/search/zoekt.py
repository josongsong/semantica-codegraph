"""
Zoekt Lexical Search Adapter

HTTP client for Zoekt search API.

API Format:
    GET /search?q={query}&num={limit}&format=json

Response:
    {
        "result": {
            "FileMatches": [
                {
                    "FileName": "example.py",
                    "Repo": "test-repo",
                    "Language": "Python",
                    "Matches": [
                        {
                            "LineNum": 1,
                            "Fragments": [
                                {"Pre": "def ", "Match": "hello", "Post": "():\n"}
                            ]
                        }
                    ]
                }
            ]
        }
    }
"""

import httpx
from pydantic import BaseModel

from src.common.observability import get_logger

logger = get_logger(__name__)


class ZoektMatchFragment(BaseModel):
    """Zoekt match fragment (Pre/Match/Post)"""

    Pre: str = ""
    Match: str = ""
    Post: str = ""


class ZoektMatch(BaseModel):
    """Zoekt match (line + fragments)"""

    LineNum: int
    Fragments: list[ZoektMatchFragment] = []
    FileName: str = ""


class ZoektFileMatch(BaseModel):
    """Zoekt file match"""

    FileName: str
    Repo: str
    Language: str = ""
    Matches: list[ZoektMatch] = []


class ZoektSearchResult(BaseModel):
    """Zoekt search result"""

    FileMatches: list[ZoektFileMatch] | None = None


class ZoektAdapter:
    """
    Zoekt HTTP API client.

    Attributes:
        base_url: Zoekt HTTP endpoint (e.g., http://localhost:7205)
    """

    def __init__(self, host: str, port: int) -> None:
        self.host = host
        self.port = port
        self.base_url = f"http://{host}:{port}"
        self.client = httpx.AsyncClient(timeout=30.0)

    async def search(
        self,
        query: str,
        limit: int = 200,
        repo_filter: str | None = None,
    ) -> list[ZoektFileMatch]:
        """
        Zoekt 검색 수행.

        Args:
            query: Zoekt query (supports regex, literal, etc)
            limit: Maximum results
            repo_filter: Optional repo name filter

        Returns:
            List of ZoektFileMatch

        Raises:
            httpx.HTTPError: HTTP request failed
        """
        # Build query with repo filter
        full_query = query
        if repo_filter:
            full_query = f"repo:{repo_filter} {query}"

        params = {"q": full_query, "num": limit, "format": "json"}

        try:
            response = await self.client.get(f"{self.base_url}/search", params=params)
            response.raise_for_status()

            data = response.json()
            result = data.get("result", {})

            # Parse FileMatches
            file_matches = result.get("FileMatches")
            if not file_matches:
                return []

            return [ZoektFileMatch(**fm) for fm in file_matches]

        except httpx.HTTPError as e:
            logger.error(f"Zoekt search failed: {e}")
            raise

    async def healthcheck(self) -> bool:
        """
        Zoekt health check.

        Returns:
            True if Zoekt is responsive
        """
        try:
            response = await self.client.get(f"{self.base_url}/")
            return response.status_code == 200
        except Exception as e:
            logger.error(f"Zoekt healthcheck failed: {e}")
            return False

    async def close(self) -> None:
        """Close HTTP client"""
        await self.client.aclose()
