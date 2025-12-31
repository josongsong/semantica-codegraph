"""
Unit Tests for PythonRoleDetector

Base/Corner/Edge/Extreme cases 전체 커버.
"""

import pytest

from codegraph_engine.code_foundation.infrastructure.role_detection import PythonRoleDetector


class TestBaseCases:
    """기본 동작"""

    def test_class_name_patterns(self):
        """클래스명 패턴"""
        detector = PythonRoleDetector()

        assert detector.detect_class_role("UserService", [], []) == "service"
        assert detector.detect_class_role("UserRepository", [], []) == "repository"
        assert detector.detect_class_role("UserController", [], []) == "controller"
        assert detector.detect_class_role("UserDTO", [], []) == "dto"
        assert detector.detect_class_role("UserEntity", [], []) == "entity"

    def test_base_class_patterns(self):
        """베이스 클래스"""
        detector = PythonRoleDetector()

        assert detector.detect_class_role("MyClass", ["BaseService"], []) == "service"
        assert detector.detect_class_role("MyClass", ["BaseRepository"], []) == "repository"
        assert detector.detect_class_role("User", ["django.db.models.Model"], []) == "entity"

    def test_decorator_priority(self):
        """데코레이터 우선순위"""
        detector = PythonRoleDetector()

        # 데코레이터 > 클래스명
        result = detector.detect_class_role("UserRepository", [], ["@injectable"])
        assert result == "service"

    def test_function_patterns(self):
        """함수 패턴"""
        detector = PythonRoleDetector()

        assert detector.detect_function_role("test_login", []) == "test"
        assert detector.detect_function_role("create_user", []) == "factory"
        assert detector.detect_function_role("validate_email", []) == "validator"

    def test_new_class_patterns(self):
        """새로 추가된 클래스 패턴"""
        detector = PythonRoleDetector()

        assert detector.detect_class_role("UserManager", [], []) == "service"
        assert detector.detect_class_role("DataProcessor", [], []) == "service"
        assert detector.detect_class_role("APIClient", [], []) == "service"
        assert detector.detect_class_role("DatabaseConnection", [], []) == "service"
        assert detector.detect_class_role("AppSettings", [], []) == "config"

    def test_parent_class_inheritance(self):
        """parent_class 상속 패턴"""
        detector = PythonRoleDetector()

        # Controller 메서드 → route
        assert detector.detect_function_role("index", [], "UserController") == "route"

        # Service 메서드 → service
        assert detector.detect_function_role("process", [], "DataService") == "service"

        # Repository 메서드 → repository
        assert detector.detect_function_role("save", [], "UserRepository") == "repository"

        # 함수명 패턴이 parent보다 우선
        assert detector.detect_function_role("create_user", [], "UserController") == "factory"


class TestCornerCases:
    """경계 조건"""

    def test_none_inputs(self):
        """None 입력"""
        detector = PythonRoleDetector()

        assert detector.detect_class_role(None, None, None) is None
        assert detector.detect_function_role(None, None) is None

    def test_empty_inputs(self):
        """빈 입력"""
        detector = PythonRoleDetector()

        assert detector.detect_class_role("", [], []) is None
        assert detector.detect_function_role("", []) is None

    def test_invalid_types_in_list(self):
        """잘못된 타입 혼합"""
        detector = PythonRoleDetector()

        # 숫자/None 무시하고 문자열만 처리
        result = detector.detect_class_role("User", [123, None, "BaseService"], [])
        assert result == "service"


class TestEdgeCases:
    """극단 조건"""

    def test_very_long_name(self):
        """매우 긴 이름"""
        detector = PythonRoleDetector()

        long_name = "A" * 10000 + "Service"
        assert detector.detect_class_role(long_name, [], []) == "service"

    def test_unicode_names(self):
        """유니코드"""
        detector = PythonRoleDetector()

        assert detector.detect_class_role("사용자Service", [], []) == "service"
        assert detector.detect_class_role("🔥Service", [], []) == "service"


class TestPerformance:
    """성능 검증"""

    def test_average_latency(self):
        """평균 레이턴시 < 0.01ms"""
        import time

        detector = PythonRoleDetector()
        times = []

        for _ in range(10000):
            start = time.perf_counter()
            detector.detect_class_role("UserService", [], [])
            elapsed = time.perf_counter() - start
            times.append(elapsed * 1000)

        avg = sum(times) / len(times)
        assert avg < 0.01


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
