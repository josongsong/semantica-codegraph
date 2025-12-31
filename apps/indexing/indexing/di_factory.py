"""
Dependency Injection Factory for Indexing

✅ Hexagonal Architecture:
- Application depends on Ports
- Factory creates Infrastructure implementations
- Wires everything together

This is the ONLY place that knows about Infrastructure classes.
"""

from pathlib import Path

from codegraph_engine.multi_index.domain.ports import IndexingMode, LexicalIndexPort


def create_lexical_index(
    index_dir: str | Path,
    chunk_store,  # ChunkStore protocol
    mode: IndexingMode = IndexingMode.BALANCED,
    batch_size: int = 100,
) -> LexicalIndexPort:
    """
    Factory: Create lexical index adapter

    ✅ This is the ONLY place that imports Infrastructure

    Args:
        index_dir: Index directory path
        chunk_store: Chunk store implementation
        mode: Performance mode
        batch_size: Batch size for indexing

    Returns:
        LexicalIndexPort implementation
    """
    # ✅ Infrastructure import is ISOLATED here
    from codegraph_engine.multi_index.infrastructure.lexical.tantivy import TantivyCodeIndex

    return TantivyCodeIndex(
        index_dir=index_dir,
        chunk_store=chunk_store,
        mode=mode,
        batch_size=batch_size,
    )
