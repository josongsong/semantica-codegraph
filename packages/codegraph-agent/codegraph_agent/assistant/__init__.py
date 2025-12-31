"""
Assistant Mode (RFC-060)

Cursor-like 빠른 코드 수정:
- Context Retrieval (1-2초)
- Patch Generation (2-5초)
- User Approval
- Quick Test Run (선택)

사용 시나리오:
- 단발성 코드 수정
- 빠른 질의응답
- 짧은 리팩토링

핵심 원칙:
1. 빠른 응답 (5초 이내)
2. 사용자 승인 필수
3. 최소 오버헤드
"""

from codegraph_agent.assistant.quick_edit import QuickEditService

__all__ = [
    "QuickEditService",
]
