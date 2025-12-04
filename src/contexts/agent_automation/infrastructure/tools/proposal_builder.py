"""
Proposal Package Builder

통합 제안 패키지 빌더.

ProposalPackage를 생성하여 다음을 포함:
- 변경 사항 (diff)
- 영향 분석
- 테스트 계획
- 리스크 평가
"""

import time
from typing import Any

from src.common.observability import get_logger
from src.contexts.agent_automation.infrastructure.schemas import ProposalPackage
from src.contexts.agent_automation.infrastructure.tools.impact_analysis_tool import ImpactAnalysisTool
from src.contexts.agent_automation.infrastructure.tools.patch_tools import ProposePatchTool
from src.contexts.code_foundation.infrastructure.graph.models import GraphDocument

logger = get_logger(__name__)


class ProposalBuilder:
    """
    통합 제안 패키지 빌더.

    여러 도구를 조합하여 완전한 제안 패키지를 생성합니다.
    """

    def __init__(
        self,
        graph: GraphDocument | None = None,
        base_path: str = ".",
    ):
        """
        Initialize proposal builder.

        Args:
            graph: GraphDocument for impact analysis
            base_path: Base path for file operations
        """
        self.graph = graph
        self.base_path = base_path
        self.patch_tool = ProposePatchTool(base_path)
        self.impact_tool = ImpactAnalysisTool(graph)

    async def build_proposal(
        self,
        title: str,
        description: str,
        patches: list[dict[str, Any]],
        changed_symbols: list[str] | None = None,
    ) -> ProposalPackage:
        """
        Build complete proposal package.

        Args:
            title: Proposal title
            description: Detailed description
            patches: List of patch specifications
                Each patch: {path, start_line, end_line, new_code, description}
            changed_symbols: Optional list of changed symbol IDs for impact analysis

        Returns:
            Complete ProposalPackage
        """
        import uuid

        proposal_id = str(uuid.uuid4())

        # 1. Generate patches and collect diffs
        changes = []
        all_diffs = []

        for patch_spec in patches:
            from src.contexts.agent_automation.infrastructure.schemas import ProposePatchInput

            patch_input = ProposePatchInput(
                path=patch_spec["path"],
                start_line=patch_spec["start_line"],
                end_line=patch_spec["end_line"],
                new_code=patch_spec["new_code"],
                description=patch_spec.get("description", "Code change"),
            )

            patch_output = await self.patch_tool._execute(patch_input)

            if patch_output.success:
                changes.append(
                    {
                        "patch_id": patch_output.patch_id,
                        "path": patch_output.path,
                        "description": patch_spec.get("description", ""),
                        "validation": patch_output.validation,
                    }
                )
                all_diffs.append(patch_output.diff)

        unified_diff = "\n\n".join(all_diffs)

        # 2. Run impact analysis (if symbols provided and graph available)
        impact_summary = {}
        if changed_symbols and self.graph:
            from src.contexts.agent_automation.infrastructure.schemas import ImpactAnalysisInput

            impact_input = ImpactAnalysisInput(
                changed_symbols=changed_symbols,
                change_type="modified",
                max_depth=3,
            )

            impact_output = await self.impact_tool._execute(impact_input)

            if impact_output.success:
                impact_summary = {
                    "direct_affected": len(impact_output.direct_affected),
                    "transitive_affected": len(impact_output.transitive_affected),
                    "affected_files": impact_output.affected_files,
                    "total_impact": impact_output.total_impact,
                    "symbols": [
                        {
                            "name": s.symbol_name,
                            "file": s.file_path,
                            "type": s.impact_type,
                        }
                        for s in impact_output.direct_affected[:10]  # Top 10
                    ],
                }

        # 3. Generate test plan
        test_plan = self._generate_test_plan(changes, impact_summary)

        # 4. Assess risks
        risk_level, risks = self._assess_risks(changes, impact_summary)

        # 5. Build proposal package
        return ProposalPackage(
            proposal_id=proposal_id,
            title=title,
            description=description,
            changes=changes,
            diff=unified_diff,
            impact_summary=impact_summary,
            test_plan=test_plan,
            risk_level=risk_level,
            risks=risks,
            created_at=time.time(),
            requires_approval=risk_level in ["medium", "high"],
        )

    def _generate_test_plan(
        self,
        changes: list[dict[str, Any]],
        impact_summary: dict[str, Any],
    ) -> dict[str, Any]:
        """Generate test plan based on changes and impact."""
        test_plan = {
            "existing_tests": [],
            "new_tests_needed": [],
            "coverage_areas": [],
        }

        # Extract affected files
        affected_files = set()
        for change in changes:
            affected_files.add(change["path"])

        # Add from impact analysis
        if "affected_files" in impact_summary:
            affected_files.update(impact_summary["affected_files"])

        # Suggest test files
        for file_path in affected_files:
            if file_path.endswith(".py"):
                # Python: suggest test file
                if not file_path.startswith("test_"):
                    test_file = f"tests/test_{file_path.split('/')[-1]}"
                    test_plan["existing_tests"].append(test_file)

        # Suggest new tests based on change count
        if len(changes) > 3:
            test_plan["new_tests_needed"].append("Integration tests for multi-file changes")

        # Coverage areas
        test_plan["coverage_areas"] = list(affected_files)

        return test_plan

    def _assess_risks(
        self,
        changes: list[dict[str, Any]],
        impact_summary: dict[str, Any],
    ) -> tuple[str, list[dict[str, Any]]]:
        """Assess risks for the proposal."""
        risks = []
        risk_score = 0

        # Risk 1: Number of changes
        if len(changes) > 5:
            risks.append(
                {
                    "type": "complexity",
                    "severity": "medium",
                    "description": f"Large number of changes ({len(changes)} files)",
                    "mitigation": "Consider breaking into smaller PRs",
                }
            )
            risk_score += 2

        # Risk 2: Impact scope
        total_impact = impact_summary.get("total_impact", 0)
        if total_impact > 20:
            risks.append(
                {
                    "type": "impact",
                    "severity": "high",
                    "description": f"Wide impact scope ({total_impact} symbols affected)",
                    "mitigation": "Extensive testing and gradual rollout recommended",
                }
            )
            risk_score += 3
        elif total_impact > 10:
            risks.append(
                {
                    "type": "impact",
                    "severity": "medium",
                    "description": f"Moderate impact scope ({total_impact} symbols affected)",
                    "mitigation": "Review and test affected areas",
                }
            )
            risk_score += 2

        # Risk 3: Validation failures
        syntax_errors = sum(1 for change in changes if not change.get("validation", {}).get("syntax_valid", True))
        if syntax_errors > 0:
            risks.append(
                {
                    "type": "syntax",
                    "severity": "high",
                    "description": f"Syntax validation failed for {syntax_errors} files",
                    "mitigation": "Fix syntax errors before applying",
                }
            )
            risk_score += 3

        # Determine overall risk level
        if risk_score >= 5:
            risk_level = "high"
        elif risk_score >= 2:
            risk_level = "medium"
        else:
            risk_level = "low"

        return risk_level, risks
