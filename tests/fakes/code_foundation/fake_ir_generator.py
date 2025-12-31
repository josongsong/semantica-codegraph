"""
Fake IR Generator

⚠️  TEST ONLY - DO NOT USE IN PRODUCTION ⚠️

테스트용 간단한 IR 생성기. 실제 IR 생성을 수행하지 않습니다.
프로덕션에서는 FoundationIRGeneratorAdapter를 사용하세요.

See Also:
    - src/contexts/code_foundation/adapters/foundation_adapters.py
    - src/contexts/code_foundation/infrastructure/generators/

Note:
    Returns Infrastructure IRDocument (with nodes) for consistency.
    Domain IRDocument (with symbols) is DEPRECATED.
"""

from codegraph_engine.code_foundation.domain.models import ASTDocument
from codegraph_engine.code_foundation.infrastructure.ir.models import IRDocument, Node, NodeKind, Span


class FakeIRGenerator:
    """테스트용 Fake IR 생성기 (Infrastructure IRDocument 반환)"""

    def generate(self, ast_doc: ASTDocument) -> IRDocument:
        """IR 생성 - Infrastructure IRDocument 반환"""
        nodes = self._extract_nodes(ast_doc.source_code, ast_doc.file_path)

        return IRDocument(
            repo_id="fake-repo",
            snapshot_id="fake-snapshot",
            schema_version="4.1.0",
            nodes=nodes,
            edges=[],
            types=[],
            signatures=[],
            meta={
                "file_path": ast_doc.file_path,
                "language": ast_doc.language.value if hasattr(ast_doc.language, "value") else str(ast_doc.language),
                "ir_generated": True,
            },
        )

    def _extract_nodes(self, code: str, file_path: str) -> list[Node]:
        """코드에서 노드 추출 (간단한 정규식 기반)"""
        nodes = []
        lines = code.splitlines()

        for i, line in enumerate(lines, 1):
            # def 찾기
            if "def " in line:
                name = line.split("def ")[1].split("(")[0].strip()
                nodes.append(
                    Node(
                        id=f"function:{file_path}:{name}",
                        kind=NodeKind.FUNCTION,
                        name=name,
                        file_path=file_path,
                        span=Span(start_line=i, end_line=i, start_col=0, end_col=len(line)),
                    )
                )
            # class 찾기
            elif "class " in line:
                name = line.split("class ")[1].split(":")[0].split("(")[0].strip()
                nodes.append(
                    Node(
                        id=f"class:{file_path}:{name}",
                        kind=NodeKind.CLASS,
                        name=name,
                        file_path=file_path,
                        span=Span(start_line=i, end_line=i, start_col=0, end_col=len(line)),
                    )
                )

        return nodes
