"""
GitPython VCS Adapter

IVCSApplier 포트 구현.

특징:
- Git branching/merging
- Conflict resolution
- Commit/patch 생성
"""

from dataclasses import dataclass
from pathlib import Path

from src.agent.domain.models import CodeChange
from src.ports import IVCSApplier


@dataclass
class CommitResult:
    """Commit 결과"""

    success: bool
    commit_sha: str | None
    branch_name: str
    files_changed: list[str]
    error: str | None = None


@dataclass
class ConflictResolutionResult:
    """Conflict resolution 결과"""

    success: bool
    resolved_files: list[str]
    remaining_conflicts: list[str]
    error: str | None = None


class GitPythonVCSAdapter(IVCSApplier):
    """
    GitPython → IVCSApplier Adapter.

    Git branching, commit, merge 지원.
    """

    def __init__(self, repo_path: str):
        """
        Args:
            repo_path: Git repository 경로
        """
        self.repo_path = Path(repo_path)

        # GitPython lazy import
        self._git = None
        self._repo = None

    def _get_repo(self):
        """GitPython lazy import & repo 초기화"""
        if self._repo is None:
            try:
                import git

                self._git = git
                self._repo = git.Repo(self.repo_path)

            except ImportError:
                raise ImportError("gitpython not installed. Run: pip install gitpython")
            except Exception as e:
                raise RuntimeError(f"Failed to open repo: {e}") from e

        return self._repo

    async def apply_changes(
        self,
        repo_path: str,
        changes: list[CodeChange],
        branch_name: str,
    ) -> CommitResult:
        """
        코드 변경사항을 Git에 적용.

        Args:
            repo_path: Repository 경로 (현재는 self.repo_path 사용)
            changes: CodeChange 리스트
            branch_name: 브랜치 이름

        Returns:
            CommitResult
        """
        repo = self._get_repo()

        try:
            # 1. 브랜치 생성/체크아웃
            try:
                # 브랜치가 이미 있으면 체크아웃
                repo.git.checkout(branch_name)
            except Exception:
                # 없으면 생성
                new_branch = repo.create_head(branch_name)
                new_branch.checkout()

            # 2. 파일 변경 적용
            files_changed = []

            for change in changes:
                file_path = self.repo_path / change.file_path

                if change.change_type.value == "create":
                    # 파일 생성
                    file_path.parent.mkdir(parents=True, exist_ok=True)
                    file_path.write_text("\n".join(change.new_lines))
                    files_changed.append(str(change.file_path))

                elif change.change_type.value == "modify":
                    # 파일 수정
                    if not file_path.exists():
                        raise FileNotFoundError(f"File not found: {change.file_path}")

                    content = file_path.read_text()
                    lines = content.splitlines()

                    # 라인 교체
                    if change.start_line is not None:
                        new_lines = (
                            lines[: change.start_line]
                            + change.new_lines
                            + lines[change.end_line + 1 if change.end_line is not None else change.start_line + 1 :]
                        )
                        file_path.write_text("\n".join(new_lines))
                        files_changed.append(str(change.file_path))

                elif change.change_type.value == "delete":
                    # 파일 삭제
                    if file_path.exists():
                        file_path.unlink()
                        files_changed.append(str(change.file_path))

            # 3. Git add
            for file in files_changed:
                repo.index.add([file])

            # 4. Commit
            commit_message = f"Apply {len(changes)} changes"
            commit = repo.index.commit(commit_message)

            return CommitResult(
                success=True,
                commit_sha=commit.hexsha,
                branch_name=branch_name,
                files_changed=files_changed,
            )

        except Exception as e:
            return CommitResult(
                success=False,
                commit_sha=None,
                branch_name=branch_name,
                files_changed=[],
                error=str(e),
            )

    async def create_pr(self, branch_name: str, title: str, description: str = "") -> dict:
        """PR 생성 (GitHub API 필요, stub)"""
        return {
            "pr_number": 0,
            "url": "https://github.com/repo/pull/0",
            "branch": branch_name,
            "title": title,
        }

    async def resolve_conflict(self, repo_path: str, conflict_data: str) -> ConflictResolutionResult:
        """
        Conflict 해결.

        Args:
            repo_path: Repository 경로
            conflict_data: Conflict 정보 (파일 경로 등)

        Returns:
            ConflictResolutionResult
        """
        repo = self._get_repo()

        try:
            # 1. Conflict 파일 찾기
            conflicted_files = []

            try:
                # Git status로 conflict 파일 확인
                status = repo.git.status("--short")

                for line in status.splitlines():
                    if line.startswith("UU"):  # Unmerged
                        file_path = line[3:].strip()
                        conflicted_files.append(file_path)

            except Exception:
                # conflict_data에서 파일 경로 추출
                conflicted_files = [conflict_data]

            if not conflicted_files:
                return ConflictResolutionResult(
                    success=True,
                    resolved_files=[],
                    remaining_conflicts=[],
                )

            # 2. 간단한 conflict resolution (우리 변경사항 우선)
            resolved_files = []

            for file_path in conflicted_files:
                full_path = self.repo_path / file_path

                if not full_path.exists():
                    continue

                # Conflict markers 제거 (ours 선택)
                content = full_path.read_text()

                # <<<<<<< HEAD
                # our changes
                # =======
                # their changes
                # >>>>>>> branch

                # 간단하게 ours 선택 (실제로는 LLM으로 해결)
                lines = []
                in_conflict = False
                keep_lines = False

                for line in content.splitlines():
                    if line.startswith("<<<<<<<"):
                        in_conflict = True
                        keep_lines = True
                        continue
                    elif line.startswith("======="):
                        keep_lines = False
                        continue
                    elif line.startswith(">>>>>>>"):
                        in_conflict = False
                        continue

                    if not in_conflict or keep_lines:
                        lines.append(line)

                full_path.write_text("\n".join(lines))

                # Git add (conflict 해결 표시)
                repo.index.add([file_path])

                resolved_files.append(file_path)

            return ConflictResolutionResult(
                success=True,
                resolved_files=resolved_files,
                remaining_conflicts=[],
            )

        except Exception as e:
            return ConflictResolutionResult(
                success=False,
                resolved_files=[],
                remaining_conflicts=conflicted_files,
                error=str(e),
            )


# ============================================================
# Stub VCS Applier (테스트용)
# ============================================================


class StubVCSApplier(IVCSApplier):
    """
    Stub VCS Applier.

    테스트/개발용 Mock VCS.
    실제 Git 없이 파일만 수정.
    """

    def __init__(self, repo_path: str):
        self.repo_path = Path(repo_path)

    async def apply_changes(
        self,
        repo_path: str,
        changes: list[CodeChange],
        branch_name: str,
    ) -> CommitResult:
        """Stub apply changes (Git 없이 파일만 수정)"""
        files_changed = []

        try:
            for change in changes:
                file_path = self.repo_path / change.file_path

                if change.change_type.value == "create":
                    file_path.parent.mkdir(parents=True, exist_ok=True)
                    file_path.write_text("\n".join(change.new_lines))
                    files_changed.append(str(change.file_path))

                elif change.change_type.value == "modify":
                    if file_path.exists():
                        content = file_path.read_text()
                        lines = content.splitlines()

                        if change.start_line is not None:
                            new_lines = (
                                lines[: change.start_line]
                                + change.new_lines
                                + lines[change.end_line + 1 if change.end_line is not None else change.start_line + 1 :]
                            )
                            file_path.write_text("\n".join(new_lines))
                            files_changed.append(str(change.file_path))

                elif change.change_type.value == "delete":
                    if file_path.exists():
                        file_path.unlink()
                        files_changed.append(str(change.file_path))

            return CommitResult(
                success=True,
                commit_sha="stub-commit-sha",
                branch_name=branch_name,
                files_changed=files_changed,
            )

        except Exception as e:
            return CommitResult(
                success=False,
                commit_sha=None,
                branch_name=branch_name,
                files_changed=[],
                error=str(e),
            )

    async def create_pr(self, branch_name: str, title: str, description: str = "") -> dict:
        """Stub PR 생성"""
        return {
            "pr_number": 0,
            "url": f"stub://pr/{branch_name}",
            "branch": branch_name,
            "title": title,
        }

    async def resolve_conflict(self, repo_path: str, conflict_data: str) -> ConflictResolutionResult:
        """Stub conflict resolution (항상 성공)"""
        return ConflictResolutionResult(
            success=True,
            resolved_files=[conflict_data],
            remaining_conflicts=[],
        )
