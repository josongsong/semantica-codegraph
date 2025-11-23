"""
Pytest Configuration and Fixtures

테스트 규칙에 맞춘 공통 픽스처 제공:
- Unit Test: Fake 인스턴스
- Integration Test: Container lazy singleton
- Test DB 설정
"""

import pytest

from tests.fakes import (
    FakeGitProvider,
    FakeGraphStore,
    FakeLexicalSearch,
    FakeLLMProvider,
    FakeRelationalStore,
    FakeVectorStore,
)

# ========================================================================
# Unit Test Fixtures (Fake Implementations)
# ========================================================================


@pytest.fixture
def fake_vector():
    """Fake Vector Store (Unit Test용)."""
    store = FakeVectorStore()
    store.create_collection("test_collection", vector_size=1536)
    yield store


@pytest.fixture
def fake_graph():
    """Fake Graph Store (Unit Test용)."""
    store = FakeGraphStore()
    yield store
    store.clear()


@pytest.fixture
def fake_relational():
    """Fake Relational Store (Unit Test용)."""
    store = FakeRelationalStore()
    yield store
    store.clear()


@pytest.fixture
def fake_lexical():
    """Fake Lexical Search (Unit Test용)."""
    search = FakeLexicalSearch()
    yield search
    search.clear()


@pytest.fixture
def fake_git():
    """Fake Git Provider (Unit Test용)."""
    return FakeGitProvider()


@pytest.fixture
def fake_llm():
    """Fake LLM Provider (Unit Test용)."""
    return FakeLLMProvider(embedding_dim=1536)


# ========================================================================
# Integration Test Fixtures (Container Singleton)
# ========================================================================


@pytest.fixture(scope="session")
def test_settings():
    """
    Test 환경 Settings.

    docker-compose.test.yml 포트 사용.
    """
    # TODO: Implement Settings after src.config is created
    return None


@pytest.fixture(scope="session")
def container(test_settings):
    """
    Test용 Container (Integration Test용).

    ⚠️  Rule: container 새 인스턴스 생성 금지
    ⚠️  실제 구현 시 global container를 test settings로 override하는 방식 필요
    """
    # TODO: Implement container after src.container is created
    return None


# ========================================================================
# Database Fixtures (Integration Test)
# ========================================================================


@pytest.fixture(scope="function")
def clean_db(container):
    """
    각 테스트 전후 DB 정리.

    Integration Test에서 사용.
    """
    # Before test: clear
    # container.postgres.clear()  # TODO: 구현 필요

    yield

    # After test: clear
    # container.postgres.clear()


# ========================================================================
# Scenario Test Fixtures
# ========================================================================


@pytest.fixture
def golden_data_dir():
    """Golden test 데이터 디렉터리."""
    import pathlib

    # TODO: Create scenarios directory if needed
    scenarios_dir = pathlib.Path(__file__).parent / "scenarios"
    scenarios_dir.mkdir(exist_ok=True)
    return scenarios_dir


@pytest.fixture
def load_golden(golden_data_dir):
    """
    Golden test JSON 로드.

    Usage:
        data = load_golden("symbol_search_01.json")
    """
    import json

    def _load(filename: str):
        path = golden_data_dir / filename
        with path.open() as f:
            return json.load(f)

    return _load


# ========================================================================
# Helpers
# ========================================================================


@pytest.fixture
def sample_code():
    """테스트용 샘플 코드."""
    return '''
def search_route(query: str):
    """Search endpoint."""
    results = vector_store.search(query)
    return results
'''


@pytest.fixture
def sample_repo():
    """테스트용 샘플 레포지토리 구조."""
    return {
        "files": [
            {
                "path": "src/api/routes.py",
                "content": "def search_route(): pass",
            },
            {
                "path": "src/services/search.py",
                "content": "class SearchService: pass",
            },
        ],
    }
