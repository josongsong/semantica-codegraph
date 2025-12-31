"""
Git Stage - Git 관련 작업 처리

Stage 1: Git operations (clone/fetch/pull, commit info)
"""

from datetime import datetime

from codegraph_engine.analysis_indexing.infrastructure.git_helper import GitHelper
from codegraph_engine.analysis_indexing.infrastructure.models import IndexingStage
from codegraph_shared.infra.observability import get_logger

from .base import BaseStage, StageContext

logger = get_logger(__name__)


class GitStage(BaseStage):
    """Git 작업 Stage"""

    stage_name = IndexingStage.GIT_OPERATIONS

    async def execute(self, ctx: StageContext) -> None:
        """Git 정보 수집"""
        stage_start = datetime.now()

        try:
            git = GitHelper(ctx.repo_path)

            if git.is_git_repo():
                commit_hash = git.get_current_commit_hash()
                ctx.result.git_commit_hash = commit_hash

                repo_info = git.get_repo_info()
                ctx.result.metadata["git_info"] = repo_info

                logger.info(
                    f"📂 Git repo: {repo_info['current_branch']} @ {commit_hash[:8] if commit_hash else 'unknown'}"
                )
            else:
                logger.warning(f"Not a Git repository: {ctx.repo_path}")
                ctx.result.add_warning("Not a Git repository")

        except Exception as e:
            logger.warning(f"Git operations failed: {e}")
            ctx.result.add_warning(f"Git operations failed: {e}")

        self._record_duration(ctx, stage_start)
