"""
Context Selector Tool

Final context selection for Agent (Stage 2 reranking).

Pipeline:
1. Retriever returns 12-20 candidates (after cross-encoder)
2. Agent selects final 6-12 chunks for LLM context

Selection criteria:
- Semantic relevance to task
- Implementation files over test files
- Dependency chain consistency
- Remove noise (fixtures, mocks, migrations)
"""

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from src.common.observability import get_logger
from src.contexts.agent_automation.infrastructure.tools.base import BaseTool

logger = get_logger(__name__)
# ============================================================
# Input/Output Schemas
# ============================================================


class ContextSelectionInput(BaseModel):
    """Input for context selection."""

    candidates: list[dict[str, Any]] = Field(description="Candidate chunks from retriever (12-20 items)")
    task_description: str = Field(description="Task description for semantic filtering")
    target_count: int = Field(
        default=10,
        description="Target number of chunks to select (6-12 range)",
    )
    keep_tests: bool = Field(
        default=False,
        description="Whether to keep test files",
    )
    keep_dependencies: bool = Field(
        default=True,
        description="Whether to maintain dependency chains",
    )


class ContextSelectionOutput(BaseModel):
    """Output from context selection."""

    success: bool = Field(description="Whether selection succeeded")
    selected_chunks: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Selected chunks (6-12 items)",
    )
    removed_count: int = Field(
        default=0,
        description="Number of chunks removed",
    )
    removal_reasons: dict[str, int] = Field(
        default_factory=dict,
        description="Breakdown of removal reasons",
    )
    error: str | None = Field(default=None, description="Error message if failed")


# ============================================================
# Selection Logic
# ============================================================


@dataclass
class SelectionStats:
    """Statistics for context selection."""

    total_candidates: int = 0
    removed_test: int = 0
    removed_noise: int = 0
    removed_low_score: int = 0
    final_count: int = 0


class ContextSelectorTool(BaseTool[ContextSelectionInput, ContextSelectionOutput]):
    """
    Final context selector for Agent.

    Filters retriever candidates (12-20) down to final context (6-12).
    """

    name = "context_selector"
    description = "Select final context chunks from retriever candidates"
    input_schema = ContextSelectionInput
    output_schema = ContextSelectionOutput

    # Noise patterns to filter out
    NOISE_PATTERNS = [
        "vendor/",
        "node_modules/",
        "migrations/",
        "legacy/",
        "__pycache__/",
        ".git/",
        "build/",
        "dist/",
    ]

    # Test file patterns
    TEST_PATTERNS = [
        "test_",
        "_test.",
        "tests/",
        "spec.",
        "fixture",
        "mock",
        "conftest",
    ]

    async def _execute(self, input_data: ContextSelectionInput) -> ContextSelectionOutput:
        """
        Execute context selection.

        Args:
            input_data: Selection criteria and candidates

        Returns:
            Selected chunks with removal statistics
        """
        try:
            stats = SelectionStats(total_candidates=len(input_data.candidates))

            # Step 1: Filter noise files
            filtered_candidates = self._filter_noise(input_data.candidates, stats)

            # Step 2: Filter test files (if requested)
            if not input_data.keep_tests:
                filtered_candidates = self._filter_tests(filtered_candidates, stats)

            # Step 3: Sort by score and select top-K
            filtered_candidates = self._select_top_k(
                filtered_candidates,
                input_data.target_count,
                stats,
            )

            # Step 4: Maintain dependency chains (if requested)
            if input_data.keep_dependencies:
                filtered_candidates = self._ensure_dependencies(
                    filtered_candidates,
                    input_data.candidates,
                )

            stats.final_count = len(filtered_candidates)

            removal_reasons = {
                "test_files": stats.removed_test,
                "noise_files": stats.removed_noise,
                "low_score": stats.removed_low_score,
            }

            logger.info(
                "context_selection_complete",
                total=stats.total_candidates,
                final=stats.final_count,
                removed=stats.total_candidates - stats.final_count,
                reasons=removal_reasons,
            )

            return ContextSelectionOutput(
                success=True,
                selected_chunks=filtered_candidates,
                removed_count=stats.total_candidates - stats.final_count,
                removal_reasons=removal_reasons,
            )

        except Exception as e:
            logger.error(f"Context selection failed: {e}", exc_info=True)
            return ContextSelectionOutput(
                success=False,
                selected_chunks=[],
                error=str(e),
            )

    def _filter_noise(
        self,
        candidates: list[dict[str, Any]],
        stats: SelectionStats,
    ) -> list[dict[str, Any]]:
        """
        Filter out noise files.

        Args:
            candidates: Input candidates
            stats: Statistics tracker

        Returns:
            Filtered candidates
        """
        filtered = []

        for candidate in candidates:
            file_path = candidate.get("file_path", "")

            # Check if file is in noise directories
            is_noise = any(pattern in file_path for pattern in self.NOISE_PATTERNS)

            if is_noise:
                stats.removed_noise += 1
                logger.debug(f"Filtered noise file: {file_path}")
            else:
                filtered.append(candidate)

        return filtered

    def _filter_tests(
        self,
        candidates: list[dict[str, Any]],
        stats: SelectionStats,
    ) -> list[dict[str, Any]]:
        """
        Filter out test files.

        Args:
            candidates: Input candidates
            stats: Statistics tracker

        Returns:
            Filtered candidates
        """
        filtered = []

        for candidate in candidates:
            file_path = candidate.get("file_path", "")
            file_name = Path(file_path).name

            # Check if file is a test file
            is_test = any(pattern in file_path or pattern in file_name for pattern in self.TEST_PATTERNS)

            if is_test:
                stats.removed_test += 1
                logger.debug(f"Filtered test file: {file_path}")
            else:
                filtered.append(candidate)

        return filtered

    def _select_top_k(
        self,
        candidates: list[dict[str, Any]],
        target_count: int,
        stats: SelectionStats,
    ) -> list[dict[str, Any]]:
        """
        Select top-K candidates by score.

        Args:
            candidates: Input candidates
            target_count: Target number of chunks
            stats: Statistics tracker

        Returns:
            Top-K candidates
        """
        # Sort by score (descending)
        sorted_candidates = sorted(
            candidates,
            key=lambda x: x.get("score", 0.0),
            reverse=True,
        )

        # Select top-K
        selected = sorted_candidates[:target_count]
        stats.removed_low_score = len(sorted_candidates) - len(selected)

        return selected

    def _ensure_dependencies(
        self,
        selected: list[dict[str, Any]],
        all_candidates: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """
        Ensure dependency chains are complete.

        If a chunk references another chunk (import, call),
        try to include the dependency.

        Args:
            selected: Selected chunks
            all_candidates: All available candidates

        Returns:
            Selected chunks with dependencies added
        """
        # Build file path set for selected chunks
        selected_files = {c.get("file_path") for c in selected if c.get("file_path")}

        # Build candidate map: file_path -> candidate
        candidate_map = {c.get("file_path"): c for c in all_candidates if c.get("file_path")}

        # Extract dependencies from selected chunks
        missing_deps = set()

        for chunk in selected:
            content = chunk.get("content", "")
            file_path = chunk.get("file_path", "")

            if not content or not file_path:
                continue

            # Parse imports from content
            imports = self._parse_imports(content, file_path)

            # Check which imports are missing
            for imported_file in imports:
                if imported_file not in selected_files and imported_file in candidate_map:
                    missing_deps.add(imported_file)

        # Add missing dependencies (up to 3 to avoid bloat)
        added_count = 0
        max_deps_to_add = 3

        for dep_file in missing_deps:
            if added_count >= max_deps_to_add:
                break

            dep_chunk = candidate_map[dep_file]
            selected.append(dep_chunk)
            added_count += 1

            logger.debug(
                "dependency_added",
                file_path=dep_file,
                score=dep_chunk.get("score", 0.0),
            )

        if added_count > 0:
            logger.info(
                "dependencies_added",
                count=added_count,
                total_missing=len(missing_deps),
            )

        return selected

    def _parse_imports(self, content: str, current_file: str) -> set[str]:
        """
        Parse Python import statements to extract file dependencies.

        Args:
            content: File content
            current_file: Current file path

        Returns:
            Set of imported file paths (relative to repo root)
        """
        imports = set()
        current_dir = Path(current_file).parent

        # Match Python import patterns
        # import foo.bar
        # from foo.bar import baz
        # from .relative import something
        # from ..parent import something

        import_patterns = [
            r"^import\s+([\w.]+)",  # import foo.bar
            r"^from\s+([\w.]+)\s+import",  # from foo.bar import ...
        ]

        lines = content.split("\n")

        for line in lines:
            line = line.strip()

            # Skip comments
            if line.startswith("#"):
                continue

            for pattern in import_patterns:
                match = re.match(pattern, line)
                if match:
                    module_path = match.group(1)

                    # Convert module path to file path
                    file_path = self._module_to_file_path(module_path, current_dir)

                    if file_path:
                        imports.add(file_path)

        return imports

    def _module_to_file_path(self, module_path: str, current_dir: Path) -> str | None:
        """
        Convert Python module path to file path.

        Args:
            module_path: Module path (e.g., 'src.agent.tools.base')
            current_dir: Current file's directory

        Returns:
            File path or None if can't be resolved
        """
        # Handle relative imports
        if module_path.startswith("."):
            # Relative import - not easily resolved without project structure
            return None

        # Convert dots to slashes
        # src.agent.tools.base -> src/agent/tools/base.py
        file_path = module_path.replace(".", "/")

        # Try common patterns
        candidates = [
            f"{file_path}.py",  # src/agent/tools/base.py
            f"{file_path}/__init__.py",  # src/agent/tools/base/__init__.py
        ]

        # Return first pattern (can't check existence without file system access)
        # Retriever will have indexed files if they exist
        return candidates[0]


# Example usage
async def example_usage():
    """Example of context selection."""
    # Mock retriever candidates (12-20 items)
    candidates = [
        {"chunk_id": "1", "file_path": "src/auth.py", "score": 0.95, "content": "..."},
        {"chunk_id": "2", "file_path": "src/utils.py", "score": 0.90, "content": "..."},
        {"chunk_id": "3", "file_path": "tests/test_auth.py", "score": 0.85, "content": "..."},
        {"chunk_id": "4", "file_path": "src/models.py", "score": 0.80, "content": "..."},
        {"chunk_id": "5", "file_path": "vendor/lib.py", "score": 0.75, "content": "..."},
        # ... more candidates
    ]

    selector = ContextSelectorTool()

    input_data = ContextSelectionInput(
        candidates=candidates,
        task_description="Implement user authentication",
        target_count=10,
        keep_tests=False,
        keep_dependencies=True,
    )

    result = await selector._execute(input_data)

    print(f"Selected {len(result.selected_chunks)} chunks")
    print(f"Removed {result.removed_count} chunks")
    print(f"Reasons: {result.removal_reasons}")

    for chunk in result.selected_chunks:
        print(f"  - {chunk['file_path']} (score: {chunk['score']:.2f})")
