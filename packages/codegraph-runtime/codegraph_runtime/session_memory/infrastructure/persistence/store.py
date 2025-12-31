"""
Memory Storage Interface

Abstract storage interface for memory persistence.
Implementations can use:
- Local files (JSON, SQLite)
- PostgreSQL
- Redis
- Vector databases (Qdrant, etc.)
"""

import base64
import json
import os
import tempfile
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

from codegraph_shared.common.observability import get_logger

logger = get_logger(__name__)


class MemoryStore(ABC):
    """Abstract interface for memory storage."""

    @abstractmethod
    async def save(self, key: str, value: Any) -> None:
        """Save value with key."""
        pass

    @abstractmethod
    async def load(self, key: str) -> Any | None:
        """Load value by key."""
        pass

    @abstractmethod
    async def delete(self, key: str) -> bool:
        """Delete value by key."""
        pass

    @abstractmethod
    async def list_keys(self, prefix: str | None = None) -> list[str]:
        """List all keys, optionally filtered by prefix."""
        pass


class InMemoryStore(MemoryStore):
    """
    Simple in-memory storage (for testing/development).

    Data is lost when process ends.
    """

    def __init__(self):
        """Initialize in-memory store."""
        self._data: dict[str, Any] = {}
        logger.info("InMemoryStore initialized")

    async def save(self, key: str, value: Any) -> None:
        """Save value."""
        self._data[key] = value

    async def load(self, key: str) -> Any | None:
        """Load value."""
        return self._data.get(key)

    async def delete(self, key: str) -> bool:
        """Delete value."""
        if key in self._data:
            del self._data[key]
            return True
        return False

    async def list_keys(self, prefix: str | None = None) -> list[str]:
        """List keys."""
        if prefix:
            return [k for k in self._data.keys() if k.startswith(prefix)]
        return list(self._data.keys())


class FileStore(MemoryStore):
    """
    File-based storage using JSON.

    Suitable for:
    - Development/testing
    - Small-scale deployments
    - Local agent instances
    """

    def __init__(self, base_path: str | Path = ".memory"):
        """
        Initialize file store.

        Args:
            base_path: Directory for storing memory files
        """
        self.base_path = Path(base_path)
        self.base_path.mkdir(parents=True, exist_ok=True)
        logger.info(f"FileStore initialized: {self.base_path}")

    def _get_file_path(self, key: str) -> Path:
        """
        Get file path for key with security validation.

        Args:
            key: Storage key

        Returns:
            Safe file path

        Raises:
            ValueError: If key is invalid or path traversal detected
        """
        # Validate key is not empty
        if not key or not key.strip():
            raise ValueError("Key cannot be empty")

        # Use base64 encoding for safe filesystem names
        # This prevents path traversal and special character issues
        try:
            safe_key = base64.urlsafe_b64encode(key.encode("utf-8")).decode("ascii")
        except Exception as e:
            raise ValueError(f"Invalid key encoding: {e}") from e

        file_path = self.base_path / f"{safe_key}.json"

        # Resolve to absolute path and verify it's within base_path
        try:
            resolved_path = file_path.resolve()
            resolved_base = self.base_path.resolve()

            # Check path traversal
            if not str(resolved_path).startswith(str(resolved_base)):
                raise ValueError(f"Path traversal detected: {key}")

        except Exception as e:
            raise ValueError(f"Invalid path: {e}") from e

        return file_path

    async def save(self, key: str, value: Any) -> None:
        """
        Save value to JSON file atomically.

        Uses temporary file and atomic rename to prevent corruption.

        Args:
            key: Storage key
            value: Value to save

        Raises:
            Exception: If save fails
        """
        file_path = self._get_file_path(key)
        tmp_path = None

        try:
            # Serialize value
            serialized = self._serialize(value)
            json_str = json.dumps(serialized, indent=2)

            # Write to temporary file first (atomic operation)
            with tempfile.NamedTemporaryFile(mode="w", dir=self.base_path, delete=False, suffix=".tmp") as tmp_file:
                tmp_file.write(json_str)
                tmp_path = tmp_file.name

            # Atomic rename (POSIX guarantee)
            os.replace(tmp_path, file_path)
            tmp_path = None  # Successfully moved

            logger.debug(f"Saved: {key}")

        except Exception as e:
            logger.error(f"Failed to save {key}: {e}")
            # Cleanup temp file if it exists
            if tmp_path and os.path.exists(tmp_path):
                try:
                    os.unlink(tmp_path)
                except Exception:
                    pass
            raise

    async def load(self, key: str) -> Any | None:
        """
        Load value from JSON file.

        Args:
            key: Storage key

        Returns:
            Deserialized value or None if not found
        """
        try:
            file_path = self._get_file_path(key)
        except ValueError as e:
            logger.warning(f"Invalid key during load: {e}")
            return None

        if not file_path.exists():
            return None

        try:
            data = json.loads(file_path.read_text())
            return self._deserialize(data)
        except Exception as e:
            logger.error(f"Failed to load key: {e}")
            logger.debug(f"Load error for {key}: {e}", exc_info=True)
            return None

    async def delete(self, key: str) -> bool:
        """Delete file."""
        file_path = self._get_file_path(key)

        if file_path.exists():
            file_path.unlink()
            logger.debug(f"Deleted: {key}")
            return True
        return False

    async def list_keys(self, prefix: str | None = None) -> list[str]:
        """
        List all keys.

        Args:
            prefix: Optional prefix filter

        Returns:
            List of keys
        """
        keys = []

        for file_path in self.base_path.glob("*.json"):
            try:
                # Decode base64 key
                encoded_key = file_path.stem
                decoded_bytes = base64.urlsafe_b64decode(encoded_key.encode("ascii"))
                key = decoded_bytes.decode("utf-8")

                if prefix is None or key.startswith(prefix):
                    keys.append(key)
            except Exception as e:
                logger.warning(f"Invalid key file: {file_path.stem} ({e})")
                continue

        return keys

    def _serialize(self, value: Any, _seen: set | None = None) -> Any:
        """
        Serialize value for JSON storage with circular reference detection.

        Args:
            value: Value to serialize
            _seen: Internal set for tracking visited objects

        Returns:
            Serializable value

        Raises:
            ValueError: If circular reference detected beyond limit
        """
        if _seen is None:
            _seen = set()

        # Check for circular references
        obj_id = id(value)
        if isinstance(value, list | dict) or hasattr(value, "__dict__"):
            if obj_id in _seen:
                # Return placeholder for circular reference
                return {"__circular_ref__": type(value).__name__}

            _seen = _seen | {obj_id}  # Create new set to avoid mutation issues

        # Handle dataclasses
        if hasattr(value, "__dataclass_fields__"):
            from dataclasses import asdict

            return self._serialize(asdict(value), _seen)

        # Handle enums
        if hasattr(value, "value"):
            return value.value

        # Handle datetime
        if hasattr(value, "isoformat"):
            return value.isoformat()

        # Handle lists recursively
        if isinstance(value, list):
            return [self._serialize(item, _seen) for item in value]

        # Handle dicts recursively
        if isinstance(value, dict):
            return {k: self._serialize(v, _seen) for k, v in value.items()}

        return value

    def _deserialize(self, data: Any) -> Any:
        """Deserialize value from JSON."""
        # For now, just return the data
        # In production, would reconstruct proper objects
        return data


# ============================================================
# Factory
# ============================================================


def create_store(store_type: str = "memory", **kwargs) -> MemoryStore:
    """
    Create memory store.

    Args:
        store_type: Type of store ('memory', 'file')
        **kwargs: Store-specific configuration

    Returns:
        MemoryStore instance
    """
    if store_type == "memory":
        return InMemoryStore()

    if store_type == "file":
        base_path = kwargs.get("base_path", ".memory")
        return FileStore(base_path=base_path)

    raise ValueError(f"Unknown store type: {store_type}")
