# Retriever V3 (S-HMR-v3) User Guide

## Overview

Semantica Hybrid Multi-Index Retriever v3 (S-HMR-v3) is a SOTA code search retriever that combines:

- **Multi-label Intent Classification**: Soft probability distribution over intent types
- **Weighted RRF**: Rank-based normalization with strategy-specific k values
- **Consensus Engine**: Multi-index co-occurrence boosting
- **Graph-aware Routing**: Flow trace and symbol navigation priority
- **LTR-ready Features**: Complete feature vectors for Learning-to-Rank models

## Architecture

```
Query
  ↓
[Intent Classifier] → Multi-label probability distribution
  ↓
[Multi-strategy Retrieval] → Vector, Lexical, Symbol, Graph
  ↓
[RRF Normalizer] → Rank-based normalization with intent weights
  ↓
[Consensus Engine] → Multi-index agreement boosting
  ↓
[Ranking Layer] → Final sorted results
  ↓
[Explainability] → Human-readable explanations
```

## Quick Start

### Basic Usage

```python
from src.retriever.v3 import RetrieverV3Service, RetrieverV3Config
from src.index.common.documents import SearchHit

# Initialize service
config = RetrieverV3Config()
service = RetrieverV3Service(config=config)

# Prepare search hits from multiple strategies
hits_by_strategy = {
    "vector": [...],
    "lexical": [...],
    "symbol": [...],
    "graph": [...],
}

# Execute retrieval
results, intent = service.retrieve(
    query="login authentication",
    hits_by_strategy=hits_by_strategy,
)

# Access results
for result in results:
    print(f"{result.chunk_id}: {result.final_score:.4f}")
```

## Intent Classification

### Multi-label Intents

v3 supports soft multi-label classification:

- **Symbol** (0-1): Symbol navigation (find class/function)
- **Flow** (0-1): Flow trace (call chain, data flow)
- **Concept** (0-1): Concept search (how does X work)
- **Code** (0-1): Code search (example implementation)
- **Balanced** (0-1): Balanced search (default)

Probabilities sum to 1.0.

### Examples

```python
# Short identifier → high symbol probability
query = "authenticate"
# → symbol=0.45, flow=0.10, concept=0.15, code=0.15, balanced=0.15

# Question → high concept probability
query = "how does authentication work?"
# → symbol=0.10, flow=0.15, concept=0.50, code=0.10, balanced=0.15

# Trace keyword → high flow probability
query = "trace call from login to database"
# → symbol=0.15, flow=0.55, concept=0.10, code=0.10, balanced=0.10
```

## Weight Profiles

Each intent type has a different weight profile for strategies:

| Intent | Vector | Lexical | Symbol | Graph |
|--------|--------|---------|--------|-------|
| Code | 0.5 | 0.3 | 0.1 | 0.1 |
| Symbol | 0.2 | 0.2 | 0.5 | 0.1 |
| Flow | 0.2 | 0.1 | 0.2 | 0.5 |
| Concept | 0.7 | 0.2 | 0.05 | 0.05 |
| Balanced | 0.4 | 0.3 | 0.2 | 0.1 |

Final weights are **linear combination** based on intent probabilities.

## RRF Normalization

### Formula

```
RRF(d) = 1 / (k + rank(d))
```

### Strategy-specific k values

- **Vector**: k=70
- **Lexical**: k=70
- **Symbol**: k=50 (more aggressive for precise matches)
- **Graph**: k=50 (more aggressive for structural matches)

### Weighted Combination

```
base_score(d) = Σ (W_strategy * RRF_strategy(d))
```

Where `W_strategy` comes from intent-based weights.

## Consensus Boosting

### Formula

```
consensus_raw = 1 + β * (sqrt(M) - 1)    # M = number of strategies
consensus_capped = min(1.5, consensus_raw)   # Cap at 1.5x
quality_factor = 1 / (1 + avg_rank / 10)
consensus_factor = consensus_capped * (0.5 + 0.5 * quality_factor)

final_score(d) = base_score(d) * consensus_factor
```

### Parameters

- **β (beta)**: 0.3 (consensus boost strength)
- **max_factor**: 1.5 (maximum boost multiplier)
- **quality_q0**: 10.0 (quality normalization factor)

### Example

Chunk appears in **4 strategies** with ranks `[0, 1, 0, 2]`:

```
M = 4
avg_rank = 0.75
consensus_raw = 1 + 0.3 * (2 - 1) = 1.3
quality_factor = 1 / (1 + 0.75/10) = 0.93
consensus_factor = 1.3 * (0.5 + 0.5 * 0.93) = 1.26x
```

## Intent-based Cutoff

Different intents apply different top-K cutoffs:

- **Symbol**: k=20 (precision-focused)
- **Flow**: k=15 (very precise)
- **Concept**: k=60 (recall-focused)
- **Code**: k=40 (balanced)
- **Balanced**: k=40 (default)

## Feature Vectors (LTR-ready)

Each result includes a complete feature vector with 18 numeric features:

### Features

1-4. **Ranks**: rank_vec, rank_lex, rank_sym, rank_graph
5-8. **RRF Scores**: rrf_vec, rrf_lex, rrf_sym, rrf_graph
9-12. **Weights**: weight_vec, weight_lex, weight_sym, weight_graph
13-16. **Consensus**: num_strategies, best_rank, avg_rank, consensus_factor
17-18. **Metadata**: chunk_size, file_depth

### Usage

```python
# Extract features for LTR training
chunk_ids, feature_arrays = service.get_feature_vectors(results)

# feature_arrays[i] is a list of 18 floats
# Use with LightGBM, XGBoost, LambdaMART, etc.
```

## Explainability

When `enable_explainability=True`, each result includes a human-readable explanation:

```python
result.explanation
# "Intent: symbol (0.45) | Found in 4 strategies (vector, lexical, symbol, graph).
#  Best rank: 0, Avg rank: 0.8. Quality factor: 0.926, Consensus boost: 1.26x.
#  Contributions: vector=0.0056 (rrf=0.0143, w=0.39), ... | Final score: 0.0123"
```

## Query Expansion

When `enable_query_expansion=True`, the classifier extracts:

```python
intent, expansions = classifier.classify_with_expansion(query)

# expansions = {
#   "symbols": ["AuthHandler", "LoginManager"],
#   "file_paths": ["auth.py", "login.ts"],
#   "modules": ["auth.handlers", "utils.db"]
# }
```

Use expansions for query rewriting, FQN resolution, or multi-hop search.

## Configuration

### Full Configuration

```python
from src.retriever.v3 import RetrieverV3Config, RRFConfig, ConsensusConfig

config = RetrieverV3Config(
    # RRF parameters
    rrf=RRFConfig(
        k_vec=70,
        k_lex=70,
        k_sym=50,
        k_graph=50,
    ),

    # Consensus parameters
    consensus=ConsensusConfig(
        beta=0.3,
        max_factor=1.5,
        quality_q0=10.0,
    ),

    # Features
    enable_query_expansion=True,
    enable_explainability=True,
    enable_cache=True,
    cache_ttl=300,
)

service = RetrieverV3Service(config=config)
```

## Advanced Usage

### Custom Weight Profiles

```python
from src.retriever.v3.config import IntentWeights, WeightProfile

custom_weights = IntentWeights(
    symbol=WeightProfile(vec=0.1, lex=0.2, sym=0.6, graph=0.1),
    # ... other intents
)

config = RetrieverV3Config(intent_weights=custom_weights)
```

### Caching

```python
from src.infra.cache.redis import RedisClient

# Initialize cache
cache_client = RedisClient(...)

# Create service with cache
service = RetrieverV3Service(
    config=config,
    cache_client=cache_client,
)

# Cache is automatically used
results, intent = service.retrieve(
    query=query,
    hits_by_strategy=hits,
    enable_cache=True,  # Enable per-query
)
```

## Performance

### Benchmarks

Tested on Python codebase with 10K chunks:

- **Intent Classification**: ~1ms
- **RRF Normalization**: ~2ms (for 200 hits)
- **Consensus Boosting**: ~1ms
- **Total Pipeline**: ~5ms (excluding index queries)

### Optimization Tips

1. **Parallel Index Queries**: Run vector/lexical/symbol/graph queries in parallel
2. **Limit Hits**: Pass top-50 per strategy to reduce fusion cost
3. **Cache**: Enable caching for repeated queries
4. **Cutoff**: Use intent-based cutoff to reduce downstream processing

## Comparison: v2 vs v3

| Feature | v2 | v3 |
|---------|----|----|
| Intent Classification | Single-label | Multi-label (soft) |
| Normalization | Score-based | Rank-based (RRF) |
| Consensus | Basic | Quality-aware |
| Graph Priority | No | Yes (flow intent) |
| LTR Support | Partial | Full feature schema |
| Explainability | No | Yes |
| Query Expansion | No | Yes |

## Best Practices

1. **Always provide metadata**: Include chunk_size, file_path, symbol_type for better features
2. **Use all strategies**: Even if some return few hits, consensus benefits from multi-index agreement
3. **Enable explainability in dev**: Helps debug ranking issues
4. **Extract features for LTR**: Train custom rankers with your ground truth
5. **Monitor intent distribution**: Adjust weight profiles if needed

## Troubleshooting

### Low scores

- Check if hits are coming from multiple strategies
- Verify metadata is populated
- Enable explainability to see contribution breakdown

### Wrong intent classification

- Review query patterns in `IntentClassifierV3`
- Consider fine-tuning weight profiles
- Use query expansion to extract entities

### Poor consensus boost

- Ensure strategies are diverse (not all returning same chunks)
- Check average rank values (high avg_rank reduces boost)
- Verify beta parameter (default 0.3)

## References

- RFC: `_command_doc/C.리트리버/RFC_S-HMR-v3.md`
- Source: `src/retriever/v3/`
- Tests: `tests/retriever/test_v3_*.py`
- Example: `examples/retriever_v3_example.py`

## Support

For issues or questions:
- Check test cases in `tests/retriever/test_v3_integration.py`
- Review example usage in `examples/retriever_v3_example.py`
- Consult RFC for algorithm details
