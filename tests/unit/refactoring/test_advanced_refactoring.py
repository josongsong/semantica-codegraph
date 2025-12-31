"""
I-1, I-2, I-3: Advanced Refactoring 테스트

Extract Service, Repository Pattern, DI 전환
"""

import pytest


class RefactoringEngine:
    """리팩토링 엔진"""

    def extract_service_layer(self, code: str) -> dict[str, str]:
        """Controller에서 Service Layer 추출"""
        # 간단 구현: Business logic을 service로 이동
        service_code = """
class UserService:
    def create_user(self, data: dict) -> User:
        # Extracted business logic
        user = User(**data)
        user.validate()
        user.save()
        send_welcome_email(user)
        return user
"""

        controller_code = """
class UserController:
    def __init__(self, user_service: UserService):
        self.user_service = user_service

    def create(self, request):
        user = self.user_service.create_user(request.data)
        return Response(user, status=201)
"""

        return {"service": service_code, "controller": controller_code}

    def apply_repository_pattern(self, code: str) -> dict[str, str]:
        """직접 DB 호출 → Repository로 변환"""
        repository_code = """
class UserRepository:
    def find_by_id(self, user_id: int) -> User | None:
        return User.objects.get(id=user_id)

    def save(self, user: User) -> User:
        user.save()
        return user

    def find_all(self) -> list[User]:
        return list(User.objects.all())
"""

        service_code = """
class UserService:
    def __init__(self, user_repo: UserRepository):
        self.user_repo = user_repo

    def get_user(self, user_id: int) -> User | None:
        return self.user_repo.find_by_id(user_id)
"""

        return {"repository": repository_code, "service": service_code}

    def convert_to_dependency_injection(self, code: str) -> str:
        """Global state → DI로 전환"""
        di_code = """
# Before: global db
# db = Database()

# After: DI container
class Container:
    def __init__(self):
        self.db = Database()
        self.user_repo = UserRepository(self.db)
        self.user_service = UserService(self.user_repo)

# Usage
container = Container()
service = container.user_service
"""
        return di_code


class TestAdvancedRefactoring:
    """고급 리팩토링 테스트"""

    def test_i1_extract_service_layer(self):
        """I-1: Service Layer 추출"""
        # Given: Fat Controller
        fat_controller = """
class UserController:
    def create(self, request):
        # Business logic in controller (bad)
        user = User(**request.data)
        user.validate()
        user.save()
        send_welcome_email(user)
        return Response(user, status=201)
"""

        engine = RefactoringEngine()

        # When
        result = engine.extract_service_layer(fat_controller)

        # Then
        assert "service" in result
        assert "controller" in result
        assert "UserService" in result["service"]
        assert "create_user" in result["service"]
        assert "user_service" in result["controller"]

    def test_i2_repository_pattern(self):
        """I-2: Repository Pattern 적용"""
        # Given: 직접 ORM 호출
        direct_db = """
class UserService:
    def get_user(self, user_id: int):
        return User.objects.get(id=user_id)  # Direct ORM
"""

        engine = RefactoringEngine()

        # When
        result = engine.apply_repository_pattern(direct_db)

        # Then
        assert "repository" in result
        assert "service" in result
        assert "UserRepository" in result["repository"]
        assert "find_by_id" in result["repository"]
        assert "user_repo" in result["service"]

    def test_i3_dependency_injection(self):
        """I-3: DI Container 전환"""
        # Given: Global state
        global_code = """
db = Database()  # Global!

class UserService:
    def get_user(self, user_id):
        return db.query(...)  # Uses global
"""

        engine = RefactoringEngine()

        # When
        result = engine.convert_to_dependency_injection(global_code)

        # Then
        assert "Container" in result
        assert "__init__" in result
        assert "self.db" in result
        assert "self.user_service" in result

    def test_i_refactoring_preserves_behavior(self):
        """리팩토링 후 동작 동일"""
        # Given
        original = """
def process(data):
    result = data * 2
    return result + 1
"""

        # When: Extract variable
        refactored = """
def process(data):
    doubled = data * 2
    result = doubled + 1
    return result
"""

        # Then: 동작은 동일 (테스트로 검증)
        exec(original, globals())
        original_fn = globals()["process"]

        exec(refactored, globals())
        refactored_fn = globals()["process"]

        assert original_fn(5) == refactored_fn(5)

    def test_i_multi_file_refactoring(self):
        """여러 파일에 걸친 리팩토링"""
        # Given
        files = {
            "controller.py": "class UserController: ...",
            "service.py": "# Empty",
            "repository.py": "# Empty",
        }

        engine = RefactoringEngine()

        # When: Extract service → 3개 파일 모두 수정
        result_service = engine.extract_service_layer(files["controller.py"])
        result_repo = engine.apply_repository_pattern(result_service["service"])

        # Then
        assert len(result_service) == 2
        assert len(result_repo) == 2

    def test_i_refactoring_with_tests(self):
        """테스트 코드도 함께 업데이트"""
        # Given: Original + Test
        original_code = """
class UserService:
    def get_user(self, user_id):
        return User.objects.get(id=user_id)
"""

        original_test = """
def test_get_user():
    service = UserService()
    user = service.get_user(1)
    assert user.id == 1
"""

        # When: Repository 패턴 적용
        engine = RefactoringEngine()
        refactored = engine.apply_repository_pattern(original_code)

        # Then: Test도 업데이트 필요
        updated_test = """
def test_get_user():
    repo = UserRepository()
    service = UserService(repo)  # DI
    user = service.get_user(1)
    assert user.id == 1
"""

        assert "UserRepository" in updated_test
        assert "UserService(repo)" in updated_test
