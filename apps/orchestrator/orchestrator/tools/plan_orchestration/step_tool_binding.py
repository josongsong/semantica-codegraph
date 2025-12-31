"""
Step → Tool Binding (RFC-041)

기존 9개 Tool을 Step에 바인딩.

기존 Tool (변경 없이 유지):
1. get_symbol_definition
2. find_all_references
3. build_call_graph
4. find_taint_flow
5. find_call_chain
6. find_data_dependency
7. compute_change_impact
8. find_affected_code
9. detect_vulnerabilities

모두 Plan 내부 Tool로만 사용됨.
"""

from typing import Any

# ================================================================
# Step Name → Tool Name 매핑
# ================================================================

STEP_TOOL_BINDING: dict[str, str] = {
    # === Understanding ===
    "resolve_symbol_definition": "get_symbol_definition",
    "find_symbol_references": "find_all_references",
    "analyze_usage_pattern": "analyze_usage_pattern",  # 신규 필요
    "analyze_file_structure": "analyze_file_structure",  # 신규 필요
    "resolve_imports": "resolve_imports",  # 신규 필요
    "build_module_graph": "build_dependency_graph",  # 신규 필요
    # === Trace ===
    "resolve_entry_point": "get_symbol_definition",
    "build_call_graph": "build_call_graph",
    "find_call_chain": "find_call_chain",
    "resolve_variable": "get_symbol_definition",
    "find_data_dependency": "find_data_dependency",
    "trace_alias": "trace_alias",  # 신규 필요
    # === Security ===
    "resolve_entry_points": "find_entry_points",  # 신규 필요
    "resolve_type_hierarchy": "find_type_hierarchy",  # 신규 필요
    "build_call_graph_slice": "build_call_graph",
    "find_taint_flow": "find_taint_flow",
    "analyze_control_flow": "analyze_control_flow",  # 신규 필요
    "validate_security_guard": "validate_security_guard",  # 신규 필요
    "detect_vulnerabilities": "detect_vulnerabilities",
    "explain_security_finding": "explain_finding",  # 신규 필요
    # === Impact ===
    "identify_change_target": "get_symbol_definition",
    "find_direct_references": "find_all_references",
    "compute_transitive_impact": "compute_change_impact",
    "find_affected_tests": "find_affected_code",
    # === Variant ===
    "extract_code_pattern": "extract_code_pattern",  # 신규 필요
    "search_similar_code": "search_similar_code",  # 신규 필요
    "rank_similarity": "rank_similarity",  # 신규 필요
    # === Explain ===
    "extract_context": "extract_context",  # 신규 필요
    "generate_explanation": "explain_finding",  # 신규 필요
    # === Generate ===
    "analyze_issue": "analyze_issue",  # 신규 필요
    "determine_fix_strategy": "determine_fix_strategy",  # 신규 필요
    "generate_patch_code": "generate_patch",  # 신규 필요
    "validate_patch": "validate_patch",  # 신규 필요
    # === Verify ===
    "parse_patch": "parse_patch",  # 신규 필요
    "verify_syntax": "verify_syntax",  # 신규 필요
    "verify_type_safety": "verify_type_safety",  # 신규 필요
    "check_regression": "check_regression",  # 신규 필요
    "run_affected_tests": "run_tests",  # 신규 필요
}


# ================================================================
# 기존 Tool 목록 (9개 - Foundation에서 제공)
# ================================================================

FOUNDATION_TOOLS: list[str] = [
    "get_symbol_definition",
    "find_all_references",
    "build_call_graph",
    "find_taint_flow",
    "find_call_chain",
    "find_data_dependency",
    "compute_change_impact",
    "find_affected_code",
    "detect_vulnerabilities",
]


# ================================================================
# 신규 구현된 Step Tools (RFC-041)
# ================================================================

STEP_TOOLS: list[str] = [
    # Understanding
    "analyze_usage_pattern",
    "analyze_file_structure",
    "resolve_imports",
    "build_dependency_graph",
    # Trace
    "trace_alias",
    "find_entry_points",
    # Security
    "find_type_hierarchy",
    "analyze_control_flow",
    "validate_security_guard",
    # Explain
    "extract_context",
    "explain_finding",
    # Generate
    "analyze_issue",
    "determine_fix_strategy",
    "generate_patch",
    "validate_patch",
    # Verify
    "parse_patch",
    "verify_syntax",
    "verify_type_safety",
    "check_regression",
    "run_tests",
    # Variant
    "extract_code_pattern",
    "search_similar_code",
    "rank_similarity",
]


# 모든 구현된 Tool (기존 + 신규)
EXISTING_TOOLS: list[str] = FOUNDATION_TOOLS + STEP_TOOLS


# ================================================================
# 필요한 Tool 목록 (전부 구현 완료)
# ================================================================

REQUIRED_NEW_TOOLS: list[str] = []  # 모두 구현 완료


def get_tool_for_step(step_name: str) -> str | None:
    """
    Step 이름으로 바인딩된 Tool 이름 반환

    Args:
        step_name: Step 이름

    Returns:
        Tool 이름 또는 None
    """
    return STEP_TOOL_BINDING.get(step_name)


def is_tool_implemented(tool_name: str) -> bool:
    """Tool이 이미 구현되어 있는지 확인"""
    return tool_name in EXISTING_TOOLS


def get_missing_tools() -> list[str]:
    """아직 구현되지 않은 Tool 목록"""
    return [t for t in REQUIRED_NEW_TOOLS if not is_tool_implemented(t)]


def get_binding_statistics() -> dict[str, Any]:
    """바인딩 통계"""
    total_steps = len(STEP_TOOL_BINDING)
    unique_tools = set(STEP_TOOL_BINDING.values())
    implemented = len([t for t in unique_tools if is_tool_implemented(t)])
    missing = len(unique_tools) - implemented

    return {
        "total_steps": total_steps,
        "unique_tools": len(unique_tools),
        "implemented_tools": implemented,
        "missing_tools": missing,
        "coverage": f"{implemented / len(unique_tools) * 100:.1f}%" if unique_tools else "0%",
    }
