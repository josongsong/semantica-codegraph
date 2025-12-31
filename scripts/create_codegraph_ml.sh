#!/bin/bash
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# codegraph-ml 패키지 생성 및 adaptive_embeddings 이동 스크립트
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

set -e

PROJECT_ROOT="/Users/songmin/Documents/code-jo/semantica-v2/codegraph"
OLD_PATH="$PROJECT_ROOT/packages/codegraph-search/codegraph_search/infrastructure/adaptive_embeddings"
NEW_PACKAGE="$PROJECT_ROOT/packages/codegraph-ml"
NEW_MODULE="$NEW_PACKAGE/codegraph_ml"

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "🚀 Step 1: 새 패키지 구조 생성"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

mkdir -p "$NEW_MODULE"
echo "✅ $NEW_PACKAGE 생성됨"

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "🚀 Step 2: adaptive_embeddings 이동"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

if [ -d "$OLD_PATH" ]; then
    mv "$OLD_PATH" "$NEW_MODULE/adaptive_embeddings"
    echo "✅ adaptive_embeddings 이동됨"
else
    echo "❌ $OLD_PATH 가 존재하지 않음"
    exit 1
fi

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "🚀 Step 3: pyproject.toml 생성"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

cat > "$NEW_PACKAGE/pyproject.toml" << 'PYPROJECT'
[project]
name = "codegraph-ml"
version = "0.1.0"
description = "Machine learning batch jobs for Semantica (LoRA training, model fine-tuning)"
requires-python = ">=3.10"
dependencies = [
    "codegraph-shared>=0.1.0",
    "numpy>=1.24.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=7.0",
    "pytest-asyncio>=0.21",
]

# ML dependencies (optional - only for training workers)
ml = [
    "torch>=2.0.0",
    "transformers>=4.30.0",
    "peft>=0.4.0",  # LoRA training
]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["codegraph_ml"]
PYPROJECT

echo "✅ pyproject.toml 생성됨"

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "🚀 Step 4: __init__.py 생성"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

cat > "$NEW_MODULE/__init__.py" << 'INIT'
"""
codegraph-ml

Machine learning batch jobs for Semantica.

Features:
- LoRA-based adaptive embeddings
- Model fine-tuning
- Embedding evaluation
"""

__version__ = "0.1.0"

__all__ = ["__version__"]
INIT

echo "✅ __init__.py 생성됨"

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "🚀 Step 5: import 경로 업데이트"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# 새 패키지 내부 import 업데이트
find "$NEW_MODULE" -name "*.py" -type f -exec sed -i '' \
    -e 's/from codegraph_search\.infrastructure\.adaptive_embeddings/from codegraph_ml.adaptive_embeddings/g' \
    -e 's/import codegraph_search\.infrastructure\.adaptive_embeddings/import codegraph_ml.adaptive_embeddings/g' \
    {} +

echo "✅ 내부 import 경로 업데이트됨"

# 프로젝트 전체에서 import 경로 변경
find "$PROJECT_ROOT" -path "$NEW_PACKAGE" -prune -o \
    -name "*.py" -type f -print 2>/dev/null | while read file; do
    if grep -q "codegraph_search\.infrastructure\.adaptive_embeddings" "$file" 2>/dev/null; then
        sed -i '' \
            -e 's/from codegraph_search\.infrastructure\.adaptive_embeddings/from codegraph_ml.adaptive_embeddings/g' \
            -e 's/import codegraph_search\.infrastructure\.adaptive_embeddings/import codegraph_ml.adaptive_embeddings/g' \
            "$file"
        echo "  📝 $file"
    fi
done

echo "✅ 프로젝트 전체 import 경로 업데이트됨"

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "🚀 Step 6: README 생성"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

cat > "$NEW_PACKAGE/README.md" << 'README'
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
README

echo "✅ README.md 생성됨"

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "✅ 마이그레이션 완료!"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "새 패키지 구조:"
ls -la "$NEW_PACKAGE"
echo ""
echo "파일 수:"
find "$NEW_MODULE" -name "*.py" -type f | wc -l

