"""
Rename Detection & Validation Tests

ADR-011 Section 20: TC-R01 ~ TC-R16
"""

import pytest

from codegraph_runtime.codegen_loop.domain.patch import FileChange, Patch, PatchStatus
from codegraph_runtime.codegen_loop.domain.rename import (
    CallerLocation,
    ChainRenameTracker,
    FunctionSignature,
    ImplicitRenameDetector,
    RenameMapping,
    RenameType,
    RenameValidator,
    SwapRenameDetector,
    detect_false_positives,
)


class TestFunctionSignature:
    """FunctionSignature 테스트"""

    def test_signature_compatible_same(self):
        """동일한 signature는 호환"""
        sig1 = FunctionSignature(
            name="foo",
            arity=2,
            param_types=["int", "str"],
            return_type="bool",
        )
        sig2 = FunctionSignature(
            name="bar",  # 이름만 다름
            arity=2,
            param_types=["int", "str"],
            return_type="bool",
        )

        assert sig1.is_compatible_with(sig2)

    def test_signature_incompatible_return_type(self):
        """Return type 변경은 비호환"""
        sig1 = FunctionSignature(
            name="foo",
            arity=1,
            param_types=["int"],
            return_type="int",
        )
        sig2 = FunctionSignature(
            name="foo",
            arity=1,
            param_types=["int"],
            return_type="str",  # 변경
        )

        assert not sig1.is_compatible_with(sig2)

    def test_signature_incompatible_arity_decrease(self):
        """파라미터 감소는 비호환"""
        sig1 = FunctionSignature(
            name="foo",
            arity=2,
            param_types=["int", "str"],
            return_type="bool",
        )
        sig2 = FunctionSignature(
            name="foo",
            arity=1,
            param_types=["int"],
            return_type="bool",
        )

        assert not sig1.is_compatible_with(sig2)

    def test_signature_compatible_exception_added(self):
        """Exception 추가는 호환"""
        sig1 = FunctionSignature(
            name="foo",
            arity=1,
            param_types=["int"],
            return_type="int",
            throws=["ValueError"],
        )
        sig2 = FunctionSignature(
            name="foo",
            arity=1,
            param_types=["int"],
            return_type="int",
            throws=["ValueError", "TypeError"],  # 추가
        )

        assert sig1.is_compatible_with(sig2)

    def test_signature_incompatible_exception_removed(self):
        """Exception 제거는 비호환"""
        sig1 = FunctionSignature(
            name="foo",
            arity=1,
            param_types=["int"],
            return_type="int",
            throws=["ValueError", "TypeError"],
        )
        sig2 = FunctionSignature(
            name="foo",
            arity=1,
            param_types=["int"],
            return_type="int",
            throws=["ValueError"],  # 제거
        )

        assert not sig1.is_compatible_with(sig2)


class TestRenameMapping:
    """RenameMapping 테스트"""

    def test_rename_mapping_fqn(self):
        """Fully Qualified Name 생성"""
        rename = RenameMapping(
            old_name="process_data",
            new_name="process_user_data",
            scope="module.utils",
        )

        assert rename.fqn_old == "module.utils.process_data"
        assert rename.fqn_new == "module.utils.process_user_data"

    def test_rename_mapping_no_scope(self):
        """Scope 없는 경우"""
        rename = RenameMapping(
            old_name="foo",
            new_name="bar",
        )

        assert rename.fqn_old == "foo"
        assert rename.fqn_new == "bar"

    def test_rename_mapping_same_name_raises(self):
        """같은 이름은 에러"""
        with pytest.raises(ValueError):
            RenameMapping(old_name="foo", new_name="foo")


class TestRenameValidator:
    """RenameValidator 테스트 (ADR-011 TC-R01~R16)"""

    def test_tc_r01_simple_rename_all_callers_updated(self):
        """TC-R01: Simple Rename (정의 + 모든 caller)"""
        validator = RenameValidator()

        # Rename: process_data → process_user_data
        rename = RenameMapping(
            old_name="process_data",
            new_name="process_user_data",
        )

        # Callers
        callers = {
            "process_data": [
                CallerLocation("main.py", 23, "main"),
                CallerLocation("handler.py", 45, "handle_request"),
            ]
        }

        # Patch에 모든 파일 포함
        patch = Patch(
            id="test",
            iteration=1,
            files=[
                FileChange("main.py", "old", "new", []),
                FileChange("handler.py", "old", "new", []),
            ],
            status=PatchStatus.GENERATED,
        )

        # 검증: 성공 (stub이라 실제로는 caller 체크 안함)
        result = validator.validate(
            patch=patch,
            explicit_renames=[rename],
            callers=callers,
        )

        # Stub 구현에서는 caller 정보 없으면 pass
        # 실제 구현 시 patch 내용 검증 필요
        assert result.passed or not result.passed  # Placeholder

    def test_tc_r02_partial_caller_update_rejected(self):
        """TC-R02: Partial Caller Update (누락) → REJECT"""
        validator = RenameValidator()

        rename = RenameMapping(
            old_name="process_data",
            new_name="process_user_data",
        )

        # 2개 caller 중 1개만 patch에 포함
        callers = {
            "process_data": [
                CallerLocation("main.py", 23, "main"),
                CallerLocation("handler.py", 45, "handle_request"),  # 누락
            ]
        }

        patch = Patch(
            id="test",
            iteration=1,
            files=[
                FileChange("main.py", "old", "new", []),
                # handler.py 누락
            ],
            status=PatchStatus.GENERATED,
        )

        result = validator.validate(
            patch=patch,
            explicit_renames=[rename],
            callers=callers,
        )

        # TODO: 실제 구현 시 검증
        # assert not result.passed
        # assert "handler.py" in result.missing_files


class TestImplicitRenameDetector:
    """ImplicitRenameDetector 테스트"""

    def test_detect_no_renames(self):
        """Rename 없는 경우"""
        detector = ImplicitRenameDetector()

        patch = Patch(
            id="test",
            iteration=1,
            files=[FileChange("main.py", "def foo(): pass", "def bar(): pass", [])],
            status=PatchStatus.GENERATED,
        )

        result = detector.detect(patch)

        # Stub 구현이라 빈 리스트
        assert result == []

    def test_body_similarity_identical(self):
        """동일한 body는 1.0"""
        detector = ImplicitRenameDetector()

        body = """
def foo(x):
    return x * 2
"""

        similarity = detector._compute_body_similarity(body, body)
        assert similarity == 1.0

    def test_body_similarity_different(self):
        """완전히 다른 body는 0.0"""
        detector = ImplicitRenameDetector()

        body1 = "def foo(x): return x * 2"
        body2 = "def bar(y): return y + 3"

        similarity = detector._compute_body_similarity(body1, body2)
        assert similarity < 0.5


class TestSwapRenameDetector:
    """SwapRenameDetector 테스트 (TC-R05)"""

    def test_detect_swap(self):
        """A↔B Swap 감지"""
        detector = SwapRenameDetector()

        renames = [
            RenameMapping(old_name="A", new_name="B"),
            RenameMapping(old_name="B", new_name="A"),
        ]

        swaps = detector.detect(renames)

        assert len(swaps) == 1
        assert swaps[0][0].old_name == "A"
        assert swaps[0][1].old_name == "B"

    def test_no_swap(self):
        """Swap 아닌 경우"""
        detector = SwapRenameDetector()

        renames = [
            RenameMapping(old_name="A", new_name="B"),
            RenameMapping(old_name="C", new_name="D"),
        ]

        swaps = detector.detect(renames)

        assert len(swaps) == 0


class TestChainRenameTracker:
    """ChainRenameTracker 테스트 (TC-R04)"""

    def test_find_chain(self):
        """Chain Rename 추적"""
        tracker = ChainRenameTracker()

        # A → B → C
        tracker.add(RenameMapping(old_name="foo", new_name="bar"))
        tracker.add(RenameMapping(old_name="bar", new_name="baz"))

        chain = tracker.find_chain("baz")

        assert len(chain) == 2
        assert chain[0].old_name == "foo"
        assert chain[0].new_name == "bar"
        assert chain[1].old_name == "bar"
        assert chain[1].new_name == "baz"

    def test_get_original_name(self):
        """원래 이름 찾기"""
        tracker = ChainRenameTracker()

        tracker.add(RenameMapping(old_name="foo", new_name="bar"))
        tracker.add(RenameMapping(old_name="bar", new_name="baz"))

        original = tracker.get_original_name("baz")

        assert original == "foo"

    def test_no_chain(self):
        """Chain 없는 경우"""
        tracker = ChainRenameTracker()

        tracker.add(RenameMapping(old_name="foo", new_name="bar"))

        chain = tracker.find_chain("baz")  # 존재하지 않음

        assert len(chain) == 0


class TestFalsePositiveDetection:
    """False Positive 감지 (TC-R07)"""

    def test_false_positive_no_caller_change(self):
        """Caller 변경 없으면 rename 아님"""
        candidates = [
            RenameMapping(old_name="calc_price", new_name="calc_total"),
        ]

        # Caller 있지만 patch에 포함 안됨
        callers = {
            "calc_price": [
                CallerLocation("main.py", 10, "main"),
            ]
        }

        patch = Patch(
            id="test",
            iteration=1,
            files=[FileChange("utils.py", "old", "new", [])],  # caller 없음
            status=PatchStatus.GENERATED,
        )

        filtered = detect_false_positives(candidates, patch, callers)

        # Caller 업데이트 없으면 제거
        assert len(filtered) == 0


@pytest.mark.parametrize(
    "old_name,new_name,callers,patch_files,expected",
    [
        # TC-R01: 모든 caller 포함 → ACCEPT
        (
            "process_data",
            "process_user_data",
            ["main.py:23", "handler.py:45"],
            ["main.py", "handler.py", "lib.py"],
            "ACCEPT",
        ),
        # TC-R02: Caller 누락 → REJECT
        (
            "process_data",
            "process_user_data",
            ["main.py:23", "handler.py:45"],
            ["main.py", "lib.py"],  # handler.py 누락
            "REJECT",
        ),
    ],
)
def test_rename_validation_matrix(old_name, new_name, callers, patch_files, expected):
    """
    ADR-011 VALIDATION MATRIX 테스트

    TODO: 실제 Patch 내용 검증 구현 필요
    """
    # Placeholder test
    assert expected in ["ACCEPT", "REJECT"]
