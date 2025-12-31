"""
MCP Prompts (RFC-SEM-022 SOTA)

LLM Agent 자기비판 및 추론 가이드.

SOTA Features:
- verify_evidence_logical_gap: 논리적 비약 점검
- suggest_additional_analysis: 추가 분석 제안
- critique_patch: Patch 자기비판
"""

from mcp.types import Prompt, PromptArgument


def get_prompts() -> list[Prompt]:
    """
    MCP Prompts 목록 (RFC-SEM-022).

    에이전트가 스스로 추론하고 자기비판하도록 유도.
    """
    return [
        # ========================================================
        # 1. verify_evidence_logical_gap
        # ========================================================
        Prompt(
            name="verify_evidence_logical_gap",
            description=(
                "에이전트 스스로 논리적 비약을 점검.\n\n"
                "Evidence → Conclusion 사이의 논리적 공백을 찾고, "
                "추가로 호출해야 할 도구를 제안."
            ),
            arguments=[
                PromptArgument(
                    name="evidence_summary",
                    description="현재까지 수집한 증거 요약",
                    required=True,
                ),
                PromptArgument(
                    name="patch_diff",
                    description="제안한 패치 diff",
                    required=False,
                ),
                PromptArgument(
                    name="claimed_conclusion",
                    description="주장하려는 결론",
                    required=True,
                ),
            ],
        ),
        # ========================================================
        # 2. suggest_additional_analysis
        # ========================================================
        Prompt(
            name="suggest_additional_analysis",
            description=(
                "현재 분석 결과를 보고 추가로 필요한 분석을 제안.\n\n"
                "예: graph.slice로 root cause 추출, "
                "graph.dataflow로 경로 증명 등."
            ),
            arguments=[
                PromptArgument(
                    name="current_findings",
                    description="현재까지 발견된 findings",
                    required=True,
                ),
                PromptArgument(
                    name="context",
                    description="분석 맥락 (코드 영역, 목적)",
                    required=True,
                ),
            ],
        ),
        # ========================================================
        # 3. critique_patch
        # ========================================================
        Prompt(
            name="critique_patch",
            description=(
                "제안한 patch를 자기비판.\n\n"
                "찾아야 할 문제:\n"
                "- 논리적 오류\n"
                "- 엣지 케이스 미처리\n"
                "- 성능 병목\n"
                "- 새로운 취약점 도입 가능성"
            ),
            arguments=[
                PromptArgument(
                    name="patch_diff",
                    description="제안한 패치 diff",
                    required=True,
                ),
                PromptArgument(
                    name="original_finding",
                    description="원래 발견된 취약점",
                    required=True,
                ),
                PromptArgument(
                    name="verification_result",
                    description="verify_patch_compile 결과 (optional)",
                    required=False,
                ),
            ],
        ),
        # ========================================================
        # 4. plan_verification_strategy
        # ========================================================
        Prompt(
            name="plan_verification_strategy",
            description=(
                "검증 전략 수립.\n\n"
                "어떤 순서로 verify 도구를 호출할지 계획:\n"
                "1. verify_patch_compile\n"
                "2. verify_finding_resolved\n"
                "3. verify_no_new_findings_introduced"
            ),
            arguments=[
                PromptArgument(
                    name="patch_type",
                    description="Patch 타입 (security_fix, refactor 등)",
                    required=True,
                ),
                PromptArgument(
                    name="impact_scope",
                    description="영향 범위 (files, functions)",
                    required=True,
                ),
            ],
        ),
        # ========================================================
        # 5. interpret_dataflow_result
        # ========================================================
        Prompt(
            name="interpret_dataflow_result",
            description=(
                "graph.dataflow 결과 해석.\n\n"
                "Dataflow 경로를 보고:\n"
                "- 취약점 심각도 평가\n"
                "- Sanitizer 효과 판단\n"
                "- 차단 지점 제안"
            ),
            arguments=[
                PromptArgument(
                    name="dataflow_result",
                    description="graph.dataflow 실행 결과",
                    required=True,
                ),
                PromptArgument(
                    name="policy",
                    description="적용된 정책 (sql_injection 등)",
                    required=True,
                ),
            ],
        ),
    ]


# ========================================================
# Prompt Templates (실제 LLM에게 전달될 텍스트)
# ========================================================


def get_prompt_template(name: str, arguments: dict) -> str:
    """
    Prompt 이름과 인자를 받아 실제 프롬프트 텍스트 생성.

    SOTA Pattern: 구조화된 추론 유도.
    """
    templates = {
        "verify_evidence_logical_gap": _verify_evidence_logical_gap_template,
        "suggest_additional_analysis": _suggest_additional_analysis_template,
        "critique_patch": _critique_patch_template,
        "plan_verification_strategy": _plan_verification_strategy_template,
        "interpret_dataflow_result": _interpret_dataflow_result_template,
    }

    template_fn = templates.get(name)
    if not template_fn:
        raise ValueError(f"Unknown prompt: {name}")

    return template_fn(arguments)


def _verify_evidence_logical_gap_template(args: dict) -> str:
    """verify_evidence_logical_gap 프롬프트."""
    return f"""
# 논리적 비약 점검 (Self-Critique)

## 수집한 증거
{args["evidence_summary"]}

## 제안한 패치
{args.get("patch_diff", "N/A")}

## 주장하려는 결론
{args["claimed_conclusion"]}

---

## 점검 항목

1. **증거 충분성**: 증거만으로 결론을 지지하는가?
2. **논리적 공백**: 증거 → 결론 사이에 빠진 단계가 있는가?
3. **추가 분석 필요**: 어떤 도구를 더 호출해야 하는가?
   - graph.slice: Root cause 확인
   - graph.dataflow: 경로 증명
   - preview_impact: 영향 범위 확인

## 출력 형식

```json
{{
  "logical_gaps": [
    {{"description": "...", "severity": "high|medium|low"}}
  ],
  "missing_evidence": ["..."],
  "suggested_tools": [
    {{"tool": "graph.slice", "reason": "..."}}
  ],
  "verdict": "solid|weak|insufficient"
}}
```
"""


def _suggest_additional_analysis_template(args: dict) -> str:
    """suggest_additional_analysis 프롬프트."""
    return f"""
# 추가 분석 제안

## 현재 Findings
{args["current_findings"]}

## 분석 맥락
{args["context"]}

---

## 제안 항목

1. **Slice 분석**: Root cause 추출 필요한가?
2. **Dataflow 증명**: 경로 증명이 필요한가?
3. **Impact 분석**: 변경 영향도를 확인해야 하는가?
4. **Reference 추적**: 호출자를 더 조사해야 하는가?

## 출력 형식

```json
{{
  "suggested_analyses": [
    {{
      "tool": "graph.slice",
      "target": "...",
      "reason": "...",
      "priority": "high|medium|low"
    }}
  ],
  "rationale": "..."
}}
```
"""


def _critique_patch_template(args: dict) -> str:
    """critique_patch 프롬프트."""
    return f"""
# Patch 자기비판

## 제안한 Patch
{args["patch_diff"]}

## 원래 Finding
{args["original_finding"]}

## 검증 결과
{args.get("verification_result", "N/A")}

---

## 비판 항목

1. **논리적 정확성**: 수정이 문제를 실제로 해결하는가?
2. **엣지 케이스**: 처리하지 못한 케이스가 있는가?
3. **성능**: 병목이 생길 가능성은?
4. **새로운 취약점**: 이 패치가 다른 문제를 일으킬 수 있는가?
5. **가독성**: 코드가 명확한가?

## 출력 형식

```json
{{
  "issues": [
    {{
      "category": "logic|edge_case|performance|security|readability",
      "severity": "critical|high|medium|low",
      "description": "...",
      "suggestion": "..."
    }}
  ],
  "overall_verdict": "approve|revise|reject",
  "confidence": 0.0-1.0
}}
```
"""


def _plan_verification_strategy_template(args: dict) -> str:
    """plan_verification_strategy 프롬프트."""
    return f"""
# 검증 전략 수립

## Patch 타입
{args["patch_type"]}

## 영향 범위
{args["impact_scope"]}

---

## 검증 순서

RFC-SEM-022 Agent Verification Loop:
1. verify_patch_compile (필수)
2. verify_finding_resolved (필수)
3. verify_no_new_findings_introduced (선택)

## 질문

1. 이 패치는 어떤 검증이 필요한가?
2. 검증 순서는?
3. 실패 시 어떻게 대응할 것인가?

## 출력 형식

```json
{{
  "verification_steps": [
    {{
      "step": 1,
      "tool": "verify_patch_compile",
      "arguments": {{}},
      "required": true,
      "timeout_s": 30
    }}
  ],
  "estimated_time_s": 60,
  "fallback_strategy": "..."
}}
```
"""


def _interpret_dataflow_result_template(args: dict) -> str:
    """interpret_dataflow_result 프롬프트."""
    return f"""
# Dataflow 결과 해석

## Dataflow 분석 결과
{args["dataflow_result"]}

## 적용된 Policy
{args["policy"]}

---

## 해석 항목

1. **경로 분석**: source → sink 경로가 실제 취약한가?
2. **Sanitizer**: 중간에 sanitization이 있는가?
3. **심각도**: 이 경로의 위험도는?
4. **차단 지점**: 어디에서 막아야 하는가?

## 출력 형식

```json
{{
  "vulnerability_confirmed": true|false,
  "severity": "critical|high|medium|low",
  "sanitizers_effective": true|false,
  "recommended_fix_points": [
    {{"file": "...", "line": 0, "reason": "..."}}
  ],
  "explanation": "..."
}}
```
"""
