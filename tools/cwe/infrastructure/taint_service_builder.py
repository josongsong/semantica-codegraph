"""
Taint Service Builder (SOTA Pattern)

Builder pattern for TaintAnalysisService construction.
Uses trcr SDK for rule compilation and execution.

Design Principles:
- Single Responsibility: Only builds TaintAnalysisService
- Builder Pattern: Step-by-step construction
- SDK-based: Uses trcr for rule compilation
- Fail-Fast: Validates dependencies at build time
"""

from pathlib import Path
from typing import TYPE_CHECKING

from codegraph_shared.common.observability import get_logger

if TYPE_CHECKING:
    from codegraph_engine.code_foundation.application.taint_analysis_service import TaintAnalysisService

logger = get_logger(__name__)


class TaintServiceBuilder:
    """
    Builder for TaintAnalysisService (trcr SDK-based)

    Uses trcr SDK for rule compilation and execution.
    Separates construction logic from business logic.

    Example:
        builder = TaintServiceBuilder()
        service = builder.build()  # Uses defaults

        # Or with custom path
        service = builder.build(custom_rules_path)
    """

    def __init__(self):
        """Initialize builder"""
        self._rules_path: Path | None = None

    def build(self, rules_base_path: Path | None = None) -> "TaintAnalysisService":
        """
        Build TaintAnalysisService with trcr SDK.

        Args:
            rules_base_path: Path to taint rules (default: from settings)

        Returns:
            TaintAnalysisService instance

        Raises:
            ImportError: If trcr SDK or taint engine not available
            FileNotFoundError: If rules directory not found
        """
        # Validate trcr SDK is available
        try:
            from trcr import TaintRuleCompiler  # noqa: F401
        except ImportError as e:
            raise ImportError(
                f"trcr SDK not available: {e}. Install with: pip install -e ../taint-rule-compiler"
            ) from e

        # Import taint service
        try:
            from codegraph_engine.code_foundation.application.taint_analysis_service import TaintAnalysisService
        except ImportError as e:
            raise ImportError(f"Taint engine not available: {e}") from e

        # Resolve rules path
        self._rules_path = self._resolve_rules_path(rules_base_path)

        # Validate rules directory exists
        if not self._rules_path.exists():
            raise FileNotFoundError(f"Taint rules directory not found: {self._rules_path}")

        logger.info(f"Building TaintAnalysisService with rules: {self._rules_path}")

        # Create service (trcr SDK handles rule compilation internally)
        taint_service = TaintAnalysisService(rules_path=self._rules_path)

        logger.info("TaintAnalysisService built successfully (trcr SDK)")
        return taint_service

    def _resolve_rules_path(self, rules_base_path: Path | None) -> Path:
        """Resolve rules path from argument or settings"""
        if rules_base_path is not None:
            return rules_base_path

        from codegraph_shared.config import settings

        return settings.TAINT_RULES_PATH
