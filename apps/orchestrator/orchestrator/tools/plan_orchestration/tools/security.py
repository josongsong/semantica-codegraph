"""
Security Tools (RFC-041)

보안 분석을 위한 Step Tools.

SOTA References:
- CodeQL: Type Hierarchy Analysis
- Semgrep: Control Flow Analysis
- Infer: Security Guard Validation
- Joern: CPG-based Security Analysis
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from codegraph_shared.common.observability import get_logger

from .base import QueryDSLMixin, StepTool, StepToolResult

logger = get_logger(__name__)


# ================================================================
# Data Models
# ================================================================


class InheritanceType(str, Enum):
    """상속 타입"""

    EXTENDS = "extends"
    IMPLEMENTS = "implements"
    MIXIN = "mixin"
    PROTOCOL = "protocol"


@dataclass
class TypeHierarchyNode:
    """타입 계층 노드"""

    name: str
    qualified_name: str
    file_path: str
    line: int
    parent: str | None
    children: list[str]
    interfaces: list[str]
    is_abstract: bool
    is_interface: bool


@dataclass
class ControlFlowPath:
    """제어 흐름 경로"""

    path_id: str
    nodes: list[dict[str, Any]]
    conditions: list[dict[str, Any]]  # 분기 조건들
    is_reachable: bool
    has_exception_handler: bool


@dataclass
class SecurityGuard:
    """보안 가드 (Sanitizer/Validator)"""

    name: str
    guard_type: str  # "sanitizer", "validator", "encoder", "escaper"
    file_path: str
    line: int
    protected_sink_types: list[str]  # ["sql", "xss", "command"]
    is_effective: bool
    bypass_conditions: list[str]  # 우회 가능 조건


# ================================================================
# Tools
# ================================================================


class FindTypeHierarchyTool(StepTool):
    """
    타입 계층 분석 Tool

    SOTA: CodeQL의 Type Hierarchy Analysis

    분석 내용:
    - 클래스 상속 관계
    - 인터페이스 구현
    - 다형성 호출 대상 식별
    """

    @property
    def name(self) -> str:
        return "find_type_hierarchy"

    @property
    def description(self) -> str:
        return "타입 계층 구조(상속, 인터페이스)를 분석합니다"

    def __init__(self, ir_analyzer: Any = None):
        self.ir_analyzer = ir_analyzer

    def execute(
        self,
        target: str = "",
        from_resolve_entry_points: Any = None,
        **kwargs,
    ) -> StepToolResult:
        """
        타입 계층 분석

        Args:
            target: 분석 대상 (클래스명 또는 파일 경로)
            from_resolve_entry_points: 이전 Step 결과
        """
        if not target:
            return StepToolResult(success=False, error="No target provided")

        try:
            import os

            # 파일 수집
            files_to_scan: list[str] = []
            if os.path.isdir(target):
                for root, _, files in os.walk(target):
                    for f in files:
                        if f.endswith((".py", ".ts", ".js", ".java")):
                            files_to_scan.append(os.path.join(root, f))
            elif os.path.isfile(target):
                files_to_scan = [target]
            else:
                # 클래스명으로 검색
                return self._search_class_hierarchy(target)

            # 타입 계층 구축
            hierarchy: dict[str, TypeHierarchyNode] = {}

            for file_path in files_to_scan[:50]:  # 최대 50개
                try:
                    nodes = self._extract_type_hierarchy(file_path)
                    for node in nodes:
                        hierarchy[node.qualified_name] = node
                except Exception as e:
                    logger.warning(f"Failed to analyze {file_path}: {e}")

            # 관계 정리
            for node in hierarchy.values():
                if node.parent and node.parent in hierarchy:
                    hierarchy[node.parent].children.append(node.name)

            # 루트 클래스 식별
            root_classes = [n for n in hierarchy.values() if not n.parent or n.parent not in hierarchy]

            # 인터페이스 식별
            interfaces = [n for n in hierarchy.values() if n.is_interface]

            # 깊이 계산
            max_depth = self._calculate_max_depth(hierarchy)

            return StepToolResult(
                success=True,
                data={
                    "total_types": len(hierarchy),
                    "root_classes": [r.name for r in root_classes][:10],
                    "interfaces": [i.name for i in interfaces][:10],
                    "max_inheritance_depth": max_depth,
                    "hierarchy": [
                        {
                            "name": n.name,
                            "qualified_name": n.qualified_name,
                            "parent": n.parent,
                            "children": n.children[:5],
                            "interfaces": n.interfaces,
                            "is_abstract": n.is_abstract,
                            "file": n.file_path,
                            "line": n.line,
                        }
                        for n in list(hierarchy.values())[:30]
                    ],
                },
                confidence=0.85,
            )

        except Exception as e:
            logger.exception("Type hierarchy analysis failed")
            return StepToolResult(success=False, error=str(e))

    def _extract_type_hierarchy(self, file_path: str) -> list[TypeHierarchyNode]:
        """파일에서 타입 계층 추출"""
        nodes: list[TypeHierarchyNode] = []

        if file_path.endswith(".py"):
            nodes = self._extract_python_hierarchy(file_path)
        elif file_path.endswith((".ts", ".js")):
            nodes = self._extract_typescript_hierarchy(file_path)
        elif file_path.endswith(".java"):
            nodes = self._extract_java_hierarchy(file_path)

        return nodes

    def _extract_python_hierarchy(self, file_path: str) -> list[TypeHierarchyNode]:
        """Python 타입 계층 추출"""
        import ast

        nodes: list[TypeHierarchyNode] = []

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()

            tree = ast.parse(content)

            for node in ast.walk(tree):
                if isinstance(node, ast.ClassDef):
                    parent = None
                    interfaces: list[str] = []

                    for base in node.bases:
                        if isinstance(base, ast.Name):
                            if parent is None:
                                parent = base.id
                            else:
                                interfaces.append(base.id)
                        elif isinstance(base, ast.Attribute):
                            base_name = f"{self._get_attr_name(base)}"
                            if parent is None:
                                parent = base_name
                            else:
                                interfaces.append(base_name)

                    # ABC 체크
                    is_abstract = any(
                        isinstance(d, ast.Name) and d.id in ("abstractmethod", "ABC") for d in node.decorator_list
                    ) or any(isinstance(b, ast.Attribute) and "ABC" in self._get_attr_name(b) for b in node.bases)

                    # Protocol 체크
                    is_interface = any(
                        "Protocol" in (self._get_attr_name(b) if isinstance(b, ast.Attribute) else getattr(b, "id", ""))
                        for b in node.bases
                    )

                    nodes.append(
                        TypeHierarchyNode(
                            name=node.name,
                            qualified_name=f"{file_path}:{node.name}",
                            file_path=file_path,
                            line=node.lineno,
                            parent=parent,
                            children=[],
                            interfaces=interfaces,
                            is_abstract=is_abstract,
                            is_interface=is_interface,
                        )
                    )

        except Exception as e:
            logger.warning(f"Python parsing failed for {file_path}: {e}")

        return nodes

    def _get_attr_name(self, node: Any) -> str:
        """Attribute 노드에서 전체 이름 추출"""
        if hasattr(node, "attr"):
            if hasattr(node, "value"):
                if hasattr(node.value, "id"):
                    return f"{node.value.id}.{node.attr}"
            return node.attr
        return ""

    def _extract_typescript_hierarchy(self, file_path: str) -> list[TypeHierarchyNode]:
        """TypeScript/JavaScript 타입 계층 추출 (정규식 기반)"""
        import re

        nodes: list[TypeHierarchyNode] = []

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()
                lines = content.splitlines()

            # class X extends Y implements Z 패턴
            class_pattern = re.compile(
                r"(?:export\s+)?class\s+(\w+)(?:\s+extends\s+(\w+))?(?:\s+implements\s+([\w,\s]+))?"
            )

            for i, line in enumerate(lines):
                match = class_pattern.search(line)
                if match:
                    name = match.group(1)
                    parent = match.group(2)
                    implements = match.group(3)

                    interfaces = []
                    if implements:
                        interfaces = [i.strip() for i in implements.split(",")]

                    nodes.append(
                        TypeHierarchyNode(
                            name=name,
                            qualified_name=f"{file_path}:{name}",
                            file_path=file_path,
                            line=i + 1,
                            parent=parent,
                            children=[],
                            interfaces=interfaces,
                            is_abstract="abstract" in line,
                            is_interface=False,
                        )
                    )

            # interface X extends Y 패턴
            interface_pattern = re.compile(r"(?:export\s+)?interface\s+(\w+)(?:\s+extends\s+([\w,\s]+))?")

            for i, line in enumerate(lines):
                match = interface_pattern.search(line)
                if match:
                    name = match.group(1)
                    extends = match.group(2)

                    interfaces = []
                    if extends:
                        interfaces = [i.strip() for i in extends.split(",")]

                    nodes.append(
                        TypeHierarchyNode(
                            name=name,
                            qualified_name=f"{file_path}:{name}",
                            file_path=file_path,
                            line=i + 1,
                            parent=None,
                            children=[],
                            interfaces=interfaces,
                            is_abstract=False,
                            is_interface=True,
                        )
                    )

        except Exception as e:
            logger.warning(f"TypeScript parsing failed for {file_path}: {e}")

        return nodes

    def _extract_java_hierarchy(self, file_path: str) -> list[TypeHierarchyNode]:
        """Java 타입 계층 추출"""
        import re

        nodes: list[TypeHierarchyNode] = []

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()
                lines = content.splitlines()

            # class X extends Y implements A, B 패턴
            class_pattern = re.compile(
                r"(?:public\s+)?(?:abstract\s+)?class\s+(\w+)(?:\s+extends\s+(\w+))?(?:\s+implements\s+([\w,\s]+))?"
            )

            for i, line in enumerate(lines):
                match = class_pattern.search(line)
                if match:
                    name = match.group(1)
                    parent = match.group(2)
                    implements = match.group(3)

                    interfaces = []
                    if implements:
                        interfaces = [i.strip() for i in implements.split(",")]

                    nodes.append(
                        TypeHierarchyNode(
                            name=name,
                            qualified_name=f"{file_path}:{name}",
                            file_path=file_path,
                            line=i + 1,
                            parent=parent,
                            children=[],
                            interfaces=interfaces,
                            is_abstract="abstract" in line,
                            is_interface=False,
                        )
                    )

        except Exception as e:
            logger.warning(f"Java parsing failed for {file_path}: {e}")

        return nodes

    def _search_class_hierarchy(self, class_name: str) -> StepToolResult:
        """클래스명으로 계층 검색"""
        return StepToolResult(
            success=True,
            data={
                "search_query": class_name,
                "note": "Class search requires full project indexing. Provide a file path for direct analysis.",
            },
            confidence=0.5,
        )

    def _calculate_max_depth(self, hierarchy: dict[str, TypeHierarchyNode]) -> int:
        """최대 상속 깊이 계산"""
        max_depth = 0

        for node in hierarchy.values():
            depth = 0
            current = node
            visited = set()

            while current.parent and current.parent in hierarchy:
                if current.parent in visited:
                    break  # 순환 참조 방지
                visited.add(current.parent)
                current = hierarchy[current.parent]
                depth += 1

            max_depth = max(max_depth, depth)

        return max_depth


class AnalyzeControlFlowTool(StepTool, QueryDSLMixin):
    """
    제어 흐름 분석 Tool

    SOTA: Joern CPG 기반 Control Flow Analysis

    분석 내용:
    - 분기 조건 분석
    - 예외 핸들링 경로
    - 도달 가능성 분석
    """

    @property
    def name(self) -> str:
        return "analyze_control_flow"

    @property
    def description(self) -> str:
        return "제어 흐름(분기, 예외 처리)을 분석합니다"

    def __init__(self, ir_analyzer: Any = None, cfg_builder: Any = None):
        self.ir_analyzer = ir_analyzer
        self.cfg_builder = cfg_builder

    def execute(
        self,
        target: str = "",
        from_find_taint_flow: Any = None,
        **kwargs,
    ) -> StepToolResult:
        """
        제어 흐름 분석

        Args:
            target: 분석 대상
            from_find_taint_flow: 이전 Step 결과 (taint path)
        """
        try:
            # Taint 경로가 있으면 해당 경로의 제어 흐름 분석
            if from_find_taint_flow:
                return self._analyze_taint_path_control_flow(from_find_taint_flow)

            # 파일 전체 분석
            if target:
                return self._analyze_file_control_flow(target)

            return StepToolResult(success=False, error="No target or taint flow provided")

        except Exception as e:
            logger.exception("Control flow analysis failed")
            return StepToolResult(success=False, error=str(e))

    def _analyze_taint_path_control_flow(self, taint_data: Any) -> StepToolResult:
        """Taint 경로의 제어 흐름 분석"""
        paths = taint_data.get("paths", [])

        analyzed_paths: list[dict] = []
        total_conditions = 0
        paths_with_guards = 0

        for i, path in enumerate(paths[:10]):  # 최대 10개 경로
            path_nodes = path if isinstance(path, list) else path.get("nodes", [])

            # 경로 내 조건문 추출
            conditions = self._extract_conditions_from_path(path_nodes)
            total_conditions += len(conditions)

            # 예외 핸들러 존재 여부
            has_exception_handler = self._has_exception_handler(path_nodes)

            # 보안 가드 존재 여부
            has_guard = self._has_security_guard(path_nodes)
            if has_guard:
                paths_with_guards += 1

            analyzed_paths.append(
                {
                    "path_id": f"path_{i}",
                    "length": len(path_nodes),
                    "conditions": conditions[:5],
                    "condition_count": len(conditions),
                    "has_exception_handler": has_exception_handler,
                    "has_security_guard": has_guard,
                    "is_guarded": has_guard or has_exception_handler,
                }
            )

        return StepToolResult(
            success=True,
            data={
                "total_paths_analyzed": len(analyzed_paths),
                "total_conditions": total_conditions,
                "paths_with_guards": paths_with_guards,
                "unguarded_paths": len(analyzed_paths) - paths_with_guards,
                "paths": analyzed_paths,
                "summary": {
                    "guard_coverage": f"{paths_with_guards}/{len(analyzed_paths)}",
                    "risk_level": "high"
                    if paths_with_guards == 0
                    else "medium"
                    if paths_with_guards < len(analyzed_paths)
                    else "low",
                },
            },
            confidence=0.8,
        )

    def _analyze_file_control_flow(self, file_path: str) -> StepToolResult:
        """파일 전체 제어 흐름 분석"""
        import ast

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()

            tree = ast.parse(content)

            # 제어 구조 수집
            control_structures = {
                "if_statements": 0,
                "loops": 0,
                "try_except": 0,
                "with_statements": 0,
                "assertions": 0,
            }

            conditions: list[dict] = []

            for node in ast.walk(tree):
                if isinstance(node, ast.If):
                    control_structures["if_statements"] += 1
                    conditions.append(
                        {
                            "type": "if",
                            "line": node.lineno,
                            "condition": ast.unparse(node.test) if hasattr(ast, "unparse") else "...",
                        }
                    )
                elif isinstance(node, (ast.For, ast.While)):
                    control_structures["loops"] += 1
                elif isinstance(node, ast.Try):
                    control_structures["try_except"] += 1
                elif isinstance(node, ast.With):
                    control_structures["with_statements"] += 1
                elif isinstance(node, ast.Assert):
                    control_structures["assertions"] += 1

            # 복잡도 계산
            cyclomatic_complexity = (
                control_structures["if_statements"] + control_structures["loops"] + control_structures["try_except"] + 1
            )

            return StepToolResult(
                success=True,
                data={
                    "file": file_path,
                    "control_structures": control_structures,
                    "cyclomatic_complexity": cyclomatic_complexity,
                    "conditions": conditions[:20],
                    "complexity_rating": "high"
                    if cyclomatic_complexity > 10
                    else "medium"
                    if cyclomatic_complexity > 5
                    else "low",
                },
                confidence=0.85,
            )

        except Exception as e:
            return StepToolResult(success=False, error=str(e))

    def _extract_conditions_from_path(self, path_nodes: list) -> list[dict]:
        """경로에서 조건문 추출"""
        conditions = []

        for node in path_nodes:
            if isinstance(node, dict):
                node_type = node.get("type", "")
                if "if" in node_type.lower() or "condition" in node_type.lower():
                    conditions.append(
                        {
                            "type": node_type,
                            "line": node.get("line", 0),
                            "expression": node.get("condition", node.get("expression", "")),
                        }
                    )

        return conditions

    def _has_exception_handler(self, path_nodes: list) -> bool:
        """예외 핸들러 존재 여부"""
        for node in path_nodes:
            if isinstance(node, dict):
                node_type = str(node.get("type", "")).lower()
                if "try" in node_type or "except" in node_type or "catch" in node_type:
                    return True
        return False

    def _has_security_guard(self, path_nodes: list) -> bool:
        """보안 가드 존재 여부"""
        guard_patterns = [
            "sanitize",
            "escape",
            "validate",
            "check",
            "verify",
            "encode",
            "filter",
            "clean",
            "purify",
            "safe",
        ]

        for node in path_nodes:
            if isinstance(node, dict):
                name = str(node.get("name", "")).lower()
                if any(p in name for p in guard_patterns):
                    return True
        return False


class ValidateSecurityGuardTool(StepTool):
    """
    보안 가드 검증 Tool

    SOTA: Infer의 Security Guard Validation

    검증 내용:
    - Sanitizer 유효성 검증
    - 우회 가능성 분석
    - 적용 범위 확인
    """

    @property
    def name(self) -> str:
        return "validate_security_guard"

    @property
    def description(self) -> str:
        return "보안 가드(sanitizer, validator)의 유효성을 검증합니다"

    def __init__(self, taint_engine: Any = None):
        self.taint_engine = taint_engine

        # 알려진 보안 가드 패턴
        self.known_guards = {
            "sql": [
                {"name": "parameterized_query", "type": "sanitizer", "effective": True},
                {"name": "escape_string", "type": "escaper", "effective": True},
                {"name": "quote", "type": "escaper", "effective": False, "bypass": "encoding"},
            ],
            "xss": [
                {"name": "html_escape", "type": "escaper", "effective": True},
                {"name": "bleach.clean", "type": "sanitizer", "effective": True},
                {"name": "strip_tags", "type": "sanitizer", "effective": False, "bypass": "attribute"},
            ],
            "command": [
                {"name": "shlex.quote", "type": "escaper", "effective": True},
                {"name": "subprocess.list", "type": "sanitizer", "effective": True},
                {"name": "shell=False", "type": "config", "effective": True},
            ],
            "path": [
                {"name": "os.path.basename", "type": "sanitizer", "effective": True},
                {"name": "realpath", "type": "sanitizer", "effective": True},
                {"name": "abspath", "type": "sanitizer", "effective": False, "bypass": "symlink"},
            ],
        }

    def execute(
        self,
        target: str = "",
        from_analyze_control_flow: Any = None,
        **kwargs,
    ) -> StepToolResult:
        """
        보안 가드 검증

        Args:
            target: 분석 대상
            from_analyze_control_flow: 이전 Step 결과
        """
        try:
            guards_found: list[SecurityGuard] = []
            validation_results: list[dict] = []

            # 제어 흐름 결과에서 가드 정보 추출
            if from_analyze_control_flow:
                paths = from_analyze_control_flow.get("paths", [])

                for path in paths:
                    if path.get("has_security_guard"):
                        # 가드 상세 분석
                        guard = self._identify_guard_type(path)
                        if guard:
                            guards_found.append(guard)
                            validation = self._validate_guard(guard)
                            validation_results.append(validation)

            # 파일 직접 스캔
            if target and not guards_found:
                guards_found = self._scan_file_for_guards(target)
                for guard in guards_found:
                    validation = self._validate_guard(guard)
                    validation_results.append(validation)

            # 결과 집계
            effective_guards = [v for v in validation_results if v.get("is_effective")]
            bypassable_guards = [v for v in validation_results if v.get("bypass_possible")]

            return StepToolResult(
                success=True,
                data={
                    "total_guards_found": len(guards_found),
                    "effective_guards": len(effective_guards),
                    "bypassable_guards": len(bypassable_guards),
                    "coverage": {
                        "sql": len([g for g in guards_found if "sql" in g.protected_sink_types]),
                        "xss": len([g for g in guards_found if "xss" in g.protected_sink_types]),
                        "command": len([g for g in guards_found if "command" in g.protected_sink_types]),
                        "path": len([g for g in guards_found if "path" in g.protected_sink_types]),
                    },
                    "validations": validation_results[:20],
                    "recommendations": self._generate_recommendations(validation_results),
                },
                confidence=0.8,
            )

        except Exception as e:
            logger.exception("Security guard validation failed")
            return StepToolResult(success=False, error=str(e))

    def _identify_guard_type(self, path: dict) -> SecurityGuard | None:
        """경로에서 가드 타입 식별"""
        # 간단한 구현 - 실제로는 더 정교한 분석 필요
        return None

    def _scan_file_for_guards(self, file_path: str) -> list[SecurityGuard]:
        """파일에서 보안 가드 스캔"""
        import re

        guards: list[SecurityGuard] = []

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()
                lines = content.splitlines()

            # 각 가드 타입별 패턴 검색
            for sink_type, known_guards in self.known_guards.items():
                for guard_info in known_guards:
                    pattern = re.escape(guard_info["name"])
                    for i, line in enumerate(lines):
                        if re.search(pattern, line, re.IGNORECASE):
                            guards.append(
                                SecurityGuard(
                                    name=guard_info["name"],
                                    guard_type=guard_info["type"],
                                    file_path=file_path,
                                    line=i + 1,
                                    protected_sink_types=[sink_type],
                                    is_effective=guard_info.get("effective", True),
                                    bypass_conditions=[guard_info.get("bypass", "")]
                                    if guard_info.get("bypass")
                                    else [],
                                )
                            )

        except Exception as e:
            logger.warning(f"Guard scanning failed for {file_path}: {e}")

        return guards

    def _validate_guard(self, guard: SecurityGuard) -> dict:
        """가드 유효성 검증"""
        return {
            "name": guard.name,
            "type": guard.guard_type,
            "protected_sinks": guard.protected_sink_types,
            "is_effective": guard.is_effective,
            "bypass_possible": len(guard.bypass_conditions) > 0,
            "bypass_conditions": guard.bypass_conditions,
            "recommendation": self._get_guard_recommendation(guard),
        }

    def _get_guard_recommendation(self, guard: SecurityGuard) -> str:
        """가드별 권장사항"""
        if not guard.is_effective:
            return f"Replace {guard.name} with a more effective guard"
        if guard.bypass_conditions:
            return f"Address bypass condition: {guard.bypass_conditions[0]}"
        return "Guard is effective"

    def _generate_recommendations(self, validations: list[dict]) -> list[str]:
        """전체 권장사항 생성"""
        recommendations = []

        # 비효과적인 가드
        ineffective = [v for v in validations if not v.get("is_effective")]
        if ineffective:
            recommendations.append(f"Replace {len(ineffective)} ineffective guards with stronger alternatives")

        # 우회 가능한 가드
        bypassable = [v for v in validations if v.get("bypass_possible")]
        if bypassable:
            recommendations.append(f"Address {len(bypassable)} guards with known bypass conditions")

        # 커버리지 부족
        if not validations:
            recommendations.append("No security guards detected. Consider adding input validation and output encoding.")

        return recommendations
