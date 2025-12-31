"""Exact Index - O(1) Hash Lookup.

RFC-034: Exact index implementation.

Supports:
    - ExactTypeCallIndex: (base_type, call) → entities
    - ExactCallIndex: call → entities
"""

from collections import defaultdict

from trcr.types.entity import Entity


class ExactTypeCallIndex:
    """Exact (type, call) hash index.

    RFC-034: O(1) lookup for exact type + call combinations.

    Usage:
        >>> index = ExactTypeCallIndex()
        >>> index.add(entity)  # cursor.execute()
        >>> entities = index.query(("sqlite3.Cursor", "execute"))
    """

    def __init__(self) -> None:
        """Initialize index."""
        self._index: dict[tuple[str, str], list[Entity]] = defaultdict(list)
        self._size = 0

    def add(self, entity: Entity) -> None:
        """Add entity to index.

        Only indexes call entities with base_type.

        Args:
            entity: Entity to index
        """
        if entity.kind != "call":
            return

        if not entity.base_type or not entity.call:
            return

        key = (entity.base_type, entity.call)
        self._index[key].append(entity)
        self._size += 1

    def query(self, key: tuple[str, str]) -> list[Entity]:
        """Query by (base_type, call).

        Args:
            key: (base_type, call) tuple

        Returns:
            List of entities (empty if no match)
        """
        return self._index.get(key, [])

    def size(self) -> int:
        """Get index size.

        Returns:
            Number of indexed entities
        """
        return self._size

    def keys(self) -> list[tuple[str, str]]:
        """Get all indexed keys.

        Returns:
            List of (base_type, call) keys
        """
        return list(self._index.keys())

    def as_dict(self) -> dict[tuple[str, str], list[Entity]]:
        """Get index as dictionary.

        Returns:
            Copy of internal index
        """
        return dict(self._index)


class ExactCallIndex:
    """Exact call name hash index.

    RFC-034: O(1) lookup for call name only.

    Indexes both simple call names AND qualified calls:
        - Simple: "execute", "input", "get"
        - Qualified: "conn.execute", "requests.get", "os.system"

    Usage:
        >>> index = ExactCallIndex()
        >>> index.add(entity)  # input()
        >>> entities = index.query("input")
        >>> entities = index.query("conn.execute")  # Also works!
    """

    def __init__(self) -> None:
        """Initialize index."""
        self._index: dict[str, list[Entity]] = defaultdict(list)
        self._size = 0

    def add(self, entity: Entity) -> None:
        """Add entity to index.

        Indexes call entities by:
            1. Simple call name (e.g., "execute")
            2. Qualified call name (e.g., "sqlite3.Cursor.execute")

        This enables matching rules like:
            - call: execute      → matches entity.call
            - call: conn.execute → matches entity.qualified_call

        Args:
            entity: Entity to index
        """
        if entity.kind != "call":
            return

        if not entity.call:
            return

        # Index by simple call name
        self._index[entity.call].append(entity)
        self._size += 1

        # Also index by qualified_call if different from simple call
        if entity.qualified_call and entity.qualified_call != entity.call:
            self._index[entity.qualified_call].append(entity)

    def query(self, call: str) -> list[Entity]:
        """Query by call name.

        Args:
            call: Call name

        Returns:
            List of entities (empty if no match)
        """
        return self._index.get(call, [])

    def size(self) -> int:
        """Get index size.

        Returns:
            Number of indexed entities
        """
        return self._size

    def keys(self) -> list[str]:
        """Get all indexed call names.

        Returns:
            List of call names
        """
        return list(self._index.keys())

    def as_dict(self) -> dict[str, list[Entity]]:
        """Get index as dictionary.

        Returns:
            Copy of internal index
        """
        return dict(self._index)


class ExactTypeReadIndex:
    """Exact (type, read) hash index for property reads.

    RFC-034: O(1) lookup for property reads.

    Usage:
        >>> index = ExactTypeReadIndex()
        >>> index.add(entity)  # request.GET
        >>> entities = index.query(("flask.Request", "GET"))
    """

    def __init__(self) -> None:
        """Initialize index."""
        self._index: dict[tuple[str, str], list[Entity]] = defaultdict(list)
        self._size = 0

    def add(self, entity: Entity) -> None:
        """Add entity to index.

        Only indexes read entities with base_type.

        Args:
            entity: Entity to index
        """
        if entity.kind != "read":
            return

        if not entity.base_type or not entity.read:
            return

        key = (entity.base_type, entity.read)
        self._index[key].append(entity)
        self._size += 1

    def query(self, key: tuple[str, str]) -> list[Entity]:
        """Query by (base_type, read).

        Args:
            key: (base_type, read) tuple

        Returns:
            List of entities (empty if no match)
        """
        return self._index.get(key, [])

    def size(self) -> int:
        """Get index size.

        Returns:
            Number of indexed entities
        """
        return self._size

    def keys(self) -> list[tuple[str, str]]:
        """Get all indexed keys.

        Returns:
            List of (base_type, read) keys
        """
        return list(self._index.keys())
