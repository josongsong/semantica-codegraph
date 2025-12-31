"""메타데이터 관리 인프라."""

from .indexing_metadata_store import (
    InMemoryFileHashStore,
    InMemoryIndexingMetadataStore,
    PostgresFileHashStore,
    PostgresIndexingMetadataStore,
)
from .schema_version import (
    CURRENT_INDEX_VERSION,
    CURRENT_SCHEMA_VERSION,
    MetadataStore,
    SchemaVersionManager,
    VersionInfo,
)

__all__ = [
    "SchemaVersionManager",
    "VersionInfo",
    "MetadataStore",
    "PostgresIndexingMetadataStore",
    "InMemoryIndexingMetadataStore",
    "PostgresFileHashStore",
    "InMemoryFileHashStore",
    "CURRENT_SCHEMA_VERSION",
    "CURRENT_INDEX_VERSION",
]
