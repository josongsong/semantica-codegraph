# codegraph-search

Code search and retrieval pipeline for Semantica.

## Features

- **Intent Analysis**: Query understanding and intent classification
- **Multi-index Search**: Lexical, Vector, Symbol, Graph search
- **Fusion Engine**: Weighted result fusion (RRF)
- **Context Builder**: LLM-optimized context generation
- **Hybrid Reranking**: Cross-encoder, BGE, LLM rerankers

## Architecture

```
codegraph_search/
├── domain/           # Domain models (SearchQuery, SearchResult)
├── ports/            # Interfaces (SearchEnginePort, RerankerPort)
├── infrastructure/   # Implementations
│   ├── intent/       # Intent analysis
│   ├── fusion/       # Result fusion
│   ├── context_builder/  # Context building
│   └── hybrid/       # Reranking
└── adapters/         # External integrations
```

## Usage

```python
from codegraph_search.infrastructure.service import RetrieverService

service = RetrieverService(...)
results = await service.search(query="authentication logic")
```
