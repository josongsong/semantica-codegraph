"""
Security Analysis Ports

보안 분석 파이프라인의 포트 인터페이스
"""

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from codegraph_analysis.security_analysis.domain.models.vulnerability import Vulnerability


class SecurityAnalyzerPort(Protocol):
    """보안 분석기 포트"""

    async def analyze(self, file_path: str, repo_id: str) -> list["Vulnerability"]:
        """파일 보안 분석"""
        ...


class VulnerabilityStorePort(Protocol):
    """취약점 저장소 포트"""

    async def save_vulnerabilities(self, vulnerabilities: list["Vulnerability"], repo_id: str) -> None:
        """취약점 저장"""
        ...

    async def get_vulnerabilities(self, repo_id: str, severity: str | None = None) -> list["Vulnerability"]:
        """취약점 조회"""
        ...

    async def delete_vulnerabilities(self, repo_id: str) -> None:
        """취약점 삭제"""
        ...
