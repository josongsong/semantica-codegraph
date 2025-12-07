"""실제 인프라 연결 검증

비판적 검증: Mock이 아닌 실제 DB/Storage 연결 확인

검증 항목:
1. PostgreSQL 연결
2. Qdrant 연결
3. Memgraph 연결
4. Zoekt 연결 (optional)
5. Redis 연결
6. Local LLM 연결 (optional)
"""

import asyncio
import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.infra.config.settings import Settings


async def check_postgres():
    """PostgreSQL 연결 확인"""
    print("\n🔍 PostgreSQL Connection Check...")

    settings = Settings()

    try:
        import asyncpg

        # 연결 시도
        conn = await asyncpg.connect(settings.database_url, timeout=5.0)

        # 간단한 쿼리
        version = await conn.fetchval("SELECT version()")
        await conn.close()

        print(f"  ✅ PostgreSQL connected: {settings.db.url}")
        print(f"  ✅ Version: {version[:50]}...")
        return True

    except ImportError:
        print("  ⚠️  asyncpg not installed (pip install asyncpg)")
        return None
    except Exception as e:
        print(f"  ❌ PostgreSQL connection failed: {e}")
        print(f"  📌 URL: {settings.db.url}")
        print("  💡 Start: docker run -d -p 5432:5432 -e POSTGRES_PASSWORD=codegraph_dev postgres")
        return False


async def check_qdrant():
    """Qdrant 연결 확인"""
    print("\n🔍 Qdrant Connection Check...")

    settings = Settings()

    try:
        from qdrant_client import AsyncQdrantClient

        # 연결 시도
        client = AsyncQdrantClient(url=settings.vector.url, timeout=5.0)

        # Health check
        health = await client.get_collections()
        await client.close()

        print(f"  ✅ Qdrant connected: {settings.vector.url}")
        print(f"  ✅ Collections: {len(health.collections)}")
        return True

    except ImportError:
        print("  ⚠️  qdrant-client not installed (pip install qdrant-client)")
        return None
    except Exception as e:
        print(f"  ❌ Qdrant connection failed: {e}")
        print(f"  📌 URL: {settings.vector.url}")
        print("  💡 Start: docker run -d -p 6333:6333 -p 6334:6334 qdrant/qdrant")
        return False


async def check_memgraph():
    """Memgraph 연결 확인"""
    print("\n🔍 Memgraph Connection Check...")

    settings = Settings()

    try:
        from neo4j import AsyncGraphDatabase

        # 연결 시도
        driver = AsyncGraphDatabase.driver(
            settings.graph.uri,
            auth=(settings.graph.username, settings.graph.password) if settings.graph.username else None,
        )

        async with driver.session() as session:
            result = await session.run("RETURN 1 as test")
            record = await result.single()
            assert record["test"] == 1

        await driver.close()

        print(f"  ✅ Memgraph connected: {settings.graph.uri}")
        return True

    except ImportError:
        print("  ⚠️  neo4j not installed (pip install neo4j)")
        return None
    except Exception as e:
        print(f"  ❌ Memgraph connection failed: {e}")
        print(f"  📌 URI: {settings.graph.uri}")
        print("  💡 Start: docker run -d -p 7687:7687 -p 7208:7208 memgraph/memgraph-platform")
        return False


async def check_redis():
    """Redis 연결 확인"""
    print("\n🔍 Redis Connection Check...")

    settings = Settings()

    try:
        import redis.asyncio as redis

        # 연결 시도
        client = redis.Redis(
            host=settings.cache.host,
            port=settings.cache.port,
            db=settings.cache.db,
            password=settings.cache.password,
            socket_connect_timeout=5,
        )

        # Ping
        pong = await client.ping()
        await client.aclose()

        print(f"  ✅ Redis connected: {settings.cache.host}:{settings.cache.port}")
        print(f"  ✅ Ping: {pong}")
        return True

    except ImportError:
        print("  ⚠️  redis not installed (pip install redis)")
        return None
    except Exception as e:
        print(f"  ❌ Redis connection failed: {e}")
        print(f"  📌 Host: {settings.cache.host}:{settings.cache.port}")
        print("  💡 Start: docker run -d -p 6379:6379 redis")
        return False


async def check_zoekt():
    """Zoekt 연결 확인 (Optional)"""
    print("\n🔍 Zoekt Connection Check...")

    settings = Settings()

    try:
        import httpx

        # Health check
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(f"{settings.lexical.url}/")

        print(f"  ✅ Zoekt connected: {settings.lexical.url}")
        print(f"  ✅ Status: {response.status_code}")
        return True

    except ImportError:
        print("  ⚠️  httpx not installed (pip install httpx)")
        return None
    except Exception as e:
        print(f"  ❌ Zoekt connection failed: {e}")
        print(f"  📌 URL: {settings.lexical.url}")
        print(f"  💡 Start: zoekt-webserver -index {settings.lexical.index_dir} -listen :6070")
        return False


async def check_local_llm():
    """Local LLM 연결 확인 (Optional)"""
    print("\n🔍 Local LLM Connection Check...")

    settings = Settings()

    try:
        import httpx

        # Health check
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(f"{settings.llm.local_base_url}/v1/models")

        print(f"  ✅ Local LLM connected: {settings.llm.local_base_url}")
        print(f"  ✅ Status: {response.status_code}")

        if response.status_code == 200:
            data = response.json()
            models = data.get("data", [])
            print(f"  ✅ Available models: {len(models)}")

        return True

    except ImportError:
        print("  ⚠️  httpx not installed (pip install httpx)")
        return None
    except Exception as e:
        print(f"  ⚠️  Local LLM connection failed: {e}")
        print(f"  📌 URL: {settings.llm.local_base_url}")
        print("  💡 This is optional for Context Adapter")
        return None  # Not critical


async def main():
    print("=" * 70)
    print("🔥 실제 인프라 연결 검증")
    print("=" * 70)
    print()
    print("⚠️  주의: .env 파일의 연결 정보를 사용합니다")
    print("⚠️  실제 서비스가 떠있어야 합니다")

    # 필수 서비스
    critical = {
        "PostgreSQL": check_postgres,
        "Qdrant": check_qdrant,
        "Memgraph": check_memgraph,
        "Redis": check_redis,
    }

    # 선택 서비스
    optional = {
        "Zoekt": check_zoekt,
        "Local LLM": check_local_llm,
    }

    critical_results = {}
    optional_results = {}

    # Critical services
    for name, check_func in critical.items():
        result = await check_func()
        critical_results[name] = result

    # Optional services
    for name, check_func in optional.items():
        result = await check_func()
        optional_results[name] = result

    print("\n" + "=" * 70)
    print("📊 인프라 연결 결과")
    print("=" * 70)

    # Critical
    print("\n🔴 필수 서비스:")
    connected = sum(1 for v in critical_results.values() if v is True)
    failed = sum(1 for v in critical_results.values() if v is False)
    not_installed = sum(1 for v in critical_results.values() if v is None)

    for name, result in critical_results.items():
        if result is True:
            print(f"  ✅ {name}: Connected")
        elif result is False:
            print(f"  ❌ {name}: Failed")
        else:
            print(f"  ⚠️  {name}: Package not installed")

    print(f"\n  📊 {connected}/{len(critical_results)} connected")

    # Optional
    print("\n🟡 선택 서비스:")
    for name, result in optional_results.items():
        if result is True:
            print(f"  ✅ {name}: Connected")
        elif result is False:
            print(f"  ⚠️  {name}: Not running (optional)")
        else:
            print(f"  ⚠️  {name}: Package not installed (optional)")

    print("\n" + "=" * 70)

    # 최종 판단
    if connected == len(critical_results):
        print("🎉 모든 필수 인프라 연결 성공!")
        print("\n✅ Context Adapter 실제 연동 준비 완료")
    elif not_installed > 0:
        print(f"⚠️  {not_installed}개 패키지 미설치")
        print("\n💡 설치: pip install asyncpg qdrant-client neo4j redis httpx")
    elif failed > 0:
        print(f"❌ {failed}개 서비스 연결 실패")
        print("\n💡 위의 docker run 명령어로 서비스 시작")
    else:
        print("⚠️  일부 서비스 연결 실패")

    print()

    # Exit code
    if connected == len(critical_results):
        sys.exit(0)
    else:
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
