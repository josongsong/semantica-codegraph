"""
Agent Query Presets - 복잡한 코드 분석 시나리오.

코드 에이전트가 사용할 수 있는 프리셋 쿼리 모음.
단순 검색이 아닌 분석/진단/리팩토링 시나리오에 최적화.

Categories:
    - Bug Analysis: 버그 가능성 높은 코드 찾기
    - Code Quality: 복잡도, 중복 코드 등
    - Security: 보안 취약점
    - Testing: 테스트 커버리지 분석
    - Refactoring: 리팩토링 후보 찾기
    - Data Flow: 데이터 흐름 추적
"""

from dataclasses import dataclass
from typing import Any


@dataclass
class PresetQuery:
    """프리셋 쿼리."""

    name: str
    description: str
    category: str
    example: str = ""


# ============================================================
# Preset Definitions
# ============================================================

PRESETS = {
    # Bug Analysis
    "bug_suspects": PresetQuery(
        name="bug_suspects",
        description="버그 가능성이 높은 함수 찾기 (복잡한 제어 흐름, 많은 분기)",
        category="Bug Analysis",
        example="High complexity, multiple branches, exception handling",
    ),
    "null_pointer_risks": PresetQuery(
        name="null_pointer_risks",
        description="None 체크 누락 가능성 (DFG 분석)",
        category="Bug Analysis",
        example="Variables that could be None without checks",
    ),
    "exception_handlers": PresetQuery(
        name="exception_handlers",
        description="예외 처리가 있는 함수 (try-except 블록)",
        category="Bug Analysis",
        example="Functions with exception handling",
    ),
    # Code Quality
    "complex_functions": PresetQuery(
        name="complex_functions",
        description="복잡도가 높은 함수 (BFG blocks > 10)",
        category="Code Quality",
        example="Functions with high cyclomatic complexity",
    ),
    "long_functions": PresetQuery(
        name="long_functions",
        description="너무 긴 함수 (LOC > 50)",
        category="Code Quality",
        example="Functions that should be split",
    ),
    "deep_nesting": PresetQuery(
        name="deep_nesting",
        description="깊은 중첩 구조 (nesting > 4)",
        category="Code Quality",
        example="Deeply nested if/for/while",
    ),
    # Security
    "sql_injection_risks": PresetQuery(
        name="sql_injection_risks",
        description="SQL Injection 위험 (문자열 concat)",
        category="Security",
        example="SQL queries with string concatenation",
    ),
    "command_injection_risks": PresetQuery(
        name="command_injection_risks",
        description="Command Injection 위험 (subprocess, os.system)",
        category="Security",
        example="Shell commands with user input",
    ),
    "sensitive_data_flow": PresetQuery(
        name="sensitive_data_flow",
        description="민감 데이터 흐름 추적 (password, token, key)",
        category="Security",
        example="Track sensitive variable flow using DFG",
    ),
    # Testing
    "untested_functions": PresetQuery(
        name="untested_functions",
        description="테스트가 없는 함수 (호출 그래프 분석)",
        category="Testing",
        example="Functions not called from test_*.py",
    ),
    "test_coverage_gaps": PresetQuery(
        name="test_coverage_gaps",
        description="테스트 커버리지 부족 영역",
        category="Testing",
        example="Functions with branches not tested",
    ),
    # Refactoring
    "refactor_candidates": PresetQuery(
        name="refactor_candidates",
        description="리팩토링 후보 (복잡도 + 길이 + 중복)",
        category="Refactoring",
        example="Functions that need refactoring",
    ),
    "duplicate_code": PresetQuery(
        name="duplicate_code",
        description="중복 코드 감지 (유사 청크)",
        category="Refactoring",
        example="Similar code blocks that should be extracted",
    ),
    "dead_code": PresetQuery(
        name="dead_code",
        description="사용되지 않는 코드 (호출 그래프)",
        category="Refactoring",
        example="Functions/classes never called",
    ),
    # Data Flow
    "trace_variable": PresetQuery(
        name="trace_variable",
        description="변수 흐름 추적 (DFG)",
        category="Data Flow",
        example="trace_variable user_input → see where it flows",
    ),
    "find_global_state": PresetQuery(
        name="find_global_state",
        description="전역 변수 사용 패턴",
        category="Data Flow",
        example="Global variables and their usage",
    ),
    "mutation_analysis": PresetQuery(
        name="mutation_analysis",
        description="변수 변경 분석 (SSA phi nodes)",
        category="Data Flow",
        example="Variables modified in multiple branches",
    ),
}


class AgentQueryEngine:
    """
    Agent용 복잡한 쿼리 엔진.

    IndexManager를 기반으로 고급 분석 시나리오 제공.
    """

    def __init__(self, index_manager):
        """
        Args:
            index_manager: IndexManager 인스턴스
        """
        self.manager = index_manager

    def list_presets(self) -> dict[str, list[PresetQuery]]:
        """카테고리별 프리셋 목록."""
        by_category: dict[str, list[PresetQuery]] = {}

        for preset in PRESETS.values():
            by_category.setdefault(preset.category, []).append(preset)

        return by_category

    # ============================================================
    # Bug Analysis Scenarios
    # ============================================================

    def bug_suspects(self) -> list[dict[str, Any]]:
        """
        버그 가능성 높은 함수 찾기.

        기준:
        - BFG blocks > 10 (복잡한 제어 흐름)
        - CFG edges > 15 (많은 분기)
        - SSA phi nodes > 5 (복잡한 상태 관리)
        """
        suspects = []

        for file_path, ir_doc in self.manager.ir_documents.items():
            if not hasattr(ir_doc, "nodes"):
                continue

            for node in ir_doc.nodes:
                if getattr(node, "kind", "") != "function":
                    continue

                function_id = getattr(node, "id", "")
                function_fqn = getattr(node, "fqn", "")

                # Check BFG complexity
                bfg_blocks = 0
                if hasattr(ir_doc, "bfg_graphs"):
                    for bfg in ir_doc.bfg_graphs:
                        if getattr(bfg, "function_id", "") == function_id:
                            bfg_blocks = len(getattr(bfg, "blocks", []))
                            break

                # Check SSA complexity
                phi_nodes = 0
                if hasattr(ir_doc, "ssa_graphs"):
                    for ssa in ir_doc.ssa_graphs:
                        if getattr(ssa, "function_id", "") == function_id:
                            phi_nodes = getattr(ssa, "phi_node_count", 0)
                            break

                # Scoring
                complexity_score = bfg_blocks * 2 + phi_nodes

                if complexity_score >= 15:  # High complexity
                    suspects.append(
                        {
                            "function_fqn": function_fqn,
                            "file_path": file_path,
                            "complexity_score": complexity_score,
                            "bfg_blocks": bfg_blocks,
                            "phi_nodes": phi_nodes,
                            "reason": "High complexity - likely to have bugs",
                        }
                    )

        # Sort by complexity
        suspects.sort(key=lambda x: x["complexity_score"], reverse=True)
        return suspects

    def complex_functions(self, threshold: int = 10) -> list[dict[str, Any]]:
        """
        복잡도가 높은 함수 찾기.

        Args:
            threshold: BFG blocks 임계값
        """
        complex = []

        for file_path, ir_doc in self.manager.ir_documents.items():
            if not hasattr(ir_doc, "bfg_graphs"):
                continue

            for bfg in ir_doc.bfg_graphs:
                function_id = getattr(bfg, "function_id", "")
                blocks = getattr(bfg, "blocks", [])

                if len(blocks) >= threshold:
                    # Find function name
                    function_fqn = self._find_function_name(ir_doc, function_id)

                    complex.append(
                        {
                            "function_fqn": function_fqn,
                            "file_path": file_path,
                            "bfg_blocks": len(blocks),
                            "statements": getattr(bfg, "total_statements", 0),
                            "cyclomatic_complexity": len(blocks),  # Approximation
                        }
                    )

        complex.sort(key=lambda x: x["bfg_blocks"], reverse=True)
        return complex

    def find_security_patterns(self, pattern_type: str) -> list[dict[str, Any]]:
        """
        보안 패턴 찾기.

        Args:
            pattern_type: "sql_injection", "command_injection", "path_traversal"
        """
        results = []

        # Pattern keywords
        patterns = {
            "sql_injection": ["execute", "query", "SELECT", "INSERT", "UPDATE", "DELETE", "+", "format"],
            "command_injection": ["subprocess", "os.system", "shell", "exec", "popen"],
            "path_traversal": ["open", "read", "write", "../", "join", "path"],
        }

        keywords = patterns.get(pattern_type, [])

        # Search in nodes for function calls
        for file_path, ir_doc in self.manager.ir_documents.items():
            if not hasattr(ir_doc, "nodes"):
                continue

            for node in ir_doc.nodes:
                node_name = getattr(node, "name", "")
                node_fqn = getattr(node, "fqn", "")

                # Check if any keyword matches
                if any(kw.lower() in node_name.lower() or kw.lower() in node_fqn.lower() for kw in keywords):
                    results.append(
                        {
                            "pattern": pattern_type,
                            "location": node_fqn,
                            "kind": getattr(node, "kind", ""),
                            "file_path": file_path,
                            "matched_keywords": [kw for kw in keywords if kw.lower() in node_name.lower()],
                        }
                    )

        return results

    def find_untested_code(self) -> list[dict[str, Any]]:
        """
        테스트되지 않은 코드 찾기.

        전략:
        1. test_*.py에서 호출되지 않는 함수
        2. 호출 그래프 분석
        """
        # Collect all test functions
        test_functions = set()
        for file_path, ir_doc in self.manager.ir_documents.items():
            if "test" not in file_path.lower():
                continue

            if not hasattr(ir_doc, "nodes"):
                continue

            for node in ir_doc.nodes:
                if getattr(node, "kind", "") == "function":
                    test_functions.add(getattr(node, "fqn", ""))

        # Build call graph from tests
        tested_functions = set()
        call_graph = self.manager.get_call_graph()

        # BFS from test functions
        queue = list(test_functions)
        while queue:
            func = queue.pop(0)
            if func in tested_functions:
                continue
            tested_functions.add(func)

            # Add callees
            if func in call_graph:
                queue.extend(call_graph[func])

        # Find untested functions
        untested = []
        for file_path, ir_doc in self.manager.ir_documents.items():
            if "test" in file_path.lower():  # Skip test files
                continue

            if not hasattr(ir_doc, "nodes"):
                continue

            for node in ir_doc.nodes:
                if getattr(node, "kind", "") != "function":
                    continue

                fqn = getattr(node, "fqn", "")
                if fqn and fqn not in tested_functions:
                    untested.append(
                        {
                            "function_fqn": fqn,
                            "file_path": file_path,
                            "reason": "Not called from any test",
                        }
                    )

        return untested

    def analyze_function(self, function_fqn: str) -> dict[str, Any]:
        """
        함수 종합 분석.

        Returns:
            - Control flow (BFG, CFG)
            - Data flow (DFG)
            - Complexity metrics
            - Call graph (callers + callees)
            - Security risks
        """
        # Get flow graphs
        flow = self.manager.get_function_flow(function_fqn)
        if not flow:
            return {"error": f"Function not found: {function_fqn}"}

        # Get callers and callees
        call_graph = self.manager.get_call_graph()
        callees = call_graph.get(function_fqn, [])

        # Find callers (reverse lookup)
        callers = [caller for caller, targets in call_graph.items() if function_fqn in targets]

        # Calculate complexity
        bfg_blocks = flow.get("bfg", {}).get("blocks", 0) if flow.get("bfg") else 0
        cyclomatic = bfg_blocks  # Approximation

        # Check for security patterns
        security_risks = []
        if any(kw in function_fqn.lower() for kw in ["execute", "query", "sql", "command"]):
            security_risks.append("Potential injection point")

        return {
            "function_fqn": function_fqn,
            "file_path": flow.get("file_path"),
            # Complexity
            "cyclomatic_complexity": cyclomatic,
            "bfg_blocks": bfg_blocks,
            "cfg_edges": len(flow.get("cfg", [])),
            # Data flow
            "dfg": flow.get("dfg"),
            "ssa": flow.get("ssa"),
            # Call graph
            "calls": callees,
            "called_by": callers,
            "call_depth": len(callees),
            # Security
            "security_risks": security_risks,
            # Recommendations
            "recommendations": self._generate_recommendations(cyclomatic, len(callees), security_risks),
        }

    def _generate_recommendations(self, complexity: int, call_count: int, security_risks: list[str]) -> list[str]:
        """분석 기반 추천사항 생성."""
        recommendations = []

        if complexity > 10:
            recommendations.append("⚠️ High complexity - consider splitting into smaller functions")

        if call_count > 5:
            recommendations.append("⚠️ Calls many functions - potential integration point")

        if security_risks:
            recommendations.append(f"🔒 Security: {', '.join(security_risks)}")

        if complexity > 15:
            recommendations.append("🐛 High bug risk - add more tests")

        return recommendations

    def _find_function_name(self, ir_doc: Any, function_id: str) -> str:
        """함수 ID로 FQN 찾기."""
        if not hasattr(ir_doc, "nodes"):
            return function_id

        for node in ir_doc.nodes:
            if getattr(node, "id", "") == function_id:
                return getattr(node, "fqn", function_id)

        return function_id

    # ============================================================
    # Batch Analysis
    # ============================================================

    def run_preset(self, preset_name: str, **kwargs) -> dict[str, Any]:
        """
        프리셋 쿼리 실행.

        Args:
            preset_name: 프리셋 이름
            **kwargs: 프리셋별 추가 파라미터
        """
        import time

        start = time.time()

        if preset_name == "bug_suspects":
            results = self.bug_suspects()
        elif preset_name == "complex_functions":
            threshold = kwargs.get("threshold", 10)
            results = self.complex_functions(threshold=threshold)
        elif preset_name == "untested_functions":
            results = self.find_untested_code()
        elif preset_name == "sql_injection_risks":
            results = self.find_security_patterns("sql_injection")
        elif preset_name == "command_injection_risks":
            results = self.find_security_patterns("command_injection")
        else:
            return {"error": f"Unknown preset: {preset_name}"}

        query_time_ms = (time.time() - start) * 1000

        return {
            "preset": preset_name,
            "results": results,
            "total": len(results),
            "query_time_ms": query_time_ms,
        }

    def batch_analysis(self, presets: list[str] | None = None) -> dict[str, Any]:
        """
        여러 프리셋을 한 번에 실행.

        Args:
            presets: 실행할 프리셋 리스트 (None이면 주요 프리셋만)
        """
        if presets is None:
            presets = ["bug_suspects", "complex_functions", "untested_functions"]

        results = {}

        for preset_name in presets:
            results[preset_name] = self.run_preset(preset_name)

        return results

    def generate_report(self) -> str:
        """
        종합 분석 리포트 생성.

        Agent가 코드베이스를 이해하는 데 필요한 모든 정보.
        """
        lines = [
            "=" * 80,
            "Code Analysis Report".center(80),
            "=" * 80,
            "",
            f"Repository: {self.manager.repo_id}",
            f"Files: {self.manager.stats.files}",
            f"Nodes: {self.manager.stats.nodes:,}",
            f"Symbols: {self.manager.stats.symbols:,}",
            "",
            "=" * 80,
            "Bug Analysis",
            "=" * 80,
            "",
        ]

        # Bug suspects
        suspects = self.bug_suspects()
        lines.append(f"Bug Suspects: {len(suspects)}")
        for s in suspects[:5]:
            lines.append(f"  ⚠️ {s['function_fqn']}")
            lines.append(
                f"     Complexity: {s['complexity_score']}, Blocks: {s['bfg_blocks']}, Φ-nodes: {s['phi_nodes']}"
            )

        lines.extend(
            [
                "",
                "=" * 80,
                "Code Quality",
                "=" * 80,
                "",
            ]
        )

        # Complex functions
        complex = self.complex_functions(threshold=10)
        lines.append(f"Complex Functions: {len(complex)}")
        for c in complex[:5]:
            lines.append(f"  📊 {c['function_fqn']}")
            lines.append(f"     Blocks: {c['bfg_blocks']}, Statements: {c['statements']}")

        lines.extend(
            [
                "",
                "=" * 80,
                "Testing",
                "=" * 80,
                "",
            ]
        )

        # Untested code
        untested = self.find_untested_code()
        lines.append(f"Untested Functions: {len(untested)}")
        for u in untested[:5]:
            lines.append(f"  ❌ {u['function_fqn']}")

        lines.extend(
            [
                "",
                "=" * 80,
            ]
        )

        return "\n".join(lines)
