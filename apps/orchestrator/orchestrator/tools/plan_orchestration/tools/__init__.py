"""
Plan Step Tools (RFC-041)

Plan의 Step에서 사용되는 세부 Tool들.
LLM에 직접 노출되지 않음 - Plan 내부에서만 사용.

Categories:
- Understanding: 코드 이해/분석
- Trace: 실행/데이터 흐름 추적
- Security: 보안 분석
- Explain: 결과 설명 (LLM 기반)
- Generate: 코드 생성
- Verify: 검증
- Variant: 유사 코드 탐색
"""

from .understanding import (
    AnalyzeFileStructureTool,
    AnalyzeUsagePatternTool,
    BuildDependencyGraphTool,
    ResolveImportsTool,
)
from .trace import (
    FindEntryPointsTool,
    TraceAliasTool,
)
from .security import (
    AnalyzeControlFlowTool,
    FindTypeHierarchyTool,
    ValidateSecurityGuardTool,
)
from .explain import (
    ExtractContextTool,
    ExplainFindingTool,
)
from .generate import (
    AnalyzeIssueTool,
    DetermineFixStrategyTool,
    GeneratePatchTool,
    ValidatePatchTool,
)
from .verify import (
    ParsePatchTool,
    VerifySyntaxTool,
    VerifyTypeSafetyTool,
    CheckRegressionTool,
    RunTestsTool,
)
from .variant import (
    ExtractCodePatternTool,
    SearchSimilarCodeTool,
    RankSimilarityTool,
)

__all__ = [
    # Understanding
    "AnalyzeUsagePatternTool",
    "AnalyzeFileStructureTool",
    "ResolveImportsTool",
    "BuildDependencyGraphTool",
    # Trace
    "TraceAliasTool",
    "FindEntryPointsTool",
    # Security
    "FindTypeHierarchyTool",
    "AnalyzeControlFlowTool",
    "ValidateSecurityGuardTool",
    # Explain
    "ExtractContextTool",
    "ExplainFindingTool",
    # Generate
    "AnalyzeIssueTool",
    "DetermineFixStrategyTool",
    "GeneratePatchTool",
    "ValidatePatchTool",
    # Verify
    "ParsePatchTool",
    "VerifySyntaxTool",
    "VerifyTypeSafetyTool",
    "CheckRegressionTool",
    "RunTestsTool",
    # Variant
    "ExtractCodePatternTool",
    "SearchSimilarCodeTool",
    "RankSimilarityTool",
]
