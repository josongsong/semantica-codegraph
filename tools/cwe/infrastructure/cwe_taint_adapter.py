"""
CWE Taint Analyzer Adapter (Infrastructure → Domain)

Adapts TaintAnalysisService to CWE domain port.

NOTE: Different from src/contexts/security_analysis/.../taint_analyzer_adapter.py
- This adapter: CWE test suite용 (TaintAnalysisService → AnalysisResult)
- That adapter: Security context용 (taint_rules → TaintPath)
"""

import logging
from pathlib import Path

from cwe.domain.ports import AnalysisResult, TaintAnalyzer

logger = logging.getLogger(__name__)


class CWETaintAnalyzer:
    """
    CWE-specific taint analyzer adapter.

    Wraps TaintAnalysisService for CWE test suite.
    Converts exceptions to ERROR results (never raises).

    Design:
    - Input: Python file path
    - Output: AnalysisResult (VULNERABLE/SAFE/ERROR)
    - Never raises exceptions
    """

    def __init__(
        self,
        taint_service,  # TaintAnalysisService
        ir_generator,  # PythonIRGenerator
        semantic_builder,  # DefaultSemanticIrBuilder
    ):
        """
        Initialize adapter.

        Args:
            taint_service: TaintAnalysisService instance
            ir_generator: IR generator instance
            semantic_builder: Semantic IR builder instance
        """
        self.taint_service = taint_service
        self.ir_generator = ir_generator
        self.semantic_builder = semantic_builder

    def analyze_file(self, file_path: Path) -> AnalysisResult:
        """
        Analyze file using taint service.

        Args:
            file_path: Path to Python file

        Returns:
            AnalysisResult (never raises)
        """
        try:
            # Import here to avoid circular dependencies
            from codegraph_engine.code_foundation.infrastructure.parsing.ast_tree import AstTree
            from codegraph_engine.code_foundation.infrastructure.parsing.source_file import SourceFile

            # Read file
            code = file_path.read_text(encoding="utf-8")

            # Generate IR
            source_file = SourceFile(
                file_path=str(file_path),
                content=code,
                language="python",
            )
            ast_tree = AstTree.parse(source_file)
            ir_doc = self.ir_generator.generate(source_file, ast_tree)

            # Build Semantic IR (BFG → CFG → Expression → DFG)
            source_map = {str(file_path): (source_file, ast_tree)}
            semantic_snapshot, _ = self.semantic_builder.build_full(ir_doc, source_map)

            # Update IR with semantic info
            ir_doc.expressions = semantic_snapshot.expressions
            ir_doc.cfg_blocks = semantic_snapshot.cfg_blocks
            ir_doc.cfg_edges = semantic_snapshot.cfg_edges
            ir_doc.bfg_blocks = semantic_snapshot.bfg_blocks
            ir_doc.dfg_snapshot = semantic_snapshot.dfg_snapshot

            # Analyze
            result = self.taint_service.analyze(ir_doc)

            # Check if vulnerabilities found
            if len(result["vulnerabilities"]) > 0:
                return AnalysisResult.VULNERABLE
            else:
                return AnalysisResult.SAFE

        except FileNotFoundError as e:
            logger.warning(f"File not found: {file_path}: {e}")
            return AnalysisResult.ERROR

        except SyntaxError as e:
            logger.warning(f"Syntax error in {file_path}: {e}")
            return AnalysisResult.ERROR

        except UnicodeDecodeError as e:
            logger.warning(f"Encoding error in {file_path}: {e}")
            return AnalysisResult.ERROR

        except Exception as e:
            # Catch-all for unexpected errors
            logger.error(f"Unexpected error analyzing {file_path}: {e}", exc_info=True)
            return AnalysisResult.ERROR
