"""
Verification Snapshot & Execution Models (RFC-SEM-022)

결정적(Deterministic) 실행을 보장하기 위한 핵심 모델.

Determinism Contract:
- engine_version 동일
- ruleset_hash / policies_hash 동일
- index_snapshot_id 동일
- workspace revision 동일
→ 동일한 Finding 보장
"""

import hashlib
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class VerificationSnapshot(BaseModel):
    """
    결정적 실행을 위한 스냅샷.

    동일 스냅샷 = 동일 결과 보장.
    """

    engine_version: str = Field(..., description="Semantica 엔진 버전 (예: 2.4.1)")
    ruleset_hash: str = Field(..., description="룰셋 SHA256 해시")
    policies_hash: str = Field(..., description="정책 SHA256 해시")
    index_snapshot_id: str = Field(..., description="인덱스 스냅샷 ID")
    repo_revision: str = Field(..., description="Git commit SHA")

    model_config = {"frozen": True}

    @classmethod
    def compute_hash(cls, content: str | bytes) -> str:
        """SHA256 해시 계산."""
        if isinstance(content, str):
            content = content.encode("utf-8")
        return f"sha256:{hashlib.sha256(content).hexdigest()[:12]}"


class AgentMetadata(BaseModel):
    """Agent 실행 메타데이터."""

    agent_model_id: str = Field(..., description="LLM 모델 ID (예: gpt-4o)")
    agent_version: str = Field(..., description="Agent 버전")
    prompt_hash: str | None = Field(None, description="프롬프트 해시 (optional)")

    model_config = {"frozen": True}


class Execution(BaseModel):
    """
    실행 단위 (Deterministic Unit).

    단순 실행 기록이 아니라 증명 가능한 스냅샷.
    """

    execution_id: str = Field(..., description="실행 ID")
    workspace_id: str = Field(..., description="워크스페이스 ID")
    spec_type: str = Field(..., description="실행 타입 (taint_analysis, impact, etc.)")
    state: Literal["pending", "running", "completed", "failed", "cancelled"] = Field("pending", description="실행 상태")
    trace_id: str = Field(..., description="추적 ID")

    # Determinism 보장
    verification_snapshot: VerificationSnapshot | None = Field(None, description="결정적 실행 스냅샷")

    # Agent 메타데이터 (optional)
    agent_metadata: AgentMetadata | None = Field(None, description="Agent 메타데이터")

    # 타임스탬프
    created_at: datetime = Field(default_factory=datetime.utcnow)
    completed_at: datetime | None = None

    # 결과
    result: dict[str, Any] | None = None
    error: str | None = None


class Workspace(BaseModel):
    """
    Immutable Revision Snapshot.

    Workspace는 특정 시점의 코드 상태를 나타냄.
    Patch는 overlay로만 적용.
    """

    workspace_id: str = Field(..., description="워크스페이스 ID")
    repo_id: str = Field(..., description="저장소 ID")
    revision: str = Field(..., description="Git commit SHA 또는 PR ref")
    created_at: datetime = Field(default_factory=datetime.utcnow)

    # Branch 관계 (A/B 실험)
    parent_workspace_id: str | None = Field(None, description="부모 워크스페이스 (branch 시)")
    patchset_id: str | None = Field(None, description="적용된 패치셋 ID")

    # 메타데이터
    metadata: dict[str, Any] = Field(default_factory=dict)

    model_config = {"frozen": True}


class PatchSet(BaseModel):
    """
    패치셋 모델.

    Workspace에 overlay로 적용되는 변경 집합.
    """

    patchset_id: str = Field(..., description="패치셋 ID")
    workspace_id: str = Field(..., description="대상 워크스페이스 ID")
    files: list[str] = Field(default_factory=list, description="변경 파일 목록")
    patches: dict[str, str] = Field(default_factory=dict, description="파일별 패치 내용")
    verified: bool = Field(False, description="검증 완료 여부")
    created_at: datetime = Field(default_factory=datetime.utcnow)

    # 검증 결과
    compile_verified: bool = Field(False, description="컴파일 검증 통과")
    finding_resolved: bool = Field(False, description="취약점 해결 확인")
    no_regression: bool = Field(False, description="회귀 없음 확인")


class Finding(BaseModel):
    """
    발견된 이슈/취약점.

    Evidence와 연결되어 증명 가능.
    """

    finding_id: str = Field(..., description="Finding ID")
    type: str = Field(..., description="타입 (sql_injection, xss, etc.)")
    severity: Literal["critical", "high", "medium", "low", "info"] = Field(..., description="심각도")
    message: str = Field(..., description="설명 메시지")

    # 위치
    file_path: str = Field(..., description="파일 경로")
    line: int = Field(..., description="라인 번호")
    column: int = Field(0, description="컬럼 번호")

    # Evidence
    evidence_uri: str | None = Field(None, description="증거 URI (semantica://executions/{id}/artifacts)")
    execution_id: str | None = Field(None, description="발견된 실행 ID")

    # CWE 매핑
    cwe_id: str | None = Field(None, description="CWE ID (예: CWE-89)")


# ============================================================
# Factory Functions
# ============================================================


def create_verification_snapshot(
    engine_version: str,
    ruleset_content: str,
    policies_content: str,
    index_id: str,
    repo_revision: str,
) -> VerificationSnapshot:
    """VerificationSnapshot 생성."""
    return VerificationSnapshot(
        engine_version=engine_version,
        ruleset_hash=VerificationSnapshot.compute_hash(ruleset_content),
        policies_hash=VerificationSnapshot.compute_hash(policies_content),
        index_snapshot_id=index_id,
        repo_revision=repo_revision,
    )


def create_workspace(
    workspace_id: str,
    repo_id: str,
    revision: str,
    parent_id: str | None = None,
    patchset_id: str | None = None,
) -> Workspace:
    """Workspace 생성."""
    return Workspace(
        workspace_id=workspace_id,
        repo_id=repo_id,
        revision=revision,
        parent_workspace_id=parent_id,
        patchset_id=patchset_id,
    )
