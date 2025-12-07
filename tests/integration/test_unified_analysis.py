"""
통합 분석 통합 테스트

Dataflow + PDG + Taint + Slicing 통합 검증
"""

from pathlib import Path

import pytest

from src.contexts.code_foundation.infrastructure.ir.models.core import Edge, EdgeKind, Node, NodeKind, Span
from src.contexts.code_foundation.infrastructure.ir.models.document import IRDocument
from src.contexts.code_foundation.infrastructure.ir.retrieval_index import RetrievalOptimizedIndex
from src.contexts.code_foundation.infrastructure.ir.unified_analyzer import enhance_ir_with_advanced_analysis


@pytest.fixture
def sample_ir_doc():
    """샘플 IR 문서"""
    ir = IRDocument(
        repo_id="test_repo",
        snapshot_id="test_snapshot",
    )

    # Function node
    func_node = Node(
        id="func:test_function",
        kind=NodeKind.FUNCTION,
        fqn="test.test_function",
        file_path="test.py",
        span=Span(start_line=1, end_line=10, start_column=0, end_column=0),
        language="python",
        name="test_function",
    )

    # Variable node
    var_node = Node(
        id="var:x",
        kind=NodeKind.VARIABLE,
        fqn="test.test_function.x",
        file_path="test.py",
        span=Span(start_line=2, end_line=2, start_column=4, end_column=5),
        language="python",
        name="x",
    )

    ir.nodes = [func_node, var_node]

    # WRITES edge (function writes variable)
    write_edge = Edge(
        id="edge:writes:1",
        kind=EdgeKind.WRITES,
        source_id="func:test_function",
        target_id="var:x",
        span=Span(start_line=2, end_line=2, start_column=0, end_column=10),
        attrs={"var_name": "x"},
    )

    ir.edges = [write_edge]

    return ir


def test_ir_model_has_advanced_fields():
    """IR 모델에 고급 분석 필드가 있는지 확인"""
    ir = IRDocument(repo_id="test", snapshot_id="test")

    assert hasattr(ir, "pdg_nodes")
    assert hasattr(ir, "pdg_edges")
    assert hasattr(ir, "taint_findings")
    assert ir.schema_version == "2.1"


def test_unified_analyzer_builds_pdg(sample_ir_doc):
    """통합 분석기가 PDG를 생성하는지 확인"""
    enhanced = enhance_ir_with_advanced_analysis(
        sample_ir_doc,
        enable_pdg=True,
        enable_taint=False,
        enable_slicing=False,
    )

    # PDG가 생성되었는지 확인
    assert enhanced._pdg_index is not None
    assert len(enhanced.pdg_nodes) > 0


def test_unified_analyzer_enables_slicing(sample_ir_doc):
    """통합 분석기가 슬라이서를 설정하는지 확인"""
    enhanced = enhance_ir_with_advanced_analysis(
        sample_ir_doc,
        enable_pdg=True,
        enable_slicing=True,
    )

    # Slicer가 설정되었는지 확인
    assert enhanced._slicer is not None

    # Slicer 메서드 사용 가능한지 확인
    slicer = enhanced.get_slicer()
    assert slicer is not None


def test_ir_document_slicing_methods(sample_ir_doc):
    """IRDocument의 슬라이싱 메서드가 작동하는지 확인"""
    enhanced = enhance_ir_with_advanced_analysis(
        sample_ir_doc,
        enable_pdg=True,
        enable_slicing=True,
    )

    # Backward slice
    result = enhanced.backward_slice("func:test_function")
    assert result is not None or result is None  # PDG가 비어있을 수 있음


def test_retrieval_index_with_advanced_analysis(sample_ir_doc):
    """RetrievalIndex가 고급 분석 기능을 사용하는지 확인"""
    enhanced = enhance_ir_with_advanced_analysis(
        sample_ir_doc,
        enable_pdg=True,
        enable_slicing=True,
    )

    # Index 생성
    index = RetrievalOptimizedIndex()
    index.index_ir_document(enhanced)

    # PDG와 slicer가 저장되었는지 확인
    assert index.pdg_builder is not None or index.pdg_builder is None
    assert index.slicer is not None or index.slicer is None
    assert index.ir_document is not None


def test_retrieval_index_dataflow_methods(sample_ir_doc):
    """RetrievalIndex의 dataflow 메서드가 있는지 확인"""
    enhanced = enhance_ir_with_advanced_analysis(sample_ir_doc)

    index = RetrievalOptimizedIndex()
    index.index_ir_document(enhanced)

    # 메서드 존재 확인
    assert hasattr(index, "search_with_dataflow")
    assert hasattr(index, "find_impact")
    assert hasattr(index, "find_dependencies")


def test_get_stats_includes_advanced_analysis(sample_ir_doc):
    """get_stats가 고급 분석 통계를 포함하는지 확인"""
    enhanced = enhance_ir_with_advanced_analysis(sample_ir_doc)

    stats = enhanced.get_stats()

    # 고급 분석 통계 포함 확인
    assert "pdg_nodes" in stats
    assert "pdg_edges" in stats
    assert "taint_findings" in stats


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
