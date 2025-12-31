"""
Redis Adapter Tests

Tests for Redis cache adapter.
"""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from codegraph_shared.infra.cache.redis import RedisAdapter


class TestRedisAdapterBasics:
    """Test basic RedisAdapter functionality."""

    def test_redis_adapter_creation(self):
        """Test RedisAdapter can be instantiated."""
        adapter = RedisAdapter(
            host="localhost",
            port=6379,
            db=0,
        )

        assert adapter is not None
        assert adapter.host == "localhost"
        assert adapter.port == 6379
        assert adapter.db == 0
        assert adapter.password is None
        assert adapter._client is None

    def test_redis_adapter_with_password(self):
        """Test RedisAdapter with password."""
        adapter = RedisAdapter(
            host="localhost",
            port=6379,
            password="secret",
            db=1,
        )

        assert adapter.password == "secret"
        assert adapter.db == 1

    def test_redis_adapter_custom_settings(self):
        """Test RedisAdapter with custom settings."""
        adapter = RedisAdapter(
            host="redis.example.com",
            port=6380,
            password="pass123",
            db=2,
        )

        assert adapter.host == "redis.example.com"
        assert adapter.port == 6380
        assert adapter.password == "pass123"
        assert adapter.db == 2


class TestGetClient:
    """Test _get_client method."""

    @pytest.mark.asyncio
    async def test_get_client_creates_client(self):
        """Test _get_client creates Redis client."""
        adapter = RedisAdapter()

        with patch("src.infra.cache.redis.Redis") as mock_redis_class:
            mock_client = MagicMock()
            mock_redis_class.return_value = mock_client

            client = await adapter._get_client()

            assert client is mock_client
            mock_redis_class.assert_called_once_with(
                host="localhost",
                port=6379,
                password=None,
                db=0,
                decode_responses=True,
            )

    @pytest.mark.asyncio
    async def test_get_client_caching(self):
        """Test _get_client caches client."""
        adapter = RedisAdapter()

        with patch("src.infra.cache.redis.Redis") as mock_redis_class:
            mock_client = MagicMock()
            mock_redis_class.return_value = mock_client

            client1 = await adapter._get_client()
            client2 = await adapter._get_client()

            assert client1 is client2
            # Should only create once
            assert mock_redis_class.call_count == 1


class TestGet:
    """Test get method."""

    @pytest.mark.asyncio
    async def test_get_string_value(self):
        """Test getting string value."""
        adapter = RedisAdapter()

        with patch("src.infra.cache.redis.Redis") as mock_redis_class:
            mock_client = MagicMock()
            mock_client.get = AsyncMock(return_value="plain_string")
            mock_redis_class.return_value = mock_client

            value = await adapter.get("test_key")

            assert value == "plain_string"
            mock_client.get.assert_called_once_with("test_key")

    @pytest.mark.asyncio
    async def test_get_json_value(self):
        """Test getting JSON value."""
        adapter = RedisAdapter()

        with patch("src.infra.cache.redis.Redis") as mock_redis_class:
            mock_client = MagicMock()
            json_data = {"name": "test", "value": 123}
            mock_client.get = AsyncMock(return_value=json.dumps(json_data))
            mock_redis_class.return_value = mock_client

            value = await adapter.get("test_key")

            assert value == json_data
            assert isinstance(value, dict)

    @pytest.mark.asyncio
    async def test_get_none_when_not_found(self):
        """Test get returns None when key not found."""
        adapter = RedisAdapter()

        with patch("src.infra.cache.redis.Redis") as mock_redis_class:
            mock_client = MagicMock()
            mock_client.get = AsyncMock(return_value=None)
            mock_redis_class.return_value = mock_client

            value = await adapter.get("nonexistent_key")

            assert value is None

    @pytest.mark.asyncio
    async def test_get_raises_on_redis_error(self):
        """Test get raises RuntimeError on Redis error."""
        from redis.exceptions import RedisError  # type: ignore[import-untyped]

        adapter = RedisAdapter()

        with patch("src.infra.cache.redis.Redis") as mock_redis_class:
            mock_client = MagicMock()
            mock_client.get = AsyncMock(side_effect=RedisError("Connection failed"))
            mock_redis_class.return_value = mock_client

            with pytest.raises(RuntimeError, match="Failed to get key"):
                await adapter.get("test_key")


class TestSet:
    """Test set method."""

    @pytest.mark.asyncio
    async def test_set_string_value(self):
        """Test setting string value."""
        adapter = RedisAdapter()

        with patch("src.infra.cache.redis.Redis") as mock_redis_class:
            mock_client = MagicMock()
            mock_client.set = AsyncMock()
            mock_redis_class.return_value = mock_client

            await adapter.set("test_key", "test_value")

            mock_client.set.assert_called_once_with("test_key", "test_value", ex=None)

    @pytest.mark.asyncio
    async def test_set_dict_value(self):
        """Test setting dict value (JSON serialized)."""
        adapter = RedisAdapter()

        with patch("src.infra.cache.redis.Redis") as mock_redis_class:
            mock_client = MagicMock()
            mock_client.set = AsyncMock()
            mock_redis_class.return_value = mock_client

            data = {"name": "test", "value": 123}
            await adapter.set("test_key", data)

            # Should serialize to JSON
            expected_json = json.dumps(data)
            mock_client.set.assert_called_once_with("test_key", expected_json, ex=None)

    @pytest.mark.asyncio
    async def test_set_with_expiration(self):
        """Test setting value with expiration."""
        adapter = RedisAdapter()

        with patch("src.infra.cache.redis.Redis") as mock_redis_class:
            mock_client = MagicMock()
            mock_client.set = AsyncMock()
            mock_redis_class.return_value = mock_client

            await adapter.set("test_key", "test_value", expire_seconds=3600)

            mock_client.set.assert_called_once_with("test_key", "test_value", ex=3600)

    @pytest.mark.asyncio
    async def test_set_raises_on_redis_error(self):
        """Test set raises RuntimeError on Redis error."""
        from redis.exceptions import RedisError

        adapter = RedisAdapter()

        with patch("src.infra.cache.redis.Redis") as mock_redis_class:
            mock_client = MagicMock()
            mock_client.set = AsyncMock(side_effect=RedisError("Write failed"))
            mock_redis_class.return_value = mock_client

            with pytest.raises(RuntimeError, match="Failed to set key"):
                await adapter.set("test_key", "test_value")


class TestDelete:
    """Test delete method."""

    @pytest.mark.asyncio
    async def test_delete_existing_key(self):
        """Test deleting existing key."""
        adapter = RedisAdapter()

        with patch("src.infra.cache.redis.Redis") as mock_redis_class:
            mock_client = MagicMock()
            mock_client.delete = AsyncMock(return_value=1)
            mock_redis_class.return_value = mock_client

            result = await adapter.delete("test_key")

            assert result is True
            mock_client.delete.assert_called_once_with("test_key")

    @pytest.mark.asyncio
    async def test_delete_nonexistent_key(self):
        """Test deleting nonexistent key."""
        adapter = RedisAdapter()

        with patch("src.infra.cache.redis.Redis") as mock_redis_class:
            mock_client = MagicMock()
            mock_client.delete = AsyncMock(return_value=0)
            mock_redis_class.return_value = mock_client

            result = await adapter.delete("nonexistent_key")

            assert result is False

    @pytest.mark.asyncio
    async def test_delete_raises_on_redis_error(self):
        """Test delete raises RuntimeError on Redis error."""
        from redis.exceptions import RedisError

        adapter = RedisAdapter()

        with patch("src.infra.cache.redis.Redis") as mock_redis_class:
            mock_client = MagicMock()
            mock_client.delete = AsyncMock(side_effect=RedisError("Delete failed"))
            mock_redis_class.return_value = mock_client

            with pytest.raises(RuntimeError, match="Failed to delete key"):
                await adapter.delete("test_key")


class TestExists:
    """Test exists method."""

    @pytest.mark.asyncio
    async def test_exists_returns_true_for_existing_key(self):
        """Test exists returns True for existing key."""
        adapter = RedisAdapter()

        with patch("src.infra.cache.redis.Redis") as mock_redis_class:
            mock_client = MagicMock()
            mock_client.exists = AsyncMock(return_value=1)
            mock_redis_class.return_value = mock_client

            result = await adapter.exists("test_key")

            assert result is True
            mock_client.exists.assert_called_once_with("test_key")

    @pytest.mark.asyncio
    async def test_exists_returns_false_for_nonexistent_key(self):
        """Test exists returns False for nonexistent key."""
        adapter = RedisAdapter()

        with patch("src.infra.cache.redis.Redis") as mock_redis_class:
            mock_client = MagicMock()
            mock_client.exists = AsyncMock(return_value=0)
            mock_redis_class.return_value = mock_client

            result = await adapter.exists("nonexistent_key")

            assert result is False


class TestExpire:
    """Test expire method."""

    @pytest.mark.asyncio
    async def test_expire_existing_key(self):
        """Test setting expiration for existing key."""
        adapter = RedisAdapter()

        with patch("src.infra.cache.redis.Redis") as mock_redis_class:
            mock_client = MagicMock()
            mock_client.expire = AsyncMock(return_value=True)
            mock_redis_class.return_value = mock_client

            result = await adapter.expire("test_key", 3600)

            assert result is True
            mock_client.expire.assert_called_once_with("test_key", 3600)

    @pytest.mark.asyncio
    async def test_expire_nonexistent_key(self):
        """Test setting expiration for nonexistent key."""
        adapter = RedisAdapter()

        with patch("src.infra.cache.redis.Redis") as mock_redis_class:
            mock_client = MagicMock()
            mock_client.expire = AsyncMock(return_value=False)
            mock_redis_class.return_value = mock_client

            result = await adapter.expire("nonexistent_key", 3600)

            assert result is False


class TestKeys:
    """Test keys method."""

    @pytest.mark.asyncio
    async def test_keys_default_pattern(self):
        """Test getting all keys with default pattern."""
        adapter = RedisAdapter()

        with patch("src.infra.cache.redis.Redis") as mock_redis_class:
            mock_client = MagicMock()
            mock_client.keys = AsyncMock(return_value=["key1", "key2", "key3"])
            mock_redis_class.return_value = mock_client

            keys = await adapter.keys()

            assert keys == ["key1", "key2", "key3"]
            mock_client.keys.assert_called_once_with("*")

    @pytest.mark.asyncio
    async def test_keys_custom_pattern(self):
        """Test getting keys with custom pattern."""
        adapter = RedisAdapter()

        with patch("src.infra.cache.redis.Redis") as mock_redis_class:
            mock_client = MagicMock()
            mock_client.keys = AsyncMock(return_value=["user:1", "user:2"])
            mock_redis_class.return_value = mock_client

            keys = await adapter.keys("user:*")

            assert keys == ["user:1", "user:2"]
            mock_client.keys.assert_called_once_with("user:*")


class TestClearAll:
    """Test clear_all method."""

    @pytest.mark.asyncio
    async def test_clear_all(self):
        """Test clearing all keys in database."""
        adapter = RedisAdapter()

        with patch("src.infra.cache.redis.Redis") as mock_redis_class:
            mock_client = MagicMock()
            mock_client.flushdb = AsyncMock()
            mock_redis_class.return_value = mock_client

            await adapter.clear_all()

            mock_client.flushdb.assert_called_once()


class TestPing:
    """Test ping method."""

    @pytest.mark.asyncio
    async def test_ping_success(self):
        """Test ping returns True when Redis is reachable."""
        adapter = RedisAdapter()

        with patch("src.infra.cache.redis.Redis") as mock_redis_class:
            mock_client = MagicMock()
            mock_client.ping = AsyncMock(return_value=True)
            mock_redis_class.return_value = mock_client

            result = await adapter.ping()

            assert result is True
            mock_client.ping.assert_called_once()

    @pytest.mark.asyncio
    async def test_ping_failure(self):
        """Test ping returns False when Redis is unreachable."""
        from redis.exceptions import RedisError

        adapter = RedisAdapter()

        with patch("src.infra.cache.redis.Redis") as mock_redis_class:
            mock_client = MagicMock()
            mock_client.ping = AsyncMock(side_effect=RedisError("Connection refused"))
            mock_redis_class.return_value = mock_client

            result = await adapter.ping()

            assert result is False


class TestClose:
    """Test close method."""

    @pytest.mark.asyncio
    async def test_close_with_client(self):
        """Test closing Redis connection."""
        adapter = RedisAdapter()

        with patch("src.infra.cache.redis.Redis") as mock_redis_class:
            mock_client = MagicMock()
            mock_client.aclose = AsyncMock()
            mock_redis_class.return_value = mock_client

            # Create client
            await adapter._get_client()
            assert adapter._client is not None

            # Close
            await adapter.close()

            mock_client.aclose.assert_called_once()
            assert adapter._client is None

    @pytest.mark.asyncio
    async def test_close_without_client(self):
        """Test closing when no client exists."""
        adapter = RedisAdapter()

        # Should not raise
        await adapter.close()
        assert adapter._client is None


class TestComplexScenarios:
    """Test complex usage scenarios."""

    @pytest.mark.asyncio
    async def test_set_get_roundtrip(self):
        """Test setting and getting value."""
        adapter = RedisAdapter()

        with patch("src.infra.cache.redis.Redis") as mock_redis_class:
            mock_client = MagicMock()
            stored_data = {}

            async def mock_set(key, value, ex=None):
                stored_data[key] = value

            async def mock_get(key):
                return stored_data.get(key)

            mock_client.set = AsyncMock(side_effect=mock_set)
            mock_client.get = AsyncMock(side_effect=mock_get)
            mock_redis_class.return_value = mock_client

            # Set and get
            data = {"test": "value"}
            await adapter.set("test_key", data)
            result = await adapter.get("test_key")

            assert result == data

    @pytest.mark.asyncio
    async def test_set_delete_get(self):
        """Test setting, deleting, then getting value."""
        adapter = RedisAdapter()

        with patch("src.infra.cache.redis.Redis") as mock_redis_class:
            mock_client = MagicMock()
            stored_data = {"test_key": "test_value"}

            async def mock_delete(key):
                if key in stored_data:
                    del stored_data[key]
                    return 1
                return 0

            async def mock_get(key):
                return stored_data.get(key)

            mock_client.delete = AsyncMock(side_effect=mock_delete)
            mock_client.get = AsyncMock(side_effect=mock_get)
            mock_redis_class.return_value = mock_client

            # Delete and verify
            deleted = await adapter.delete("test_key")
            assert deleted is True

            # Get should return None
            value = await adapter.get("test_key")
            assert value is None
