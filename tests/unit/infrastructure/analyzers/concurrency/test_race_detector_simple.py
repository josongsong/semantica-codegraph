"""
AsyncRaceDetector Simple Tests (RFC-028 Phase 2)

간소화된 테스트 (핵심 기능만 검증)
"""

import pytest

from codegraph_engine.code_foundation.infrastructure.analyzers.concurrency import (
    AccessType,
    AsyncRaceDetector,
    RaceSeverity,
)


class TestAsyncRaceDetectorBasic:
    """기본 기능 테스트"""

    def test_initialization(self):
        """초기화"""
        detector = AsyncRaceDetector()
        assert detector.alias_analyzer is not None

    def test_severity_write_write(self):
        """Write-Write: CRITICAL"""
        detector = AsyncRaceDetector()
        severity = detector._determine_severity(AccessType.WRITE, AccessType.WRITE)
        assert severity == RaceSeverity.CRITICAL

    def test_severity_write_read(self):
        """Write-Read: HIGH"""
        detector = AsyncRaceDetector()
        severity = detector._determine_severity(AccessType.WRITE, AccessType.READ)
        assert severity == RaceSeverity.HIGH

    def test_access_type_inference_write(self):
        """Access type: WRITE"""
        detector = AsyncRaceDetector()
        stmt = {"text": "self.count = 1"}
        access_type = detector._infer_access_type(stmt, "self.count")
        assert access_type == AccessType.WRITE

    def test_access_type_inference_read_write(self):
        """Access type: READ_WRITE"""
        detector = AsyncRaceDetector()
        stmt = {"text": "self.count += 1"}
        access_type = detector._infer_access_type(stmt, "self.count")
        assert access_type == AccessType.READ_WRITE

    def test_access_type_inference_read(self):
        """Access type: READ"""
        detector = AsyncRaceDetector()
        stmt = {"text": "x = self.count"}
        access_type = detector._infer_access_type(stmt, "self.count")
        assert access_type == AccessType.READ

    def test_extract_lock_var(self):
        """Lock variable 추출"""
        detector = AsyncRaceDetector()
        lock_var = detector._extract_lock_var("async with self.lock:")
        assert "lock" in lock_var.lower()

    def test_has_await_between(self):
        """Await 사이 확인"""
        from codegraph_engine.code_foundation.infrastructure.analyzers.concurrency.models import AwaitPoint

        detector = AsyncRaceDetector()
        await_points = [AwaitPoint(file_path="test.py", line=5, await_expr="await sleep()", function_name="func")]

        # Line 3 ~ 7 사이에 await (line 5)
        assert detector._has_await_between(3, 7, await_points) == True

        # Line 1 ~ 3 사이에 await 없음
        assert detector._has_await_between(1, 3, await_points) == False


class TestRaceDetectorArchitecture:
    """Architecture 검증"""

    def test_no_infrastructure_coupling(self):
        """Infrastructure 의존성 없음 (Hexagonal)"""
        import inspect

        from codegraph_engine.code_foundation.infrastructure.analyzers.concurrency import race_detector

        source = inspect.getsource(race_detector)

        # No DB imports (Hexagonal)
        assert "import psycopg" not in source
        assert "import redis" not in source
        assert "import sqlalchemy" not in source

    def test_must_alias_dependency(self):
        """Must-alias 의존성 (100% 정확도)"""
        detector = AsyncRaceDetector()

        # AliasAnalyzer 있음
        assert detector.alias_analyzer is not None

        # Must-alias 메서드 있음
        assert hasattr(detector.alias_analyzer, "is_aliased")
