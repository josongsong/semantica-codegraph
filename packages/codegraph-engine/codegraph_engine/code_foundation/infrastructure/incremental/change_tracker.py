"""
Incremental Update - Change Tracker

파일 변경 감지 및 delta 추적
"""

import hashlib
from collections import deque
from dataclasses import dataclass, field


@dataclass
class FileState:
    """파일 상태"""

    path: str
    hash: str
    last_modified: float
    dependencies: set[str] = field(default_factory=set)  # 이 파일이 의존하는 파일들
    dependents: set[str] = field(default_factory=set)  # 이 파일에 의존하는 파일들
    is_placeholder: bool = False  # BUG FIX: Mark placeholder files to skip hash comparison


class ChangeTracker:
    """
    파일 변경 추적 및 영향 분석

    기능:
    - 파일 hash 기반 변경 감지
    - Dependency graph로 영향받는 파일 계산
    - 재빌드 필요 파일 목록 반환
    """

    def __init__(self):
        self._file_states: dict[str, FileState] = {}

    def compute_file_hash(self, content: str) -> str:
        """파일 컨텐츠 hash 계산"""
        return hashlib.sha256(content.encode()).hexdigest()[:16]

    def register_file(
        self,
        file_path: str,
        content: str,
        last_modified: float,
        dependencies: set[str] = None,
    ) -> bool:
        """
        파일 등록 및 변경 감지

        Returns:
            True if file changed or new
        """
        file_hash = self.compute_file_hash(content)

        # 새 파일
        if file_path not in self._file_states:
            self._file_states[file_path] = FileState(
                path=file_path,
                hash=file_hash,
                last_modified=last_modified,
                dependencies=dependencies or set(),
                is_placeholder=False,
            )
            return True

        old_state = self._file_states[file_path]

        # BUG FIX: If this was a placeholder, upgrade it to real file
        # Placeholder files have empty hash and is_placeholder=True
        # When actual content arrives, we need to register it properly
        if old_state.is_placeholder:
            old_state.hash = file_hash
            old_state.last_modified = last_modified
            old_state.is_placeholder = False
            if dependencies:
                old_state.dependencies = dependencies
            return True  # First real registration counts as changed

        # Hash가 다르면 변경됨
        if old_state.hash != file_hash:
            # Update state
            old_state.hash = file_hash
            old_state.last_modified = last_modified
            if dependencies:
                old_state.dependencies = dependencies
            return True

        return False

    def update_dependencies(self, file_path: str, dependencies: set[str]):
        """의존성 업데이트"""
        if file_path not in self._file_states:
            return

        old_deps = self._file_states[file_path].dependencies
        new_deps = dependencies

        # Remove old dependent links
        for dep in old_deps:
            if dep in self._file_states:
                self._file_states[dep].dependents.discard(file_path)

        # Add new dependent links
        for dep in new_deps:
            if dep not in self._file_states:
                # Create placeholder for external file
                # BUG FIX: Mark as placeholder to avoid false change detection
                self._file_states[dep] = FileState(
                    path=dep,
                    hash="",
                    last_modified=0,
                    is_placeholder=True,
                )
            self._file_states[dep].dependents.add(file_path)

        self._file_states[file_path].dependencies = new_deps

    def get_affected_files(self, changed_files: set[str]) -> set[str]:
        """
        변경된 파일로 인해 영향받는 모든 파일 계산

        Returns:
            재빌드가 필요한 파일 목록 (변경된 파일 포함)
        """
        affected = set(changed_files)
        queue = deque(changed_files)

        while queue:
            file_path = queue.popleft()

            if file_path not in self._file_states:
                continue

            # 이 파일에 의존하는 파일들도 영향받음
            for dependent in self._file_states[file_path].dependents:
                if dependent not in affected:
                    affected.add(dependent)
                    queue.append(dependent)

        return affected

    def clear(self):
        """모든 상태 초기화"""
        self._file_states.clear()

    def get_state(self, file_path: str) -> FileState | None:
        """파일 상태 조회"""
        return self._file_states.get(file_path)

    def get_all_files(self) -> set[str]:
        """모든 추적 중인 파일 목록"""
        return set(self._file_states.keys())
