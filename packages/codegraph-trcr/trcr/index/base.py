"""Index Protocol - RFC-034.

Base protocol for all index types.
"""

from typing import Any, Protocol

from trcr.types.entity import Entity


class Index(Protocol):
    """Index protocol for efficient entity lookup.

    RFC-034: Multi-Index Implementation.

    Different index types:
        - ExactIndex: O(1) hash lookup
        - PrefixIndex: O(log N) trie
        - SuffixIndex: O(log N) suffix trie
        - TrigramIndex: O(T) trigram inverted index
    """

    def add(self, entity: Entity) -> None:
        """Add entity to index.

        Args:
            entity: Entity to index
        """
        ...

    def query(self, key: Any) -> list[Entity]:
        """Query index for entities.

        Args:
            key: Query key (type depends on index)

        Returns:
            List of matching entities
        """
        ...

    def size(self) -> int:
        """Get index size (number of entries).

        Returns:
            Number of entries in index
        """
        ...
