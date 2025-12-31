"""
Incremental IR Builder

Delta 기반 incremental update

Note:
    Renamed from IncrementalBuilder to IncrementalIRBuilder (2025-12-12)
    for clarity and to avoid name collision with reasoning_engine.ImpactAnalysisPlanner

TODO(refactor): This class uses _PythonIRGenerator directly (Layer 1 only).
    Consider integrating with LayeredIRBuilder for full 9-layer support.
    Now that LayeredIRBuilder has sync wrappers (build_full_sync, parse_file_sync),
    migration is possible. However, this class has self-managed cache + ChangeTracker
    that differs from LayeredIRBuilder's external state management pattern.
    Migration requires refactoring the caching strategy.
"""

import logging
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

from codegraph_engine.code_foundation.infrastructure.generators.python_generator import _PythonIRGenerator
from codegraph_engine.code_foundation.infrastructure.incremental.change_tracker import ChangeTracker
from codegraph_engine.code_foundation.infrastructure.ir.models import IRDocument
from codegraph_engine.code_foundation.infrastructure.ir.models.core import EdgeKind
from codegraph_engine.code_foundation.infrastructure.parsing import AstTree, SourceFile


@dataclass
class IncrementalResult:
    """Incremental update 결과"""

    changed_files: set[str]
    affected_files: set[str]
    rebuilt_files: set[str]
    ir_documents: dict[str, IRDocument]
    skipped_files: int


class IncrementalIRBuilder:
    """
    Incremental IR Builder (File-level)

    기능:
    - 변경된 파일만 재빌드
    - 의존성 기반 affected files 계산
    - IR cache 유지 및 업데이트

    Architecture:
    - workspace_root: 명시적 작업 디렉토리 (fragile cwd 의존성 제거)
    - 상대 경로를 절대 경로로 변환하여 안전한 파일 접근
    """

    def __init__(self, repo_id: str, workspace_root: Path | None = None):
        """
        Initialize IncrementalIRBuilder

        Args:
            repo_id: Repository identifier
            workspace_root: Workspace root directory (optional, defaults to cwd)

        Design:
            workspace_root를 명시적으로 받아 상대 경로 의존성 제거.
            이를 통해 테스트 환경에서도 안정적인 파일 접근 보장.
        """
        self.repo_id = repo_id
        self.workspace_root = workspace_root or Path.cwd()
        self._change_tracker = ChangeTracker()
        self._ir_cache: dict[str, IRDocument] = {}

    def build_incremental(
        self,
        files: list[Path],
        language: str = "python",
    ) -> IncrementalResult:
        """
        Incremental build

        Args:
            files: 처리할 파일 목록 (상대 경로 또는 절대 경로)
            language: 프로그래밍 언어

        Returns:
            IncrementalResult with delta info

        Design:
            상대 경로는 workspace_root 기준으로 변환하여
            cwd 의존성을 제거하고 안정적인 파일 접근 보장.
        """
        changed_files = set()

        # 1. 변경 감지
        for file_path in files:
            try:
                # Convert to absolute path (workspace_root 기준)
                if not file_path.is_absolute():
                    abs_file_path = self.workspace_root / file_path
                else:
                    abs_file_path = file_path

                content = abs_file_path.read_text()
                last_modified = abs_file_path.stat().st_mtime

                # BUG FIX: Normalize file path for consistent tracking
                # Always use absolute path to avoid path format mismatches
                normalized_path = str(abs_file_path.resolve())

                is_changed = self._change_tracker.register_file(
                    normalized_path,
                    content,
                    last_modified,
                )

                if is_changed:
                    changed_files.add(normalized_path)

            except Exception as e:
                # Python logging 표준 준수: extra={} 사용
                logger.warning(
                    f"incremental_file_read_failed: {file_path}",
                    extra={"file_path": str(file_path), "error": str(e)},
                )

        # 2. 영향받는 파일 계산
        affected_files = self._change_tracker.get_affected_files(changed_files)

        # 3. 재빌드
        rebuilt_files = set()
        new_ir_docs = {}

        for file_path_str in affected_files:
            file_path = Path(file_path_str)

            # file_path_str is already absolute (normalized in step 1)
            abs_file_path = file_path

            if not abs_file_path.exists():
                # File deleted
                if file_path_str in self._ir_cache:
                    del self._ir_cache[file_path_str]
                continue

            try:
                # Generate IR
                content = abs_file_path.read_text()
                source = SourceFile.from_content(file_path_str, content, language)
                ast = AstTree.parse(source)
                generator = _PythonIRGenerator(repo_id=self.repo_id)
                ir_doc = generator.generate(source, self.repo_id, ast)

                # BUG FIX: Use helper method for dependency extraction (O(1) lookup)
                dependencies = self._extract_dependencies(ir_doc, file_path_str)

                # Update dependency graph
                self._change_tracker.update_dependencies(file_path_str, dependencies)

                # Cache IR
                self._ir_cache[file_path_str] = ir_doc
                new_ir_docs[file_path_str] = ir_doc
                rebuilt_files.add(file_path_str)

            except Exception as e:
                logger.warning(
                    "incremental_build_failed",
                    file_path=str(file_path),
                    error=str(e),
                    error_type=type(e).__name__,
                )

        # 4. 결과
        skipped = len(files) - len(rebuilt_files)

        return IncrementalResult(
            changed_files=changed_files,
            affected_files=affected_files,
            rebuilt_files=rebuilt_files,
            ir_documents=new_ir_docs,
            skipped_files=skipped,
        )

    def get_all_ir(self) -> dict[str, IRDocument]:
        """모든 cached IR documents"""
        return self._ir_cache.copy()

    def clear_cache(self):
        """Cache 초기화"""
        self._change_tracker.clear()
        self._ir_cache.clear()

    def get_file_state(self, file_path: str):
        """
        Get file state for a tracked file.

        Public API to access file state without exposing internal _change_tracker.

        Args:
            file_path: Absolute file path

        Returns:
            FileState if file is tracked, None otherwise
        """
        return self._change_tracker.get_state(file_path)

    def get_dependents(self, file_path: str) -> set[str]:
        """
        Get files that depend on the given file.

        Public API to query dependency graph.

        Args:
            file_path: Absolute file path

        Returns:
            Set of file paths that depend on this file
        """
        state = self._change_tracker.get_state(file_path)
        return state.dependents.copy() if state else set()

    def _extract_dependencies(self, ir_doc: IRDocument, file_path: str) -> set[str]:
        """
        Extract file dependencies from IR document.

        BUG FIX: Use O(1) dict lookup instead of O(N²) nested loop.
        Also handles external module references in target_id format.

        Args:
            ir_doc: IR document to extract dependencies from
            file_path: Current file path (to exclude self-references)

        Returns:
            Set of file paths this document depends on
        """
        dependencies: set[str] = set()

        # Build node index for O(1) lookup
        node_by_id: dict[str, str | None] = {}
        for node in ir_doc.nodes:
            if node.file_path:
                # Normalize dependency paths too
                node_by_id[node.id] = str(Path(node.file_path).resolve())

        # Extract dependencies from IMPORTS edges
        for edge in ir_doc.edges:
            if edge.kind == EdgeKind.IMPORTS:
                # Case 1: Target node exists in IR with file_path
                target_file = node_by_id.get(edge.target_id)
                if target_file and target_file != file_path:
                    dependencies.add(target_file)
                    continue

                # Case 2: External module reference in target_id
                # Format: "module:/path/file.py:symbol"
                target_id = edge.target_id
                if ":" in target_id:
                    parts = target_id.split(":", 1)
                    if len(parts) == 2:
                        module_ref = parts[1]
                        # Only accept absolute paths
                        if module_ref.startswith("/"):
                            if ":" in module_ref:
                                dep_path = module_ref.split(":")[0]
                            else:
                                dep_path = module_ref
                            if dep_path.endswith(".py") and dep_path != file_path:
                                dependencies.add(dep_path)

        return dependencies
