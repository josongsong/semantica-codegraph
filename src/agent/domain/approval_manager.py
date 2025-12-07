"""
Approval Manager (SOTA급)

사용자 승인/거부를 관리합니다.

핵심 기능:
1. File/Hunk/Line 단위 승인
2. 승인 세션 추적
3. 통계 및 이력
4. 자동 승인 규칙
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Protocol

from src.agent.domain.diff_manager import FileDiff

logger = logging.getLogger(__name__)


@dataclass
class ApprovalDecision:
    """승인 결정"""

    file_path: str
    hunk_index: int | None = None  # None = 전체 파일
    action: str = "approve"  # "approve", "reject", "skip", "edit"
    reason: str | None = None  # 거부/스킵 이유
    timestamp: datetime = field(default_factory=datetime.now)
    metadata: dict[str, Any] = field(default_factory=dict)

    def is_approved(self) -> bool:
        """승인되었는지 확인"""
        return self.action == "approve"

    def is_rejected(self) -> bool:
        """거부되었는지 확인"""
        return self.action == "reject"

    def is_skipped(self) -> bool:
        """스킵되었는지 확인"""
        return self.action == "skip"


@dataclass
class ApprovalSession:
    """
    승인 세션 (상태 추적).

    하나의 변경사항 세트에 대한 승인 과정을 추적합니다.
    """

    session_id: str
    file_diffs: list[FileDiff]
    decisions: list[ApprovalDecision] = field(default_factory=list)
    current_file_index: int = 0
    current_hunk_index: int = 0
    started_at: datetime = field(default_factory=datetime.now)
    completed_at: datetime | None = None

    def add_decision(self, decision: ApprovalDecision) -> None:
        """결정 추가"""
        self.decisions.append(decision)

    def get_approved_file_diffs(self) -> list[FileDiff]:
        """
        승인된 변경사항만 반환.

        Returns:
            승인된 FileDiff 리스트
        """
        approved_files = {}

        for decision in self.decisions:
            if not decision.is_approved():
                continue

            file_path = decision.file_path

            # 파일 전체 승인
            if decision.hunk_index is None:
                # 원본 FileDiff 찾기
                for file_diff in self.file_diffs:
                    if file_diff.file_path == file_path:
                        approved_files[file_path] = file_diff
                        break
            else:
                # Hunk 단위 승인
                if file_path not in approved_files:
                    # 원본 찾기
                    for file_diff in self.file_diffs:
                        if file_diff.file_path == file_path:
                            # 빈 FileDiff 생성
                            approved_files[file_path] = FileDiff(
                                file_path=file_path,
                                old_path=file_diff.old_path,
                                change_type=file_diff.change_type,
                                hunks=[],
                            )
                            break

                # Hunk 추가
                if file_path in approved_files:
                    for file_diff in self.file_diffs:
                        if file_diff.file_path == file_path:
                            hunk = file_diff.get_hunk(decision.hunk_index)
                            if hunk:
                                approved_files[file_path].hunks.append(hunk)

        return list(approved_files.values())

    def get_rejected_decisions(self) -> list[ApprovalDecision]:
        """거부된 결정만 반환"""
        return [d for d in self.decisions if d.is_rejected()]

    def get_statistics(self) -> dict[str, Any]:
        """
        승인 통계.

        Returns:
            통계 정보
        """
        total_decisions = len(self.decisions)
        approved = sum(1 for d in self.decisions if d.is_approved())
        rejected = sum(1 for d in self.decisions if d.is_rejected())
        skipped = sum(1 for d in self.decisions if d.is_skipped())

        # 시간 계산
        duration = None
        if self.completed_at:
            duration = (self.completed_at - self.started_at).total_seconds()

        return {
            "total_decisions": total_decisions,
            "approved": approved,
            "rejected": rejected,
            "skipped": skipped,
            "approval_rate": approved / total_decisions if total_decisions > 0 else 0.0,
            "duration_seconds": duration,
            "total_files": len(self.file_diffs),
            "total_hunks": sum(len(fd.hunks) for fd in self.file_diffs),
        }

    def is_complete(self) -> bool:
        """모든 결정이 완료되었는지 확인"""
        return self.completed_at is not None

    def mark_complete(self) -> None:
        """세션 완료 표시"""
        self.completed_at = datetime.now()


@dataclass
class ApprovalCriteria:
    """자동 승인 규칙"""

    auto_approve_tests: bool = False  # 테스트 파일 자동 승인
    auto_approve_docs: bool = False  # 문서 파일 자동 승인
    max_lines_auto: int = 0  # 이 라인 이하면 자동 승인 (0 = 비활성화)
    allowed_patterns: list[str] = field(default_factory=list)  # 자동 승인 패턴
    blocked_patterns: list[str] = field(default_factory=list)  # 자동 거부 패턴

    def should_auto_approve(self, file_diff: FileDiff) -> bool:
        """
        자동 승인해야 하는지 판단.

        Args:
            file_diff: FileDiff

        Returns:
            True면 자동 승인
        """
        # 테스트 파일 자동 승인
        if self.auto_approve_tests and "test" in file_diff.file_path.lower():
            return True

        # 문서 파일 자동 승인
        if self.auto_approve_docs and file_diff.file_path.endswith((".md", ".txt", ".rst")):
            return True

        # 라인 수 제한
        if self.max_lines_auto > 0:
            total_lines = file_diff.total_added + file_diff.total_removed
            if total_lines <= self.max_lines_auto:
                return True

        # 패턴 매칭
        for pattern in self.allowed_patterns:
            if pattern in file_diff.file_path:
                return True

        # Blocked 패턴
        for pattern in self.blocked_patterns:
            if pattern in file_diff.file_path:
                return False

        return False


class UIAdapter(Protocol):
    """UI Adapter 인터페이스"""

    async def show_diff(
        self,
        file_diff: FileDiff,
        hunk_index: int | None = None,
    ) -> None:
        """Diff 표시"""
        ...

    async def ask_approval(
        self,
        prompt: str,
        options: list[str],
        default: str | None = None,
    ) -> str:
        """
        사용자 선택 요청.

        Args:
            prompt: 질문
            options: 선택지 리스트
            default: 기본값

        Returns:
            사용자 선택
        """
        ...

    async def show_message(
        self,
        message: str,
        level: str = "info",
    ) -> None:
        """메시지 표시"""
        ...


class ApprovalManager:
    """
    사용자 승인 관리 (SOTA급).

    File/Hunk/Line 단위 승인을 지원합니다.
    """

    def __init__(
        self,
        ui_adapter: UIAdapter | None = None,
        criteria: ApprovalCriteria | None = None,
    ):
        """
        Args:
            ui_adapter: UI Adapter (CLI, Web, IDE 등)
            criteria: 자동 승인 규칙
        """
        self.ui_adapter = ui_adapter
        self.criteria = criteria or ApprovalCriteria()

    async def request_approval(
        self,
        file_diffs: list[FileDiff],
        mode: str = "hunk",  # "file", "hunk", "line"
    ) -> ApprovalSession:
        """
        사용자에게 승인 요청.

        Args:
            file_diffs: FileDiff 리스트
            mode: 승인 모드 ("file", "hunk", "line")

        Returns:
            ApprovalSession
        """
        logger.info(f"Starting approval session: {len(file_diffs)} files, mode={mode}")

        session = ApprovalSession(
            session_id=f"approval-{datetime.now().strftime('%Y%m%d-%H%M%S')}",
            file_diffs=file_diffs,
        )

        if mode == "file":
            await self._approve_by_file(session)
        elif mode == "hunk":
            await self._approve_by_hunk(session)
        elif mode == "line":
            await self._approve_by_line(session)
        else:
            raise ValueError(f"Invalid mode: {mode}")

        session.mark_complete()

        stats = session.get_statistics()
        logger.info(
            f"Approval completed: {stats['approved']}/{stats['total_decisions']} approved ({stats['approval_rate']:.1%})"
        )

        return session

    async def _approve_by_file(self, session: ApprovalSession) -> None:
        """파일 단위 승인"""
        logger.debug(f"File-level approval: {len(session.file_diffs)} files")

        for file_diff in session.file_diffs:
            # 자동 승인 체크
            if self.criteria.should_auto_approve(file_diff):
                session.add_decision(
                    ApprovalDecision(
                        file_path=file_diff.file_path,
                        action="approve",
                        reason="Auto-approved",
                    )
                )
                logger.debug(f"Auto-approved: {file_diff.file_path}")
                continue

            # 사용자에게 물어보기
            if self.ui_adapter:
                await self.ui_adapter.show_diff(file_diff)

                choice = await self.ui_adapter.ask_approval(
                    f"Approve {file_diff.file_path}?",
                    ["y", "n", "s", "q"],
                    default="y",
                )

                if choice == "q":
                    break

                action = {
                    "y": "approve",
                    "n": "reject",
                    "s": "skip",
                }.get(choice, "skip")
            else:
                # UI 없으면 자동 승인
                action = "approve"

            session.add_decision(
                ApprovalDecision(
                    file_path=file_diff.file_path,
                    action=action,
                )
            )

    async def _approve_by_hunk(self, session: ApprovalSession) -> None:
        """Hunk 단위 승인 (가장 실용적)"""
        for file_diff in session.file_diffs:
            # 자동 승인 체크
            if self.criteria.should_auto_approve(file_diff):
                # 모든 hunk 자동 승인
                for i in range(len(file_diff.hunks)):
                    session.add_decision(
                        ApprovalDecision(
                            file_path=file_diff.file_path,
                            hunk_index=i,
                            action="approve",
                            reason="Auto-approved",
                        )
                    )
                continue

            # 각 hunk에 대해 물어보기
            for i, _hunk in enumerate(file_diff.hunks):
                if self.ui_adapter:
                    await self.ui_adapter.show_diff(file_diff, hunk_index=i)

                    choice = await self.ui_adapter.ask_approval(
                        f"Approve hunk {i + 1}/{len(file_diff.hunks)}?",
                        ["y", "n", "s", "a", "r", "q"],
                        default="y",
                    )

                    if choice == "q":
                        return  # 전체 종료

                    if choice == "a":
                        # 남은 모든 것 승인
                        for j in range(i, len(file_diff.hunks)):
                            session.add_decision(
                                ApprovalDecision(
                                    file_path=file_diff.file_path,
                                    hunk_index=j,
                                    action="approve",
                                    reason="Approve all",
                                )
                            )
                        break

                    if choice == "r":
                        # 남은 모든 것 거부
                        for j in range(i, len(file_diff.hunks)):
                            session.add_decision(
                                ApprovalDecision(
                                    file_path=file_diff.file_path,
                                    hunk_index=j,
                                    action="reject",
                                    reason="Reject all",
                                )
                            )
                        break

                    action = {
                        "y": "approve",
                        "n": "reject",
                        "s": "skip",
                    }.get(choice, "skip")
                else:
                    # UI 없으면 자동 승인
                    action = "approve"

                session.add_decision(
                    ApprovalDecision(
                        file_path=file_diff.file_path,
                        hunk_index=i,
                        action=action,
                    )
                )

    async def _approve_by_line(self, session: ApprovalSession) -> None:
        """Line 단위 승인 (가장 세밀, 시간 많이 걸림)"""
        # TODO: 미래 구현
        # 현재는 hunk 단위로 fallback
        await self._approve_by_hunk(session)

    async def auto_approve(
        self,
        file_diffs: list[FileDiff],
    ) -> ApprovalSession:
        """
        자동 승인 (규칙 기반).

        Args:
            file_diffs: FileDiff 리스트

        Returns:
            ApprovalSession (모두 승인됨)
        """
        logger.info(f"Auto-approval: {len(file_diffs)} files")

        session = ApprovalSession(
            session_id=f"auto-{datetime.now().strftime('%Y%m%d-%H%M%S')}",
            file_diffs=file_diffs,
        )

        auto_count = 0
        for file_diff in file_diffs:
            if self.criteria.should_auto_approve(file_diff):
                # 파일 전체 승인
                session.add_decision(
                    ApprovalDecision(
                        file_path=file_diff.file_path,
                        action="approve",
                        reason="Auto-approved by criteria",
                    )
                )
                auto_count += 1
            else:
                # 기본: 승인 (사용자 개입 없음)
                session.add_decision(
                    ApprovalDecision(
                        file_path=file_diff.file_path,
                        action="approve",
                        reason="Auto-approved (no UI)",
                    )
                )

        session.mark_complete()

        logger.info(f"Auto-approval completed: {auto_count}/{len(file_diffs)} by criteria")

        return session


class CLIApprovalAdapter:
    """
    CLI 기반 승인 UI (SOTA급).

    Rich library를 사용한 아름다운 터미널 UI.
    """

    def __init__(self, colorize: bool = True):
        """
        Args:
            colorize: Color 지원 여부
        """
        self.colorize = colorize

    async def show_diff(
        self,
        file_diff: FileDiff,
        hunk_index: int | None = None,
    ) -> None:
        """Diff 표시 (CLI)"""
        from src.agent.domain.diff_manager import DiffManager

        manager = DiffManager()

        # 전체 파일 or 특정 hunk
        if hunk_index is None:
            output = manager.format_file_diff(file_diff, colorize=self.colorize)
        else:
            hunk = file_diff.get_hunk(hunk_index)
            if hunk:
                # File info
                print(f"\n{file_diff.file_path} (Hunk {hunk_index + 1}/{len(file_diff.hunks)})")
                print("─" * 60)

                # Hunk
                output = manager.format_hunk(hunk, colorize=self.colorize)
            else:
                output = f"Hunk {hunk_index} not found"

        print(output)

    async def ask_approval(
        self,
        prompt: str,
        options: list[str],
        default: str | None = None,
    ) -> str:
        """
        사용자 선택 요청 (CLI).

        Args:
            prompt: 질문
            options: 선택지
            default: 기본값

        Returns:
            사용자 선택
        """
        # Options 표시
        options_str = "/".join(options)
        if default:
            options_str = options_str.replace(default, default.upper())

        full_prompt = f"\n{prompt} [{options_str}] "

        # 입력 받기
        try:
            choice = input(full_prompt).strip().lower()

            if not choice and default:
                return default

            if choice in options:
                return choice

            # Invalid choice
            print(f"Invalid choice: {choice}")
            return await self.ask_approval(prompt, options, default)

        except (KeyboardInterrupt, EOFError):
            return "q"  # Quit

    async def show_message(
        self,
        message: str,
        level: str = "info",
    ) -> None:
        """메시지 표시 (CLI)"""
        if self.colorize:
            colors = {
                "info": "\033[36m",  # Cyan
                "success": "\033[32m",  # Green
                "warning": "\033[33m",  # Yellow
                "error": "\033[31m",  # Red
            }
            color = colors.get(level, "")
            reset = "\033[0m"
            print(f"{color}{message}{reset}")
        else:
            print(message)
