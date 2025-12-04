"""
Rust LSP Adapter (rust-analyzer) - Skeleton

TODO: Implement rust-analyzer integration.
"""

from pathlib import Path

from src.common.observability import get_logger
from src.contexts.code_foundation.infrastructure.ir.lsp.adapter import Diagnostic, Location, TypeInfo

logger = get_logger(__name__)


class RustAnalyzerAdapter:
    """Rust LSP adapter (rust-analyzer) - Skeleton"""

    def __init__(self, project_root: Path):
        self.project_root = project_root
        self.logger = logger
        self.logger.warning("rust-analyzer adapter not yet implemented (skeleton only)")

    async def hover(self, file_path: Path, line: int, col: int) -> TypeInfo | None:
        return None

    async def definition(self, file_path: Path, line: int, col: int) -> Location | None:
        return None

    async def references(
        self,
        file_path: Path,
        line: int,
        col: int,
        include_declaration: bool = True,
    ) -> list[Location]:
        return []

    async def diagnostics(self, file_path: Path) -> list[Diagnostic]:
        return []

    async def shutdown(self) -> None:
        pass
