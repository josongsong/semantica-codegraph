"""
Integration tests for Chunking Layer
"""

import pytest
from src.chunking import (
    ChunkingConfig,
    ChunkingInput,
    ChunkingOrchestrator,
    DefaultSummaryBuilder,
)
from src.core.ports.parser_port import ParsedFileInput, ParserPort, ParserResult


class MockTokenizer:
    """Mock TokenizerPort"""

    def count_tokens(self, text: str) -> int:
        return len(text.split())

    def encode(self, text: str) -> list[int]:
        return [1] * self.count_tokens(text)


class MockNormalizer:
    """Mock CanonicalTextNormalizerPort"""

    def canonicalize(self, text: str, language: str) -> str:
        return text.strip()

    def normalize_signature(self, node) -> str:
        return f"{node.node_type}:{node.name}"

    def strip_comments(self, text: str, language: str) -> str:
        return text

    def strip_whitespace(self, text: str) -> str:
        return text.strip()


class MockLLMProvider:
    """Mock LLMProviderPort"""

    async def generate_summary(self, code: str, language: str) -> str:
        return f"Summary of {language} code"


class MockParser(ParserPort):
    """Mock ParserPort"""

    def supports(self, language: str) -> bool:
        return True

    def parse_file(self, file_input: ParsedFileInput) -> ParserResult:
        # 빈 노드 리스트 반환
        return ParserResult(
            file_path=str(file_input.file_path),
            language=file_input.language,
            nodes=[],
            success=True,
        )


@pytest.fixture
def orchestrator():
    """Create ChunkingOrchestrator instance"""
    config = ChunkingConfig(
        min_tokens=5,
        max_tokens=20,
        enable_summary_generation=True,
        dry_run=True,  # LLM 호출 건너뛰기
    )

    parser = MockParser()
    tokenizer = MockTokenizer()
    normalizer = MockNormalizer()
    summary_builder = DefaultSummaryBuilder(MockLLMProvider(), config)

    return ChunkingOrchestrator(parser, tokenizer, normalizer, summary_builder, config)


@pytest.mark.asyncio
async def test_full_pipeline_no_previous_state(orchestrator):
    """Test: 전체 파이프라인 (이전 상태 없음 → 전체 INSERT)"""
    input_data = ChunkingInput(
        file_path="test.py",
        content="def foo():\n    pass",
        language="python",
        repo_id="repo1",
        file_hash="abc123",
        old_leaf_chunks=None,
        old_parent_chunks=None,
    )

    result = await orchestrator.process_file(input_data)

    assert result.success is True
    assert result.file_path == "test.py"
    assert result.repo_id == "repo1"

    # TODO: Parser 통합 후 아래 주석 해제
    # assert len(result.leaf_chunks) > 0
    # assert len(result.parent_chunks) > 0
    # assert len(result.deltas) > 0


@pytest.mark.asyncio
async def test_delta_calculation_incremental(orchestrator):
    """Test: 증분 업데이트 (Delta 계산)"""
    # 이전 상태 (빈 리스트)
    input_data = ChunkingInput(
        file_path="test.py",
        content="def foo():\n    pass",
        language="python",
        repo_id="repo1",
        file_hash="abc123",
        old_leaf_chunks=[],  # 빈 상태
        old_parent_chunks=[],
    )

    _result = await orchestrator.process_file(input_data)

    # TODO: Parser 통합 후 아래 주석 해제
    # 이전 상태가 빈 리스트였으므로, 새 청크는 모두 INSERT
    # insert_deltas = [d for d in _result.deltas if d.operation == ChunkDeltaOperation.INSERT]
    # assert len(insert_deltas) > 0


@pytest.mark.asyncio
async def test_embedding_document_generation(orchestrator):
    """Test: EmbeddingDocument 생성"""
    input_data = ChunkingInput(
        file_path="test.py",
        content="def foo():\n    pass",
        language="python",
        repo_id="repo1",
        file_hash="abc123",
    )

    _result = await orchestrator.process_file(input_data)

    # TODO: Parser 통합 후 아래 주석 해제
    # EmbeddingDocument가 생성되어야 함
    # assert len(_result.embedding_documents) > 0

    # 용도별로 구분되어야 함 (summary, code, signature)
    # purposes = {doc.embedding_purpose for doc in _result.embedding_documents}
    # assert EmbeddingPurpose.SUMMARY in purposes or EmbeddingPurpose.CODE in purposes


@pytest.mark.asyncio
async def test_processing_time_tracking(orchestrator):
    """Test: 처리 시간 추적"""
    input_data = ChunkingInput(
        file_path="test.py",
        content="def foo():\n    pass",
        language="python",
        repo_id="repo1",
        file_hash="abc123",
    )

    result = await orchestrator.process_file(input_data)

    # 처리 시간이 기록되어야 함
    assert result.processing_time_ms is not None
    assert result.processing_time_ms >= 0


@pytest.mark.asyncio
async def test_error_handling(orchestrator):
    """Test: 에러 처리 (빈 입력)"""
    input_data = ChunkingInput(
        file_path="test.py",
        content="",  # 빈 파일
        language="python",
        repo_id="repo1",
        file_hash="abc123",
    )

    result = await orchestrator.process_file(input_data)

    # 에러가 발생해도 결과 객체는 반환되어야 함
    assert result is not None
    assert result.file_path == "test.py"
