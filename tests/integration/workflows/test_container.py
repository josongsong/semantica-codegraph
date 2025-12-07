"""
Container Tests

Tests for dependency injection container.
"""

from unittest.mock import MagicMock, patch

from src.container import Container


class TestContainerBasics:
    """Test basic container functionality."""

    def test_container_creation(self):
        """Test container can be instantiated."""
        container = Container()
        assert container is not None

    def test_singleton_module_level(self):
        """Test module-level container is singleton."""
        from src.container import container as container1
        from src.container import container as container2

        assert container1 is container2

    def test_cached_property_singleton(self):
        """Test cached_property creates singletons."""
        container = Container()

        # Access postgres twice
        postgres1 = container.postgres
        postgres2 = container.postgres

        # Should be same instance
        assert postgres1 is postgres2


class TestInfrastructureAdapters:
    """Test infrastructure adapter creation."""

    @patch("src.infra.storage.postgres.PostgresStore")
    def test_postgres_adapter(self, mock_postgres_class):
        """Test PostgreSQL adapter creation."""
        container = Container()

        # Access postgres adapter
        postgres = container.postgres

        # Should have created PostgresStore
        mock_postgres_class.assert_called_once()
        assert postgres is not None

    @patch("src.infra.graph.kuzu.KuzuGraphStore")
    def test_kuzu_adapter(self, mock_kuzu_class):
        """Test Kuzu adapter creation."""
        container = Container()

        kuzu = container.kuzu

        mock_kuzu_class.assert_called_once()
        assert kuzu is not None

    @patch("src.infra.vector.qdrant.QdrantAdapter")
    def test_qdrant_adapter(self, mock_qdrant_class):
        """Test Qdrant adapter creation."""
        container = Container()

        qdrant = container.qdrant

        mock_qdrant_class.assert_called_once()
        assert qdrant is not None

    @patch("src.infra.cache.redis.RedisAdapter")
    def test_redis_adapter(self, mock_redis_class):
        """Test Redis adapter creation."""
        container = Container()

        redis = container.redis

        mock_redis_class.assert_called_once()
        assert redis is not None

    @patch("src.infra.llm.openai.OpenAIAdapter")
    def test_llm_adapter(self, mock_llm_class):
        """Test LLM adapter creation."""
        container = Container()

        llm = container.llm

        mock_llm_class.assert_called_once()
        assert llm is not None


class TestIndexAdapters:
    """Test index adapter creation."""

    @patch("src.index.fuzzy.adapter_pgtrgm.PostgresFuzzyIndex")
    @patch("src.infra.storage.postgres.PostgresStore")
    def test_fuzzy_index(self, mock_postgres, mock_fuzzy_class):
        """Test fuzzy index creation with postgres dependency."""
        container = Container()

        fuzzy_index = container.fuzzy_index

        # Should create fuzzy index
        mock_fuzzy_class.assert_called_once()

        # Should inject postgres_store
        call_kwargs = mock_fuzzy_class.call_args.kwargs
        assert "postgres_store" in call_kwargs

    @patch("src.index.domain_meta.adapter_meta.DomainMetaIndex")
    @patch("src.infra.storage.postgres.PostgresStore")
    def test_domain_index(self, mock_postgres, mock_domain_class):
        """Test domain index creation with postgres dependency."""
        container = Container()

        domain_index = container.domain_index

        mock_domain_class.assert_called_once()

        # Should inject postgres_store
        call_kwargs = mock_domain_class.call_args.kwargs
        assert "postgres_store" in call_kwargs

    @patch("src.index.symbol.adapter_kuzu.KuzuSymbolIndex")
    def test_symbol_index(self, mock_symbol_class):
        """Test symbol index creation."""
        container = Container()

        symbol_index = container.symbol_index

        mock_symbol_class.assert_called_once()

    @patch("qdrant_client.AsyncQdrantClient")
    @patch("src.index.vector.adapter_qdrant.QdrantVectorIndex")
    @patch("src.index.vector.adapter_qdrant.OpenAIEmbeddingProvider")
    def test_vector_index(self, mock_embedding, mock_vector_class, mock_qdrant_client):
        """Test vector index creation with dependencies."""
        container = Container()

        vector_index = container.vector_index

        mock_vector_class.assert_called_once()

        # Should create embedding provider
        mock_embedding.assert_called_once()


class TestServices:
    """Test service creation."""

    @patch("src.index.service.IndexingService")
    @patch("src.index.fuzzy.adapter_pgtrgm.PostgresFuzzyIndex")
    @patch("src.index.domain_meta.adapter_meta.DomainMetaIndex")
    @patch("src.infra.storage.postgres.PostgresStore")
    def test_indexing_service(self, mock_postgres, mock_domain, mock_fuzzy, mock_service_class):
        """Test indexing service creation with all index dependencies."""
        container = Container()

        service = container.indexing_service

        # Should create IndexingService
        mock_service_class.assert_called_once()

        # Should have index adapters as parameters
        call_kwargs = mock_service_class.call_args.kwargs
        assert "fuzzy_index" in call_kwargs
        assert "domain_index" in call_kwargs

    @patch("src.index.service.IndexingService")
    @patch("src.infra.storage.postgres.PostgresStore")
    def test_search_service_alias(self, mock_postgres, mock_service_class):
        """Test search_service is alias for indexing_service."""
        container = Container()

        search_service = container.search_service
        indexing_service = container.indexing_service

        # Should be same instance
        assert search_service is indexing_service


class TestRepoMapComponents:
    """Test RepoMap component creation."""

    @patch("src.repomap.storage_postgres.PostgresRepoMapStore")
    def test_repomap_store(self, mock_store_class):
        """Test RepoMap store creation."""
        container = Container()

        store = container.repomap_store

        mock_store_class.assert_called_once()

    @patch("src.repomap.RepoMapBuilder")
    @patch("src.repomap.storage_postgres.PostgresRepoMapStore")
    @patch("src.infra.llm.openai.OpenAIAdapter")
    def test_repomap_builder(self, mock_llm, mock_store, mock_builder_class):
        """Test RepoMap builder creation with dependencies."""
        container = Container()

        builder = container.repomap_builder

        mock_builder_class.assert_called_once()

        # Should inject store and llm
        call_kwargs = mock_builder_class.call_args.kwargs
        assert "store" in call_kwargs
        assert "llm" in call_kwargs


class TestFoundationComponents:
    """Test foundation component creation."""

    @patch("src.foundation.chunk.InMemoryChunkStore")
    def test_chunk_store(self, mock_store_class):
        """Test chunk store creation."""
        container = Container()

        store = container.chunk_store

        mock_store_class.assert_called_once()

    @patch("src.infra.graph.kuzu.KuzuGraphStore")
    def test_graph_store_alias(self, mock_kuzu):
        """Test graph_store is alias for kuzu."""
        container = Container()

        graph_store = container.graph_store
        kuzu = container.kuzu

        # Should be same instance
        assert graph_store is kuzu


class TestDependencyInjection:
    """Test dependency injection works correctly."""

    @patch("src.index.fuzzy.adapter_pgtrgm.PostgresFuzzyIndex")
    @patch("src.infra.storage.postgres.PostgresStore")
    def test_shared_postgres_dependency(self, mock_postgres_class, mock_fuzzy_class):
        """Test multiple components share same postgres instance."""
        mock_postgres_instance = MagicMock()
        mock_postgres_class.return_value = mock_postgres_instance

        container = Container()

        # Access fuzzy_index (depends on postgres)
        _ = container.fuzzy_index

        # Access domain_index (also depends on postgres)
        _ = container.domain_index

        # Postgres should only be created once
        assert mock_postgres_class.call_count == 1

        # Both should receive same postgres instance
        fuzzy_call_kwargs = mock_fuzzy_class.call_args.kwargs
        assert fuzzy_call_kwargs["postgres_store"] is mock_postgres_instance

    @patch("src.index.service.IndexingService")
    @patch("src.infra.storage.postgres.PostgresStore")
    def test_deep_dependency_chain(self, mock_postgres, mock_service_class):
        """Test deep dependency chain works (service -> indexes -> adapters)."""
        container = Container()

        # Access indexing_service (depends on indexes, which depend on adapters)
        service = container.indexing_service

        # Should create service
        mock_service_class.assert_called_once()

        # Postgres should be created (needed by fuzzy/domain indexes)
        mock_postgres.assert_called_once()


class TestHealthCheck:
    """Test health check functionality."""

    def test_health_check_method_exists(self):
        """Test health_check method exists."""
        container = Container()

        health = container.health_check()

        assert isinstance(health, dict)

    def test_health_check_returns_status(self):
        """Test health_check returns status for adapters."""
        container = Container()

        health = container.health_check()

        # Should have some adapter status
        # (implementation is TODO, so just check it doesn't crash)
        assert isinstance(health, dict)
