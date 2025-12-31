"""
LATS Reflexion Integration (v9 Advanced)

실패 이유 전파 (Verbal Feedback)

EXTREME-ADDENDUM P2 항목
"""

import logging

from .lats_models import LATSNode

logger = logging.getLogger(__name__)


class LATSReflexion:
    """
    LATS Reflexion (Domain Service)

    책임:
    1. 실패 이유 추출
    2. 부모 노드로 전파
    3. 형제 노드 생성 시 활용

    SOTA:
    - Verbal Feedback (숫자 → 텍스트)
    - Rejection Reason 관리

    효과: 탐색 효율 3배 향상

    EXTREME-ADDENDUM P2
    """

    def __init__(self):
        """초기화"""
        logger.info("LATSReflexion initialized")

    def extract_failure_reason(
        self,
        node: LATSNode,
        execution_error: str | None = None,
    ) -> str:
        """
        실패 이유 추출

        Args:
            node: 실패한 노드
            execution_error: 실행 에러 (Optional)

        Returns:
            실패 이유 (텍스트)
        """
        if execution_error:
            # 에러 메시지에서 핵심 추출
            reason = self._parse_error_message(execution_error)
            logger.debug(f"Extracted failure reason: {reason}")
            return reason

        # Q-value가 낮은 경우
        if node.q_value < 0.3:
            return "Low Q-value (poor solution quality)"

        # Thought Score가 낮은 경우
        if node.thought_score < 0.3:
            return "Low thought score (weak intermediate step)"

        return "Unknown failure"

    def propagate_to_parent(
        self,
        failed_node: LATSNode,
        failure_reason: str,
    ):
        """
        실패 이유를 부모 노드로 전파

        Args:
            failed_node: 실패한 노드
            failure_reason: 실패 이유
        """
        if not failed_node.parent:
            logger.debug("No parent to propagate to")
            return

        # 부모의 rejected_reasons에 추가
        failed_node.parent.add_rejection_reason(failure_reason)

        logger.debug(f"Propagated failure reason to parent: {failed_node.parent.node_id} ← {failure_reason}")

    def get_rejection_context(self, node: LATSNode) -> str:
        """
        형제 노드들의 실패 이유 요약

        Args:
            node: 현재 노드 (부모)

        Returns:
            실패 이유 컨텍스트 (프롬프트용)
        """
        if not node.rejected_reasons:
            return ""

        # 중복 제거
        unique_reasons = list(set(node.rejected_reasons))

        # 요약
        context = "이전 시도들이 실패한 이유:\n"
        for i, reason in enumerate(unique_reasons[:5], 1):  # 최대 5개
            context += f"{i}. {reason}\n"

        context += "\n위 실패를 피하는 다른 접근을 시도하세요."

        return context

    # ========================================================================
    # Private Methods
    # ========================================================================

    def _parse_error_message(self, error: str) -> str:
        """
        에러 메시지 파싱

        Args:
            error: 에러 메시지

        Returns:
            핵심 이유
        """
        # 간단한 휴리스틱
        if "IndexError" in error:
            return "IndexError (list index out of range)"

        if "TypeError" in error:
            return "TypeError (type mismatch)"

        if "AttributeError" in error:
            return "AttributeError (missing attribute)"

        if "ImportError" in error or "ModuleNotFoundError" in error:
            return "ImportError (missing library/module)"

        if "SyntaxError" in error:
            return "SyntaxError (invalid Python syntax)"

        if "NameError" in error:
            return "NameError (undefined variable)"

        # 기본: 첫 줄만
        first_line = error.split("\n")[0] if "\n" in error else error

        return first_line[:100]  # 최대 100자
