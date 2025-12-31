"""
Role Detector Protocol

역할 감지 인터페이스 정의.
"""

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    pass


class RoleDetector(Protocol):
    """
    역할 감지 인터페이스.

    언어별 구현체가 이 프로토콜을 따름:
    - PythonRoleDetector
    - TypeScriptRoleDetector
    - JavaRoleDetector
    """

    def detect_class_role(
        self,
        class_name: str,
        base_classes: list[str],
        decorators: list[str],
        method_names: list[str] | None = None,
    ) -> str | None:
        """
        클래스 역할 감지.

        우선순위:
        1. 데코레이터/어노테이션 (가장 명시적)
        2. 베이스 클래스
        3. 클래스명 패턴
        4. 구조 패턴 (싱글톤, 팩토리 등)

        Args:
            class_name: 클래스명 (e.g., "UserService")
            base_classes: 베이스 클래스 리스트 (e.g., ["BaseService", "ABC"])
            decorators: 데코레이터 리스트 (e.g., ["@injectable", "@singleton"])
            method_names: 메서드명 리스트 (선택, e.g., ["create_user", "build_user"])

        Returns:
            역할 문자열 또는 None
            - "service", "repository", "controller", "route"
            - "factory", "builder", "adapter"
            - "singleton", "dto", "entity", "config"
            - "test", "util", "middleware"

        Example:
            >>> detector = PythonRoleDetector()
            >>> role = detector.detect_class_role(
            ...     class_name="UserService",
            ...     base_classes=["BaseService"],
            ...     decorators=["@injectable"],
            ...     ast_node=ast,
            ... )
            >>> assert role == "service"
        """
        ...

    def detect_function_role(
        self,
        func_name: str,
        decorators: list[str],
        parent_class: str | None = None,
    ) -> str | None:
        """
        함수/메서드 역할 감지.

        Args:
            func_name: 함수명 (e.g., "test_login", "create_user")
            decorators: 데코레이터 리스트 (e.g., ["@app.route", "@pytest.fixture"])
            parent_class: 부모 클래스명 (메서드인 경우, e.g., "UserController")
            ast_node: Tree-sitter AST 노드

        Returns:
            역할 문자열 또는 None
            - "route", "test", "entry", "factory", "validator"

        Example:
            >>> role = detector.detect_function_role(
            ...     func_name="test_login",
            ...     decorators=[],
            ...     parent_class=None,
            ...     ast_node=ast,
            ... )
            >>> assert role == "test"
        """
        ...
