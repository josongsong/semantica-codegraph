"""
TypeScript Language Plugin

ILanguagePlugin implementation for TypeScript/JavaScript.

Strategy: Wrap existing components
- Structural IR: _TypeScriptIRGenerator (existing)
- Semantic IR: DefaultSemanticIrBuilder (existing)
- LSP: TypeScriptAdapter (existing)
- Taint: typescript.atoms.yaml (existing)
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


class TypeScriptPlugin:
    """
    TypeScript/JavaScript language plugin.

    Implements ILanguagePlugin by wrapping existing TypeScript components.

    Components wrapped:
    - _TypeScriptIRGenerator (Layer 1)
    - DefaultSemanticIrBuilder (Layer 5)
    - TypeScriptAdapter (LSP)
    - typescript.atoms.yaml (Taint)

    Supports:
    - TypeScript (.ts, .tsx)
    - JavaScript (.js, .jsx)

    Example:
        plugin = TypeScriptPlugin()
        generator = plugin.create_structural_generator("my-repo")
        ir_doc = generator.generate(source, snapshot_id)
    """

    # ================================================================
    # Identity
    # ================================================================

    @property
    def language(self) -> str:
        """Return 'typescript'."""
        return "typescript"

    @property
    def supported_extensions(self) -> set[str]:
        """Return TypeScript/JavaScript file extensions."""
        return {".ts", ".tsx", ".js", ".jsx"}

    @property
    def typing_mode(self) -> TypingMode:
        """TypeScript is gradually typed."""
        return TypingMode.GRADUAL

    # ================================================================
    # Layer 1: Structural IR
    # ================================================================

    def create_structural_generator(self, repo_id: str) -> "IRGenerator":
        """
        Create TypeScript IR generator.

        Wraps existing _TypeScriptIRGenerator.

        Args:
            repo_id: Repository identifier

        Returns:
            _TypeScriptIRGenerator instance
        """
        from codegraph_engine.code_foundation.infrastructure.generators.typescript_generator import (
            _TypeScriptIRGenerator,
        )

        return _TypeScriptIRGenerator(repo_id=repo_id)

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
            Future: Return TypeScript-specific builder with optimizations.

        Args:
            lsp_adapter: LSP adapter for type enrichment (unused for now)
            enable_ssa: Enable SSA/Dominator analysis

        Returns:
            DefaultSemanticIrBuilder instance

        TODO:
            Integrate lsp_adapter with ExpressionBuilder.
            Need sync/async adapter conversion.
        """
        # v2: Create TypeScript-specific expression builder
        from codegraph_engine.code_foundation.infrastructure.language_plugin.typescript.expression_builder import (
            TypeScriptExpressionBuilder,
        )
        from codegraph_engine.code_foundation.infrastructure.semantic_ir.builder import (
            DefaultSemanticIrBuilder,
        )

        # TypeScript 전용 builder
        expression_builder = TypeScriptExpressionBuilder(lsp_adapter=lsp_adapter)

        if lsp_adapter:
            logger.warning(
                "lsp_adapter_ignored",
                language=self.language,
                reason="Async/Sync adapter conversion not implemented",
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
        Create TypeScript LSP adapter.

        Args:
            project_root: Project root directory
            config: LSP configuration (optional)

        Returns:
            TypeScriptAdapter instance or None
        """
        try:
            from codegraph_engine.code_foundation.infrastructure.ir.lsp.typescript import (
                TypeScriptAdapter,
            )

            return TypeScriptAdapter(project_root, config or {})
        except ImportError as e:
            logger.warning(
                "typescript_lsp_import_failed",
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
        Get TypeScript taint atoms file path.

        Args:
            rules_dir: Base rules directory

        Returns:
            Path to typescript.atoms.yaml if exists
        """
        path = rules_dir / "atoms" / "typescript.atoms.yaml"
        return path if path.exists() else None

    # ================================================================
    # Utility Methods
    # ================================================================

    def __repr__(self) -> str:
        """String representation."""
        return f"TypeScriptPlugin(language={self.language}, typing_mode={self.typing_mode.value})"
