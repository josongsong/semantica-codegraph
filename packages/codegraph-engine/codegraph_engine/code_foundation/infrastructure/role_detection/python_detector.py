"""
Python Role Detector - Production Grade

Python 코드의 클래스/함수 역할 자동 감지.

특징:
- 완전한 Null safety
- 완전한 에러 핸들링
- 타입 검증
- Thread-safe
"""

import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass


class PythonRoleDetector:
    """
    Python 역할 감지기 - Production Grade

    감지 우선순위:
    1. 데코레이터 (@app.route, @injectable 등)
    2. 베이스 클래스 (BaseService, Repository 등)
    3. 클래스명 패턴 (UserService, UserRepo 등)
    4. 구조 패턴 (싱글톤, 팩토리 등)
    """

    # 클래스명 → 역할 (정규식 패턴, 긴 것부터 매칭)
    CLASS_PATTERNS = {
        # Service layer (길이 우선)
        r".*Repository$": "repository",
        r".*Service$": "service",
        r".*Repo$": "repository",
        r".*Manager$": "service",  # 추가: UserManager, DataManager
        # Controller/Handler
        r".*Controller$": "controller",
        r".*Handler$": "controller",
        r".*Processor$": "service",  # 추가: DataProcessor, EventProcessor
        # Client/Connection
        r".*Client$": "service",  # 추가: APIClient, DatabaseClient
        r".*Connection$": "service",  # 추가: DatabaseConnection
        # DTO/Entity
        r".*DTO$": "dto",
        r".*Dto$": "dto",
        r".*Entity$": "entity",
        r".*Model$": "entity",
        # Config
        r".*Config$": "config",
        r".*Configuration$": "config",
        r".*Settings$": "config",
        # Patterns
        r".*Factory$": "factory",
        r".*Builder$": "builder",
        r".*Adapter$": "adapter",
        r".*Validator$": "validator",
        r".*Middleware$": "middleware",
        r".*Serializer$": "serializer",
        r".*Mapper$": "mapper",
        r".*Provider$": "provider",
    }

    # 데코레이터 → 역할
    DECORATOR_ROLES = {
        # Web frameworks
        "app.route": "route",
        "route": "route",
        "api_view": "route",
        "app.get": "route",
        "app.post": "route",
        "app.put": "route",
        "app.delete": "route",
        "app.patch": "route",
        "get": "route",
        "post": "route",
        "put": "route",
        "delete": "route",
        "patch": "route",
        # DI/IoC
        "injectable": "service",
        "singleton": "singleton",
        "inject": "service",
        # Testing
        "pytest.fixture": "test",
        "fixture": "test",
        # Caching
        "cached_property": "util",
        "cache": "util",
        "lru_cache": "util",
        # Async
        "asynccontextmanager": "middleware",
    }

    # 베이스 클래스 → 역할
    BASE_CLASS_ROLES = {
        # Service
        "BaseService": "service",
        "ServiceBase": "service",
        "AbstractService": "service",
        # Repository
        "Repository": "repository",
        "BaseRepository": "repository",
        "AbstractRepository": "repository",
        "RepositoryBase": "repository",
        # Controller
        "Controller": "controller",
        "BaseController": "controller",
        "Handler": "controller",
        "APIView": "controller",
        "GenericAPIView": "controller",
        # Entity/Model
        "Model": "entity",
        "BaseModel": "entity",
        "Entity": "entity",
        "Base": "entity",  # SQLAlchemy
        # Config
        "Config": "config",
        "BaseConfig": "config",
        "Settings": "config",
        "BaseSettings": "config",
        # DTO (베이스 클래스로도 우선순위 높임)
        "DTO": "dto",
        "BaseDTO": "dto",
        # Misc
        "ABC": None,
        "object": None,
    }

    def __init__(self):
        """초기화 (정규식 컴파일 + 에러 핸들링)"""
        self._compiled_patterns = {}
        self._pattern_compile_errors = []

        # 정규식 컴파일
        for pattern_str in self.CLASS_PATTERNS.keys():
            try:
                self._compiled_patterns[pattern_str] = re.compile(pattern_str)
            except re.error as e:
                self._pattern_compile_errors.append((pattern_str, str(e)))

    def detect_class_role(
        self,
        class_name: str,
        base_classes: list[str],
        decorators: list[str],
        method_names: list[str] | None = None,
    ) -> str | None:
        """
        클래스 역할 감지 (Production-grade: 중복 AST 순회 없음)

        우선순위:
        1. 데코레이터 (가장 명시적)
        2. 베이스 클래스
        3. 클래스명 패턴
        4. 메서드 패턴 (이미 생성된 IR 활용)

        Args:
            class_name: 클래스명
            base_classes: 베이스 클래스 목록
            decorators: 데코레이터 목록
            method_names: 메서드명 목록 (선택, IR에서 추출)
        """
        # Null safety
        if class_name is None or not isinstance(class_name, str):
            return None

        if not class_name.strip():
            return None

        # None → 빈 리스트
        if base_classes is None:
            base_classes = []
        if decorators is None:
            decorators = []
        if method_names is None:
            method_names = []

        try:
            # 1. 데코레이터 우선
            for decorator in decorators:
                if not isinstance(decorator, str):
                    continue
                try:
                    if role := self._match_decorator(decorator):
                        return role
                except Exception:
                    continue

            # 2. 베이스 클래스
            for base in base_classes:
                if not isinstance(base, str):
                    continue
                try:
                    base_name = base.split(".")[-1]
                    if role := self.BASE_CLASS_ROLES.get(base_name):
                        return role
                except Exception:
                    continue

            # 3. 클래스명 패턴 (정규식)
            for pattern_str, compiled_pattern in self._compiled_patterns.items():
                try:
                    if compiled_pattern.match(class_name):
                        return self.CLASS_PATTERNS[pattern_str]
                except Exception:
                    continue

            # 4. 메서드 기반 패턴 (IR 활용, AST 재순회 없음)
            if method_names:
                # 팩토리 패턴: create_*/build_* 메서드 2개 이상
                create_methods = sum(
                    1
                    for m in method_names
                    if isinstance(m, str) and (m.startswith("create_") or m.startswith("build_"))
                )
                if create_methods >= 2:
                    return "factory"

                # 싱글톤 패턴: __new__ 존재
                if "__new__" in method_names:
                    return "singleton"

            return None

        except Exception:
            return None

    def detect_function_role(
        self,
        func_name: str,
        decorators: list[str],
        parent_class: str | None = None,
    ) -> str | None:
        """
        함수/메서드 역할 감지 (Production-grade: parent_class 활용)
        """
        # Null safety
        if func_name is None or not isinstance(func_name, str):
            return None

        if not func_name.strip():
            return None

        if decorators is None:
            decorators = []

        try:
            # 1. 데코레이터 우선 (가장 명시적)
            for decorator in decorators:
                if not isinstance(decorator, str):
                    continue
                try:
                    if role := self._match_decorator(decorator):
                        return role
                except Exception:
                    continue

            # 2. 함수명 패턴 (명시적 패턴)
            try:
                # Test
                if func_name.startswith("test_"):
                    return "test"

                # Entry
                if func_name in ["main", "__main__"]:
                    return "entry"

                # Factory
                if func_name.startswith("create_") or func_name.startswith("build_"):
                    return "factory"

                # Validator
                if func_name.startswith("validate_"):
                    return "validator"

                # Serializer
                if func_name.startswith("serialize_") or func_name.startswith("deserialize_"):
                    return "serializer"
            except Exception:
                pass

            # 3. parent_class 기반 추론 (클래스 역할 상속)
            if parent_class and isinstance(parent_class, str):
                try:
                    # Controller/Handler 클래스의 메서드 → route
                    if "Controller" in parent_class or "Handler" in parent_class:
                        # create/build는 factory 우선 (이미 위에서 처리됨)
                        return "route"

                    # Service 클래스의 메서드 → service
                    if "Service" in parent_class or "Manager" in parent_class:
                        return "service"

                    # Repository 클래스의 메서드 → repository
                    if "Repository" in parent_class or "Repo" in parent_class:
                        return "repository"
                except Exception:
                    pass

            return None

        except Exception:
            return None

    def _match_decorator(self, decorator: str) -> str | None:
        """
        데코레이터 매칭 (Null-safe, Error-safe)
        """
        if decorator is None or not isinstance(decorator, str):
            return None

        if not decorator.strip():
            return None

        try:
            # @ 제거
            decorator = decorator.lstrip("@").strip()

            # 파라미터 제거
            if "(" in decorator:
                decorator = decorator.split("(")[0].strip()

            # 매칭
            for pattern, role in self.DECORATOR_ROLES.items():
                if pattern in decorator or decorator.endswith(pattern):
                    return role

            return None

        except Exception:
            return None
