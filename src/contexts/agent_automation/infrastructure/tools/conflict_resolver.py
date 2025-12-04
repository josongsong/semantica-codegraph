"""
Patch Conflict Resolver

3-way merge 기반 패치 충돌 해결.

Features:
- diff-match-patch를 이용한 패치 생성/적용
- merge3 알고리즘으로 3-way merge
- 충돌 시 마커 삽입 및 수동 해결 지원

Usage:
    resolver = PatchConflictResolver()

    # 3-way merge
    result = resolver.merge_3way(base, current, proposed)
    if result.success:
        print(result.content)
    else:
        print(f"Conflicts: {result.conflicts}")

    # 패치 적용 (실패 시 3-way merge fallback)
    result = resolver.apply_patch_safe(original, modified, target)
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Literal

from diff_match_patch import diff_match_patch

from src.common.observability import get_logger

logger = get_logger(__name__)


class ConflictResolution(Enum):
    """충돌 해결 상태."""

    AUTO_MERGED = "auto_merged"  # 자동 병합 성공
    MANUAL_REQUIRED = "manual_required"  # 수동 해결 필요
    OURS = "ours"  # 현재 버전 선택
    THEIRS = "theirs"  # 제안 버전 선택


@dataclass
class ConflictRegion:
    """충돌 영역 정보."""

    base: str  # 원본 내용
    ours: str  # 현재 버전 내용
    theirs: str  # 제안 버전 내용
    line_start: int  # 시작 라인 (1-based)
    line_end: int  # 종료 라인 (1-based)


@dataclass
class MergeResult:
    """병합 결과."""

    success: bool
    content: str
    resolution: ConflictResolution
    conflicts: list[ConflictRegion] = field(default_factory=list)
    message: str = ""


class Merge3:
    """
    Simple 3-way merge implementation.

    Python stdlib의 difflib을 활용한 3-way merge.
    """

    def __init__(
        self,
        base_lines: list[str],
        ours_lines: list[str],
        theirs_lines: list[str],
    ):
        self.base = base_lines
        self.ours = ours_lines
        self.theirs = theirs_lines

    def merge_groups(self):
        """
        Generate merge groups.

        Yields:
            Tuples of (type, lines) where type is 'unchanged', 'ours', 'theirs', or 'conflict'
        """
        import difflib

        # SequenceMatcher로 세 버전 비교
        matcher_ours = difflib.SequenceMatcher(None, self.base, self.ours)
        matcher_theirs = difflib.SequenceMatcher(None, self.base, self.theirs)

        ours_changes = self._get_changes(matcher_ours)
        theirs_changes = self._get_changes(matcher_theirs)

        # 변경 영역 병합
        result = []
        base_idx = 0

        while base_idx < len(self.base):
            ours_change = self._find_change_at(ours_changes, base_idx)
            theirs_change = self._find_change_at(theirs_changes, base_idx)

            if ours_change is None and theirs_change is None:
                # 변경 없음
                result.append(("unchanged", [self.base[base_idx]]))
                base_idx += 1
            elif ours_change is not None and theirs_change is None:
                # ours만 변경
                result.append(("ours", ours_change["new_lines"]))
                base_idx = ours_change["base_end"]
            elif ours_change is None and theirs_change is not None:
                # theirs만 변경
                result.append(("theirs", theirs_change["new_lines"]))
                base_idx = theirs_change["base_end"]
            else:
                # 둘 다 변경 - 충돌 가능
                if ours_change["new_lines"] == theirs_change["new_lines"]:
                    # 같은 변경 - 충돌 아님
                    result.append(("ours", ours_change["new_lines"]))
                else:
                    # 충돌
                    base_start = min(ours_change["base_start"], theirs_change["base_start"])
                    base_end = max(ours_change["base_end"], theirs_change["base_end"])
                    result.append(
                        (
                            "conflict",
                            self.base[base_start:base_end],
                            ours_change["new_lines"],
                            theirs_change["new_lines"],
                        )
                    )
                base_idx = max(
                    ours_change["base_end"] if ours_change else base_idx + 1,
                    theirs_change["base_end"] if theirs_change else base_idx + 1,
                )

        return result

    def _get_changes(self, matcher) -> list[dict]:
        """Get list of changes from SequenceMatcher."""
        changes = []
        for tag, i1, i2, j1, j2 in matcher.get_opcodes():
            if tag != "equal":
                changes.append(
                    {
                        "base_start": i1,
                        "base_end": i2,
                        "new_lines": matcher.b[j1:j2],
                    }
                )
        return changes

    def _find_change_at(self, changes: list[dict], idx: int) -> dict | None:
        """Find change that includes the given base index."""
        for change in changes:
            if change["base_start"] <= idx < change["base_end"]:
                return change
        return None

    def merge_lines(self) -> tuple[list[str], list[tuple]]:
        """
        Perform 3-way merge and return merged lines with conflict info.

        Returns:
            Tuple of (merged_lines, conflicts)
            conflicts: list of (line_start, base_lines, ours_lines, theirs_lines)
        """
        import difflib

        merged = []
        conflicts = []
        line_num = 1

        # 간단한 구현: difflib.Differ 사용
        # base와 ours 비교, base와 theirs 비교
        sm_ours = difflib.SequenceMatcher(None, self.base, self.ours)
        sm_theirs = difflib.SequenceMatcher(None, self.base, self.theirs)

        # 양쪽 변경 사항을 인덱스로 매핑
        ours_ops = {op[1]: op for op in sm_ours.get_opcodes() if op[0] != "equal"}
        theirs_ops = {op[1]: op for op in sm_theirs.get_opcodes() if op[0] != "equal"}

        i = 0
        while i < len(self.base):
            ours_op = ours_ops.get(i)
            theirs_op = theirs_ops.get(i)

            if ours_op is None and theirs_op is None:
                # 변경 없음 - base 유지
                merged.append(self.base[i])
                line_num += 1
                i += 1

            elif ours_op is not None and theirs_op is None:
                # ours만 변경
                _, i1, i2, j1, j2 = ours_op
                merged.extend(self.ours[j1:j2])
                line_num += j2 - j1
                i = i2

            elif ours_op is None and theirs_op is not None:
                # theirs만 변경
                _, i1, i2, j1, j2 = theirs_op
                merged.extend(self.theirs[j1:j2])
                line_num += j2 - j1
                i = i2

            else:
                # 둘 다 변경 - 충돌 확인
                _, oi1, oi2, oj1, oj2 = ours_op
                _, ti1, ti2, tj1, tj2 = theirs_op

                ours_new = self.ours[oj1:oj2]
                theirs_new = self.theirs[tj1:tj2]

                if ours_new == theirs_new:
                    # 같은 변경 - 충돌 아님
                    merged.extend(ours_new)
                    line_num += len(ours_new)
                else:
                    # 충돌
                    conflict_start = line_num
                    base_content = self.base[i : max(oi2, ti2)]
                    conflicts.append((conflict_start, base_content, ours_new, theirs_new))

                    # 충돌 마커 삽입
                    merged.append("<<<<<<< CURRENT\n")
                    merged.extend(ours_new)
                    merged.append("=======\n")
                    merged.extend(theirs_new)
                    merged.append(">>>>>>> PROPOSED\n")
                    line_num += len(ours_new) + len(theirs_new) + 3

                i = max(oi2, ti2)

        return merged, conflicts


class PatchConflictResolver:
    """
    3-way merge 기반 패치 충돌 해결기.

    Usage:
        resolver = PatchConflictResolver()

        # 3-way merge
        result = resolver.merge_3way(base, current, proposed)

        # 안전한 패치 적용
        result = resolver.apply_patch_safe(original, modified, target)
    """

    def __init__(self):
        self.dmp = diff_match_patch()
        # 패치 적용 허용 임계값 (0.0 ~ 1.0)
        self.dmp.Match_Threshold = 0.5
        self.dmp.Patch_DeleteThreshold = 0.5

    def merge_3way(
        self,
        base: str,
        ours: str,
        theirs: str,
    ) -> MergeResult:
        """
        3-way merge 수행.

        Args:
            base: 원본 (공통 조상)
            ours: 현재 버전 (예: 파일의 현재 상태)
            theirs: 제안 버전 (예: 에이전트 제안)

        Returns:
            MergeResult with merged content or conflicts
        """
        # 라인 단위로 분리
        base_lines = base.splitlines(keepends=True)
        ours_lines = ours.splitlines(keepends=True)
        theirs_lines = theirs.splitlines(keepends=True)

        # 빈 파일 처리
        if not base_lines:
            base_lines = []
        if not ours_lines:
            ours_lines = []
        if not theirs_lines:
            theirs_lines = []

        # 3-way merge 수행
        m3 = Merge3(base_lines, ours_lines, theirs_lines)
        merged_lines, conflict_info = m3.merge_lines()

        content = "".join(merged_lines)

        # 충돌 정보 변환
        conflicts = []
        for line_start, base_content, ours_content, theirs_content in conflict_info:
            conflicts.append(
                ConflictRegion(
                    base="".join(base_content),
                    ours="".join(ours_content),
                    theirs="".join(theirs_content),
                    line_start=line_start,
                    line_end=line_start + len(ours_content) + len(theirs_content) + 3,
                )
            )

        if conflicts:
            return MergeResult(
                success=False,
                content=content,
                resolution=ConflictResolution.MANUAL_REQUIRED,
                conflicts=conflicts,
                message=f"Found {len(conflicts)} conflict(s) requiring manual resolution",
            )

        return MergeResult(
            success=True,
            content=content,
            resolution=ConflictResolution.AUTO_MERGED,
            conflicts=[],
            message="Successfully merged without conflicts",
        )

    def apply_patch_safe(
        self,
        original: str,
        modified: str,
        target: str,
    ) -> MergeResult:
        """
        diff-match-patch로 패치 생성 후 적용.

        original → modified 변경을 target에 적용.
        실패 시 3-way merge로 폴백.

        Args:
            original: 패치 생성 기준 원본
            modified: 패치 적용 후 결과
            target: 패치를 적용할 대상

        Returns:
            MergeResult with patched content
        """
        # 패치 생성
        patches = self.dmp.patch_make(original, modified)

        if not patches:
            # 변경 없음
            return MergeResult(
                success=True,
                content=target,
                resolution=ConflictResolution.AUTO_MERGED,
                message="No changes to apply",
            )

        # 패치 적용
        result, applied = self.dmp.patch_apply(patches, target)

        if all(applied):
            # 모든 패치 성공
            logger.info("patch_applied_successfully", patch_count=len(patches))
            return MergeResult(
                success=True,
                content=result,
                resolution=ConflictResolution.AUTO_MERGED,
                message=f"Successfully applied {len(patches)} patch(es)",
            )

        # 일부 패치 실패 - 3-way merge로 폴백
        failed_count = sum(1 for a in applied if not a)
        logger.warning(
            "patch_apply_partial_failure",
            total_patches=len(patches),
            failed_patches=failed_count,
        )

        return self.merge_3way(original, target, modified)

    def create_patch(self, original: str, modified: str) -> str:
        """
        Unified diff 형식의 패치 생성.

        Args:
            original: 원본 내용
            modified: 수정된 내용

        Returns:
            Unified diff 형식 문자열
        """
        patches = self.dmp.patch_make(original, modified)
        return self.dmp.patch_toText(patches)

    def apply_patch_text(self, target: str, patch_text: str) -> MergeResult:
        """
        텍스트 형식 패치 적용.

        Args:
            target: 패치 적용 대상
            patch_text: patch_toText()로 생성된 패치

        Returns:
            MergeResult
        """
        patches = self.dmp.patch_fromText(patch_text)

        if not patches:
            return MergeResult(
                success=True,
                content=target,
                resolution=ConflictResolution.AUTO_MERGED,
                message="No patches to apply",
            )

        result, applied = self.dmp.patch_apply(patches, target)

        if all(applied):
            return MergeResult(
                success=True,
                content=result,
                resolution=ConflictResolution.AUTO_MERGED,
                message=f"Applied {len(patches)} patch(es)",
            )

        failed_count = sum(1 for a in applied if not a)
        return MergeResult(
            success=False,
            content=result,
            resolution=ConflictResolution.MANUAL_REQUIRED,
            message=f"Failed to apply {failed_count}/{len(patches)} patch(es)",
        )

    def resolve_conflicts(
        self,
        merge_result: MergeResult,
        strategy: Literal["ours", "theirs"],
    ) -> MergeResult:
        """
        충돌 해결 전략 적용.

        Args:
            merge_result: 충돌이 있는 병합 결과
            strategy: 'ours' (현재 유지) 또는 'theirs' (제안 선택)

        Returns:
            충돌이 해결된 MergeResult
        """
        if merge_result.success:
            return merge_result

        content = merge_result.content
        lines = content.splitlines(keepends=True)
        resolved_lines = []

        i = 0
        while i < len(lines):
            line = lines[i]

            if line.startswith("<<<<<<< CURRENT"):
                # 충돌 시작
                ours_lines = []
                theirs_lines = []
                in_ours = True

                i += 1
                while i < len(lines):
                    line = lines[i]
                    if line.startswith("======="):
                        in_ours = False
                    elif line.startswith(">>>>>>> PROPOSED"):
                        break
                    elif in_ours:
                        ours_lines.append(line)
                    else:
                        theirs_lines.append(line)
                    i += 1

                # 전략에 따라 선택
                if strategy == "ours":
                    resolved_lines.extend(ours_lines)
                else:
                    resolved_lines.extend(theirs_lines)
            else:
                resolved_lines.append(line)

            i += 1

        return MergeResult(
            success=True,
            content="".join(resolved_lines),
            resolution=ConflictResolution.OURS if strategy == "ours" else ConflictResolution.THEIRS,
            conflicts=[],
            message=f"Resolved conflicts using '{strategy}' strategy",
        )

    def has_conflict_markers(self, content: str) -> bool:
        """충돌 마커가 있는지 확인."""
        return "<<<<<<< CURRENT" in content and ">>>>>>> PROPOSED" in content

    def count_conflicts(self, content: str) -> int:
        """충돌 개수 세기."""
        return content.count("<<<<<<< CURRENT")
