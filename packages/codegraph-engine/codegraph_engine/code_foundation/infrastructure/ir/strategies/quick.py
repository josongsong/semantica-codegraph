"""
Quick IR Build Strategy

Layer 1 only for fast feedback (LSP, autocomplete, etc.).
Minimal processing for sub-100ms response times.
"""

import time
from pathlib import Path

from codegraph_shared.common.observability import get_logger
from codegraph_engine.code_foundation.infrastructure.ir.strategies.protocol import (
    IRBuildContext,
    IRBuildResult,
    IRBuildStrategy,
)

logger = get_logger(__name__)


class QuickStrategy(IRBuildStrategy):
    """
    Quick IR build strategy - Layer 1 only.

    Minimal processing for fastest possible feedback.
    Skips all optional layers (occurrences, LSP, semantic, etc.).

    Use this for:
    - LSP hover/completion (needs <100ms response)
    - Syntax highlighting
    - Quick validation during typing
    - Preview/draft mode

    What you get:
    - Structural IR (nodes + edges)
    - Basic symbol information
    - Import relationships

    What you don't get:
    - SCIP occurrences
    - Type information
    - CFG/DFG/BFG
    - Taint analysis
    - Cross-file resolution

    Performance:
    - ~10-50ms per file (vs 200-500ms for full build)
    """

    @property
    def name(self) -> str:
        return "quick"

    async def build(
        self,
        files: list[Path],
        context: IRBuildContext,
    ) -> IRBuildResult:
        """
        Build Layer 1 only IR.

        Uses generators directly for maximum speed.
        """
        from codegraph_engine.code_foundation.infrastructure.generators.java_generator import _JavaIRGenerator
        from codegraph_engine.code_foundation.infrastructure.generators.python_generator import _PythonIRGenerator
        from codegraph_engine.code_foundation.infrastructure.generators.typescript_generator import (
            _TypeScriptIRGenerator,
        )
        from codegraph_engine.code_foundation.infrastructure.ir.cross_file_resolver import GlobalContext
        from codegraph_engine.code_foundation.infrastructure.ir.retrieval_index import RetrievalOptimizedIndex
        from codegraph_engine.code_foundation.infrastructure.parsing import AstTree, SourceFile

        start = time.perf_counter()

        ir_docs = {}
        repo_id = str(context.project_root)

        # Language detection
        ext_to_lang = {
            ".py": "python",
            ".ts": "typescript",
            ".tsx": "typescript",
            ".js": "javascript",
            ".jsx": "javascript",
            ".java": "java",
        }

        # Generator cache
        generators = {
            "python": _PythonIRGenerator(repo_id=repo_id),
            "typescript": _TypeScriptIRGenerator(repo_id=repo_id),
            "javascript": _TypeScriptIRGenerator(repo_id=repo_id),
            "java": _JavaIRGenerator(repo_id=repo_id),
        }

        success_count = 0
        fail_count = 0

        for file_path in files:
            try:
                # Detect language
                lang = ext_to_lang.get(file_path.suffix)
                if not lang:
                    continue

                generator = generators.get(lang)
                if not generator:
                    continue

                # Read and parse
                content = file_path.read_text(encoding="utf-8")
                source = SourceFile.from_content(str(file_path), content, lang)
                ast = AstTree.parse(source)

                # Generate structural IR only
                ir_doc = generator.generate(source, "quick", ast)
                ir_docs[str(file_path)] = ir_doc
                success_count += 1

            except Exception as e:
                logger.debug(f"Quick build failed for {file_path}: {e}")
                fail_count += 1

        elapsed = time.perf_counter() - start

        logger.info(
            f"⚡ Quick build: {success_count}/{len(files)} files "
            f"in {elapsed * 1000:.0f}ms ({success_count / elapsed:.0f} files/sec)"
        )

        return IRBuildResult(
            ir_documents=ir_docs,
            global_ctx=GlobalContext(),  # Empty (no cross-file)
            retrieval_index=RetrievalOptimizedIndex(),  # Empty (no indexing)
            files_processed=success_count,
            files_failed=fail_count,
            elapsed_seconds=elapsed,
            extra={
                "quick_mode": True,
                "layers": ["structural"],
            },
        )
