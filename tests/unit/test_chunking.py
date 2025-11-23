
from core.chunking.hcr import HCRChunker


def test_chunk_code():
    """코드 청킹 테스트"""
    chunker = HCRChunker(chunk_size=5, overlap=2)
    code = "\n".join([f"line {i}" for i in range(20)])

    chunks = chunker.chunk_code(code, "test.py")
    assert len(chunks) > 0
    assert all(c.file_path == "test.py" for c in chunks)


def test_hierarchical_chunks():
    """계층적 청크 테스트"""
    chunker = HCRChunker(chunk_size=5, overlap=2)
    code = "\n".join([f"line {i}" for i in range(10)])

    base_chunks = chunker.chunk_code(code, "test.py")
    all_chunks = chunker.build_hierarchical_chunks(base_chunks)

    assert len(all_chunks) >= len(base_chunks)
    assert any(c.level > 0 for c in all_chunks)
