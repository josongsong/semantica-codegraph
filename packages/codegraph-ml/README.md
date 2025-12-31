# codegraph-ml

Machine learning batch jobs for Semantica.

## Features

### Adaptive Embeddings (LoRA)

Repo-specific embedding fine-tuning using LoRA (Low-Rank Adaptation).

**Pipeline:**
1. **Collect feedback** - User clicks/selections logged
2. **Train LoRA** - Batch training when min samples reached (default: 100)
3. **Apply weights** - Adapted embeddings for improved search

**Usage:**

```python
from codegraph_ml.adaptive_embeddings import (
    AdaptationCollector,
    LoRATrainer,
    AdaptiveEmbeddingModel,
)

# 1. Collect user feedback
collector = AdaptationCollector(min_samples_for_adaptation=100)
collector.log_user_selection(
    repo_id="myrepo",
    query="authentication",
    shown_results=results,
    selected_chunk_id="chunk123",
    selected_rank=3,
)

# 2. Train when ready
if collector.is_ready_for_adaptation("myrepo"):
    examples = collector.get_examples("myrepo")
    trainer = LoRATrainer()
    adaptation = trainer.train("myrepo", examples, base_model)

# 3. Use adapted embeddings
model = AdaptiveEmbeddingModel(base_model, adaptation)
embedding = model.embed("new query", repo_id="myrepo")
```

## Installation

```bash
# Base package
pip install -e packages/codegraph-ml

# With ML dependencies (for training workers)
pip install -e "packages/codegraph-ml[ml]"
```

## Architecture

- **Offline batch processing** - Separate from online search
- **Independent deployment** - ML workers run separately
- **Optional dependencies** - PyTorch/transformers only for training

```
codegraph_ml/
└── adaptive_embeddings/
    ├── collector.py        # Feedback collection
    ├── lora_trainer.py     # LoRA training
    ├── adaptive_model.py   # Adapted embeddings
    └── models.py           # Data models
```

