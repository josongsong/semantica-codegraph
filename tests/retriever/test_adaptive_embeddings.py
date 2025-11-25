"""
Integration Tests for Repo-Adaptive Embeddings (Phase 3.5)
"""

import pytest

from src.retriever.adaptive_embeddings.adaptive_model import AdaptiveEmbeddingModel
from src.retriever.adaptive_embeddings.collector import AdaptationCollector
from src.retriever.adaptive_embeddings.lora_trainer import LoRATrainer
from src.retriever.adaptive_embeddings.models import (
    AdaptationExample,
    AdaptationStatus,
    LoRAConfig,
)


class MockEmbeddingModel:
    """Mock base embedding model for testing."""

    def embed(self, text):
        """Return mock embedding."""
        import numpy as np

        return np.random.randn(768)


def test_adaptation_collector_basic():
    """Test basic example collection."""
    collector = AdaptationCollector(min_samples_for_adaptation=10)

    # Log user selections
    for i in range(15):
        collector.log_user_selection(
            repo_id="test-repo",
            query=f"query_{i}",
            shown_results=[
                {"chunk_id": f"chunk_{j}"} for j in range(10)
            ],
            selected_chunk_id=f"chunk_{i % 10}",
            selected_rank=5,
        )

    status = collector.get_status("test-repo")

    assert isinstance(status, AdaptationStatus)
    assert status.samples_collected == 15
    assert status.is_adapted  # >= 10 samples
    assert status.samples_required == 10


def test_collector_negative_examples():
    """Test negative example collection."""
    collector = AdaptationCollector()

    shown_results = [
        {"chunk_id": "chunk_1"},
        {"chunk_id": "chunk_2"},
        {"chunk_id": "chunk_3"},
        {"chunk_id": "chunk_4"},
        {"chunk_id": "chunk_5"},
    ]

    collector.log_user_selection(
        repo_id="repo1",
        query="test query",
        shown_results=shown_results,
        selected_chunk_id="chunk_5",
        selected_rank=5,
    )

    examples = collector.get_training_examples("repo1", min_samples=1)

    assert len(examples) > 0
    example = examples[0]
    assert isinstance(example, AdaptationExample)
    assert example.positive_chunk_id == "chunk_5"
    assert len(example.negative_chunk_ids) == 4  # Ranks 1-4


def test_collector_implicit_negatives():
    """Test implicit negative logging."""
    collector = AdaptationCollector()

    shown_results = [
        {"chunk_id": f"chunk_{i}"} for i in range(5)
    ]

    collector.log_implicit_negative(
        repo_id="repo1",
        query="test query",
        shown_results=shown_results,
    )

    examples = collector.examples.get("repo1", [])
    assert len(examples) > 0
    # Implicit negatives have no positive
    assert examples[-1].positive_chunk_id == ""
    assert len(examples[-1].negative_chunk_ids) > 0


def test_collector_max_samples():
    """Test maximum sample limit."""
    collector = AdaptationCollector(
        min_samples_for_adaptation=10,
        max_samples_per_repo=20,
    )

    # Add more than max
    for i in range(30):
        collector.log_user_selection(
            repo_id="repo1",
            query=f"query_{i}",
            shown_results=[{"chunk_id": "chunk_1"}],
            selected_chunk_id="chunk_1",
            selected_rank=1,
        )

    # Should keep only most recent max_samples
    assert len(collector.examples["repo1"]) == 20


def test_lora_trainer_basic():
    """Test basic LoRA training."""
    config = LoRAConfig(
        rank=4,
        num_epochs=1,
        batch_size=2,
    )
    trainer = LoRATrainer(config)
    base_model = MockEmbeddingModel()

    # Create training examples
    examples = [
        AdaptationExample(
            query=f"query_{i}",
            positive_chunk_id=f"pos_{i}",
            negative_chunk_ids=[f"neg_{i}_1", f"neg_{i}_2"],
            repo_id="repo1",
        )
        for i in range(5)
    ]

    adaptation = trainer.train(
        repo_id="repo1",
        examples=examples,
        base_embedding_model=base_model,
    )

    assert adaptation.repo_id == "repo1"
    assert adaptation.training_samples == 5
    assert len(adaptation.lora_weights) > 0
    assert "performance_metrics" in dir(adaptation)
    assert adaptation.performance_metrics.get("accuracy") is not None


def test_lora_matrices_initialization():
    """Test LoRA matrix initialization."""
    config = LoRAConfig(rank=8, target_modules=["q_proj", "v_proj"])
    trainer = LoRATrainer(config)

    lora_weights = trainer._initialize_lora_matrices()

    # Verify A and B matrices for each module
    assert "q_proj_A" in lora_weights
    assert "q_proj_B" in lora_weights
    assert "v_proj_A" in lora_weights
    assert "v_proj_B" in lora_weights

    # Verify shapes
    assert lora_weights["q_proj_A"].shape[0] == 8  # rank
    assert lora_weights["q_proj_B"].shape[1] == 8  # rank


def test_adaptive_embedding_model():
    """Test adaptive embedding model."""
    base_model = MockEmbeddingModel()
    adaptive_model = AdaptiveEmbeddingModel(base_model)

    # Without adaptation
    import numpy as np

    emb1 = adaptive_model.embed("test text", repo_id=None)
    assert isinstance(emb1, np.ndarray)

    # Load adaptation
    from src.retriever.adaptive_embeddings.models import RepoAdaptation

    adaptation = RepoAdaptation(
        repo_id="repo1",
        lora_weights={
            "q_proj_A": np.random.randn(8, 768),
            "q_proj_B": np.random.randn(768, 8),
        },
        training_samples=100,
    )

    adaptive_model.load_adaptation(adaptation)

    # With adaptation
    emb2 = adaptive_model.embed("test text", repo_id="repo1")
    assert isinstance(emb2, np.ndarray)

    # Embeddings should be different (adapted vs base)
    assert not np.allclose(emb1, emb2)


def test_adaptive_model_without_adaptation():
    """Test that model works without adaptation."""
    base_model = MockEmbeddingModel()
    adaptive_model = AdaptiveEmbeddingModel(base_model)

    emb = adaptive_model.embed("test", repo_id="nonexistent_repo")

    import numpy as np

    assert isinstance(emb, np.ndarray)


def test_adaptive_model_info():
    """Test adaptation info retrieval."""
    base_model = MockEmbeddingModel()
    adaptive_model = AdaptiveEmbeddingModel(base_model)

    # No adaptation
    info = adaptive_model.get_adaptation_info("repo1")
    assert info is None

    # Load adaptation
    from src.retriever.adaptive_embeddings.models import RepoAdaptation

    adaptation = RepoAdaptation(
        repo_id="repo1",
        training_samples=150,
        performance_metrics={"accuracy": 0.85},
    )

    adaptive_model.load_adaptation(adaptation)

    # With adaptation
    info = adaptive_model.get_adaptation_info("repo1")
    assert info is not None
    assert info["repo_id"] == "repo1"
    assert info["training_samples"] == 150
    assert info["metrics"]["accuracy"] == 0.85


def test_is_adapted():
    """Test adaptation status check."""
    base_model = MockEmbeddingModel()
    adaptive_model = AdaptiveEmbeddingModel(base_model)

    assert not adaptive_model.is_adapted("repo1")

    from src.retriever.adaptive_embeddings.models import RepoAdaptation

    adaptation = RepoAdaptation(repo_id="repo1")
    adaptive_model.load_adaptation(adaptation)

    assert adaptive_model.is_adapted("repo1")
    assert not adaptive_model.is_adapted("repo2")


@pytest.mark.asyncio
async def test_production_adapter_integration():
    """Test OpenAI embedding adapter integration."""
    from src.retriever.adaptive_embeddings.openai_embedding_adapter import (
        OpenAIEmbeddingAdapter,
    )

    class MockOpenAIAdapter:
        """Mock OpenAI adapter."""

        async def embed(self, text):
            """Return mock embedding."""
            return [0.1] * 1536

        async def embed_batch(self, texts):
            """Return mock embeddings."""
            return [[0.1] * 1536 for _ in texts]

    mock_openai = MockOpenAIAdapter()
    adapter = OpenAIEmbeddingAdapter(mock_openai)

    # Test single embedding
    emb = await adapter.embed("test text")
    import numpy as np

    assert isinstance(emb, np.ndarray)
    assert emb.shape[0] == 1536

    # Test batch embedding
    embs = await adapter.embed_batch(["text1", "text2", "text3"])
    assert len(embs) == 3
    assert all(isinstance(e, np.ndarray) for e in embs)


@pytest.mark.asyncio
async def test_end_to_end_adaptation_flow():
    """Test complete adaptation flow from collection to inference."""
    # 1. Collect examples
    collector = AdaptationCollector(min_samples_for_adaptation=5)

    for i in range(10):
        collector.log_user_selection(
            repo_id="my-repo",
            query=f"query_{i}",
            shown_results=[{"chunk_id": f"chunk_{j}"} for j in range(5)],
            selected_chunk_id=f"chunk_{i % 5}",
            selected_rank=3,
        )

    # 2. Check status
    status = collector.get_status("my-repo")
    assert status.is_adapted
    assert status.samples_collected == 10

    # 3. Train adaptation
    examples = collector.get_training_examples("my-repo")
    assert len(examples) > 0

    base_model = MockEmbeddingModel()
    trainer = LoRATrainer(LoRAConfig(num_epochs=1))
    adaptation = trainer.train("my-repo", examples, base_model)

    assert adaptation.training_samples == len(examples)

    # 4. Load and use adaptation
    adaptive_model = AdaptiveEmbeddingModel(base_model)
    adaptive_model.load_adaptation(adaptation)

    assert adaptive_model.is_adapted("my-repo")

    # 5. Generate adapted embeddings
    emb = adaptive_model.embed("test query", repo_id="my-repo")
    import numpy as np

    assert isinstance(emb, np.ndarray)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
