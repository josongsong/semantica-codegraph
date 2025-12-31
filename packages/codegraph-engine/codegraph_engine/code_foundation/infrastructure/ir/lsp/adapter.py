"""
Multi-LSP Adapter Interface

Unified interface for Language Server Protocol clients across multiple languages.

Supports:
- Python: Pyright
- TypeScript/JavaScript: TypeScript Language Server
- Go: gopls
- Rust: rust-analyzer
- Java: Eclipse JDT LS (future)

Architecture:
- LSPAdapter: Protocol (interface) for all LSP clients
- MultiLSPManager: Central manager for all language-specific adapters
- Language-specific implementations in separate files

Example usage:
    manager = MultiLSPManager(project_root="/path/to/project")

    # Python
    type_info = await manager.get_type_info("python", Path("src/calc.py"), 10, 5)

    # TypeScript
    type_info = await manager.get_type_info("typescript", Path("src/calc.ts"), 15, 8)

    # Cleanup
    await manager.shutdown_all()
"""

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Protocol

from codegraph_shared.common.observability import get_logger

if TYPE_CHECKING:
    from codegraph_engine.code_foundation.infrastructure.ir.external_analyzers.pyright_lsp import PyrightLSPClient

logger = get_logger(__name__)


# ============================================================
# Data Models
# ============================================================


@dataclass
class Location:
    """Source code location"""

    file_path: str
    line: int  # 1-indexed
    column: int  # 0-indexed


# Re-export TypeInfo from base (canonical)
# Kept for backward compatibility - use external_analyzers.base.TypeInfo
from codegraph_engine.code_foundation.infrastructure.ir.external_analyzers.base import TypeInfo as _BaseTypeInfo


# Legacy TypeInfo (deprecated - use _BaseTypeInfo)
@dataclass
class TypeInfo:
    """
    Type information from LSP (DEPRECATED)

    Use external_analyzers.base.TypeInfo instead for new code.
    This is kept for backward compatibility only.
    """

    type_string: str  # e.g., "int", "str", "List[str]"
    documentation: str | None = None  # Hover docs
    signature: str | None = None  # Function signature

    # Metadata
    is_nullable: bool = False
    is_union: bool = False
    is_generic: bool = False

    # Source location
    definition_location: Location | None = None

    def to_base_type_info(self, symbol_name: str, file_path: str, line: int, column: int) -> _BaseTypeInfo:
        """Convert to base TypeInfo (canonical)"""
        return _BaseTypeInfo(
            symbol_name=symbol_name,
            file_path=file_path,
            line=line,
            column=column,
            inferred_type=self.type_string,
            is_union=self.is_union,
        )


@dataclass
class Diagnostic:
    """Code diagnostic (error, warning, hint)"""

    severity: str  # "error", "warning", "information", "hint"
    message: str
    file_path: str
    start_line: int  # 1-indexed
    start_col: int  # 0-indexed
    end_line: int  # 1-indexed
    end_col: int  # 0-indexed

    # Optional metadata
    code: str | None = None  # Error code (e.g., "type-mismatch")
    source: str | None = None  # Source (e.g., "pyright", "typescript")


# ============================================================
# LSP Adapter Interface (Protocol)
# ============================================================


class LSPAdapter(Protocol):
    """
    Unified LSP adapter interface.

    All language-specific adapters must implement this interface.

    Key methods:
    - hover: Get type and documentation at position
    - definition: Get definition location
    - references: Find all references
    - diagnostics: Get file diagnostics
    - shutdown: Clean up resources
    """

    async def hover(
        self,
        file_path: Path,
        line: int,
        col: int,
    ) -> TypeInfo | None:
        """
        Get type and documentation at position.

        Args:
            file_path: Source file path
            line: Line number (1-indexed)
            col: Column number (0-indexed)

        Returns:
            TypeInfo with type and docs, or None if not available
        """
        ...

    async def definition(
        self,
        file_path: Path,
        line: int,
        col: int,
    ) -> Location | None:
        """
        Get definition location for symbol at position.

        Args:
            file_path: Source file path
            line: Line number (1-indexed)
            col: Column number (0-indexed)

        Returns:
            Definition location, or None if not found
        """
        ...

    async def references(
        self,
        file_path: Path,
        line: int,
        col: int,
        include_declaration: bool = True,
    ) -> list[Location]:
        """
        Find all references to symbol at position.

        Args:
            file_path: Source file path
            line: Line number (1-indexed)
            col: Column number (0-indexed)
            include_declaration: Include symbol declaration in results

        Returns:
            List of reference locations
        """
        ...

    async def diagnostics(
        self,
        file_path: Path,
    ) -> list[Diagnostic]:
        """
        Get diagnostics for file.

        Args:
            file_path: Source file path

        Returns:
            List of diagnostics (errors, warnings, hints)
        """
        ...

    async def shutdown(self) -> None:
        """Shutdown LSP server and clean up resources"""
        ...


# ============================================================
# Multi-LSP Manager
# ============================================================


class MultiLSPManager:
    """
    Central manager for all LSP adapters.

    Manages lifecycle and routing for language-specific LSP clients.

    Example usage:
        manager = MultiLSPManager(project_root="/path/to/project")

        # Query type info (automatically routes to correct adapter)
        type_info = await manager.get_type_info(
            language="python",
            file_path=Path("src/calc.py"),
            line=10,
            col=5,
        )

        # Cleanup
        await manager.shutdown_all()
    """

    def __init__(
        self,
        project_root: Path | str,
        shared_pyright_client: "PyrightLSPClient | None" = None,
    ):
        """
        Initialize multi-LSP manager.

        Args:
            project_root: Project root directory
            shared_pyright_client: Optional shared PyrightLSPClient for Layer 3/5 reuse
                                   If provided, avoids creating a new Pyright process
        """
        self.project_root = Path(project_root)
        self.adapters: dict[str, LSPAdapter] = {}
        self.logger = logger

        # SOTA: Shared Pyright client for Layer 3/5 reuse (avoids double process)
        self._shared_pyright_client = shared_pyright_client

        # Initialize adapters (lazy)
        self._initialized_languages: set[str] = set()

    async def _ensure_adapter(self, language: str) -> LSPAdapter | None:
        """
        Ensure adapter is initialized for language.

        Lazy initialization: Only create adapter when first used.

        Args:
            language: Language name (python, typescript, go, rust)

        Returns:
            LSP adapter, or None if language not supported
        """
        if language in self._initialized_languages:
            return self.adapters.get(language)

        # Initialize adapter
        try:
            if language == "python":
                from codegraph_engine.code_foundation.infrastructure.ir.lsp.pyright import PyrightAdapter

                # SOTA: Use shared client if provided (avoids double Pyright process)
                if self._shared_pyright_client:
                    self.adapters[language] = PyrightAdapter(
                        self.project_root,
                        shared_client=self._shared_pyright_client,
                    )
                    self.logger.info("Initialized Pyright adapter for Python (shared client)")
                else:
                    self.adapters[language] = PyrightAdapter(self.project_root)
                    self.logger.info("Initialized Pyright adapter for Python")

            elif language in ["typescript", "javascript"]:
                from codegraph_engine.code_foundation.infrastructure.ir.lsp.typescript import TypeScriptAdapter

                self.adapters[language] = TypeScriptAdapter(self.project_root)
                self.logger.info(f"Initialized TypeScript adapter for {language}")

            elif language == "go":
                from codegraph_engine.code_foundation.infrastructure.ir.lsp.gopls import GoplsAdapter

                self.adapters[language] = GoplsAdapter(self.project_root)
                self.logger.info("Initialized gopls adapter for Go")

            elif language == "rust":
                from codegraph_engine.code_foundation.infrastructure.ir.lsp.rust_analyzer import RustAnalyzerAdapter

                self.adapters[language] = RustAnalyzerAdapter(self.project_root)
                self.logger.info("Initialized rust-analyzer adapter for Rust")

            elif language == "kotlin":
                from codegraph_engine.code_foundation.infrastructure.ir.external_analyzers.kotlin_lsp_async import (
                    KotlinLSPClientAsync,
                )
                from codegraph_engine.code_foundation.infrastructure.ir.lsp.kotlin import KotlinAdapter

                client = KotlinLSPClientAsync(self.project_root)
                await client.start()  # Async start
                self.adapters[language] = KotlinAdapter(client)
                self.logger.info("Initialized kotlin-language-server adapter for Kotlin (async)")

            elif language == "java":
                from codegraph_engine.code_foundation.infrastructure.ir.lsp.jdtls import JdtlsAdapter

                self.adapters[language] = JdtlsAdapter(self.project_root)
                self.logger.info("Initialized JDT.LS adapter for Java")

            else:
                self.logger.warning(f"Language '{language}' not supported for LSP integration")
                return None

            self._initialized_languages.add(language)
            return self.adapters.get(language)

        except Exception as e:
            self.logger.error(f"Failed to initialize LSP adapter for {language}: {e}")
            import traceback

            self.logger.error(f"Traceback: {traceback.format_exc()}")
            return None

    async def get_type_info(
        self,
        language: str,
        file_path: Path,
        line: int,
        col: int,
    ) -> TypeInfo | None:
        """
        Get type information at position.

        Args:
            language: Language name (python, typescript, go, rust)
            file_path: Source file path
            line: Line number (1-indexed)
            col: Column number (0-indexed)

        Returns:
            TypeInfo, or None if not available
        """
        adapter = await self._ensure_adapter(language)
        if not adapter:
            return None

        try:
            return await adapter.hover(file_path, line, col)
        except Exception as e:
            self.logger.debug(f"LSP hover failed for {language} at {file_path}:{line}:{col}: {e}")
            return None

    async def get_definition(
        self,
        language: str,
        file_path: Path,
        line: int,
        col: int,
    ) -> Location | None:
        """
        Get definition location.

        Args:
            language: Language name
            file_path: Source file path
            line: Line number (1-indexed)
            col: Column number (0-indexed)

        Returns:
            Definition location, or None if not found
        """
        adapter = await self._ensure_adapter(language)
        if not adapter:
            return None

        try:
            return await adapter.definition(file_path, line, col)
        except Exception as e:
            self.logger.debug(f"LSP definition failed for {language} at {file_path}:{line}:{col}: {e}")
            return None

    async def get_references(
        self,
        language: str,
        file_path: Path,
        line: int,
        col: int,
        include_declaration: bool = True,
    ) -> list[Location]:
        """
        Find all references.

        Args:
            language: Language name
            file_path: Source file path
            line: Line number (1-indexed)
            col: Column number (0-indexed)
            include_declaration: Include declaration in results

        Returns:
            List of reference locations
        """
        adapter = await self._ensure_adapter(language)
        if not adapter:
            return []

        try:
            return await adapter.references(file_path, line, col, include_declaration)
        except Exception as e:
            self.logger.debug(f"LSP references failed for {language} at {file_path}:{line}:{col}: {e}")
            return []

    async def get_diagnostics(
        self,
        language: str,
        file_path: Path,
    ) -> list[Diagnostic]:
        """
        Get file diagnostics.

        Args:
            language: Language name
            file_path: Source file path

        Returns:
            List of diagnostics
        """
        adapter = await self._ensure_adapter(language)
        if not adapter:
            return []

        try:
            return await adapter.diagnostics(file_path)
        except Exception as e:
            self.logger.debug(f"LSP diagnostics failed for {language} at {file_path}: {e}")
            return []

    async def shutdown_all(self) -> None:
        """Shutdown all LSP adapters"""
        self.logger.info("Shutting down all LSP adapters")

        for language, adapter in self.adapters.items():
            try:
                await adapter.shutdown()
                self.logger.debug(f"Shutdown {language} adapter")
            except Exception as e:
                self.logger.warning(f"Failed to shutdown {language} adapter: {e}")

        self.adapters.clear()
        self._initialized_languages.clear()

    def get_client(self, language: str) -> LSPAdapter | None:
        """
        Get LSP client (adapter) for language.

        Synchronous accessor for already-initialized adapters.
        For lazy initialization, use `await _ensure_adapter(language)` instead.

        Args:
            language: Language name (python, typescript, go, rust, etc.)

        Returns:
            LSP adapter if already initialized, None otherwise
        """
        return self.adapters.get(language)

    async def get_client_async(self, language: str) -> LSPAdapter | None:
        """
        Get or initialize LSP client (adapter) for language.

        Async version that ensures adapter is initialized.

        Args:
            language: Language name (python, typescript, go, rust, etc.)

        Returns:
            LSP adapter, or None if language not supported
        """
        return await self._ensure_adapter(language)

    def get_supported_languages(self) -> list[str]:
        """Get list of supported languages"""
        return ["python", "typescript", "javascript", "go", "rust", "kotlin", "java"]

    def is_language_supported(self, language: str) -> bool:
        """Check if language is supported"""
        return language in self.get_supported_languages()

    async def __aenter__(self):
        """Async context manager entry"""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit"""
        await self.shutdown_all()
        return False


# ============================================================
# Helper Functions
# ============================================================


def create_lsp_manager(project_root: Path | str) -> MultiLSPManager:
    """
    Create MultiLSPManager instance.

    Args:
        project_root: Project root directory

    Returns:
        MultiLSPManager instance
    """
    return MultiLSPManager(project_root)
