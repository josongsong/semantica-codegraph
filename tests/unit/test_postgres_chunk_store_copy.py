"""
Unit Test: PostgresChunkStore COPY 최적화

COPY 명령을 사용한 bulk insert 정합성 검증
"""

from unittest.mock import AsyncMock, MagicMock, call

import pytest

from codegraph_engine.code_foundation.infrastructure.chunk.models import Chunk
from codegraph_engine.code_foundation.infrastructure.chunk.store_postgres import PostgresChunkStore


@pytest.fixture
def mock_postgres_store():
    """Mock PostgresStore"""
    store = MagicMock()
    pool = AsyncMock()
    store._ensure_pool = AsyncMock(return_value=pool)
    return store


@pytest.fixture
def chunk_store(mock_postgres_store):
    """PostgresChunkStore instance"""
    return PostgresChunkStore(mock_postgres_store)


@pytest.fixture
def sample_chunks():
    """Sample chunks for testing"""
    return [
        Chunk(
            chunk_id="chunk:repo1:file:main.py",
            repo_id="repo1",
            snapshot_id="snap1",
            project_id=None,
            module_path=None,
            file_path="main.py",
            parent_id=None,
            children=[],
            kind="file",
            fqn="main.py",
            language="python",
            symbol_visibility="public",
            symbol_id="sym1",
            symbol_owner_id=None,
            start_line=1,
            end_line=10,
            original_start_line=1,
            original_end_line=10,
            content_hash="hash1",
            version=1,
            is_deleted=False,
            last_indexed_commit=None,
            summary="Test file",
            importance=1.0,
            attrs={"test_key": "test_value"},
            is_test=False,
            is_overlay=False,
            overlay_session_id=None,
            base_chunk_id=None,
        ),
        Chunk(
            chunk_id="chunk:repo1:func:test",
            repo_id="repo1",
            snapshot_id="snap1",
            project_id=None,
            module_path=None,
            file_path="main.py",
            parent_id="chunk:repo1:file:main.py",
            children=[],
            kind="function",
            fqn="test",
            language="python",
            symbol_visibility="public",
            symbol_id="sym2",
            symbol_owner_id=None,
            start_line=5,
            end_line=8,
            original_start_line=5,
            original_end_line=8,
            content_hash="hash2",
            version=1,
            is_deleted=False,
            last_indexed_commit=None,
            summary="Test function",
            importance=0.8,
            attrs={},
            is_test=True,
            is_overlay=False,
            overlay_session_id=None,
            base_chunk_id=None,
        ),
    ]


@pytest.mark.asyncio
async def test_upsert_batch_uses_copy(chunk_store, sample_chunks):
    """
    COPY 명령이 올바르게 호출되는지 검증
    """
    mock_conn = AsyncMock()

    await chunk_store._upsert_batch(mock_conn, sample_chunks)

    # 검증 1: CREATE TEMP TABLE 호출
    create_table_calls = [call for call in mock_conn.execute.call_args_list if "CREATE TEMP TABLE" in str(call)]
    assert len(create_table_calls) == 1, "CREATE TEMP TABLE should be called once"

    # 검증 2: copy_records_to_table 호출
    assert mock_conn.copy_records_to_table.called, "copy_records_to_table should be called"
    copy_call = mock_conn.copy_records_to_table.call_args

    # asyncpg API: copy_records_to_table(table_name, records=..., columns=...)
    assert copy_call[0][0] == "temp_chunks", "Table name should be temp_chunks"

    # records는 keyword argument
    if "records" in copy_call[1]:
        assert len(copy_call[1]["records"]) == 2, "Should copy 2 records"

    # 검증 3: INSERT ... SELECT ... ON CONFLICT 호출
    insert_calls = [
        call for call in mock_conn.execute.call_args_list if "INSERT INTO chunks" in str(call) and "SELECT" in str(call)
    ]
    assert len(insert_calls) == 1, "INSERT ... SELECT should be called once"


@pytest.mark.asyncio
async def test_upsert_batch_empty_chunks(chunk_store):
    """
    빈 청크 리스트 처리
    """
    mock_conn = AsyncMock()

    await chunk_store._upsert_batch(mock_conn, [])

    # 빈 리스트는 아무 작업도 하지 않아야 함
    assert not mock_conn.execute.called
    assert not mock_conn.copy_records_to_table.called


@pytest.mark.asyncio
async def test_upsert_batch_deduplication(chunk_store):
    """
    중복 chunk_id 제거 검증
    """
    duplicate_chunks = [
        Chunk(
            chunk_id="chunk:repo1:file:main.py",
            repo_id="repo1",
            snapshot_id="snap1",
            project_id=None,
            module_path=None,
            file_path="main.py",
            parent_id=None,
            children=[],
            kind="file",
            fqn="main.py",
            language="python",
            symbol_visibility="public",
            symbol_id="sym1",
            symbol_owner_id=None,
            start_line=1,
            end_line=10,
            original_start_line=1,
            original_end_line=10,
            content_hash="hash1",
            version=1,
            is_deleted=False,
            last_indexed_commit=None,
            summary="Version 1",
            importance=1.0,
            attrs={},
            is_test=False,
            is_overlay=False,
            overlay_session_id=None,
            base_chunk_id=None,
        ),
        Chunk(
            chunk_id="chunk:repo1:file:main.py",  # 같은 ID
            repo_id="repo1",
            snapshot_id="snap1",
            project_id=None,
            module_path=None,
            file_path="main.py",
            parent_id=None,
            children=[],
            kind="file",
            fqn="main.py",
            language="python",
            symbol_visibility="public",
            symbol_id="sym1",
            symbol_owner_id=None,
            start_line=1,
            end_line=10,
            original_start_line=1,
            original_end_line=10,
            content_hash="hash2",
            version=2,
            is_deleted=False,
            last_indexed_commit=None,
            summary="Version 2",  # 최신 버전
            importance=1.0,
            attrs={},
            is_test=False,
            is_overlay=False,
            overlay_session_id=None,
            base_chunk_id=None,
        ),
    ]

    mock_conn = AsyncMock()

    await chunk_store._upsert_batch(mock_conn, duplicate_chunks)

    # COPY 호출시 1개만 전달되어야 함 (마지막 occurrence)
    copy_call = mock_conn.copy_records_to_table.call_args
    records = copy_call[1]["records"] if "records" in copy_call[1] else copy_call[0][1]

    assert len(records) == 1, "Duplicates should be removed"
    # 최신 버전의 summary가 유지되어야 함
    assert "Version 2" in str(records[0])


@pytest.mark.asyncio
async def test_upsert_batch_attrs_serialization(chunk_store, sample_chunks):
    """
    attrs + children 필드 JSON 직렬화 검증
    """
    mock_conn = AsyncMock()

    # children이 있는 청크 추가
    sample_chunks[0].children = ["child1", "child2"]
    sample_chunks[0].attrs = {"key1": "value1", "key2": 123}

    await chunk_store._upsert_batch(mock_conn, sample_chunks)

    # COPY 호출시 전달된 records 확인
    copy_call = mock_conn.copy_records_to_table.call_args
    records = copy_call[1]["records"] if "records" in copy_call[1] else copy_call[0][1]

    # 첫 번째 record의 attrs 필드 (23번째 인덱스)
    import json

    attrs_json = records[0][23]
    attrs_data = json.loads(attrs_json)

    assert "children" in attrs_data
    assert attrs_data["children"] == ["child1", "child2"]
    assert attrs_data["key1"] == "value1"
    assert attrs_data["key2"] == 123


@pytest.mark.asyncio
async def test_upsert_batch_nullable_fields(chunk_store):
    """
    Nullable 필드 처리 검증
    """
    chunk_with_nulls = Chunk(
        chunk_id="chunk:repo1:file:test.py",
        repo_id="repo1",
        snapshot_id="snap1",
        project_id=None,  # NULL
        module_path=None,  # NULL
        file_path="test.py",
        parent_id=None,  # NULL
        children=[],
        kind="file",
        fqn="test.py",
        language=None,  # NULL
        symbol_visibility=None,  # NULL
        symbol_id=None,  # NULL
        symbol_owner_id=None,  # NULL
        start_line=None,  # NULL
        end_line=None,  # NULL
        original_start_line=None,  # NULL
        original_end_line=None,  # NULL
        content_hash=None,  # NULL
        version=1,
        is_deleted=False,
        last_indexed_commit=None,  # NULL
        summary=None,  # NULL
        importance=None,  # NULL
        attrs={},
        is_test=None,  # NULL
        is_overlay=False,
        overlay_session_id=None,  # NULL
        base_chunk_id=None,  # NULL
    )

    mock_conn = AsyncMock()

    # NULL 값이 있어도 예외 없이 처리되어야 함
    await chunk_store._upsert_batch(mock_conn, [chunk_with_nulls])

    assert mock_conn.copy_records_to_table.called
    copy_call = mock_conn.copy_records_to_table.call_args
    records = copy_call[1]["records"] if "records" in copy_call[1] else copy_call[0][1]

    # NULL 값들이 None으로 전달되어야 함
    record = records[0]
    assert record[3] is None  # project_id
    assert record[4] is None  # module_path
    assert record[9] is None  # language
