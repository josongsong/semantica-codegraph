"""
IR Generator Adapter

IR 및 Semantic IR 생성 어댑터
"""


class IRGeneratorAdapter:
    """IR 생성 어댑터"""

    def __init__(self, python_ir_generator, semantic_ir_builder):
        """
        초기화

        Args:
            python_ir_generator: PythonIRGenerator
            semantic_ir_builder: SemanticIRBuilder
        """
        self.python_ir_generator = python_ir_generator
        self.semantic_ir_builder = semantic_ir_builder

    def generate_ir(self, ast, file_path: str, language: str):
        """
        IR 생성

        Args:
            ast: AST 객체
            file_path: 파일 경로
            language: 언어

        Returns:
            IRDocument
        """
        # SourceFile 추출
        source = ast.source if hasattr(ast, "source") else None

        # IR 생성
        ir_doc = self.python_ir_generator.generate(
            source=source,
            snapshot_id="default",
            ast=ast,
        )

        return ir_doc

    def generate_semantic_ir(self, ir):
        """
        Semantic IR 생성

        Args:
            ir: IRDocument

        Returns:
            SemanticIRSnapshot
        """
        if not ir or not self.semantic_ir_builder:
            return None

        try:
            semantic_snapshot = self.semantic_ir_builder.build(ir)
            return semantic_snapshot
        except Exception:
            # Semantic IR 실패 시 None 반환 (graceful degradation)
            return None
