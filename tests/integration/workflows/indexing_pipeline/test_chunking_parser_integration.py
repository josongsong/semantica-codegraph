"""
Integration tests with real Parser

실제 Parser를 사용한 통합 테스트
"""

import pytest
from src.chunking import (
    ChunkingConfig,
    ChunkingInput,
    ChunkingOrchestrator,
)
from src.core.domain.parser_config import ParserConfig
from src.infra.chunking import LLMSummaryBuilder, TreeSitterNormalizer
from src.infra.parser.python_parser import TreeSitterPythonParser


class MockLLMProvider:
    """Mock LLMProviderPort"""

    async def generate_summary(self, code: str, language: str) -> str:
        return f"Summary of {language} code"


@pytest.fixture
def real_orchestrator():
    """Create Orchestrator with real parser"""
    # Real parser
    parser = TreeSitterPythonParser(ParserConfig())

    # Tokenizer (Simple for testing)
    from src.infra.chunking.tokenizer import SimpleTokenizer

    tokenizer = SimpleTokenizer()

    # Normalizer
    normalizer = TreeSitterNormalizer()

    # Summary builder
    config = ChunkingConfig(
        min_tokens=5,
        max_tokens=50,
        enable_summary_generation=True,
        dry_run=True,  # LLM 호출 건너뛰기
    )
    summary_builder = LLMSummaryBuilder(MockLLMProvider(), config)

    return ChunkingOrchestrator(parser, tokenizer, normalizer, summary_builder, config)


@pytest.mark.asyncio
async def test_real_python_parsing(real_orchestrator):
    """Test: 실제 Python 코드 파싱 → 청킹"""
    python_code = """
def hello_world():
    '''A simple hello world function'''
    print("Hello, World!")
    return "Hello"

class Calculator:
    '''A simple calculator class'''

    def add(self, a, b):
        return a + b

    def subtract(self, a, b):
        return a - b
"""

    input_data = ChunkingInput(
        file_path="test.py",
        content=python_code,
        language="python",
        repo_id="test_repo",
        file_hash="abc123",
    )

    result = await real_orchestrator.process_file(input_data)

    # 성공 확인
    assert result.success is True
    assert len(result.errors) == 0

    # LeafChunk 생성 확인
    assert len(result.leaf_chunks) > 0

    # ParentChunk 생성 확인 (function + class + file)
    assert len(result.parent_chunks) > 0

    # function과 class 청크가 있어야 함
    parent_kinds = {chunk.kind for chunk in result.parent_chunks}
    assert "function" in parent_kinds
    assert "class" in parent_kinds
    assert "file" in parent_kinds

    # EmbeddingDocument 생성 확인
    assert len(result.embedding_documents) > 0

    # Delta 확인 (이전 상태 없으므로 모두 INSERT)
    assert len(result.deltas) > 0


@pytest.mark.asyncio
async def test_real_incremental_update(real_orchestrator):
    """Test: 증분 업데이트 (코드 수정 시나리오)"""
    # 첫 번째 버전
    code_v1 = """
def foo():
    return 1
"""

    input_v1 = ChunkingInput(
        file_path="test.py",
        content=code_v1,
        language="python",
        repo_id="test_repo",
        file_hash="v1",
    )

    result_v1 = await real_orchestrator.process_file(input_v1)

    # 두 번째 버전 (함수 수정 + 새 함수 추가)
    code_v2 = """
def foo():
    return 42  # Changed

def bar():
    return 2  # New
"""

    input_v2 = ChunkingInput(
        file_path="test.py",
        content=code_v2,
        language="python",
        repo_id="test_repo",
        file_hash="v2",
        old_leaf_chunks=result_v1.leaf_chunks,
        old_parent_chunks=result_v1.parent_chunks,
    )

    result_v2 = await real_orchestrator.process_file(input_v2)

    assert result_v2.success is True

    # Delta 확인
    # - foo 함수 변경 → UPDATE
    # - bar 함수 추가 → INSERT
    from src.chunking import ChunkDeltaOperation

    operations = {delta.operation for delta in result_v2.deltas}
    assert ChunkDeltaOperation.UPDATE in operations  # foo changed
    assert ChunkDeltaOperation.INSERT in operations  # bar added


@pytest.mark.asyncio
async def test_empty_file(real_orchestrator):
    """Test: 빈 파일 처리"""
    input_data = ChunkingInput(
        file_path="empty.py",
        content="",
        language="python",
        repo_id="test_repo",
        file_hash="empty",
    )

    result = await real_orchestrator.process_file(input_data)

    # 에러 없이 처리되어야 함
    assert result.success is True

    # 빈 파일도 file-level 청크는 생성됨
    # (Parser가 module 노드를 생성하므로)
    file_chunks = [c for c in result.parent_chunks if c.kind == "file"]
    assert len(file_chunks) == 1  # File-level chunk exists


@pytest.mark.asyncio
async def test_syntax_error_handling(real_orchestrator):
    """Test: 구문 오류 파일 처리"""
    # 구문 오류가 있는 Python 코드
    invalid_code = """
def foo(:
    return
"""

    input_data = ChunkingInput(
        file_path="invalid.py",
        content=invalid_code,
        language="python",
        repo_id="test_repo",
        file_hash="invalid",
    )

    result = await real_orchestrator.process_file(input_data)

    # Parser가 실패하더라도 ChunkingResult는 반환되어야 함
    assert result is not None

    # 실패 여부는 Parser 구현에 따라 다를 수 있음
    # (일부 Parser는 오류가 있어도 부분 파싱 가능)
