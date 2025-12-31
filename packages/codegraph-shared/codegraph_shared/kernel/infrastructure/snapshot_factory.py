"""
VerificationSnapshot Factory (RFC-SEM-022 SOTA)

결정적 실행을 위한 스냅샷 자동 생성.

SOTA Features:
- 엔진 버전 자동 추출
- Ruleset/Policy 해시 자동 계산
- Index 스냅샷 ID 자동 연결
"""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
from typing import Any

from codegraph_shared.kernel.contracts import VerificationSnapshot


def get_engine_version() -> str:
    """
    엔진 버전 자동 추출.

    우선순위:
    1. __version__.py 파일
    2. 환경변수 SEMANTICA_VERSION
    3. Fallback: "dev"
    """
    # 1. __version__.py
    try:
        version_file = Path(__file__).parent.parent.parent.parent / "__version__.py"
        if version_file.exists():
            namespace: dict[str, Any] = {}
            exec(version_file.read_text(), namespace)
            return namespace.get("__version__", "dev")
    except Exception:
        pass

    # 2. 환경변수
    if version := os.environ.get("SEMANTICA_VERSION"):
        return version

    # 3. Fallback
    return "dev"


def compute_ruleset_hash(ruleset_dir: str | Path = "cwe/ruleset") -> str:
    """
    Ruleset 디렉토리 전체 해시 계산.

    모든 .yaml 파일의 내용을 합쳐서 해시.
    """
    ruleset_path = Path(ruleset_dir)

    if not ruleset_path.exists():
        return "sha256:no_ruleset"

    # 모든 .yaml 파일 수집
    yaml_files = sorted(ruleset_path.glob("**/*.yaml"))

    if not yaml_files:
        return "sha256:empty_ruleset"

    # 파일명 순서대로 내용 연결
    combined = []
    for f in yaml_files:
        combined.append(f"# {f.name}\n")
        combined.append(f.read_text())

    content = "\n".join(combined)
    hash_obj = hashlib.sha256(content.encode("utf-8"))
    return f"sha256:{hash_obj.hexdigest()[:12]}"


def compute_policies_hash(policy_dir: str | Path = "cwe/policies") -> str:
    """
    Policy 디렉토리 전체 해시 계산.
    """
    policy_path = Path(policy_dir)

    if not policy_path.exists():
        return "sha256:no_policies"

    policy_files = sorted(policy_path.glob("**/*.yaml"))

    if not policy_files:
        return "sha256:empty_policies"

    combined = []
    for f in policy_files:
        combined.append(f"# {f.name}\n")
        combined.append(f.read_text())

    content = "\n".join(combined)
    hash_obj = hashlib.sha256(content.encode("utf-8"))
    return f"sha256:{hash_obj.hexdigest()[:12]}"


def get_current_index_snapshot_id() -> str:
    """
    현재 인덱스 스냅샷 ID 획득.

    우선순위:
    1. DI Container에서 index service 조회
    2. 환경변수 SEMANTICA_INDEX_ID
    3. Fallback: "index_latest"
    """
    # 1. Container
    try:
        from src.container import container

        index_service = container.index_service()
        if hasattr(index_service, "get_snapshot_id"):
            return index_service.get_snapshot_id()
    except Exception:
        pass

    # 2. 환경변수
    if index_id := os.environ.get("SEMANTICA_INDEX_ID"):
        return index_id

    # 3. Fallback
    return "index_latest"


def create_snapshot_for_execution(
    workspace_id: str,
    repo_revision: str | None = None,
    ruleset_dir: str | Path = "cwe/ruleset",
    policy_dir: str | Path = "cwe/policies",
) -> VerificationSnapshot:
    """
    Execution을 위한 VerificationSnapshot 자동 생성 (SOTA).

    Args:
        workspace_id: Workspace ID
        repo_revision: Git commit SHA (None이면 workspace에서 추출)
        ruleset_dir: Ruleset 디렉토리 경로
        policy_dir: Policy 디렉토리 경로

    Returns:
        VerificationSnapshot with all fields auto-populated
    """
    # repo_revision 획득 (환경변수 우선)
    if not repo_revision:
        repo_revision = os.environ.get("SEMANTICA_REPO_REVISION", "HEAD")

    return VerificationSnapshot(
        engine_version=get_engine_version(),
        ruleset_hash=compute_ruleset_hash(ruleset_dir),
        policies_hash=compute_policies_hash(policy_dir),
        index_snapshot_id=get_current_index_snapshot_id(),
        repo_revision=repo_revision,
    )


# ============================================================
# Singleton Cache (성능 최적화)
# ============================================================

_cached_snapshot: VerificationSnapshot | None = None
_cache_invalidated = False


def get_current_snapshot(force_refresh: bool = False) -> VerificationSnapshot:
    """
    현재 스냅샷 캐싱 (SOTA Pattern).

    Ruleset/Policy가 변경되지 않는 한 동일한 스냅샷 반환.
    """
    global _cached_snapshot, _cache_invalidated

    if force_refresh or _cache_invalidated or _cached_snapshot is None:
        _cached_snapshot = create_snapshot_for_execution(
            workspace_id="default",
            repo_revision="HEAD",
        )
        _cache_invalidated = False

    return _cached_snapshot


def invalidate_snapshot_cache() -> None:
    """
    스냅샷 캐시 무효화.

    Ruleset/Policy 변경 시 호출.
    """
    global _cache_invalidated
    _cache_invalidated = True
