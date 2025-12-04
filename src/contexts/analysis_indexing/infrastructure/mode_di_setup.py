"""모드 시스템 DI 설정."""

from src.contexts.analysis_indexing.infrastructure.background_scheduler import BackgroundScheduler
from src.contexts.analysis_indexing.infrastructure.change_detector import ChangeDetector
from src.contexts.analysis_indexing.infrastructure.mode_controller import ModeController
from src.contexts.analysis_indexing.infrastructure.mode_manager import ModeManager
from src.contexts.analysis_indexing.infrastructure.scope_expander import ScopeExpander
from src.infra.metadata import PostgresFileHashStore, SchemaVersionManager
from src.infra.observability import get_logger

logger = get_logger(__name__)


def setup_mode_system(container):
    """
    DI Container에 모드 시스템 컴포넌트 등록.

    Args:
        container: DI Container 인스턴스

    Usage:
        from src.container import Container
        container = Container()
        setup_mode_system(container)
    """
    logger.info("Setting up mode system in DI container")

    # 1. FileHashStore (PostgreSQL 영속화)
    file_hash_store = PostgresFileHashStore(db_store=container.postgres)
    container.register("file_hash_store", file_hash_store)

    # 2. MetadataStore (PostgreSQL 영속화)
    metadata_store = container.indexing_metadata_store
    container.register("metadata_store", metadata_store)

    # 3. ChangeDetector
    change_detector = ChangeDetector(
        git_helper=None,  # Runtime에 생성
        file_hash_store=file_hash_store,
    )
    container.register("change_detector", change_detector)

    # 4. ScopeExpander
    graph_store = container.get("graph_store")
    scope_expander = ScopeExpander(graph_store=graph_store)
    container.register("scope_expander", scope_expander)

    # 5. ModeManager
    mode_manager = ModeManager(
        change_detector=change_detector,
        scope_expander=scope_expander,
        metadata_store=metadata_store,
    )
    container.register("mode_manager", mode_manager)

    # 6. SchemaVersionManager
    schema_version_manager = SchemaVersionManager(metadata_store=metadata_store)
    container.register("schema_version_manager", schema_version_manager)

    # 7. BackgroundScheduler
    async def indexing_callback(repo_id: str, mode, checkpoint):
        """백그라운드 인덱싱 콜백."""
        orchestrator = container.get("orchestrator")
        await orchestrator.index_with_mode(
            repo_path=container.get("repo_path"),  # 런타임에 설정
            repo_id=repo_id,
            mode=mode,
        )

    background_scheduler = BackgroundScheduler(indexing_callback=indexing_callback)
    container.register("background_scheduler", background_scheduler)

    # 8. ModeController
    orchestrator = container.get("orchestrator")
    mode_controller = ModeController(
        orchestrator=orchestrator,
        mode_manager=mode_manager,
        schema_version_manager=schema_version_manager,
        background_scheduler=background_scheduler,
    )
    container.register("mode_controller", mode_controller)

    # 9. Orchestrator 초기화
    orchestrator.initialize_mode_system(
        metadata_store=metadata_store,
        file_hash_store=file_hash_store,
    )

    logger.info("Mode system setup completed")


async def start_background_workers(container):
    """백그라운드 워커 시작."""
    import asyncio

    scheduler = container.get("background_scheduler")
    asyncio.create_task(scheduler.start())
    logger.info("Background scheduler started")
