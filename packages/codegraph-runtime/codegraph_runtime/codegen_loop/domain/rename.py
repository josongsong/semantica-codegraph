"""
Rename Detection & Validation

ADR-011 Section 4 구현: Semantic Contract with Rename Handling
"""

from dataclasses import dataclass, field
from enum import Enum

from .patch import Patch


class RenameType(Enum):
    """Rename 유형"""

    SIMPLE = "simple"  # 단순 rename
    OVERLOAD = "overload"  # 오버로드 중 일부
    NAMESPACE = "namespace"  # 네임스페이스 변경
    SCOPE_AWARE = "scope_aware"  # 같은 이름, 다른 스코프
    CHAIN = "chain"  # A→B→C 체인
    SWAP = "swap"  # A↔B 교환


@dataclass(frozen=True)
class FunctionSignature:
    """
    함수 시그니처 (불변)

    ADR-011 CONTRACT SIGNATURE
    """

    name: str
    arity: int
    param_types: list[str]
    return_type: str
    throws: list[str] = field(default_factory=list)
    side_effects: dict[str, any] = field(default_factory=dict)

    def is_compatible_with(self, other: "FunctionSignature") -> bool:
        """
        호환성 검사 (backward compatibility)

        호환 규칙:
        - Parameter 수 같거나 기본값 있는 추가만
        - Return type 동일 또는 subtype
        - Exception은 추가 가능, 제거 불가
        """
        # Arity check (같거나, 기본값 있는 추가만 허용)
        if self.arity > other.arity:
            return False

        # Param types (기존 파라미터는 동일해야 함)
        for i in range(min(len(self.param_types), len(other.param_types))):
            if self.param_types[i] != other.param_types[i]:
                return False

        # Return type (동일해야 함 - subtype은 P1)
        if self.return_type != other.return_type:
            return False

        # Exception (기존 exception은 유지되어야 함)
        old_exceptions = set(self.throws)
        new_exceptions = set(other.throws)
        if not old_exceptions.issubset(new_exceptions):
            return False

        return True


@dataclass(frozen=True)
class RenameMapping:
    """
    Rename 매핑 (불변)

    old_name → new_name
    """

    old_name: str
    new_name: str
    rename_type: RenameType = RenameType.SIMPLE
    scope: str | None = None  # Class/Module scope

    def __post_init__(self):
        if self.old_name == self.new_name:
            raise ValueError("Rename mapping must have different names")

    @property
    def fqn_old(self) -> str:
        """Fully Qualified Name (old)"""
        return f"{self.scope}.{self.old_name}" if self.scope else self.old_name

    @property
    def fqn_new(self) -> str:
        """Fully Qualified Name (new)"""
        return f"{self.scope}.{self.new_name}" if self.scope else self.new_name


@dataclass
class CallerLocation:
    """호출 위치"""

    file_path: str
    line: int
    function_name: str

    def __hash__(self):
        return hash((self.file_path, self.line))


@dataclass
class RenameValidationResult:
    """Rename 검증 결과"""

    passed: bool
    reason: str = ""
    missing_files: list[str] = field(default_factory=list)
    incomplete_renames: list[CallerLocation] = field(default_factory=list)
    action: str = ""

    @classmethod
    def success(cls) -> "RenameValidationResult":
        return cls(passed=True)

    @classmethod
    def failure(
        cls,
        reason: str,
        missing_files: list[str] | None = None,
        action: str = "",
    ) -> "RenameValidationResult":
        return cls(
            passed=False,
            reason=reason,
            missing_files=missing_files or [],
            action=action,
        )


class ImplicitRenameDetector:
    """
    Implicit Rename 감지기 (순수 로직)

    ADR-011: detect_implicit_renames()
    """

    def __init__(
        self,
        similarity_threshold: float = 0.85,
        signature_check: bool = True,
    ):
        self.similarity_threshold = similarity_threshold
        self.signature_check = signature_check

    def detect(self, patch: Patch) -> list[RenameMapping]:
        """
        Patch에서 Implicit Rename 감지

        Heuristic:
        - 1 deleted + 1 added
        - Body similarity > threshold
        - Signature 동일 (이름 제외)

        Returns:
            감지된 Rename 리스트 (구현 완료 전까지 빈 리스트)

        Note:
            AST 기반 함수 추출이 구현되기 전까지는 빈 리스트 반환.
            명시적 rename만 지원 (implicit 감지 미지원).
        """
        candidates: list[RenameMapping] = []

        # TODO: Patch에서 deleted/added functions 추출
        # AST 기반 구현 전까지는 implicit rename 감지 불가
        try:
            deleted_funcs = self._extract_deleted_functions(patch)
            added_funcs = self._extract_added_functions(patch)
        except NotImplementedError:
            # 명시적으로 구현 안 됨을 인지하고 빈 리스트 반환
            # (implicit rename 감지 skip, explicit rename만 지원)
            return []

        for old_func in deleted_funcs:
            for new_func in added_funcs:
                # Body similarity
                similarity = self._compute_body_similarity(
                    old_func["body"],
                    new_func["body"],
                )

                if similarity < self.similarity_threshold:
                    continue

                # Signature check (optional)
                if self.signature_check:
                    if not self._same_signature_modulo_name(
                        old_func["signature"],
                        new_func["signature"],
                    ):
                        continue

                # Rename 후보 발견
                candidates.append(
                    RenameMapping(
                        old_name=old_func["name"],
                        new_name=new_func["name"],
                        rename_type=self._detect_rename_type(old_func, new_func),
                        scope=old_func.get("scope"),
                    )
                )

        return candidates

    def _extract_deleted_functions(self, patch: Patch) -> list[dict]:
        """
        삭제된 함수 추출

        L11 SOTA: Fake/Stub 금지 - 구현 안 됨을 명시적으로 표시

        Raises:
            NotImplementedError: AST 기반 구현 필요

        TODO: AST 기반 구현 (RFC-027)
        """
        raise NotImplementedError(
            "AST-based deleted function extraction not implemented yet. "
            "Use explicit rename detection instead. "
            "See RFC-027 for implementation plan."
        )

    def _extract_added_functions(self, patch: Patch) -> list[dict]:
        """
        추가된 함수 추출

        L11 SOTA: Fake/Stub 금지 - 구현 안 됨을 명시적으로 표시

        Raises:
            NotImplementedError: AST 기반 구현 필요

        TODO: AST 기반 구현 (RFC-027)
        """
        raise NotImplementedError(
            "AST-based added function extraction not implemented yet. "
            "Use explicit rename detection instead. "
            "See RFC-027 for implementation plan."
        )

    def _compute_body_similarity(self, body1: str, body2: str) -> float:
        """
        Body similarity (이름 제외)

        간단한 구현: 라인 기반 Jaccard
        TODO: AST 기반 구조적 비교
        """
        lines1 = {line.strip() for line in body1.splitlines() if line.strip()}
        lines2 = {line.strip() for line in body2.splitlines() if line.strip()}

        if not lines1 and not lines2:
            return 1.0

        intersection = len(lines1 & lines2)
        union = len(lines1 | lines2)

        return intersection / union if union > 0 else 0.0

    def _same_signature_modulo_name(self, sig1: dict, sig2: dict) -> bool:
        """
        Signature 동일 여부 (이름 제외)

        TODO: FunctionSignature 타입 사용
        """
        return (
            sig1.get("arity") == sig2.get("arity")
            and sig1.get("param_types") == sig2.get("param_types")
            and sig1.get("return_type") == sig2.get("return_type")
        )

    def _detect_rename_type(self, old_func: dict, new_func: dict) -> RenameType:
        """Rename 유형 감지"""
        # Simple heuristic
        if old_func.get("scope") != new_func.get("scope"):
            return RenameType.NAMESPACE

        return RenameType.SIMPLE


class RenameValidator:
    """
    Rename 검증기 (순수 로직)

    ADR-011: validate_with_rename_detection()
    """

    def __init__(self):
        self.detector = ImplicitRenameDetector()

    def validate(
        self,
        patch: Patch,
        explicit_renames: list[RenameMapping] | None = None,
        callers: dict[str, list[CallerLocation]] | None = None,
    ) -> RenameValidationResult:
        """
        Rename 검증

        Args:
            patch: 검증할 패치
            explicit_renames: Planner가 명시한 rename (우선순위 높음)
            callers: 각 함수의 caller 정보 {function_name: [CallerLocation]}

        Returns:
            검증 결과
        """
        # 1. Rename 수집 (Explicit + Implicit)
        renames = list(explicit_renames or [])
        if not explicit_renames:
            renames.extend(self.detector.detect(patch))

        if not renames:
            return RenameValidationResult.success()

        # 2. 각 Rename 검증
        for rename in renames:
            result = self._validate_single_rename(rename, patch, callers)
            if not result.passed:
                return result

        return RenameValidationResult.success()

    def _validate_single_rename(
        self,
        rename: RenameMapping,
        patch: Patch,
        callers: dict[str, list[CallerLocation]] | None,
    ) -> RenameValidationResult:
        """
        단일 Rename 검증

        검증 항목:
        1. 모든 caller가 patch에 포함되었는지
        2. Caller 내부에서 실제로 rename 되었는지
        3. Signature 호환성
        """
        if not callers:
            # Caller 정보 없으면 pass (HCG 필요)
            return RenameValidationResult.success()

        function_callers = callers.get(rename.old_name, [])

        # 1. 모든 caller 파일이 patch에 포함되었는지
        patch_files = patch.modified_files
        missing_files = []

        for caller in function_callers:
            if caller.file_path not in patch_files:
                missing_files.append(caller.file_path)

        if missing_files:
            return RenameValidationResult.failure(
                reason=f"Rename {rename.old_name}→{rename.new_name} but callers not updated",
                missing_files=list(set(missing_files)),
                action="UPDATE_CALLERS_FIRST",
            )

        # 2. Caller 내부에서 실제로 rename 되었는지
        # TODO: Patch의 실제 내용 확인
        # 현재는 Stub

        return RenameValidationResult.success()

    def validate_signature_compatibility(
        self,
        old_sig: FunctionSignature,
        new_sig: FunctionSignature,
    ) -> RenameValidationResult:
        """
        Signature 호환성 검증

        Rename + Signature 변경 동시 발생 시 reject
        """
        if not old_sig.is_compatible_with(new_sig):
            return RenameValidationResult.failure(
                reason="Rename changed signature: incompatible",
                action="RENAME_AND_SIGNATURE_MUST_BE_SEPARATE",
            )

        return RenameValidationResult.success()


class SwapRenameDetector:
    """
    Swap Rename 감지 (A↔B)

    ADR-011 TC-R05: Swap Rename
    """

    def detect(self, renames: list[RenameMapping]) -> list[tuple[RenameMapping, RenameMapping]]:
        """
        Swap 패턴 감지

        Returns:
            Swap 쌍 리스트
        """
        swaps = []

        for i, r1 in enumerate(renames):
            for r2 in renames[i + 1 :]:
                # A→B, B→A 패턴
                if r1.old_name == r2.new_name and r1.new_name == r2.old_name:
                    swaps.append((r1, r2))

        return swaps

    def validate_atomic(self, swap_pair: tuple[RenameMapping, RenameMapping]) -> bool:
        """
        Swap은 atomic하게 성공해야 함

        둘 중 하나라도 실패하면 전체 reject
        """
        # TODO: 실제 검증 로직
        return True


class ChainRenameTracker:
    """
    Chain Rename 추적 (A→B→C)

    ADR-011 TC-R04: Chain Rename
    """

    def __init__(self):
        self.history: list[RenameMapping] = []

    def add(self, rename: RenameMapping):
        """Rename 기록"""
        self.history.append(rename)

    def find_chain(self, target: str) -> list[RenameMapping]:
        """
        특정 이름으로 이어지는 Chain 찾기

        Example:
            foo → bar (Commit 1)
            bar → baz (Commit 2)
            → find_chain("baz") returns [foo→bar, bar→baz]
        """
        chain = []
        current = target

        # Backward tracking
        for rename in reversed(self.history):
            if rename.new_name == current:
                chain.insert(0, rename)
                current = rename.old_name

        return chain

    def get_original_name(self, current_name: str) -> str:
        """
        Chain의 원래 이름 찾기

        baz → foo (chain 거슬러 올라감)
        """
        chain = self.find_chain(current_name)
        return chain[0].old_name if chain else current_name


def detect_false_positives(
    candidates: list[RenameMapping],
    patch: Patch,
    callers: dict[str, list[CallerLocation]],
) -> list[RenameMapping]:
    """
    False Positive 제거

    ADR-011 TC-R07: 비슷한 코드지만 다른 함수

    규칙: Caller 변경이 없으면 rename이 아님
    """
    filtered = []

    for rename in candidates:
        old_callers = callers.get(rename.old_name, [])

        # Caller가 없으면 rename 아님 (사용되지 않는 함수)
        if not old_callers:
            continue

        # Caller 파일이 patch에 포함되어 있으면 valid rename
        patch_files = patch.modified_files
        has_caller_update = any(caller.file_path in patch_files for caller in old_callers)

        if has_caller_update:
            filtered.append(rename)

    return filtered
