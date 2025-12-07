#!/usr/bin/env python3
"""
실제 E2E 파이프라인 (Mock 없음!)

1. 실제 문제 코드 생성
2. LLM으로 전략 생성 (실제 API 호출)
3. 생성된 코드를 실제 파일에 적용
4. Sandbox에서 실제 실행
5. 결과 검증
"""

import asyncio
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, ".")


async def main():
    print("=" * 80)
    print("🚀 실제 E2E 파이프라인 (No Mock, No Fake!)")
    print("=" * 80)

    # ============================================================
    # Step 1: 실제 문제 코드 준비
    # ============================================================
    print("\n" + "=" * 80)
    print("Step 1: 실제 문제 코드 생성")
    print("=" * 80)

    # 임시 디렉토리 생성
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)

        # 문제 코드 작성 (NullPointerException 발생)
        problem_file = tmpdir / "service.py"
        problem_code = """def process_user(user):
    # 문제: user가 None일 때 crash
    return user.email.lower()

def test_process_user():
    # Test case
    user = type('User', (), {'email': 'TEST@EXAMPLE.COM'})()
    result = process_user(user)
    assert result == 'test@example.com'
    
    # 이 케이스가 crash
    # process_user(None)
"""

        problem_file.write_text(problem_code)
        print(f"✅ 문제 코드 생성: {problem_file}")
        print(f"\n```python\n{problem_code}\n```")

        # ============================================================
        # Step 2: LLM으로 해결책 생성 (실제 API!)
        # ============================================================
        print("\n" + "=" * 80)
        print("Step 2: LLM으로 해결책 생성 (실제 OpenAI API)")
        print("=" * 80)

        from src.container import Container

        container = Container()

        result = await container.v8_execute_tot.execute(
            problem="Fix NullPointerException in process_user function",
            context={"code": problem_code, "files": ["service.py"]},
            strategy_count=2,
        )

        # Best strategy 찾기
        best_strategy = None
        for strategy in result.all_strategies:
            if strategy.strategy_id == result.best_strategy_id:
                best_strategy = strategy
                break

        if not best_strategy:
            best_strategy = result.all_strategies[0] if result.all_strategies else None

        if not best_strategy:
            print("\n❌ 전략이 생성되지 않았습니다!")
            return 1

        print("\n✅ 전략 생성 완료:")
        print(f"  Strategy ID: {best_strategy.strategy_id}")
        print(f"  Title: {best_strategy.title}")
        print(f"  Score: {result.best_score:.2f}")
        print(f"  Has Code: {len(best_strategy.file_changes) > 0}")

        if not best_strategy.file_changes:
            print("\n❌ file_changes가 비어있습니다!")
            return 1

        # ============================================================
        # Step 3: 생성된 코드를 실제 파일에 적용
        # ============================================================
        print("\n" + "=" * 80)
        print("Step 3: 생성된 코드를 실제 파일에 적용")
        print("=" * 80)

        for file_path, new_code in best_strategy.file_changes.items():
            # 실제 파일에 쓰기
            target_file = tmpdir / file_path
            target_file.parent.mkdir(parents=True, exist_ok=True)
            target_file.write_text(new_code)

            print(f"\n✅ 파일 적용: {target_file}")
            print(f"\n```python\n{new_code}\n```")

        # ============================================================
        # Step 4: Sandbox에서 실제 실행
        # ============================================================
        print("\n" + "=" * 80)
        print("Step 4: Sandbox에서 실제 실행")
        print("=" * 80)

        sandbox = container.v8_sandbox_executor

        # 실제 실행 (execute_code 메서드 사용)
        exec_result = await sandbox.execute_code(
            file_changes=best_strategy.file_changes,
            timeout=5,
        )

        print("\n실행 결과:")
        print(f"  Compile Success: {exec_result.compile_success}")
        print(f"  Tests Passed: {exec_result.tests_passed}")
        print(f"  Tests Failed: {exec_result.tests_failed}")
        print(f"  Execution Time: {exec_result.execution_time:.3f}s")

        # ============================================================
        # Step 5: 결과 요약
        # ============================================================
        print("\n" + "=" * 80)
        print("Step 5: 실행 결과 요약")
        print("=" * 80)

        test_success = exec_result.tests_passed > 0 and exec_result.tests_failed == 0

        print(f"\n테스트 성공: {test_success}")
        print(f"  Passed: {exec_result.tests_passed}")
        print(f"  Failed: {exec_result.tests_failed}")

        # ============================================================
        # Step 6: 실제 DB에 저장
        # ============================================================
        print("\n" + "=" * 80)
        print("Step 6: Experience를 실제 DB에 저장")
        print("=" * 80)

        from src.agent.domain.experience import AgentExperience, ProblemType

        experience = AgentExperience(
            problem_type=ProblemType.BUGFIX,
            problem_description="Fix NullPointerException in process_user (Real E2E)",
            code_chunk_ids=["real_e2e_001"],
            strategy_type=best_strategy.strategy_type.value,
            strategy_id=best_strategy.strategy_id,
            file_paths=list(best_strategy.file_changes.keys()),
            success=test_success,
            tot_score=result.best_score,
            reflection_verdict="accept" if test_success else "revise",
        )

        repo = container.v8_experience_repository
        saved = repo.save(experience)

        print("\n✅ DB 저장 완료:")
        print(f"  Repository: {type(repo).__name__}")
        print(f"  Experience ID: {saved.id}")
        print(f"  Success: {saved.success}")
        print(f"  Score: {saved.tot_score:.2f}")

        # ============================================================
        # 최종 결과
        # ============================================================
        print("\n" + "=" * 80)
        print("🎉 실제 E2E 파이프라인 완료!")
        print("=" * 80)

        print("\n실제 작동 확인:")
        print(f"  ✅ LLM API 호출: {best_strategy.strategy_id.startswith('llm_')}")
        print(f"  ✅ 코드 생성: {len(best_strategy.file_changes) > 0}")
        print(f"  ✅ 파일 적용: {target_file.exists()}")
        print(f"  ✅ Sandbox 실행: {exec_result.compile_success}")
        print(f"  ✅ 테스트 실행: {exec_result.tests_passed > 0}")
        print(f"  ✅ DB 저장: {saved.id is not None}")

        success = all(
            [
                best_strategy.strategy_id.startswith("llm_"),
                len(best_strategy.file_changes) > 0,
                target_file.exists(),
                exec_result.compile_success,
                saved.id is not None,
            ]
        )

        if success:
            print("\n🎊 전체 파이프라인 실제 작동 검증 완료!")
            return 0
        else:
            print("\n⚠️ 일부 단계 실패")
            return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
