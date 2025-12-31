"""
Python Language Plugin

ILanguagePlugin implementation for Python.

Strategy: Wrap existing components (no new implementation needed for Phase 1)
- Structural IR: _PythonIRGenerator (existing)
- Semantic IR: DefaultSemanticIrBuilder (existing)
- LSP: PyrightAdapter (existing)
- Taint: python.atoms.yaml (existing)

This is a "thin wrapper" that delegates to existing implementations.
Future: Replace with language-specific optimizations.
"""

from pathlib import Path
from typing import TYPE_CHECKING, Any

from codegraph_shared.common.observability import get_logger
from codegraph_engine.code_foundation.infrastructure.language_plugin.protocols import (
    TypingMode,
)

if TYPE_CHECKING:
    from codegraph_engine.code_foundation.domain.ports.semantic_ir_ports import SemanticIRBuilderPort
    from codegraph_engine.code_foundation.infrastructure.generators.base import IRGenerator
    from codegraph_engine.code_foundation.infrastructure.ir.lsp.adapter import IAsyncLSPAdapter

logger = get_logger(__name__)


class PythonPlugin:
    """
    Python language plugin.

    Implements ILanguagePlugin by wrapping existing Python components.

    Components wrapped:
    - _PythonIRGenerator (Layer 1)
    - DefaultSemanticIrBuilder (Layer 5)
    - PyrightAdapter (LSP)
    - python.atoms.yaml (Taint)

    Example:
        plugin = PythonPlugin()

        # Get generator
        generator = plugin.create_structural_generator("my-repo")
        ir_doc = generator.generate(source, snapshot_id)

        # Get LSP adapter
        lsp = plugin.create_lsp_adapter(project_root)
    """

    # ================================================================
    # Identity
    # ================================================================

    @property
    def language(self) -> str:
        """Return 'python'."""
        return "python"

    @property
    def supported_extensions(self) -> set[str]:
        """Return Python file extensions."""
        return {".py", ".pyi"}

    @property
    def typing_mode(self) -> TypingMode:
        """Python is dynamically typed."""
        return TypingMode.DYNAMIC

    # ================================================================
    # Layer 1: Structural IR
    # ================================================================

    def create_structural_generator(self, repo_id: str) -> "IRGenerator":
        """
        Create Python IR generator.

        Wraps existing _PythonIRGenerator.

        Args:
            repo_id: Repository identifier

        Returns:
            _PythonIRGenerator instance
        """
        from codegraph_engine.code_foundation.infrastructure.generators.python_generator import (
            _PythonIRGenerator,
        )

        return _PythonIRGenerator(repo_id=repo_id)

    # ================================================================
    # Layer 5: Semantic IR
    # ================================================================

    def create_semantic_builder(
        self,
        lsp_adapter: "IAsyncLSPAdapter | None" = None,
        enable_ssa: bool = True,
    ) -> "SemanticIRBuilderPort":
        """
        Create semantic IR builder.

        Wraps existing DefaultSemanticIrBuilder.

        Note:
            Currently returns the shared DefaultSemanticIrBuilder.
            Future: Return Python-specific builder with optimizations.

        Args:
            lsp_adapter: LSP adapter for type enrichment (unused for now)
            enable_ssa: Enable SSA/Dominator analysis

        Returns:
            DefaultSemanticIrBuilder instance

        TODO:
            Properly integrate lsp_adapter with ExpressionBuilder.
            Current ExpressionBuilder expects PyrightExternalAnalyzer,
            not IAsyncLSPAdapter. Need adapter conversion layer.
        """
        # ExpressionBuilder integration
        # NOTE: lsp_adapter is IAsyncLSPAdapter, but ExpressionBuilder expects
        # PyrightExternalAnalyzer (sync). Conversion layer needed in Phase 2.5.
        # v2: Create Python-specific expression analyzer
        from codegraph_engine.code_foundation.infrastructure.language_plugin.python.expression_analyzer import (
            PythonExpressionAnalyzer,
        )
        from codegraph_engine.code_foundation.infrastructure.semantic_ir.builder import (
            DefaultSemanticIrBuilder,
        )
        from codegraph_engine.code_foundation.infrastructure.semantic_ir.expression.builder import (
            ExpressionBuilder,
        )

        python_analyzer = PythonExpressionAnalyzer(lsp_adapter=None)

        # Create ExpressionBuilder with Python analyzer
        expression_builder = ExpressionBuilder(
            expression_analyzer=python_analyzer,
        )

        if lsp_adapter:
            logger.warning(
                "lsp_adapter_ignored",
                reason="ExpressionBuilder expects sync Pyright, got async LSP adapter",
                todo="Implement adapter conversion in Phase 2.5",
            )

        return DefaultSemanticIrBuilder(
            expression_builder=expression_builder,
        )

    # ================================================================
    # LSP Integration
    # ================================================================

    def create_lsp_adapter(
        self,
        project_root: Path,
        config: dict[str, Any] | None = None,
    ) -> "IAsyncLSPAdapter | None":
        """
        Create Pyright LSP adapter.

        Args:
            project_root: Project root directory
            config: LSP configuration (optional)
                - timeout: Request timeout in seconds
                - pyright_mode: "fast", "balanced", "thorough"

        Returns:
            PyrightAdapter instance or None if unavailable
        """
        try:
            from codegraph_engine.code_foundation.infrastructure.ir.lsp.pyright import (
                PyrightAdapter,
            )

            return PyrightAdapter(project_root, config or {})
        except ImportError as e:
            logger.warning(
                "pyright_import_failed",
                error=str(e),
                project_root=str(project_root),
            )
            return None
        except Exception as e:
            logger.warning(
                "lsp_adapter_init_failed",
                language=self.language,
                error=str(e),
                project_root=str(project_root),
            )
            return None

    # ================================================================
    # Taint Rules
    # ================================================================

    def get_taint_atoms_path(self, rules_dir: Path) -> Path | None:
        """
        Get Python taint atoms file path.

        Args:
            rules_dir: Base rules directory

        Returns:
            Path to python.atoms.yaml if exists
        """
        path = rules_dir / "atoms" / "python.atoms.yaml"
        return path if path.exists() else None

    # ================================================================
    # Utility Methods
    # ================================================================

    def __repr__(self) -> str:
        """String representation."""
        return f"PythonPlugin(language={self.language}, typing_mode={self.typing_mode.value})"


# Note: Protocol compliance is verified in tests
# See: tests/unit/language_plugin/test_registry_integration.py
