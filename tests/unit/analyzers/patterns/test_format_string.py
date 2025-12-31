"""
Format String Detector Tests

RFC-024 Option 3: CWE-134 탐지 검증
"""

import pytest

from codegraph_engine.code_foundation.infrastructure.analyzers.patterns.format_string import FormatStringDetector
from codegraph_engine.code_foundation.infrastructure.ir.models.core import Node, NodeKind, Span
from codegraph_engine.code_foundation.infrastructure.ir.models.document import IRDocument


class TestFormatStringDetector:
    """Format String 탐지"""

    def test_detector_creation(self):
        """Detector 생성"""
        detector = FormatStringDetector()
        assert detector is not None

    def test_c_printf_detected(self):
        """C printf() 탐지"""
        detector = FormatStringDetector()

        # Mock IR with printf call
        # Note: NodeKind에는 CALL 없음, Expression.kind에 있음
        # 간단히 FUNCTION으로 대체 (Integration Test에서 실제 검증)
        node = Node(
            id="call:1",
            kind=NodeKind.FUNCTION,  # NodeKind에는 CALL 없음
            fqn="test::printf",
            file_path="test.c",
            span=Span(10, 0, 10, 20),
            language="c",
            attrs={"callee_name": "printf"},
        )

        ir_doc = IRDocument(
            repo_id="test",
            snapshot_id="v1",
            nodes=[node],
        )

        vulns = detector.detect(ir_doc)

        assert len(vulns) == 1
        assert vulns[0].function == "printf"
        assert vulns[0].severity == "critical"

    def test_sprintf_detected(self):
        """sprintf() 탐지"""
        detector = FormatStringDetector()

        node = Node(
            id="call:2",
            kind=NodeKind.FUNCTION,
            fqn="test::sprintf",
            file_path="test.c",
            span=Span(20, 0, 20, 30),
            language="c",
            attrs={"callee_name": "sprintf"},
        )

        ir_doc = IRDocument(repo_id="test", snapshot_id="v1", nodes=[node])

        vulns = detector.detect(ir_doc)

        assert len(vulns) == 1
        assert vulns[0].severity == "critical"

    def test_python_format_detected(self):
        """Python str.format() 탐지"""
        detector = FormatStringDetector()

        node = Node(
            id="call:3",
            kind=NodeKind.METHOD,
            fqn="test::format",
            file_path="test.py",
            span=Span(30, 0, 30, 40),
            language="python",
            attrs={"method_name": "format"},
        )

        ir_doc = IRDocument(repo_id="test", snapshot_id="v1", nodes=[node])

        vulns = detector.detect(ir_doc)

        assert len(vulns) == 1
        assert vulns[0].severity == "medium"  # Python은 덜 위험

    def test_no_format_calls(self):
        """Format 호출 없으면 빈 리스트"""
        detector = FormatStringDetector()

        node = Node(
            id="func:1",
            kind=NodeKind.FUNCTION,
            fqn="test",
            file_path="test.c",
            span=Span(1, 0, 10, 0),
            language="c",
        )

        ir_doc = IRDocument(repo_id="test", snapshot_id="v1", nodes=[node])

        vulns = detector.detect(ir_doc)

        assert len(vulns) == 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
