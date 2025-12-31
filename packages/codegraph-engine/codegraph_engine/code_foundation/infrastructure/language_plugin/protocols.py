"""
Language Plugin Protocols

Core interfaces for multi-language support.

Design Principles:
1. Reuse existing Ports from domain/ports/
2. Minimal new abstractions
3. Template Method for ExpressionAnalyzer
4. Feature Flag for gradual migration

Existing Ports (reused):
- IRGenerator (generators/base.py)
- SemanticIRBuilderPort (domain/ports/semantic_ir_ports.py)
- ExpressionBuilderPort (domain/ports/semantic_ir_ports.py)
"""

from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

if TYPE_CHECKING:
    from codegraph_engine.code_foundation.domain.ports.semantic_ir_ports import SemanticIRBuilderPort
    from codegraph_engine.code_foundation.infrastructure.generators.base import IRGenerator
    from codegraph_engine.code_foundation.infrastructure.ir.lsp.adapter import IAsyncLSPAdapter


class TypingMode(str, Enum):
    """
    Language typing mode.

    Used for type-aware analysis in UnifiedAnalyzer.

    Examples:
        - STATIC: Java, C++, Rust, Go
        - DYNAMIC: Python, JavaScript, Ruby
        - GRADUAL: TypeScript (optional typing)
    """

    STATIC = "static"
    """Strict compile-time type checking (Java, C++, Rust, Go)"""

    DYNAMIC = "dynamic"
    """Runtime type checking only (Python, JavaScript, Ruby)"""

    GRADUAL = "gradual"
    """Optional static typing (TypeScript)"""

    UNKNOWN = "unknown"
    """Unknown or mixed"""


@runtime_checkable
class ILanguagePlugin(Protocol):
    """
    Language-specific plugin interface.

    Each supported language implements this interface to provide:
    - Layer 1: Structural IR generator
    - Layer 5: Semantic IR builder (optional)
    - Layer 5: Expression analyzer (optional)
    - LSP adapter (optional)
    - Taint rules path (optional)

    Existing components are reused:
    - generators/*.py → create_structural_generator()
    - semantic_ir/builder.py → create_semantic_builder()
    - ir/lsp/*.py → create_lsp_adapter()

    Implementation location:
    - language_plugin/python/plugin.py
    - language_plugin/typescript/plugin.py
    - language_plugin/java/plugin.py

    Example:
        class PythonPlugin:
            @property
            def language(self) -> str:
                return "python"

            def create_structural_generator(self, repo_id: str) -> IRGenerator:
                return _PythonIRGenerator(repo_id=repo_id)
    """

    # ================================================================
    # Identity
    # ================================================================

    @property
    def language(self) -> str:
        """
        Language identifier.

        Returns:
            Lowercase language name (e.g., "python", "typescript", "java")

        Contract:
            - Must be unique across all registered plugins
            - Must match file extension mapping
        """
        ...

    @property
    def supported_extensions(self) -> set[str]:
        """
        Supported file extensions.

        Returns:
            Set of extensions including dot (e.g., {".py", ".pyi"})

        Contract:
            - Extensions must start with "."
            - Used for automatic language detection
        """
        ...

    @property
    def typing_mode(self) -> TypingMode:
        """
        Language typing mode.

        Returns:
            TypingMode enum value

        Usage:
            Used by UnifiedAnalyzer for type-aware analysis.
            - DYNAMIC: Consider possible_types (type set)
            - STATIC: Use declared type directly
            - GRADUAL: Hybrid approach
        """
        ...

    # ================================================================
    # Layer 1: Structural IR
    # ================================================================

    def create_structural_generator(self, repo_id: str) -> "IRGenerator":
        """
        Create structural IR generator.

        Args:
            repo_id: Repository identifier

        Returns:
            IRGenerator instance (from generators/base.py)

        Contract:
            - Must return existing generator implementation
            - e.g., _PythonIRGenerator, _TypeScriptIRGenerator

        Example:
            def create_structural_generator(self, repo_id: str) -> IRGenerator:
                from ...generators.python_generator import _PythonIRGenerator
                return _PythonIRGenerator(repo_id=repo_id)
        """
        ...

    # ================================================================
    # Layer 5: Semantic IR (Optional)
    # ================================================================

    def create_semantic_builder(
        self,
        lsp_adapter: "IAsyncLSPAdapter | None" = None,
        enable_ssa: bool = True,
    ) -> "SemanticIRBuilderPort":
        """
        Create semantic IR builder.

        Args:
            lsp_adapter: LSP adapter for type enrichment (optional)
            enable_ssa: Enable SSA/Dominator analysis

        Returns:
            SemanticIRBuilderPort implementation
            (DefaultSemanticIrBuilder or language-specific)

        Contract:
            - May return shared DefaultSemanticIrBuilder
            - Or language-specific builder with custom logic

        Note:
            This is optional. If not implemented, LayeredIRBuilder
            will use DefaultSemanticIrBuilder.
        """
        ...

    # ================================================================
    # LSP Integration (Optional)
    # ================================================================

    def create_lsp_adapter(
        self,
        project_root: Path,
        config: dict[str, Any] | None = None,
    ) -> "IAsyncLSPAdapter | None":
        """
        Create LSP adapter.

        Args:
            project_root: Project root directory
            config: LSP configuration (optional)

        Returns:
            IAsyncLSPAdapter or None if not supported

        Contract:
            - Return existing LSP adapter from ir/lsp/*.py
            - Return None if language doesn't have LSP support

        Example:
            def create_lsp_adapter(self, project_root, config):
                from ...ir.lsp.pyright import PyrightAdapter
                return PyrightAdapter(project_root, config or {})
        """
        ...

    # ================================================================
    # Taint Rules (Optional)
    # ================================================================

    def get_taint_atoms_path(self, rules_dir: Path) -> Path | None:
        """
        Get taint atoms file path.

        Args:
            rules_dir: Base rules directory

        Returns:
            Path to {language}.atoms.yaml or None

        Contract:
            - Return path to TRCR atoms file if exists
            - Return None if language has no taint rules

        Example:
            def get_taint_atoms_path(self, rules_dir: Path) -> Path | None:
                path = rules_dir / "atoms" / "python.atoms.yaml"
                return path if path.exists() else None
        """
        ...
