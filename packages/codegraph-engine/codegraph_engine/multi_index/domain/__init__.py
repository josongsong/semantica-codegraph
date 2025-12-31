"""Multi Index Domain"""

from .models import DeleteResult, IndexType, UpsertResult
from .ports import (
    DeletableIndex,
    GraphStoreProtocol,
    IndexableIndex,
    IndexPort,
    PostgresStoreProtocol,
    SearchableIndex,
    UpsertableIndex,
)

__all__ = [
    # Models
    "DeleteResult",
    "IndexType",
    "UpsertResult",
    # Index Protocols
    "IndexPort",
    "SearchableIndex",
    "IndexableIndex",
    "UpsertableIndex",
    "DeletableIndex",
    # Store Protocols
    "PostgresStoreProtocol",
    "GraphStoreProtocol",
]
