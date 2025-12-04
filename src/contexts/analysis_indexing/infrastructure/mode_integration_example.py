"""모드 시스템 통합 예제."""

import asyncio
from pathlib import Path

from src.contexts.analysis_indexing.infrastructure.background_scheduler import BackgroundScheduler
from src.contexts.analysis_indexing.infrastructure.change_detector import ChangeDetector
from src.contexts.analysis_indexing.infrastructure.mode_controller import ModeController
from src.contexts.analysis_indexing.infrastructure.mode_manager import ModeManager
from src.contexts.analysis_indexing.infrastructure.models import IndexingMode
from src.contexts.analysis_indexing.infrastructure.scope_expander import ScopeExpander
from src.infra.metadata.schema_version import SchemaVersionManager


async def example_ide_workflow():
    """IDE 워크플로우 예제."""
    # DI Container에서 주입받은 컴포넌트들
    orchestrator = get_orchestrator()  # DI
    graph_store = get_graph_store()  # DI
    metadata_store = get_metadata_store()  # DI
    file_hash_store = get_file_hash_store()  # DI

    # Mode system 초기화
    change_detector = ChangeDetector(file_hash_store=file_hash_store)
    scope_expander = ScopeExpander(graph_store=graph_store)
    mode_manager = ModeManager(
        change_detector=change_detector,
        scope_expander=scope_expander,
        metadata_store=metadata_store,
    )
    schema_version_manager = SchemaVersionManager(metadata_store=metadata_store)

    # Background scheduler
    async def indexing_callback(repo_id: str, mode: IndexingMode, checkpoint):
        await orchestrator.index_with_mode(
            repo_path=Path(f"/repos/{repo_id}"),
            repo_id=repo_id,
            mode=mode,
        )

    background_scheduler = BackgroundScheduler(indexing_callback=indexing_callback)
    asyncio.create_task(background_scheduler.start())

    # Controller 생성
    controller = ModeController(
        orchestrator=orchestrator,
        mode_manager=mode_manager,
        schema_version_manager=schema_version_manager,
        background_scheduler=background_scheduler,
    )

    # 1. 앱 시작 시
    await controller.on_startup(repo_id="my-repo", repo_path=Path("/repos/my-repo"))

    # 2. 파일 저장 시
    await controller.on_file_save(
        repo_id="my-repo",
        repo_path=Path("/repos/my-repo"),
        file_path="src/main.py",
    )

    # 3. git pull 후
    await controller.on_git_pull(repo_id="my-repo", repo_path=Path("/repos/my-repo"))

    # 4. idle 감지 (백그라운드 루프)
    while True:
        await asyncio.sleep(60)  # 1분마다
        await controller.on_idle(repo_id="my-repo", repo_path=Path("/repos/my-repo"))


async def example_ci_workflow():
    """CI/CD 워크플로우 예제."""
    orchestrator = get_orchestrator()
    repo_path = Path("/ci/workspace")
    repo_id = "my-repo"

    # PR: Fast Mode (변경 파일만)
    result = await orchestrator.index_with_mode(
        repo_path=repo_path,
        repo_id=repo_id,
        mode=IndexingMode.FAST,
    )
    print(f"PR indexing: {result.files_processed} files, {result.total_duration_seconds:.1f}s")

    # main push: Fast → Balanced
    fast_result = await orchestrator.index_with_mode(
        repo_path=repo_path,
        repo_id=repo_id,
        mode=IndexingMode.FAST,
    )

    balanced_result = await orchestrator.index_with_mode(
        repo_path=repo_path,
        repo_id=repo_id,
        mode=IndexingMode.BALANCED,
    )
    fast_time = fast_result.total_duration_seconds
    balanced_time = balanced_result.total_duration_seconds
    print(f"Main push: Fast {fast_time:.1f}s + Balanced {balanced_time:.1f}s")

    # Nightly: Deep Mode
    deep_result = await orchestrator.index_with_mode(
        repo_path=repo_path,
        repo_id=repo_id,
        mode=IndexingMode.DEEP,
    )
    print(f"Nightly Deep: {deep_result.total_duration_seconds / 60:.1f} minutes")


async def example_agent_workflow():
    """에이전트 워크플로우 예제."""
    controller = get_mode_controller()
    repo_id = "my-repo"
    repo_path = Path("/repos/my-repo")

    # 일반 쿼리: 기존 인덱스 사용 (인덱싱 불필요)
    # ... retriever.search() 호출 ...

    # 고급 분석 요청: on-demand Deep subset
    query_files = {"src/auth/login.py", "src/auth/session.py"}
    result = await controller.request_deep_analysis(
        repo_id=repo_id,
        repo_path=repo_path,
        query_files=query_files,
    )
    print(f"Deep subset analysis: {result.files_processed} files")


async def example_bootstrap():
    """신규 레포 Bootstrap 예제."""
    orchestrator = get_orchestrator()
    repo_path = Path("/repos/new-repo")
    repo_id = "new-repo"

    # Bootstrap Mode (최초 1회)
    result = await orchestrator.index_with_mode(
        repo_path=repo_path,
        repo_id=repo_id,
        mode=IndexingMode.BOOTSTRAP,
    )

    print(f"Bootstrap: {result.files_processed} files, {result.total_duration_seconds / 60:.1f} minutes")
    print("Warm-up completed: ready for Fast mode")


# Stub functions (실제는 DI Container에서 주입)
def get_orchestrator():
    """DI Container에서 orchestrator 가져오기."""
    raise NotImplementedError("Use DI container")


def get_graph_store():
    """DI Container에서 graph_store 가져오기."""
    raise NotImplementedError("Use DI container")


def get_metadata_store():
    """DI Container에서 metadata_store 가져오기."""
    raise NotImplementedError("Use DI container")


def get_file_hash_store():
    """DI Container에서 file_hash_store 가져오기."""
    raise NotImplementedError("Use DI container")


def get_mode_controller():
    """DI Container에서 mode_controller 가져오기."""
    raise NotImplementedError("Use DI container")


if __name__ == "__main__":
    # 테스트 실행
    asyncio.run(example_bootstrap())
