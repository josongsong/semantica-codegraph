"""
Lock Key Generator for File-based Locking

파일 단위 Lock을 위한 key 생성 유틸리티.
병렬 인덱싱 성능 향상을 위해 repo 전체가 아닌 파일별로 Lock.
"""

import hashlib


class LockKeyGenerator:
    """
    파일 기반 Lock key 생성기.

    기존: repo_id:snapshot_id (전체 repo Lock)
    개선: repo_id:snapshot_id:file_hash (파일 단위 Lock)

    장점:
    - 병렬 인덱싱 가능 (다른 파일 동시 작업)
    - Agent A, B가 동시 작업 시 블로킹 없음

    단점:
    - Lock 수 증가
    - Key 생성 overhead (해시 계산)
    """

    @staticmethod
    def generate_repo_lock_key(repo_id: str, snapshot_id: str) -> str:
        """
        전체 repo Lock key 생성 (legacy).

        사용 시나리오:
        - 전체 repo 인덱싱
        - RepoMap 빌드

        Args:
            repo_id: Repository ID
            snapshot_id: Snapshot ID

        Returns:
            Lock key (예: "myrepo:main")
        """
        return f"{repo_id}:{snapshot_id}"

    @staticmethod
    def generate_file_lock_key(repo_id: str, snapshot_id: str, file_paths: list[str]) -> str:
        """
        파일 단위 Lock key 생성.

        사용 시나리오:
        - 증분 인덱싱 (1-N개 파일)
        - Agent 자동 재인덱싱

        Args:
            repo_id: Repository ID
            snapshot_id: Snapshot ID
            file_paths: 인덱싱 대상 파일 경로 리스트

        Returns:
            Lock key (예: "myrepo:main:abc123")

        Note:
            - 파일 순서에 무관하게 동일 key 생성 (정렬)
            - 긴 파일 목록은 SHA256 해시로 압축
        """
        if not file_paths:
            # 파일 없으면 repo lock
            return LockKeyGenerator.generate_repo_lock_key(repo_id, snapshot_id)

        # 파일 경로 정렬 (순서 무관하게 동일 key)
        sorted_paths = sorted(file_paths)

        # 파일이 1개이고 짧으면 그대로 사용
        if len(sorted_paths) == 1 and len(sorted_paths[0]) < 50:
            return f"{repo_id}:{snapshot_id}:{sorted_paths[0]}"

        # 파일이 여러 개이거나 긴 경로면 해시 사용
        paths_str = ",".join(sorted_paths)

        # SHA256 해시 (앞 16자만 사용)
        hash_digest = hashlib.sha256(paths_str.encode()).hexdigest()[:16]

        return f"{repo_id}:{snapshot_id}:files:{hash_digest}"

    @staticmethod
    def should_use_file_lock(scope_paths: list[str] | None, max_files: int = 10) -> bool:
        """
        파일 단위 Lock을 사용할지 판단.

        Args:
            scope_paths: 인덱싱 대상 파일 경로 (None = 전체 repo)
            max_files: 파일 단위 Lock 사용 최대 파일 수

        Returns:
            True: 파일 단위 Lock 사용
            False: Repo 단위 Lock 사용
        """
        if scope_paths is None:
            # 전체 repo 인덱싱 = repo lock
            return False

        if len(scope_paths) == 0:
            return False

        if len(scope_paths) > max_files:
            # 파일이 너무 많으면 repo lock (효율성)
            return False

        # 1-max_files개 파일 = 파일 lock
        return True
