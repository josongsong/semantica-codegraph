"""
Workspace API (RFC-SEM-022 SOTA)

Immutable Revision Snapshot 관리.

SOTA Features:
- FastAPI Dependency Injection
- SQLite/PostgreSQL 듀얼 모드
- Workspace 계층 구조
- A/B 실험 지원
- PatchSet 관리

Workspace는 특정 시점의 코드 상태를 나타내며,
Patch는 overlay로만 적용됨.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from codegraph_engine.shared_kernel.contracts import Workspace
from codegraph_engine.shared_kernel.infrastructure.workspace_repository import (
    WorkspaceRepository,
    get_workspace_repository,
)

router = APIRouter(prefix="/api/v1/workspaces", tags=["Workspaces"])


def get_repository() -> WorkspaceRepository:
    """
    Dependency Injection용 Repository Provider (SOTA Pattern).

    테스트에서는 app.dependency_overrides로 교체 가능.
    """
    return get_workspace_repository()


# ============================================================
# Request/Response Models
# ============================================================


class WorkspaceCreate(BaseModel):
    """Workspace 생성 요청."""

    repo_id: str = Field(..., description="저장소 ID")
    revision: str = Field(..., description="Git commit SHA 또는 PR ref")
    metadata: dict[str, Any] = Field(default_factory=dict, description="메타데이터")


class WorkspaceBranch(BaseModel):
    """Workspace 분기 요청 (A/B 실험)."""

    base_workspace_id: str = Field(..., description="기준 워크스페이스 ID")
    patchset_id: str = Field(..., description="적용할 패치셋 ID")
    metadata: dict[str, Any] = Field(default_factory=dict)


class WorkspaceResponse(BaseModel):
    """Workspace 응답."""

    workspace_id: str
    repo_id: str
    revision: str
    created_at: str
    parent_workspace_id: str | None = None
    patchset_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class WorkspaceListResponse(BaseModel):
    """Workspace 목록 응답."""

    workspaces: list[WorkspaceResponse]
    total: int


# ============================================================
# Endpoints
# ============================================================


@router.post("", response_model=WorkspaceResponse)
async def create_workspace(
    request: WorkspaceCreate,
    repo: WorkspaceRepository = Depends(get_repository),
):
    """
    Workspace 생성 (RFC-SEM-022 SOTA).

    새로운 immutable revision snapshot을 생성.
    """
    from codegraph_engine.shared_kernel.infrastructure.workspace_repository import (
        create_workspace as create_ws,
    )

    workspace = await create_ws(
        repo_id=request.repo_id,
        revision=request.revision,
        metadata=request.metadata,
        repository=repo,
    )

    return WorkspaceResponse(
        workspace_id=workspace.workspace_id,
        repo_id=workspace.repo_id,
        revision=workspace.revision,
        created_at=workspace.created_at.isoformat(),
        parent_workspace_id=workspace.parent_workspace_id,
        patchset_id=workspace.patchset_id,
        metadata=workspace.metadata,
    )


@router.get("/{workspace_id}", response_model=WorkspaceResponse)
async def get_workspace(
    workspace_id: str,
    repo: WorkspaceRepository = Depends(get_repository),
):
    """
    Workspace 조회 (RFC-SEM-022 SOTA).

    특정 workspace의 상세 정보를 반환.
    """
    workspace = await repo.get(workspace_id)

    if not workspace:
        raise HTTPException(status_code=404, detail=f"Workspace not found: {workspace_id}")

    return WorkspaceResponse(
        workspace_id=workspace.workspace_id,
        repo_id=workspace.repo_id,
        revision=workspace.revision,
        created_at=workspace.created_at.isoformat(),
        parent_workspace_id=workspace.parent_workspace_id,
        patchset_id=workspace.patchset_id,
        metadata=workspace.metadata,
    )


@router.get("", response_model=WorkspaceListResponse)
async def list_workspaces(
    repo_id: str | None = Query(None, description="저장소 ID로 필터"),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    repo: WorkspaceRepository = Depends(get_repository),
):
    """
    Workspace 목록 조회 (RFC-SEM-022 SOTA).
    """
    workspaces, total = await repo.list(repo_id, limit, offset)

    return WorkspaceListResponse(
        workspaces=[
            WorkspaceResponse(
                workspace_id=w.workspace_id,
                repo_id=w.repo_id,
                revision=w.revision,
                created_at=w.created_at.isoformat(),
                parent_workspace_id=w.parent_workspace_id,
                patchset_id=w.patchset_id,
                metadata=w.metadata,
            )
            for w in workspaces
        ],
        total=total,
    )


@router.post("/branch", response_model=WorkspaceResponse)
async def branch_workspace_endpoint(
    request: WorkspaceBranch,
    repo: WorkspaceRepository = Depends(get_repository),
):
    """
    Workspace 분기 (A/B 실험) - RFC-SEM-022 SOTA.

    기존 workspace를 기반으로 patchset을 적용한 새 workspace 생성.

    RFC-SEM-022:
    - ws_base
    -   ├─ ws_trial_A (patchset_A)
    -   └─ ws_trial_B (patchset_B)
    """
    from codegraph_engine.shared_kernel.infrastructure.workspace_repository import (
        branch_workspace,
    )

    try:
        workspace = await branch_workspace(
            base_workspace_id=request.base_workspace_id,
            patchset_id=request.patchset_id,
            metadata=request.metadata,
            repository=repo,
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    return WorkspaceResponse(
        workspace_id=workspace.workspace_id,
        repo_id=workspace.repo_id,
        revision=workspace.revision,
        created_at=workspace.created_at.isoformat(),
        parent_workspace_id=workspace.parent_workspace_id,
        patchset_id=workspace.patchset_id,
        metadata=workspace.metadata,
    )


@router.delete("/{workspace_id}")
async def delete_workspace(
    workspace_id: str,
    repo: WorkspaceRepository = Depends(get_repository),
):
    """
    Workspace 삭제 (RFC-SEM-022 SOTA).

    Note: 자식 workspace가 있으면 삭제 불가.
    """
    workspace = await repo.get(workspace_id)

    if not workspace:
        raise HTTPException(status_code=404, detail=f"Workspace not found: {workspace_id}")

    # Check for children
    children = await repo.get_children(workspace_id)

    if children:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot delete workspace with {len(children)} child workspace(s)",
        )

    await repo.delete(workspace_id)

    return {"status": "deleted", "workspace_id": workspace_id}
