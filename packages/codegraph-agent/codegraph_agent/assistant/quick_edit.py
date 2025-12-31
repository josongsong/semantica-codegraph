"""
Quick Edit Service (Assistant Mode)

RFC-060 Section 1.3: Cursor-like 빠른 코드 수정

Pipeline:
1. Context Retrieval (1-2초)
2. Patch Generation (2-5초)
3. User Approval (Diff Preview)
4. Apply + Optional Test
"""

from dataclasses import dataclass
from enum import Enum
from typing import Protocol

from codegraph_agent.ports.cascade import IFuzzyPatcher, PatchResult
from codegraph_agent.ports.static_gate import IStaticAnalysisGate


class ApprovalStatus(Enum):
    """사용자 승인 상태"""

    APPROVED = "approved"
    REJECTED = "rejected"
    EDITED = "edited"  # 사용자가 수정함
    PENDING = "pending"


@dataclass
class EditRequest:
    """수정 요청"""

    file_path: str
    instruction: str  # 사용자 지시 (e.g., "None 체크 추가")
    selection: str | None = None  # 선택된 코드 범위
    line_start: int | None = None
    line_end: int | None = None


@dataclass
class EditProposal:
    """수정 제안"""

    file_path: str
    original_content: str
    proposed_content: str
    diff: str  # Unified Diff
    explanation: str  # 변경 설명
    approval_status: ApprovalStatus = ApprovalStatus.PENDING


class IContextRetriever(Protocol):
    """컨텍스트 검색 Port"""

    async def retrieve(
        self,
        file_path: str,
        query: str,
        max_tokens: int = 4000,
    ) -> dict[str, str]:
        """
        관련 컨텍스트 검색

        Returns:
            {file_path: content} 매핑
        """
        ...


class IPatchGenerator(Protocol):
    """패치 생성 Port"""

    async def generate(
        self,
        request: EditRequest,
        context: dict[str, str],
    ) -> str:
        """
        LLM으로 패치 생성

        Returns:
            수정된 파일 내용
        """
        ...


class QuickEditService:
    """
    Quick Edit Service (Assistant Mode)

    빠른 코드 수정 서비스:
    - 5초 이내 Diff 표시 목표
    - 사용자 승인 필수
    - Static Gate 검증
    - Fuzzy Patch 적용

    Dependency Injection:
    - context_retriever: 컨텍스트 검색
    - patch_generator: 패치 생성 (LLM)
    - static_gate: 정적 분석
    - fuzzy_patcher: 패치 적용
    """

    def __init__(
        self,
        context_retriever: IContextRetriever,
        patch_generator: IPatchGenerator,
        static_gate: IStaticAnalysisGate,
        fuzzy_patcher: IFuzzyPatcher,
    ):
        self._retriever = context_retriever
        self._generator = patch_generator
        self._static_gate = static_gate
        self._patcher = fuzzy_patcher

    async def propose_edit(
        self,
        request: EditRequest,
    ) -> EditProposal:
        """
        수정 제안 생성

        Pipeline:
        1. 파일 읽기
        2. 관련 컨텍스트 검색
        3. LLM 패치 생성
        4. Static Gate 검증
        5. Diff 생성

        Args:
            request: 수정 요청

        Returns:
            EditProposal: 승인 대기 중인 수정 제안
        """
        # 1. 원본 파일 읽기
        original_content = await self._read_file(request.file_path)

        # 2. 컨텍스트 검색
        context = await self._retriever.retrieve(
            file_path=request.file_path,
            query=request.instruction,
        )
        context[request.file_path] = original_content

        # 3. 패치 생성
        proposed_content = await self._generator.generate(
            request=request,
            context=context,
        )

        # 4. Static Gate 검증 + 자동 수정
        fixed_content, passed = await self._static_gate.validate_and_fix(
            file_path=request.file_path,
            content=proposed_content,
        )

        if passed:
            proposed_content = fixed_content

        # 5. Diff 생성
        diff = self._generate_diff(
            file_path=request.file_path,
            original=original_content,
            proposed=proposed_content,
        )

        return EditProposal(
            file_path=request.file_path,
            original_content=original_content,
            proposed_content=proposed_content,
            diff=diff,
            explanation=f"변경: {request.instruction}",
            approval_status=ApprovalStatus.PENDING,
        )

    async def apply_edit(
        self,
        proposal: EditProposal,
    ) -> PatchResult:
        """
        승인된 수정 적용

        Args:
            proposal: 승인된 EditProposal

        Returns:
            PatchResult: 적용 결과
        """
        if proposal.approval_status != ApprovalStatus.APPROVED:
            from codegraph_agent.ports.cascade import PatchResult, PatchStatus

            return PatchResult(
                status=PatchStatus.FAILED,
                applied_lines=(),
                conflicts=("Not approved",),
                fuzzy_matches=(),
            )

        return await self._patcher.apply_patch(
            file_path=proposal.file_path,
            diff=proposal.diff,
            fallback_to_fuzzy=True,
        )

    async def _read_file(self, file_path: str) -> str:
        """파일 읽기"""
        # TODO: ShadowFS 연동
        from pathlib import Path

        return Path(file_path).read_text()

    def _generate_diff(
        self,
        file_path: str,
        original: str,
        proposed: str,
    ) -> str:
        """Unified Diff 생성"""
        import difflib

        original_lines = original.splitlines(keepends=True)
        proposed_lines = proposed.splitlines(keepends=True)

        diff = difflib.unified_diff(
            original_lines,
            proposed_lines,
            fromfile=f"a/{file_path}",
            tofile=f"b/{file_path}",
        )

        return "".join(diff)
