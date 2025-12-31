"""
Java Language Plugin

ILanguagePlugin implementation for Java.

Strategy: Wrap existing components
- Structural IR: _JavaIRGenerator (existing)
- Semantic IR: DefaultSemanticIrBuilder (existing)
- LSP: JdtlsAdapter (existing)
- Taint: java.atoms.yaml (existing)
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


class JavaPlugin:
    """
    Java language plugin.

    Implements ILanguagePlugin by wrapping existing Java components.

    Components wrapped:
    - _JavaIRGenerator (Layer 1)
    - DefaultSemanticIrBuilder (Layer 5)
    - JdtlsAdapter (LSP)
    - java.atoms.yaml (Taint)

    Example:
        plugin = JavaPlugin()
        generator = plugin.create_structural_generator("my-repo")
    """

    # ================================================================
    # Identity
    # ================================================================

    @property
    def language(self) -> str:
        """Return 'java'."""
        return "java"

    @property
    def supported_extensions(self) -> set[str]:
        """Return Java file extensions."""
        return {".java"}

    @property
    def typing_mode(self) -> TypingMode:
        """Java is statically typed."""
        return TypingMode.STATIC

    # ================================================================
    # Layer 1: Structural IR
    # ================================================================

    def create_structural_generator(self, repo_id: str) -> "IRGenerator":
        """
        Create Java IR generator.

        Args:
            repo_id: Repository identifier

        Returns:
            _JavaIRGenerator instance
        """
        from codegraph_engine.code_foundation.infrastructure.generators.java_generator import (
            _JavaIRGenerator,
        )

        return _JavaIRGenerator(repo_id=repo_id)

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

        Args:
            lsp_adapter: LSP adapter for type enrichment (unused for now)
            enable_ssa: Enable SSA/Dominator analysis

        Returns:
            DefaultSemanticIrBuilder instance

        TODO:
            Integrate JDTLS adapter for Java type enrichment.
        """
        from codegraph_engine.code_foundation.infrastructure.semantic_ir.builder import (
            DefaultSemanticIrBuilder,
        )
        from codegraph_engine.code_foundation.infrastructure.semantic_ir.expression.builder import (
            ExpressionBuilder,
        )

        expression_builder = ExpressionBuilder()

        if lsp_adapter:
            logger.warning(
                "lsp_adapter_ignored",
                language=self.language,
                reason="JDTLS integration not implemented",
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
        Create JDTLS LSP adapter.

        Args:
            project_root: Project root directory
            config: LSP configuration (optional)

        Returns:
            JdtlsAdapter instance or None
        """
        try:
            from codegraph_engine.code_foundation.infrastructure.ir.lsp.jdtls import (
                JdtlsAdapter,
            )

            return JdtlsAdapter(project_root, config or {})
        except ImportError as e:
            logger.warning(
                "jdtls_import_failed",
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
        Get Java taint atoms file path.

        Args:
            rules_dir: Base rules directory

        Returns:
            Path to java.atoms.yaml if exists
        """
        path = rules_dir / "atoms" / "java.atoms.yaml"
        return path if path.exists() else None

    def __repr__(self) -> str:
        """String representation."""
        return f"JavaPlugin(language={self.language}, typing_mode={self.typing_mode.value})"
