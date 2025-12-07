"""
Tests for RepoMap LLM Summarizer.
"""

import pytest
from src.repomap.models import RepoMapMetrics, RepoMapNode
from src.repomap.summarizer import (
    CostController,
    InMemorySummaryCache,
    LLMSummarizer,
    SummaryCostConfig,
    SummaryPromptTemplate,
)
from tests.fakes.fake_llm import FakeLLM


@pytest.fixture
def sample_nodes():
    """Create sample RepoMap nodes for testing."""
    return [
        RepoMapNode(
            id="node:1",
            repo_id="test",
            snapshot_id="main",
            kind="function",
            name="process_data",
            fqn="module.process_data",
            chunk_ids=["chunk:1"],
            graph_node_ids=["func:1"],
            metrics=RepoMapMetrics(importance=0.8, loc=50),
        ),
        RepoMapNode(
            id="node:2",
            repo_id="test",
            snapshot_id="main",
            kind="function",
            name="helper_func",
            fqn="module.helper_func",
            chunk_ids=["chunk:2"],
            graph_node_ids=["func:2"],
            metrics=RepoMapMetrics(importance=0.3, loc=20),
        ),
        RepoMapNode(
            id="node:3",
            repo_id="test",
            snapshot_id="main",
            kind="function",
            name="main",
            fqn="module.main",
            chunk_ids=["chunk:3"],
            graph_node_ids=["func:3"],
            metrics=RepoMapMetrics(importance=0.9, loc=30),
            is_entrypoint=True,
        ),
    ]


def test_summary_cache_basic():
    """Test basic cache operations."""
    cache = InMemorySummaryCache()

    # Initially empty
    assert cache.get("hash1") is None

    # Set and get
    cache.set("hash1", "Summary for hash1")
    assert cache.get("hash1") == "Summary for hash1"

    # Multiple entries
    cache.set("hash2", "Summary for hash2")
    assert cache.size() == 2

    # Clear
    cache.clear()
    assert cache.size() == 0
    assert cache.get("hash1") is None


def test_cost_controller_select_nodes(sample_nodes):
    """Test cost controller selects nodes by importance."""
    config = SummaryCostConfig(
        min_importance_threshold=0.5,
        max_tokens_per_snapshot=10000,
    )
    controller = CostController(config)

    # Select nodes (should pick nodes with importance >= 0.5)
    selected = controller.select_nodes_to_summarize(sample_nodes, cached_hashes=set())

    # Should select node:1 (0.8) and node:3 (0.9)
    # node:2 (0.3) is below threshold
    assert len(selected) == 2
    assert selected[0].id == "node:3"  # Highest importance first
    assert selected[1].id == "node:1"


def test_cost_controller_budget_limit(sample_nodes):
    """Test cost controller respects budget limits."""
    # Very low budget
    config = SummaryCostConfig(
        min_importance_threshold=0.0,
        max_tokens_per_snapshot=500,  # Very low
        estimate_output_tokens=150,
    )
    controller = CostController(config)

    selected = controller.select_nodes_to_summarize(sample_nodes, cached_hashes=set())

    # Should only select 1-2 nodes due to budget
    assert len(selected) < len(sample_nodes)


def test_cost_controller_cached_nodes(sample_nodes):
    """Test cost controller skips cached nodes."""
    config = SummaryCostConfig(min_importance_threshold=0.0)
    controller = CostController(config)

    # Mark node:3 as cached
    cached = {"chunk:3"}

    selected = controller.select_nodes_to_summarize(sample_nodes, cached_hashes=cached)

    # Should not include node:3
    selected_ids = {n.id for n in selected}
    assert "node:3" not in selected_ids


def test_prompt_template_function():
    """Test function prompt template."""
    template = SummaryPromptTemplate.get_template("function")
    assert "function" in template.lower()
    assert "{fqn}" in template
    assert "{code}" in template


def test_prompt_template_class():
    """Test class prompt template."""
    template = SummaryPromptTemplate.get_template("class")
    assert "class" in template.lower()
    assert "{fqn}" in template


def test_prompt_template_default():
    """Test default template for unknown kinds."""
    template = SummaryPromptTemplate.get_template("unknown_kind")
    assert "{kind}" in template
    assert "{fqn}" in template


@pytest.mark.asyncio
async def test_llm_summarizer_basic(sample_nodes):
    """Test basic summarization flow."""
    # Setup fake dependencies
    fake_llm = FakeLLM()
    cache = InMemorySummaryCache()
    config = SummaryCostConfig(min_importance_threshold=0.0)
    controller = CostController(config)

    # Fake chunk store
    class FakeChunkStore:
        def get_chunk(self, chunk_id):
            # Return a simple fake chunk
            class FakeChunk:
                file_path = "test.py"
                start_line = 1
                end_line = 10
                language = "python"
                content_hash = f"hash_{chunk_id}"

            return FakeChunk()

    chunk_store = FakeChunkStore()

    # Create summarizer
    summarizer = LLMSummarizer(fake_llm, cache, controller, chunk_store)

    # Summarize nodes
    summaries = await summarizer.summarize_nodes(sample_nodes)

    # Check summaries generated
    assert len(summaries) > 0
    for node_id, summary in summaries.items():
        assert isinstance(summary, str)
        assert len(summary) > 0


@pytest.mark.asyncio
async def test_llm_summarizer_caching(sample_nodes):
    """Test summary caching works."""
    fake_llm = FakeLLM()
    cache = InMemorySummaryCache()
    config = SummaryCostConfig(min_importance_threshold=0.0)
    controller = CostController(config)

    class FakeChunkStore:
        def get_chunk(self, chunk_id):
            class FakeChunk:
                file_path = "test.py"
                start_line = 1
                end_line = 10
                language = "python"
                content_hash = "same_hash"  # Same hash for all

            return FakeChunk()

    chunk_store = FakeChunkStore()

    # Pre-populate cache
    cache.set("same_hash", "Cached summary")

    summarizer = LLMSummarizer(fake_llm, cache, controller, chunk_store)

    # First call should use cache
    summaries = await summarizer.summarize_nodes(sample_nodes[:1])

    assert "node:1" in summaries
    assert summaries["node:1"] == "Cached summary"


@pytest.mark.asyncio
async def test_llm_summarizer_update_nodes(sample_nodes):
    """Test updating nodes with summaries."""
    fake_llm = FakeLLM()
    cache = InMemorySummaryCache()
    config = SummaryCostConfig(min_importance_threshold=0.0)
    controller = CostController(config)

    class FakeChunkStore:
        def get_chunk(self, chunk_id):
            class FakeChunk:
                file_path = "test.py"
                start_line = 1
                end_line = 10
                language = "python"
                content_hash = f"hash_{chunk_id}"

            return FakeChunk()

    chunk_store = FakeChunkStore()

    summarizer = LLMSummarizer(fake_llm, cache, controller, chunk_store)

    # Generate summaries
    summaries = await summarizer.summarize_nodes(sample_nodes)

    # Update nodes
    summarizer.update_node_summaries(sample_nodes, summaries)

    # Check nodes were updated
    for node in sample_nodes:
        if node.id in summaries:
            assert node.summary_body is not None
            assert node.summary_title is not None
