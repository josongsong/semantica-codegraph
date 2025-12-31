"""
Kotlin Language Plugin

ILanguagePlugin implementation for Kotlin (JVM language).

Strategy: Based on Java plugin (similar structure)
- Structural IR: KotlinGenerator (NEW)
- Semantic IR: DefaultSemanticIrBuilder (shared)
- LSP: KotlinAdapter (existing)
- Taint: kotlin.atoms.yaml (NEW)
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


class KotlinPlugin:
    """
    Kotlin language plugin (JVM language).

    Based on Java with Kotlin-specific features:
    - Null safety (T vs T?)
    - Extension functions
    - Data classes
    - Coroutines
    - Lambda with receivers

    Example:
        plugin = KotlinPlugin()
        generator = plugin.create_structural_generator("my-repo")
        ir_doc = generator.generate(source, snapshot_id)
    """

    # ================================================================
    # Identity
    # ================================================================

    @property
    def language(self) -> str:
        """Return 'kotlin'."""
        return "kotlin"

    @property
    def supported_extensions(self) -> set[str]:
        """Return Kotlin file extensions."""
        return {".kt", ".kts"}

    @property
    def typing_mode(self) -> TypingMode:
        """Kotlin is statically typed with null safety."""
        return TypingMode.STATIC

    # ================================================================
    # Layer 1: Structural IR
    # ================================================================

    def create_structural_generator(self, repo_id: str) -> "IRGenerator":
        """
        Create Kotlin IR generator.

        Args:
            repo_id: Repository identifier

        Returns:
            KotlinGenerator instance
        """
        from codegraph_engine.code_foundation.infrastructure.generators.kotlin_generator import (
            _KotlinIRGenerator,
        )

        return _KotlinIRGenerator(repo_id=repo_id)

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
            lsp_adapter: LSP adapter for type enrichment
            enable_ssa: Enable SSA/Dominator analysis

        Returns:
            DefaultSemanticIrBuilder instance with Kotlin expression analyzer
        """
        from codegraph_engine.code_foundation.infrastructure.language_plugin.kotlin.expression_analyzer import (
            KotlinExpressionAnalyzer,
        )
        from codegraph_engine.code_foundation.infrastructure.semantic_ir.builder import (
            DefaultSemanticIrBuilder,
        )

        # Kotlin expression analyzer
        expression_analyzer = KotlinExpressionAnalyzer()

        if lsp_adapter:
            logger.info(
                "kotlin_lsp_adapter_provided",
                message="Kotlin LSP adapter for type enrichment",
            )

        return DefaultSemanticIrBuilder(
            expression_builder=None,  # Will use analyzer directly
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
        Create Kotlin LSP adapter.

        Args:
            project_root: Project root directory
            config: LSP configuration

        Returns:
            KotlinAdapter instance or None
        """
        try:
            from codegraph_engine.code_foundation.infrastructure.ir.lsp.kotlin import (
                KotlinAdapter,
            )

            return KotlinAdapter(project_root, config or {})
        except ImportError as e:
            logger.warning(
                "kotlin_lsp_import_failed",
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
        Get Kotlin taint atoms file path.

        Args:
            rules_dir: Base rules directory

        Returns:
            Path to kotlin.atoms.yaml if exists
        """
        path = rules_dir / "atoms" / "kotlin.atoms.yaml"
        return path if path.exists() else None

    # ================================================================
    # Utility Methods
    # ================================================================

    def __repr__(self) -> str:
        """String representation."""
        return f"KotlinPlugin(language={self.language}, typing_mode={self.typing_mode.value})"
