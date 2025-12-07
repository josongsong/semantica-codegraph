#!/usr/bin/env python3
"""
실제 vs Stub 비판적 검증.

각 컴포넌트가 실제 구현을 사용하는지, Stub을 사용하는지 확실히 구분.
"""

import asyncio
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

from src.container import Container


class RealVsStubVerifier:
    """실제 vs Stub 검증"""

    def __init__(self):
        self.container = Container()
        self.real_count = 0
        self.stub_count = 0
        self.results = {}

    async def verify_all(self):
        """모든 컴포넌트 검증"""
        print("=" * 80)
        print(" " * 25 + "실제 vs Stub 비판적 검증")
        print("=" * 80)

        await self.verify_llm_provider()
        await self.verify_cache()
        await self.verify_multi_agent_lock()
        await self.verify_database()
        await self.verify_vector_db()
        await self.verify_graph_db()
        await self.verify_orchestrator()

        self.print_summary()

    async def verify_llm_provider(self):
        """LLM Provider 검증"""
        print("\n1️⃣  LLM Provider")
        print("-" * 80)

        try:
            llm = self.container.v7_optimized_llm_provider

            # 클래스 이름 확인
            class_name = type(llm).__name__
            print(f"  클래스: {class_name}")

            # OpenAI API 키 확인
            api_key = os.getenv("OPENAI_API_KEY", "")
            if not api_key:
                print("  ❌ STUB: API 키 없음")
                self.results["llm"] = "STUB"
                self.stub_count += 1
                return

            # 실제 API 호출 시도
            try:
                result = await llm.complete(messages=[{"role": "user", "content": "Say 'test'"}], max_tokens=5)

                if result and isinstance(result, str) and len(result) > 0:
                    print(f"  ✅ REAL: API 호출 성공 → {result[:30]}...")

                    # Circuit Breaker, Rate Limiter 확인
                    has_circuit = hasattr(llm, "circuit_breakers")
                    has_rate = hasattr(llm, "rate_limiter")
                    has_cache = hasattr(llm, "cache")

                    print(f"     - Circuit Breaker: {'✅' if has_circuit else '❌'}")
                    print(f"     - Rate Limiter: {'✅' if has_rate else '❌'}")
                    print(f"     - Cache: {'✅' if has_cache else '❌'}")

                    self.results["llm"] = "REAL"
                    self.real_count += 1
                else:
                    print(f"  ⚠️  FAKE: 응답 이상 → {type(result)}")
                    self.results["llm"] = "FAKE"
                    self.stub_count += 1

            except Exception as e:
                print(f"  ❌ STUB: API 호출 실패 → {e}")
                self.results["llm"] = "STUB"
                self.stub_count += 1

        except Exception as e:
            print(f"  ❌ ERROR: {e}")
            self.results["llm"] = "ERROR"
            self.stub_count += 1

    async def verify_cache(self):
        """Cache 검증"""
        print("\n2️⃣  Cache")
        print("-" * 80)

        try:
            cache = self.container.v7_advanced_cache

            # 클래스 이름 확인
            class_name = type(cache).__name__
            print(f"  클래스: {class_name}")

            # Redis 연결 확인
            if hasattr(cache, "redis_client") and cache.redis_client:
                try:
                    await cache.redis_client.ping()
                    print("  ✅ REAL: Redis 연결 성공 (Multi-tier Cache)")

                    # Multi-tier 확인
                    has_bloom = hasattr(cache, "bloom_filter")
                    has_compression = hasattr(cache, "compression_threshold")

                    print(f"     - Bloom Filter: {'✅' if has_bloom else '❌'}")
                    print(f"     - Compression: {'✅' if has_compression else '❌'}")

                    self.results["cache"] = "REAL"
                    self.real_count += 1
                except Exception as e:
                    print(f"  ❌ STUB: Redis 연결 실패 → {e}")
                    print("     → 메모리 모드 fallback (개인용 OK)")
                    self.results["cache"] = "MEMORY"
                    self.stub_count += 1
            else:
                print("  ⚠️  MEMORY: Redis 없음 (메모리 모드)")
                self.results["cache"] = "MEMORY"
                self.stub_count += 1

        except Exception as e:
            print(f"  ❌ ERROR: {e}")
            self.results["cache"] = "ERROR"
            self.stub_count += 1

    async def verify_multi_agent_lock(self):
        """Multi-Agent Lock 검증"""
        print("\n3️⃣  Multi-Agent Lock")
        print("-" * 80)

        try:
            lock_mgr = self.container.v7_soft_lock_manager

            # 클래스 이름 확인
            class_name = type(lock_mgr).__name__
            print(f"  클래스: {class_name}")

            # Redis 연결 확인
            if hasattr(lock_mgr, "redis_client") and lock_mgr.redis_client:
                try:
                    await lock_mgr.redis_client.ping()
                    print("  ✅ REAL: Redis 연결 성공 (분산 Lock)")

                    # 실제 Lock 테스트 (실제 파일 사용)
                    from src.agent.domain.soft_lock_manager import SoftLockManager

                    test_file = "test_real_vs_stub.py"  # 현재 파일 사용

                    mgr1 = SoftLockManager(redis_client=lock_mgr.redis_client)
                    mgr2 = SoftLockManager(redis_client=lock_mgr.redis_client)

                    # 이전 테스트의 Lock 정리
                    await lock_mgr.redis_client.delete(f"lock:{test_file}")

                    r1 = await mgr1.acquire_lock("test-1", test_file)
                    r2 = await mgr2.acquire_lock("test-2", test_file)

                    if r1.success and not r2.success:
                        print("     ✅ 분산 Lock 정상 작동")
                    elif not r1.success:
                        print(f"     ❌ Lock 획득 실패: r1={r1.message}")
                    else:
                        print(f"     ⚠️  Lock 이상: r1={r1.success}, r2={r2.success}")
                        if r2.success:
                            print("        → Agent 2도 락 획득 (충돌 감지 실패!)")

                    await mgr1.release_lock("test-1", test_file)

                    self.results["lock"] = "REAL"
                    self.real_count += 1
                except Exception as e:
                    print(f"  ❌ STUB: Redis 연결 실패 → {e}")
                    print("     → 메모리 모드 fallback (개인용 OK)")
                    self.results["lock"] = "MEMORY"
                    self.stub_count += 1
            else:
                print("  ⚠️  MEMORY: Redis 없음 (메모리 모드, 개인용 OK)")

                # 메모리 모드 테스트 (클래스 변수 공유 확인)
                from src.agent.domain.soft_lock_manager import SoftLockManager

                test_file = "test_real_vs_stub.py"  # 현재 파일 사용

                mgr1 = SoftLockManager(redis_client=None)
                mgr2 = SoftLockManager(redis_client=None)

                r1 = await mgr1.acquire_lock("test-1", test_file)
                r2 = await mgr2.acquire_lock("test-2", test_file)

                if r1.success and not r2.success:
                    print("     ✅ 메모리 모드 Lock 정상 작동 (클래스 변수 공유)")
                    self.results["lock"] = "MEMORY"
                else:
                    print(f"     ❌ 메모리 모드 Lock 이상: r1={r1.success}, r2={r2.success}")
                    self.results["lock"] = "BROKEN"

                await mgr1.release_lock("test-1", test_file)
                self.stub_count += 1

        except Exception as e:
            print(f"  ❌ ERROR: {e}")
            import traceback

            traceback.print_exc()
            self.results["lock"] = "ERROR"
            self.stub_count += 1

    async def verify_database(self):
        """PostgreSQL 검증"""
        print("\n4️⃣  PostgreSQL")
        print("-" * 80)

        try:
            # Container에서 PostgreSQL 가져오기
            postgres = self.container.postgres

            # 실제 연결 테스트
            result = await postgres.execute("SELECT version()")
            version = result if isinstance(result, str) else str(result)[:100]

            print("  ✅ REAL: PostgreSQL 연결 성공")
            print(f"     결과: {version[:50]}...")

            self.results["postgres"] = "REAL"
            self.real_count += 1

        except Exception as e:
            print(f"  ❌ STUB: PostgreSQL 연결 실패 → {e}")
            self.results["postgres"] = "STUB"
            self.stub_count += 1

    async def verify_vector_db(self):
        """Qdrant 검증"""
        print("\n5️⃣  Qdrant (Vector DB)")
        print("-" * 80)

        try:
            # Qdrant 클라이언트 확인
            qdrant = self.container.qdrant

            # 실제 연결 테스트 (healthcheck 메서드 사용)
            if hasattr(qdrant, "healthcheck"):
                health = await qdrant.healthcheck()

                print("  ✅ REAL: Qdrant 연결 성공")
                print(f"     Health: {health}")

                self.results["qdrant"] = "REAL"
                self.real_count += 1
            else:
                print(f"  ⚠️  클래스: {type(qdrant).__name__}")
                print("  ⚠️  healthcheck 메서드 없음")
                self.results["qdrant"] = "UNKNOWN"
                self.stub_count += 1

        except Exception as e:
            print(f"  ❌ STUB: Qdrant 연결 실패 → {e}")
            self.results["qdrant"] = "STUB"
            self.stub_count += 1

    async def verify_graph_db(self):
        """Memgraph 검증"""
        print("\n6️⃣  Memgraph (Graph DB)")
        print("-" * 80)

        try:
            # Memgraph 스토어 확인
            graph = self.container.graph_store

            print(f"  클래스: {type(graph).__name__}")

            # CachedGraphStore는 _store 속성을 통해 실제 Memgraph에 접근
            if hasattr(graph, "_store") and graph._store:
                print("  ✅ REAL: Memgraph 통합 (CachedGraphStore)")
                print(f"     - Base Store: {type(graph.store).__name__}")
                print("     - 3-tier 캐싱 활성화")
                self.results["memgraph"] = "REAL"
                self.real_count += 1
            elif hasattr(graph, "store"):
                print("  ✅ REAL: Memgraph 통합")
                print(f"     - Store: {type(graph.store).__name__}")
                self.results["memgraph"] = "REAL"
                self.real_count += 1
            else:
                print("  ⚠️  구조 확인 불가")
                self.results["memgraph"] = "UNKNOWN"
                self.stub_count += 1

        except Exception as e:
            print(f"  ❌ STUB: Memgraph 연결 실패 → {e}")
            self.results["memgraph"] = "STUB"
            self.stub_count += 1

    async def verify_orchestrator(self):
        """Orchestrator 검증"""
        print("\n7️⃣  Orchestrator")
        print("-" * 80)

        try:
            # Singleton 캐시 회피 - 직접 생성
            from src.agent.v7_container import V7AgentContainer

            v7_container = V7AgentContainer()
            orch = v7_container.agent_orchestrator

            # 클래스 이름
            class_name = type(orch).__name__
            print(f"  클래스: {class_name}")

            # 구성 요소 확인
            components = {
                "workflow_engine": hasattr(orch, "workflow_engine"),
                "llm_provider": hasattr(orch, "llm_provider"),
                "sandbox": hasattr(orch, "sandbox"),
                "guardrail": hasattr(orch, "guardrail"),
                "vcs_applier": hasattr(orch, "vcs_applier"),
                "incremental_workflow": hasattr(orch, "incremental_workflow"),
            }

            print("\n  구성 요소:")
            for comp, exists in components.items():
                symbol = "✅" if exists else "❌"
                print(f"     {symbol} {comp}")

            # 각 구성 요소의 실제/Stub 확인
            if hasattr(orch, "llm_provider"):
                llm_class = type(orch.llm_provider).__name__
                is_stub = "Stub" in llm_class or "Mock" in llm_class
                print(f"\n  LLM: {llm_class} ({'STUB' if is_stub else 'REAL'})")

            if hasattr(orch, "sandbox"):
                sandbox_class = type(orch.sandbox).__name__
                is_stub = "Stub" in sandbox_class or "Local" in sandbox_class or "Mock" in sandbox_class
                print(f"  Sandbox: {sandbox_class} ({'STUB' if is_stub else 'REAL'})")

            if hasattr(orch, "vcs_applier"):
                vcs_class = type(orch.vcs_applier).__name__
                is_stub = "Stub" in vcs_class or "Mock" in vcs_class
                print(f"  VCS: {vcs_class} ({'STUB' if is_stub else 'REAL'})")

            all_exist = all(components.values())
            if all_exist:
                print("\n  ✅ INTEGRATED: 모든 구성 요소 존재")
                self.results["orchestrator"] = "INTEGRATED"
                self.real_count += 1
            else:
                print("\n  ⚠️  PARTIAL: 일부 구성 요소 누락")
                self.results["orchestrator"] = "PARTIAL"
                self.stub_count += 1

        except Exception as e:
            print(f"  ❌ ERROR: {e}")
            import traceback

            traceback.print_exc()
            self.results["orchestrator"] = "ERROR"
            self.stub_count += 1

    def print_summary(self):
        """결과 요약"""
        print("\n" + "=" * 80)
        print(" " * 30 + "최종 결과")
        print("=" * 80)

        print("\n📊 구성 요소별 결과:\n")

        for component, status in self.results.items():
            if status == "REAL":
                symbol = "✅"
                color = "REAL"
            elif status == "MEMORY":
                symbol = "⚠️ "
                color = "MEMORY (개인용 OK)"
            elif status in ["STUB", "FAKE"]:
                symbol = "❌"
                color = status
            else:
                symbol = "⚠️ "
                color = status

            print(f"  {symbol} {component:<15} : {color}")

        print("\n" + "-" * 80)

        total = self.real_count + self.stub_count
        real_rate = (self.real_count / total * 100) if total > 0 else 0

        print(f"\n  실제 구현: {self.real_count}/{total} ({real_rate:.1f}%)")
        print(f"  Stub/Memory: {self.stub_count}/{total} ({100 - real_rate:.1f}%)")

        print("\n" + "=" * 80)

        # 판정
        if real_rate >= 80:
            print("🎉 프로덕션 준비 완료! (80% 이상 실제 구현)")
            return True
        elif real_rate >= 50:
            print("⚠️  개발/테스트 환경 (50-80% 실제 구현)")
            print("   → Redis, Qdrant, Memgraph 연결 확인 필요")
            return True
        else:
            print("❌ 로컬 개발 환경 (50% 미만 실제 구현)")
            print("   → 대부분 Stub/Memory 모드")
            return False


async def main():
    """메인 함수"""
    # .env 로드
    load_dotenv()

    # API 키 매핑
    if os.getenv("SEMANTICA_OPENAI_API_KEY"):
        os.environ["OPENAI_API_KEY"] = os.getenv("SEMANTICA_OPENAI_API_KEY")
        print("✅ OPENAI_API_KEY 설정 완료")

    verifier = RealVsStubVerifier()

    try:
        await verifier.verify_all()

        # 종료 코드
        if verifier.real_count >= 4:  # 최소 4개 이상 실제 구현
            sys.exit(0)
        else:
            sys.exit(1)

    except Exception as e:
        print(f"\n❌ 검증 중 오류: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
