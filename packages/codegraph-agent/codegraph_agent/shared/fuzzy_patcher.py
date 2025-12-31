"""
Smart Fuzzy Patcher Adapter

RFC-060: git apply 실패 시 유연한 패칭 제공

Hexagonal Architecture: Infrastructure Port 사용
"""

import difflib
import logging
import re

from codegraph_agent.ports.cascade import (
    DiffAnchor,
    IFuzzyPatcher,
    PatchResult,
    PatchStatus,
)
from codegraph_agent.ports.infrastructure import IFileSystem, IInfraCommandExecutor

logger = logging.getLogger(__name__)


class FuzzyPatcherAdapter(IFuzzyPatcher):
    """
    Smart Fuzzy Patcher 구현체

    책임:
    1. git apply 시도
    2. 실패 시 fuzzy matching fallback
    3. 앵커 포인트 기반 위치 탐색

    Dependency Injection:
    - command_executor: 명령 실행
    - filesystem: 파일 시스템 접근
    """

    def __init__(
        self,
        command_executor: IInfraCommandExecutor,
        filesystem: IFileSystem,
        whitespace_insensitive: bool = True,
        min_confidence: float = 0.8,
    ):
        self._executor = command_executor
        self._fs = filesystem
        self._whitespace_insensitive = whitespace_insensitive
        self._min_confidence = min_confidence

    async def apply_patch(
        self,
        file_path: str,
        diff: str,
        fallback_to_fuzzy: bool = True,
    ) -> PatchResult:
        """패치 적용 (git apply 실패 시 fuzzy matching)"""
        # Input validation
        if not file_path or not file_path.strip():
            raise ValueError("file_path cannot be empty")
        if not diff or not diff.strip():
            raise ValueError("diff cannot be empty")

        # Security: Path traversal 차단
        if ".." in file_path:
            raise ValueError(f"Invalid file path (security): {file_path}")

        # 1. git apply 시도
        git_result = await self._try_git_apply(file_path, diff)
        if git_result.is_success():
            logger.info(f"Git apply succeeded: {file_path}")
            return git_result

        # 2. git apply 실패 시 fuzzy 폴백
        if not fallback_to_fuzzy:
            logger.warning(f"Git apply failed, fuzzy disabled: {file_path}")
            return git_result

        logger.info(f"Git apply failed, trying fuzzy match: {file_path}")
        return await self._fuzzy_apply(file_path, diff)

    async def find_anchors(
        self,
        file_content: str,
        target_block: str,
    ) -> list[DiffAnchor]:
        """변경 대상 블록의 앵커 포인트 탐색"""
        anchors = []
        target_lines = target_block.strip().split("\n")
        file_lines = file_content.split("\n")

        # 특징적인 라인 선택 (주석 제외, 길이 > 10)
        significant_lines = [
            (i, line)
            for i, line in enumerate(target_lines)
            if len(line.strip()) > 10 and not line.strip().startswith("#")
        ]

        for line_idx, line in significant_lines:
            context_before = tuple(target_lines[max(0, line_idx - 2) : line_idx])
            context_after = tuple(target_lines[line_idx + 1 : line_idx + 3])

            for file_line_num, file_line in enumerate(file_lines):
                if self._lines_match(line, file_line):
                    anchor = DiffAnchor(
                        line_number=file_line_num,
                        content=line,
                        context_before=context_before,
                        context_after=context_after,
                    )
                    anchors.append(anchor)
                    break

        logger.debug(f"Found {len(anchors)} anchors")
        return anchors

    async def fuzzy_match(
        self,
        anchor: DiffAnchor,
        file_content: str,
        threshold: float = 0.8,
    ) -> int | None:
        """Fuzzy matching으로 앵커 위치 찾기"""
        # Input validation
        if anchor is None:
            raise ValueError("anchor cannot be None")
        if file_content is None:
            raise ValueError("file_content cannot be None")
        if not (0.0 <= threshold <= 1.0):
            raise ValueError(f"threshold must be between 0.0 and 1.0, got {threshold}")

        file_lines = file_content.split("\n")
        best_match_line = None
        best_similarity = 0.0

        for i in range(len(file_lines)):
            line_sim = self._similarity(anchor.content, file_lines[i])

            if line_sim < threshold:
                continue

            # 컨텍스트 유사도 (가중치: 앵커 70%, 컨텍스트 30%)
            context_sim = self._context_similarity(anchor, file_lines, i)
            total_sim = 0.7 * line_sim + 0.3 * context_sim

            if total_sim > best_similarity:
                best_similarity = total_sim
                best_match_line = i

        if best_match_line is not None and best_similarity >= threshold:
            logger.debug(f"Fuzzy match found at line {best_match_line} (confidence: {best_similarity:.2f})")
            return best_match_line

        logger.warning(f"No fuzzy match found (best: {best_similarity:.2f})")
        return None

    # ========================================================================
    # Private Methods
    # ========================================================================

    async def _try_git_apply(
        self,
        file_path: str,
        diff: str,
    ) -> PatchResult:
        """git apply 시도"""
        try:
            # diff를 임시 파일로 저장
            patch_file = await self._fs.create_temp_file(
                suffix=".patch",
                content=diff,
            )

            # git apply --check
            check_result = await self._executor.execute(
                command=["git", "apply", "--check", patch_file],
                timeout=10.0,
            )

            if check_result.is_success():
                # 실제 적용
                apply_result = await self._executor.execute(
                    command=["git", "apply", patch_file],
                    timeout=10.0,
                )

                await self._fs.delete(patch_file)

                if apply_result.is_success():
                    return PatchResult(
                        status=PatchStatus.SUCCESS,
                        applied_lines=tuple(self._extract_applied_lines(diff)),
                        conflicts=(),
                        fuzzy_matches=(),
                    )

            await self._fs.delete(patch_file)

            return PatchResult(
                status=PatchStatus.FAILED,
                applied_lines=(),
                conflicts=(check_result.stderr,),
                fuzzy_matches=(),
            )

        except Exception as e:
            logger.error(f"Git apply error: {e}")
            return PatchResult(
                status=PatchStatus.FAILED,
                applied_lines=(),
                conflicts=(str(e),),
                fuzzy_matches=(),
            )

    async def _fuzzy_apply(
        self,
        file_path: str,
        diff: str,
    ) -> PatchResult:
        """Fuzzy matching으로 패치 적용"""
        changes = self._parse_diff(diff)

        if not await self._fs.exists(file_path):
            return PatchResult(
                status=PatchStatus.FAILED,
                applied_lines=(),
                conflicts=(f"File not found: {file_path}",),
                fuzzy_matches=(),
            )

        file_content = await self._fs.read_text(file_path)
        file_lines = file_content.split("\n")

        applied_lines: list[int] = []
        fuzzy_matches: list[tuple[int, float]] = []
        conflicts: list[str] = []

        for change in changes:
            old_block = change["old"]
            new_block = change["new"]

            anchors = await self.find_anchors(file_content, old_block)

            if not anchors:
                conflicts.append(f"No anchor found for: {old_block[:50]}...")
                continue

            anchor = anchors[0]
            match_line = await self.fuzzy_match(
                anchor,
                file_content,
                self._min_confidence,
            )

            if match_line is None:
                conflicts.append(f"Fuzzy match failed for: {old_block[:50]}...")
                continue

            # 변경 적용
            old_lines = old_block.split("\n")
            new_lines = new_block.split("\n")

            end_line = match_line + len(old_lines)
            file_lines[match_line:end_line] = new_lines

            applied_lines.extend(range(match_line, match_line + len(new_lines)))
            similarity = self._similarity(
                old_block,
                "\n".join(file_lines[match_line : match_line + len(new_lines)]),
            )
            fuzzy_matches.append((match_line, similarity))

        # 결과 저장
        if applied_lines and not conflicts:
            await self._fs.write_text(file_path, "\n".join(file_lines))
            status = PatchStatus.FUZZY_APPLIED
        elif applied_lines:
            await self._fs.write_text(file_path, "\n".join(file_lines))
            status = PatchStatus.CONFLICT
        else:
            status = PatchStatus.FAILED

        return PatchResult(
            status=status,
            applied_lines=tuple(applied_lines),
            conflicts=tuple(conflicts),
            fuzzy_matches=tuple(fuzzy_matches),
        )

    def _parse_diff(self, diff: str) -> list[dict[str, str]]:
        """Unified diff 파싱"""
        changes: list[dict[str, str]] = []
        lines = diff.split("\n")

        i = 0
        while i < len(lines):
            line = lines[i]

            if line.startswith("@@"):
                old_lines: list[str] = []
                new_lines: list[str] = []
                i += 1

                while i < len(lines) and not lines[i].startswith("@@"):
                    if lines[i].startswith("-"):
                        old_lines.append(lines[i][1:])
                    elif lines[i].startswith("+"):
                        new_lines.append(lines[i][1:])
                    elif lines[i].startswith(" "):
                        old_lines.append(lines[i][1:])
                        new_lines.append(lines[i][1:])
                    i += 1

                changes.append(
                    {
                        "old": "\n".join(old_lines),
                        "new": "\n".join(new_lines),
                    }
                )
            else:
                i += 1

        return changes

    def _lines_match(self, line1: str, line2: str) -> bool:
        """두 라인이 매칭되는지 확인"""
        if self._whitespace_insensitive:
            return line1.strip() == line2.strip()
        return line1 == line2

    def _similarity(self, str1: str, str2: str) -> float:
        """문자열 유사도 계산 (0.0 ~ 1.0)"""
        if self._whitespace_insensitive:
            str1 = re.sub(r"\s+", " ", str1.strip())
            str2 = re.sub(r"\s+", " ", str2.strip())

        return difflib.SequenceMatcher(None, str1, str2).ratio()

    def _context_similarity(
        self,
        anchor: DiffAnchor,
        file_lines: list[str],
        center_line: int,
    ) -> float:
        """컨텍스트 유사도 계산"""
        before_start = max(0, center_line - len(anchor.context_before))
        before_file = file_lines[before_start:center_line]

        after_end = min(
            len(file_lines),
            center_line + 1 + len(anchor.context_after),
        )
        after_file = file_lines[center_line + 1 : after_end]

        before_sim = 0.0
        if anchor.context_before and before_file:
            before_sim = self._similarity(
                "\n".join(anchor.context_before),
                "\n".join(before_file),
            )

        after_sim = 0.0
        if anchor.context_after and after_file:
            after_sim = self._similarity(
                "\n".join(anchor.context_after),
                "\n".join(after_file),
            )

        if before_sim > 0 and after_sim > 0:
            return (before_sim + after_sim) / 2
        return max(before_sim, after_sim)

    def _extract_applied_lines(self, diff: str) -> list[int]:
        """Diff에서 적용된 라인 번호 추출"""
        applied: list[int] = []

        for line in diff.split("\n"):
            match = re.match(
                r"@@\s+-\d+,?\d*\s+\+(\d+),?(\d*)\s+@@",
                line,
            )
            if match:
                start = int(match.group(1))
                count = int(match.group(2)) if match.group(2) else 1
                applied.extend(range(start, start + count))

        return applied
