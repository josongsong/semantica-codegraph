"""
리포지토리 인덱싱 UseCase

전체 리포지토리를 인덱싱하는 비즈니스 로직
"""

from ..domain.models import IndexingJob, IndexingResult, IndexingStatus
from ..domain.ports import MetadataStoragePort, ProgressCallbackPort
from .index_file import IndexFileUseCase


class IndexRepositoryUseCase:
    """리포지토리 인덱싱 UseCase"""

    def __init__(
        self,
        index_file_usecase: IndexFileUseCase,
        progress_callback: ProgressCallbackPort | None = None,
        metadata_storage: MetadataStoragePort | None = None,
    ):
        """
        초기화

        Args:
            index_file_usecase: 파일 인덱싱 UseCase
            progress_callback: 진행 상황 콜백 (선택)
            metadata_storage: 메타데이터 저장소 (선택)
        """
        self.index_file = index_file_usecase
        self.progress_callback = progress_callback
        self.metadata_storage = metadata_storage

    async def execute(self, job: IndexingJob) -> IndexingResult:
        """
        리포지토리 인덱싱 실행

        Args:
            job: 인덱싱 작업

        Returns:
            인덱싱 결과
        """
        result = IndexingResult(
            repo_id=job.repo_id,
            snapshot_id=job.snapshot_id or "default",
            mode=job.mode,
            status=IndexingStatus.IN_PROGRESS,
            total_files=len(job.files),
        )

        # 파일별 인덱싱
        for i, file in enumerate(job.files, 1):
            # 진행 상황 보고
            if self.progress_callback:
                self.progress_callback.on_progress(i, len(job.files), f"Processing {file.file_path}")

            # 파일 인덱싱
            file_result = await self.index_file.execute(job.repo_id, file)
            result.file_results.append(file_result)

            if file_result.success:
                result.success_files += 1
            else:
                result.failed_files += 1
                if file_result.error:
                    result.errors.append(f"{file.file_path}: {file_result.error}")

        # 최종 상태 결정
        if result.failed_files == 0:
            result.status = IndexingStatus.COMPLETED
        elif result.success_files == 0:
            result.status = IndexingStatus.FAILED
        else:
            result.status = IndexingStatus.COMPLETED  # 부분 성공

        # 메타데이터 저장
        if self.metadata_storage:
            await self.metadata_storage.save_indexing_metadata(
                repo_id=job.repo_id,
                snapshot_id=result.snapshot_id,
                metadata={
                    "total_files": result.total_files,
                    "success_files": result.success_files,
                    "failed_files": result.failed_files,
                    "mode": job.mode.value,
                },
            )

        return result
