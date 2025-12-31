"""
TRCR Analysis Module - 고급 분석 엔진

주요 컴포넌트:
- DifferentialAnalyzer: 변경 부분만 분석 (PR review 최적화)
- GitDiffParser: Git diff 파싱
"""

from trcr.analysis.differential import (
    ChangedFunction,
    DiffAnalysisResult,
    DifferentialAnalyzer,
)
from trcr.analysis.git_diff_parser import (
    DiffHunk,
    FileDiff,
    GitDiffParser,
)

__all__ = [
    "DifferentialAnalyzer",
    "DiffAnalysisResult",
    "ChangedFunction",
    "GitDiffParser",
    "DiffHunk",
    "FileDiff",
]
