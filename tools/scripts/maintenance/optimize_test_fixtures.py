#!/usr/bin/env python3
"""
테스트 파일들의 LayeredIRBuilder() 사용을 shared_ir_builder로 자동 변환

Usage:
    python scripts/optimize_test_fixtures.py
"""

import re
from pathlib import Path


def optimize_file(file_path: Path) -> tuple[bool, str]:
    """
    파일의 LayeredIRBuilder 사용을 shared_ir_builder로 변환

    Returns:
        (변경됨, 메시지)
    """
    content = file_path.read_text()
    original = content

    # 1. shared_parser_registry를 shared_ir_builder로 변경
    content = re.sub(r"([,(]\s*)shared_parser_registry(\s*[,)])", r"\1shared_ir_builder\2", content)

    # 2. LayeredIRBuilder 생성을 shared_ir_builder 사용으로 변경
    # Pattern: builder = LayeredIRBuilder(project_root=X, parser_registry=shared_parser_registry)
    content = re.sub(
        r"(\s+)builder = LayeredIRBuilder\(project_root=[^,]+(?:,\s*parser_registry=shared_parser_registry)?\)",
        r"\1builder = shared_ir_builder",
        content,
    )

    # 3. LayeredIRBuilder 생성 (parser_registry 없이)
    content = re.sub(
        r"(\s+)builder = LayeredIRBuilder\(project_root=[^)]+\)", r"\1builder = shared_ir_builder", content
    )

    if content != original:
        file_path.write_text(content)
        return True, f"✓ Optimized: {file_path}"
    else:
        return False, f"  No change: {file_path}"


def main():
    """메인 함수"""
    test_dir = Path("tests")

    # LayeredIRBuilder를 사용하는 모든 파일 찾기
    py_files = list(test_dir.rglob("test_*.py"))

    optimized = []
    unchanged = []
    errors = []

    for file_path in py_files:
        # conftest.py는 제외
        if file_path.name == "conftest.py":
            continue

        # LayeredIRBuilder를 포함하는 파일만 처리
        content = file_path.read_text()
        if "LayeredIRBuilder(" not in content:
            continue

        try:
            changed, msg = optimize_file(file_path)
            if changed:
                optimized.append(msg)
            else:
                unchanged.append(msg)
        except Exception as e:
            errors.append(f"✗ Error in {file_path}: {e}")

    # 결과 출력
    print(f"\n=== 테스트 Fixture 최적화 결과 ===\n")

    if optimized:
        print(f"최적화 완료 ({len(optimized)}개):")
        for msg in optimized[:10]:  # 상위 10개만
            print(f"  {msg}")
        if len(optimized) > 10:
            print(f"  ... and {len(optimized) - 10} more")

    if errors:
        print(f"\n오류 ({len(errors)}개):")
        for msg in errors:
            print(f"  {msg}")

    print(f"\n총계:")
    print(f"  - 최적화: {len(optimized)}개")
    print(f"  - 변경 없음: {len(unchanged)}개")
    print(f"  - 오류: {len(errors)}개")

    if optimized:
        print(f"\n예상 성능 개선:")
        print(f"  - 테스트당: 133ms 단축 (138ms → 5ms)")
        print(f"  - 총 단축: ~{len(optimized) * 0.133:.1f}초")


if __name__ == "__main__":
    main()
