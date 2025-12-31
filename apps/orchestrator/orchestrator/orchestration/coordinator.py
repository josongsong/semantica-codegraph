"""
Agent Coordinator

전체 Agent 시스템의 총괄 조율자.

책임:
1. Intent 분류 (Router 위임)
2. Context 선택 (code_editing, conversation, search)
3. 실행 위임
4. 결과 수집 및 반환

Example:
    coordinator = AgentCoordinator()
    result = await coordinator.handle("Fix bug in payment.py")
"""

import logging
from typing import Any

logger = logging.getLogger(__name__)


class AgentCoordinator:
    """
    Agent Coordinator - 중앙 관제탑

    모든 agent contexts를 조율하고 적절한 context로 라우팅합니다.
    """

    def __init__(
        self,
        router: Any = None,
        code_editing_context: Any = None,
        conversation_context: Any = None,
        search_context: Any = None,
    ):
        """
        Args:
            router: UnifiedRouter 인스턴스
            code_editing_context: CodeEditingContext 인스턴스
            conversation_context: ConversationContext 인스턴스 (TODO)
            search_context: SearchContext 인스턴스 (TODO)
        """
        self.router = router
        self.contexts = {
            "code_edit": code_editing_context,
            "conversation": conversation_context,
            "search": search_context,
        }

    async def handle(self, user_input: str, context: dict[str, Any] | None = None) -> dict[str, Any]:
        """
        사용자 요청 처리

        Args:
            user_input: 사용자 입력
            context: 추가 컨텍스트

        Returns:
            실행 결과
        """
        if context is None:
            context = {}

        # 1. Intent 분류
        if self.router:
            intent_result = await self.router.route(user_input, context)
            intent = intent_result.intent
            logger.info(f"Intent classified: {intent}")
        else:
            # Fallback: code_edit로 가정
            intent = "code_edit"
            logger.warning("Router not configured, defaulting to code_edit")

        # 2. 적절한 Context 선택
        selected_context = self.contexts.get(intent)

        if not selected_context:
            raise ValueError(f"No context registered for intent: {intent}")

        # 3. 실행
        logger.info(f"Delegating to {intent} context")
        result = await selected_context.execute(user_input, context)

        return result
