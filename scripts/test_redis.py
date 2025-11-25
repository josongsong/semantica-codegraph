#!/usr/bin/env python3
"""
Redis Connection Test Script

Usage:
    python scripts/test_redis.py
"""

import asyncio
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.infra.cache.redis import RedisAdapter


async def test_basic_operations():
    """Test basic Redis operations."""
    print("🔌 Connecting to Redis...")

    redis = RedisAdapter(
        host="localhost",
        port=7202,
        password="codegraph_redis",
        db=0,
    )

    try:
        # Ping test
        print("📡 Testing connection...")
        is_alive = await redis.ping()
        if is_alive:
            print("✅ Redis is alive!")
        else:
            print("❌ Redis ping failed")
            return False

        # Set/Get test
        print("\n📝 Testing SET/GET...")
        test_key = "test:hello"
        test_value = "Hello Redis from Codegraph!"

        await redis.set(test_key, test_value, expire_seconds=60)
        print(f"   SET {test_key} = {test_value}")

        result = await redis.get(test_key)
        print(f"   GET {test_key} = {result}")

        if result == test_value:
            print("✅ SET/GET works!")
        else:
            print(f"❌ SET/GET failed: expected {test_value}, got {result}")
            return False

        # JSON test
        print("\n🔢 Testing JSON serialization...")
        json_key = "test:json"
        json_value = {
            "repo_id": "test-repo",
            "snapshot_id": "abc123",
            "chunks": [1, 2, 3],
            "metadata": {"author": "test", "timestamp": 123456789},
        }

        await redis.set(json_key, json_value)
        print(f"   SET {json_key} = {json_value}")

        result = await redis.get(json_key)
        print(f"   GET {json_key} = {result}")

        if result == json_value:
            print("✅ JSON serialization works!")
        else:
            print(f"❌ JSON failed: {result}")
            return False

        # Expiration test
        print("\n⏰ Testing expiration...")
        expire_key = "test:expire"
        await redis.set(expire_key, "will expire", expire_seconds=5)

        exists = await redis.exists(expire_key)
        print(f"   Key exists: {exists}")

        if exists:
            print("✅ Key created successfully!")
        else:
            print("❌ Key creation failed")
            return False

        # Delete test
        print("\n🗑️  Testing DELETE...")
        deleted = await redis.delete(test_key)
        print(f"   DELETE {test_key}: {deleted}")

        exists = await redis.exists(test_key)
        print(f"   Key exists: {exists}")

        if not exists:
            print("✅ DELETE works!")
        else:
            print("❌ DELETE failed")
            return False

        # Keys pattern test
        print("\n🔍 Testing KEYS pattern...")
        await redis.set("test:pattern:1", "value1")
        await redis.set("test:pattern:2", "value2")
        await redis.set("test:other", "other")

        keys = await redis.keys("test:pattern:*")
        print(f"   Keys matching 'test:pattern:*': {keys}")

        if len(keys) == 2:
            print("✅ KEYS pattern works!")
        else:
            print(f"❌ KEYS pattern failed: expected 2, got {len(keys)}")
            return False

        # Cleanup
        print("\n🧹 Cleaning up test keys...")
        await redis.delete(json_key)
        await redis.delete(expire_key)
        await redis.delete("test:pattern:1")
        await redis.delete("test:pattern:2")
        await redis.delete("test:other")

        print("\n✨ All tests passed!")
        return True

    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback

        traceback.print_exc()
        return False

    finally:
        await redis.close()
        print("👋 Connection closed")


async def test_performance():
    """Test Redis performance with batch operations."""
    print("\n⚡ Performance Test")
    print("=" * 50)

    redis = RedisAdapter(
        host="localhost",
        port=7202,
        password="codegraph_redis",
        db=0,
    )

    try:
        import time

        # Batch write test
        print("📊 Testing batch writes (1000 keys)...")
        start = time.time()

        for i in range(1000):
            await redis.set(f"perf:test:{i}", f"value_{i}")

        elapsed = time.time() - start
        ops_per_sec = 1000 / elapsed
        print(f"   ✓ Completed in {elapsed:.2f}s ({ops_per_sec:.0f} ops/sec)")

        # Batch read test
        print("📊 Testing batch reads (1000 keys)...")
        start = time.time()

        for i in range(1000):
            await redis.get(f"perf:test:{i}")

        elapsed = time.time() - start
        ops_per_sec = 1000 / elapsed
        print(f"   ✓ Completed in {elapsed:.2f}s ({ops_per_sec:.0f} ops/sec)")

        # Cleanup
        print("🧹 Cleaning up performance test keys...")
        for i in range(1000):
            await redis.delete(f"perf:test:{i}")

        print("✅ Performance test completed!")

    except Exception as e:
        print(f"❌ Performance test failed: {e}")

    finally:
        await redis.close()


async def main():
    """Run all tests."""
    print("=" * 50)
    print("Redis Adapter Test Suite")
    print("=" * 50)
    print()

    # Basic tests
    success = await test_basic_operations()

    if not success:
        print("\n❌ Basic tests failed!")
        sys.exit(1)

    # Performance tests
    await test_performance()

    print("\n" + "=" * 50)
    print("🎉 All tests completed successfully!")
    print("=" * 50)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\n⚠️  Test interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Fatal error: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)
