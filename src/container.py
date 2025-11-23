"""
Dependency Injection Container

Semi-DI + Lazy Singleton Pattern (SOTA)

모든 의존성을 @cached_property 기반으로 Lazy Loading하며,
API/MCP/CLI/Agent는 오직 이 container에서만 의존성을 가져다 사용한다.

Rules:
- Settings: Eager loading (전역 singleton)
- Adapters/Services: Lazy loading (@cached_property)
- Core Layer: container/infra/settings import 금지
- Constructor Injection만 사용
"""

from functools import cached_property

# Settings는 eager loading (즉시 생성)
from .config import Settings

settings = Settings()


class Container:
    """
    Dependency Injection Container.

    모든 adapter와 service를 cached_property로 lazy singleton 생성.
    Thread-safe하며 최초 접근 시 한 번만 생성됨.
    """

    # ========================================================================
    # Infrastructure Layer (Adapters) - Lazy Singleton
    # ========================================================================

    @cached_property
    def qdrant(self):
        """Qdrant Vector Store (Lazy)."""
        from .infra.vector.qdrant import QdrantAdapter

        return QdrantAdapter(
            host=settings.vector_host,
            port=settings.vector_port,
        )

    @cached_property
    def kuzu(self):
        """Kùzu Graph Store (Lazy)."""
        # TODO: Implement KuzuGraphStore
        # from .infra.graph.kuzu import KuzuGraphStore
        # return KuzuGraphStore(settings)
        raise NotImplementedError("Kùzu graph store not yet implemented")

    @cached_property
    def postgres(self):
        """PostgreSQL Relational Store (Lazy)."""
        from .infra.storage.postgres import PostgresAdapter

        return PostgresAdapter(
            connection_string=settings.db_connection_string,
        )

    @cached_property
    def redis(self):
        """Redis Cache/Session Store (Lazy)."""
        # TODO: Implement RedisAdapter
        # from .infra.cache.redis import RedisAdapter
        # return RedisAdapter(
        #     host=settings.redis_host,
        #     port=settings.redis_port,
        #     password=settings.redis_password,
        #     db=settings.redis_db,
        # )
        raise NotImplementedError("Redis adapter not yet implemented")

    @cached_property
    def zoekt(self):
        """Zoekt Lexical Search (Lazy)."""
        # TODO: Implement ZoektAdapter
        # from .infra.search.zoekt import ZoektAdapter
        # return ZoektAdapter(
        #     host=settings.zoekt_host,
        #     port=settings.zoekt_port,
        # )
        raise NotImplementedError("Zoekt adapter not yet implemented")

    @cached_property
    def git(self):
        """Git Provider (Lazy)."""
        from .infra.git.git_cli import GitCLIAdapter

        return GitCLIAdapter()

    @cached_property
    def llm(self):
        """LLM Provider (Lazy)."""
        from .infra.llm.openai import OpenAIAdapter

        return OpenAIAdapter(
            api_key=settings.openai_api_key or "",
        )

    # ========================================================================
    # Backward Compatibility Aliases
    # ========================================================================

    @cached_property
    def vector_store(self):
        """Alias for qdrant (backward compatibility)."""
        return self.qdrant

    @cached_property
    def graph_store(self):
        """Alias for kuzu (backward compatibility)."""
        return self.kuzu

    @cached_property
    def relational_store(self):
        """Alias for postgres (backward compatibility)."""
        return self.postgres

    @cached_property
    def lexical_search(self):
        """Alias for zoekt (backward compatibility)."""
        return self.zoekt

    @cached_property
    def git_provider(self):
        """Alias for git (backward compatibility)."""
        return self.git

    @cached_property
    def llm_provider(self):
        """Alias for llm (backward compatibility)."""
        return self.llm

    # ========================================================================
    # Application Layer (Services) - Lazy Singleton
    # ========================================================================

    @cached_property
    def search_service(self):
        """Search Service (Lazy)."""
        from .core.services.search_service import SearchService

        return SearchService(
            vector_store=self.qdrant,
            lexical_search=self.zoekt,
            llm_provider=self.llm,
        )

    @cached_property
    def indexing_service(self):
        """Indexing Service (Lazy)."""
        from .core.services.indexing_service import IndexingService

        return IndexingService(
            vector_store=self.qdrant,
            graph_store=self.kuzu,
            relational_store=self.postgres,
            git_provider=self.git,
            llm_provider=self.llm,
            lexical_search=self.zoekt,
        )

    @cached_property
    def graph_service(self):
        """Graph Service (Lazy)."""
        from .core.services.graph_service import GraphService

        return GraphService(
            graph_store=self.kuzu,
            relational_store=self.postgres,
        )

    @cached_property
    def git_service(self):
        """Git Service (Lazy)."""
        from .core.services.git_service import GitService

        return GitService(
            git_provider=self.git,
            relational_store=self.postgres,
        )


# ========================================================================
# Global Container Instance (Singleton)
# ========================================================================
container = Container()
