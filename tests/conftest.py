"""
Global test configuration and fixtures
"""

import pytest
import time
from typing import Generator

# 느린 테스트 임계값 (초)
SLOW_TEST_THRESHOLD = 5.0
WARNING_TEST_THRESHOLD = 2.0


@pytest.fixture(autouse=True)
def track_test_duration(request):
    """모든 테스트의 실행 시간을 추적하고 느린 테스트 경고"""
    start_time = time.time()

    yield

    duration = time.time() - start_time
    test_name = request.node.nodeid

    # 느린 테스트 경고
    if duration > SLOW_TEST_THRESHOLD:
        print(f"\n⚠️  SLOW TEST ({duration:.2f}s): {test_name}")
        print(f"   Consider marking with @pytest.mark.slow or optimizing")
    elif duration > WARNING_TEST_THRESHOLD:
        print(f"\n⏱️  Slow ({duration:.2f}s): {test_name}")


@pytest.fixture
def temp_dir(tmp_path) -> Generator[str, None, None]:
    """임시 디렉토리 제공"""
    yield str(tmp_path)


@pytest.fixture
def mock_repo_path(tmp_path) -> str:
    """Mock 리포지토리 경로"""
    repo = tmp_path / "test_repo"
    repo.mkdir()
    return str(repo)


# Pytest hooks
def pytest_configure(config):
    """pytest 설정"""
    config.addinivalue_line("markers", "unit: Unit tests (fast, isolated)")
    config.addinivalue_line("markers", "integration: Integration tests (medium speed)")
    config.addinivalue_line("markers", "e2e: End-to-end tests (slow)")
    config.addinivalue_line("markers", "slow: Slow tests (>5s)")
    config.addinivalue_line("markers", "benchmark: Performance benchmarks")
    config.addinivalue_line("markers", "security: Security tests")


def pytest_collection_modifyitems(config, items):
    """테스트 수집 후 처리"""
    for item in items:
        # 경로 기반 자동 마커 추가
        if "unit" in str(item.fspath):
            item.add_marker(pytest.mark.unit)
        elif "integration" in str(item.fspath):
            item.add_marker(pytest.mark.integration)
        elif "e2e" in str(item.fspath):
            item.add_marker(pytest.mark.e2e)
        elif "performance" in str(item.fspath):
            item.add_marker(pytest.mark.benchmark)
        elif "security" in str(item.fspath):
            item.add_marker(pytest.mark.security)


def pytest_report_header(config):
    """리포트 헤더 추가"""
    return [
        "Test Structure: SOTA-level Pyramid (Unit > Integration > E2E)",
        f"Slow test threshold: {SLOW_TEST_THRESHOLD}s",
        f"Warning threshold: {WARNING_TEST_THRESHOLD}s",
    ]
