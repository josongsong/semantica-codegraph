"""
Role Detection Infrastructure

역할 기반 패턴 감지 시스템.

클래스/함수의 역할(role)을 자동으로 감지:
- service, repository, controller, route
- factory, builder, adapter
- singleton, dto, entity, config
- test, util, middleware

감지 방식:
1. 데코레이터/어노테이션 (가장 명시적)
2. 베이스 클래스/인터페이스
3. 이름 패턴 (클래스명/함수명)
4. 구조 패턴 (싱글톤, 팩토리 등)
"""

from codegraph_engine.code_foundation.infrastructure.role_detection.base import RoleDetector
from codegraph_engine.code_foundation.infrastructure.role_detection.python_detector import PythonRoleDetector

__all__ = [
    "RoleDetector",
    "PythonRoleDetector",
]
