"""
Diff Chunk Builder

Git diff를 분석하여 diff chunk를 생성합니다.
PR 리뷰, 커밋 분석 등에 활용됩니다.
"""

from pathlib import Path

from src.common.observability import get_logger
from src.contexts.code_foundation.infrastructure.chunk.diff_analyzer import DiffAnalyzer, DiffBlock, FileDiff
from src.contexts.code_foundation.infrastructure.chunk.models import Chunk

logger = get_logger(__name__)


class DiffChunkBuilder:
    """Diff chunk 생성기"""

    def __init__(self, repo_path: Path | str):
        self.repo_path = Path(repo_path)
        self.diff_analyzer = DiffAnalyzer(repo_path)

    async def build_from_commit(
        self,
        repo_id: str,
        commit_sha: str,
        snapshot_id: str | None = None,
    ) -> list[Chunk]:
        """
        커밋에서 diff chunk 생성.

        Args:
            repo_id: Repository ID
            commit_sha: Git commit SHA
            snapshot_id: Snapshot ID (기본값: commit_sha)

        Returns:
            Diff chunk 리스트
        """
        file_diffs = await self.diff_analyzer.analyze_commit(commit_sha)
        snapshot_id = snapshot_id or commit_sha

        chunks = []
        for file_diff in file_diffs:
            file_chunks = self._build_chunks_from_file_diff(file_diff, repo_id, snapshot_id, commit_sha)
            chunks.extend(file_chunks)

        logger.info(
            "diff_chunks_from_commit",
            commit_sha=commit_sha,
            file_count=len(file_diffs),
            chunk_count=len(chunks),
        )

        return chunks

    async def build_from_pr(
        self,
        repo_id: str,
        base_sha: str,
        head_sha: str,
        pr_number: int | None = None,
    ) -> list[Chunk]:
        """
        PR에서 diff chunk 생성.

        Args:
            repo_id: Repository ID
            base_sha: Base branch commit
            head_sha: PR branch commit
            pr_number: PR number (optional)

        Returns:
            Diff chunk 리스트
        """
        file_diffs = await self.diff_analyzer.analyze_diff(base_sha, head_sha)
        snapshot_id = f"pr_{pr_number}" if pr_number else f"{base_sha}..{head_sha}"

        chunks = []
        for file_diff in file_diffs:
            file_chunks = self._build_chunks_from_file_diff(file_diff, repo_id, snapshot_id, head_sha)
            chunks.extend(file_chunks)

        logger.info(
            "diff_chunks_from_pr",
            base=base_sha[:8],
            head=head_sha[:8],
            pr=pr_number,
            file_count=len(file_diffs),
            chunk_count=len(chunks),
        )

        return chunks

    def _build_chunks_from_file_diff(
        self,
        file_diff: FileDiff,
        repo_id: str,
        snapshot_id: str,
        commit_sha: str,
    ) -> list[Chunk]:
        """
        파일 diff에서 chunk 생성.

        각 변경 블록(hunk)마다 하나의 chunk 생성.
        """
        chunks = []

        # Skip binary files
        if file_diff.change_type == "binary":
            logger.debug(f"Skipping binary file: {file_diff.file_path}")
            return chunks

        for idx, block in enumerate(file_diff.blocks):
            chunk_id = self._generate_chunk_id(
                repo_id,
                file_diff.file_path,
                block.new_start,
                idx,
            )

            # Content: 변경 타입에 따라 다르게 구성
            content = self._build_diff_content(block, file_diff.change_type)

            # Summary 생성
            summary = self._generate_summary(block, file_diff.change_type)

            # FQN: 파일 경로 + 라인 범위
            fqn = f"{file_diff.file_path}:{block.new_start}-{block.new_start + block.new_lines - 1}"

            chunk = Chunk(
                chunk_id=chunk_id,
                repo_id=repo_id,
                snapshot_id=snapshot_id,
                project_id=None,
                module_path=str(Path(file_diff.file_path).parent),
                file_path=file_diff.file_path,
                kind="diff",
                fqn=fqn,
                start_line=block.new_start,
                end_line=block.new_start + block.new_lines - 1,
                original_start_line=block.old_start,
                original_end_line=block.old_start + block.old_lines - 1,
                content_hash=None,  # Will be computed by chunk store
                parent_id=None,
                children=[],
                language=self._detect_language(file_diff.file_path),
                symbol_visibility=None,
                symbol_id=None,
                symbol_owner_id=None,
                summary=summary,
                importance=None,
                attrs={
                    "change_type": block.change_type,
                    "file_change_type": file_diff.change_type,
                    "old_path": file_diff.old_path,
                    "commit_sha": commit_sha,
                    "old_start": block.old_start,
                    "old_lines": block.old_lines,
                    "new_start": block.new_start,
                    "new_lines": block.new_lines,
                    "diff_content": content,  # Store actual diff content
                    "old_content": block.old_content,
                    "new_content": block.new_content,
                },
                version=1,
                last_indexed_commit=commit_sha,
                is_deleted=False,
                is_test=None,
                is_overlay=False,
                overlay_session_id=None,
                base_chunk_id=None,
            )

            chunks.append(chunk)

        return chunks

    def _build_diff_content(self, block: DiffBlock, file_change_type: str) -> str:
        """
        Diff content 구성.

        포맷:
        ```diff
        - old line
        + new line
        ```
        """
        lines = []

        if file_change_type == "added":
            lines.append(f"Added {block.new_lines} lines:")
            if block.new_content:
                for line in block.new_content.split("\n"):
                    lines.append(f"+ {line}")

        elif file_change_type == "deleted":
            lines.append(f"Deleted {block.old_lines} lines:")
            if block.old_content:
                for line in block.old_content.split("\n"):
                    lines.append(f"- {line}")

        else:  # modified
            lines.append(f"Modified {block.old_lines} → {block.new_lines} lines:")

            if block.old_content:
                for line in block.old_content.split("\n"):
                    lines.append(f"- {line}")

            if block.new_content:
                for line in block.new_content.split("\n"):
                    lines.append(f"+ {line}")

        return "\n".join(lines)

    def _generate_summary(self, block: DiffBlock, file_change_type: str) -> str:
        """Diff summary 생성"""
        if file_change_type == "added":
            return f"Added {block.new_lines} lines at line {block.new_start}"
        elif file_change_type == "deleted":
            return f"Deleted {block.old_lines} lines at line {block.old_start}"
        else:
            return f"Modified lines {block.old_start}-{block.old_start + block.old_lines - 1}"

    def _generate_chunk_id(
        self,
        repo_id: str,
        file_path: str,
        start_line: int,
        block_idx: int,
    ) -> str:
        """Chunk ID 생성"""
        # Format: chunk:repo:diff:path:line:idx
        safe_path = file_path.replace("/", "_").replace(".", "_")
        return f"chunk:{repo_id}:diff:{safe_path}:{start_line}:{block_idx}"

    def _detect_language(self, file_path: str) -> str | None:
        """파일 확장자에서 언어 감지"""
        ext_map = {
            ".py": "python",
            ".js": "javascript",
            ".ts": "typescript",
            ".tsx": "typescript",
            ".jsx": "javascript",
            ".java": "java",
            ".go": "go",
            ".rs": "rust",
            ".c": "c",
            ".cpp": "cpp",
            ".h": "c",
            ".hpp": "cpp",
        }

        suffix = Path(file_path).suffix.lower()
        return ext_map.get(suffix)
