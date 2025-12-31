"""
Local Overlay - Uncommitted 변경사항 처리

Git uncommitted changes를 IR에 반영

TODO(refactor): OverlayIRBuilder uses _PythonIRGenerator directly (Layer 1 only).
    Consider integrating with LayeredIRBuilder for full 9-layer support.
    Now that LayeredIRBuilder has sync wrappers (build_full_sync, parse_file_sync),
    migration is straightforward:
    - Use LayeredIRBuilder.parse_file_sync() for per-file IR generation
    - Or batch files and use build_full_sync() for better performance
"""

import subprocess
from dataclasses import dataclass
from pathlib import Path

from codegraph_shared.common.observability import get_logger

logger = get_logger(__name__)


@dataclass
class LocalChange:
    """로컬 변경 정보"""

    file_path: str
    change_type: str  # modified, added, deleted
    content: str | None
    is_staged: bool


class LocalOverlay:
    """
    Local Overlay System

    기능:
    - Git status로 uncommitted 파일 감지
    - Working directory 파일 내용 읽기
    - Committed + Uncommitted 통합 IR 생성
    """

    def __init__(self, repo_root: Path):
        self.repo_root = repo_root
        self._changes_cache: dict[str, LocalChange] = {}

    def detect_local_changes(self) -> dict[str, LocalChange]:
        """
        Git으로 uncommitted 변경 감지

        Returns:
            {file_path: LocalChange}
        """
        changes = {}

        try:
            # Git status --porcelain
            result = subprocess.run(
                ["git", "status", "--porcelain"],
                cwd=self.repo_root,
                capture_output=True,
                text=True,
                timeout=5,
            )

            if result.returncode != 0:
                return changes

            # Parse output
            for line in result.stdout.strip().split("\n"):
                if not line:
                    continue

                # Format: XY filename
                status = line[:2]
                filepath = line[3:].strip()

                full_path = self.repo_root / filepath

                # Determine change type
                if status[0] in ["M", "A", "?"] or status[1] in ["M", "A", "?"]:
                    if full_path.exists():
                        content = full_path.read_text()
                        change_type = "added" if status[0] == "?" or status[1] == "?" else "modified"
                    else:
                        content = None
                        change_type = "deleted"

                    is_staged = status[0] != " " and status[0] != "?"

                    changes[str(full_path)] = LocalChange(
                        file_path=str(full_path),
                        change_type=change_type,
                        content=content,
                        is_staged=is_staged,
                    )

        except subprocess.SubprocessError as e:
            logger.warning(
                "git_status_failed",
                error=str(e),
                repo_root=str(self.repo_root),
                fallback="returning_empty_changes",
            )
            # Fallback: return empty changes (safer than assuming all uncommitted)
        except FileNotFoundError:
            logger.warning(
                "git_not_found",
                repo_root=str(self.repo_root),
                fallback="returning_empty_changes",
            )
        except Exception as e:
            logger.error(
                "local_overlay_unexpected_error",
                error=str(e),
                error_type=type(e).__name__,
                repo_root=str(self.repo_root),
            )

        self._changes_cache = changes
        return changes

    def get_file_content(self, file_path: str) -> str | None:
        """
        파일 내용 가져오기 (local overlay 우선)

        Returns:
            Uncommitted content if exists, else committed content
        """
        # Check if uncommitted
        if file_path in self._changes_cache:
            change = self._changes_cache[file_path]
            if change.content:
                return change.content
            else:
                # Deleted
                return None

        # Read from filesystem
        path = Path(file_path)
        if path.exists():
            return path.read_text()

        return None

    def get_all_files(self, include_uncommitted: bool = True) -> set[str]:
        """
        모든 파일 목록 (committed + uncommitted)

        Args:
            include_uncommitted: Uncommitted 파일 포함 여부

        Returns:
            파일 경로 set
        """
        files = set()

        # Committed files (from git)
        try:
            result = subprocess.run(
                ["git", "ls-files"],
                cwd=self.repo_root,
                capture_output=True,
                text=True,
                timeout=5,
            )

            if result.returncode == 0:
                for line in result.stdout.strip().split("\n"):
                    if line:
                        files.add(str(self.repo_root / line))
        except Exception:  # noqa: S110
            # Fallback: scan directory
            for py_file in self.repo_root.rglob("*.py"):
                files.add(str(py_file))

        # Add uncommitted
        if include_uncommitted:
            changes = self.detect_local_changes()
            for filepath, change in changes.items():
                if change.change_type != "deleted":
                    files.add(filepath)

        return files

    def is_uncommitted(self, file_path: str) -> bool:
        """파일이 uncommitted인지 확인"""
        if not self._changes_cache:
            self.detect_local_changes()
        return file_path in self._changes_cache

    def get_uncommitted_count(self) -> int:
        """Uncommitted 파일 개수"""
        if not self._changes_cache:
            self.detect_local_changes()
        return len(self._changes_cache)

    def clear_cache(self):
        """Cache 초기화"""
        self._changes_cache.clear()


class OverlayIRBuilder:
    """
    Overlay IR Builder

    Committed + Uncommitted 통합 IR 생성
    """

    def __init__(self, repo_root: Path, repo_id: str):
        self.repo_root = repo_root
        self.repo_id = repo_id
        self.overlay = LocalOverlay(repo_root)

    def build_with_overlay(
        self,
        language: str = "python",
        include_uncommitted: bool = True,
    ):
        """
        Overlay IR 생성

        Args:
            language: 프로그래밍 언어
            include_uncommitted: Uncommitted 파일 포함 여부

        Returns:
            IR documents (committed + uncommitted)
        """
        from codegraph_engine.code_foundation.infrastructure.generators.python_generator import _PythonIRGenerator
        from codegraph_engine.code_foundation.infrastructure.parsing import AstTree, SourceFile

        # Get all files
        all_files = self.overlay.get_all_files(include_uncommitted)

        # Filter by language
        if language == "python":
            all_files = {f for f in all_files if f.endswith(".py")}

        # Build IR
        ir_docs = {}
        uncommitted_count = 0

        for file_path in all_files:
            try:
                # Get content (overlay priority)
                content = self.overlay.get_file_content(file_path)

                if not content:
                    continue

                # Generate IR
                source = SourceFile.from_content(file_path, content, language)
                ast = AstTree.parse(source)
                generator = _PythonIRGenerator(repo_id=self.repo_id)
                ir_doc = generator.generate(source, self.repo_id, ast)

                # Mark if uncommitted
                if self.overlay.is_uncommitted(file_path):
                    uncommitted_count += 1
                    # Add metadata
                    for node in ir_doc.nodes:
                        if not hasattr(node, "attrs"):
                            node.attrs = {}
                        node.attrs["uncommitted"] = True

                ir_docs[file_path] = ir_doc

            except Exception as e:
                logger.warning(
                    "overlay_ir_build_failed",
                    file_path=str(file_path),
                    error=str(e),
                    error_type=type(e).__name__,
                )

        return {
            "ir_documents": ir_docs,
            "total_files": len(ir_docs),
            "uncommitted_files": uncommitted_count,
        }
