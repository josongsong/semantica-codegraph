"""
E2E Taint Analysis Wrapper

Direct wrapper for E2E pipeline taint analysis.
Bypasses PyO3 function registration issues by using the integrated pipeline approach.

Usage:
    >>> from codegraph_analysis.security_analysis.infrastructure.adapters.e2e_taint_wrapper import E2ETaintAnalyzer
    >>> analyzer = E2ETaintAnalyzer()
    >>> result = analyzer.analyze_repo(repo_path="/path/to/repo")
    >>> print(result["taint_paths"])
"""

import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class E2ETaintAnalyzer:
    """
    E2E Pipeline Taint Analyzer

    Uses run_ir_indexing_pipeline instead of standalone analyze_taint.
    This is the recommended approach per Rust lib.rs DEPRECATED comments.
    """

    def analyze_repo(
        self,
        repo_path: str | Path,
        file_paths: list[str] | None = None,
    ) -> dict[str, Any]:
        """
        Run taint analysis on repository using E2E pipeline

        Args:
            repo_path: Path to repository root
            file_paths: Optional list of specific files to analyze

        Returns:
            Dict with keys:
                - nodes: IR nodes
                - edges: IR edges
                - taint_paths: List of taint paths (when enable_taint works)
                - stats: Analysis statistics

        Note:
            Currently returns IR only. Taint paths pending PyO3 fix for enable_taint parameter.
        """
        try:
            import codegraph_ir

            repo_path = Path(repo_path)
            repo_name = repo_path.name

            logger.info(f"Running E2E taint analysis on {repo_path}")

            # ✅ PyO3 signature issue FIXED!
            result = codegraph_ir.run_ir_indexing_pipeline(
                repo_root=str(repo_path),
                repo_name=repo_name,
                file_paths=file_paths,
                enable_chunking=True,
                enable_cross_file=True,
                enable_symbols=True,
                enable_points_to=True,
                enable_repomap=False,
                enable_taint=True,  # ✅ Now works!
                parallel_workers=0,
            )

            # Extract taint results (from E2E pipeline)
            taint_results = result.get("taint_results", [])

            # Legacy: Also check for taint_paths key
            taint_paths = result.get("taint_paths", [])

            if not taint_results and not taint_paths:
                logger.info(
                    "No taint_results in result. "
                    "Pipeline taint analysis may not be implemented yet in Rust orchestrator."
                )

            return {
                "nodes": result.get("nodes", []),
                "edges": result.get("edges", []),
                "chunks": result.get("chunks", []),
                "symbols": result.get("symbols", []),
                "taint_results": taint_results,  # ✅ Use taint_results from E2E pipeline
                "taint_paths": taint_paths,  # Legacy support
                "stats": result.get("stats", {}),
            }

        except ImportError as e:
            logger.error(f"codegraph_ir not available: {e}")
            return {
                "nodes": [],
                "edges": [],
                "taint_paths": [],
                "stats": {},
                "error": str(e),
            }
        except Exception as e:
            logger.error(f"E2E analysis failed: {e}", exc_info=True)
            return {
                "nodes": [],
                "edges": [],
                "taint_paths": [],
                "stats": {},
                "error": str(e),
            }
