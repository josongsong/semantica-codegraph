"""
Understanding Tools (RFC-041)

코드 이해/분석을 위한 Step Tools.

SOTA References:
- Aider RepoMap: 파일 구조 + 심볼 밀도 분석
- Cursor Tab: 사용 패턴 기반 컨텍스트 추출
- CodeQL: Import/Dependency 그래프 분석
"""

from dataclasses import dataclass
from typing import Any

from codegraph_shared.common.observability import get_logger

from .base import IRAnalyzerMixin, QueryDSLMixin, StepTool, StepToolResult

logger = get_logger(__name__)


# ================================================================
# Data Models
# ================================================================


@dataclass
class UsagePattern:
    """사용 패턴"""

    symbol_name: str
    usage_type: str  # "call", "assignment", "parameter", "return"
    frequency: int
    locations: list[dict[str, Any]]  # file, line, context
    pattern_signature: str  # 패턴 시그니처 (유사 패턴 탐색용)


@dataclass
class FileStructure:
    """파일 구조"""

    file_path: str
    language: str
    classes: list[dict[str, Any]]
    functions: list[dict[str, Any]]
    imports: list[str]
    exports: list[str]
    line_count: int
    complexity_score: float  # Cyclomatic complexity 기반


@dataclass
class ImportRelation:
    """Import 관계"""

    source_file: str
    target_module: str
    import_type: str  # "absolute", "relative", "star"
    imported_symbols: list[str]
    is_external: bool  # 외부 패키지 여부


@dataclass
class DependencyNode:
    """의존성 그래프 노드"""

    module_path: str
    dependencies: list[str]  # outgoing
    dependents: list[str]  # incoming
    is_entry_point: bool
    is_leaf: bool
    centrality_score: float  # PageRank 기반


# ================================================================
# Tools
# ================================================================


class AnalyzeUsagePatternTool(StepTool, QueryDSLMixin):
    """
    사용 패턴 분석 Tool

    SOTA: Cursor Tab의 사용 패턴 기반 컨텍스트 추출

    분석 내용:
    - 심볼이 어떻게 사용되는지 패턴화
    - 호출 빈도, 파라미터 패턴, 반환값 사용 패턴
    - 유사 사용 패턴 클러스터링
    """

    @property
    def name(self) -> str:
        return "analyze_usage_pattern"

    @property
    def description(self) -> str:
        return "심볼의 사용 패턴을 분석합니다 (호출 빈도, 파라미터 패턴 등)"

    def __init__(self, ir_analyzer: Any = None, embedding_service: Any = None):
        self.ir_analyzer = ir_analyzer
        self.embedding_service = embedding_service

    def execute(
        self,
        target: str = "",
        from_find_symbol_references: Any = None,
        **kwargs,
    ) -> StepToolResult:
        """
        사용 패턴 분석

        Args:
            target: 분석 대상 심볼
            from_find_symbol_references: 이전 Step 결과 (참조 목록)
        """
        if not from_find_symbol_references:
            return StepToolResult(
                success=False,
                error="No references provided from previous step",
            )

        try:
            references = from_find_symbol_references
            if isinstance(references, dict):
                references = references.get("references", [])

            # 1. 사용 타입별 분류
            usage_by_type: dict[str, list] = {
                "call": [],
                "assignment": [],
                "parameter": [],
                "return": [],
                "attribute_access": [],
                "other": [],
            }

            for ref in references:
                usage_type = self._classify_usage(ref)
                usage_by_type[usage_type].append(ref)

            # 2. 패턴 시그니처 추출
            patterns: list[UsagePattern] = []
            for usage_type, refs in usage_by_type.items():
                if refs:
                    pattern = UsagePattern(
                        symbol_name=target,
                        usage_type=usage_type,
                        frequency=len(refs),
                        locations=[
                            {
                                "file": r.get("file", ""),
                                "line": r.get("line", 0),
                                "context": r.get("context", ""),
                            }
                            for r in refs[:10]  # 최대 10개
                        ],
                        pattern_signature=self._extract_signature(refs),
                    )
                    patterns.append(pattern)

            # 3. 통계 계산
            total_usages = sum(len(refs) for refs in usage_by_type.values())
            dominant_type = max(usage_by_type.items(), key=lambda x: len(x[1]))[0]

            return StepToolResult(
                success=True,
                data={
                    "symbol": target,
                    "total_usages": total_usages,
                    "dominant_usage_type": dominant_type,
                    "usage_distribution": {k: len(v) for k, v in usage_by_type.items()},
                    "patterns": [
                        {
                            "type": p.usage_type,
                            "frequency": p.frequency,
                            "signature": p.pattern_signature,
                            "sample_locations": p.locations[:3],
                        }
                        for p in patterns
                    ],
                },
                confidence=0.85,
            )

        except Exception as e:
            logger.exception("Usage pattern analysis failed")
            return StepToolResult(success=False, error=str(e))

    def _classify_usage(self, ref: dict) -> str:
        """사용 타입 분류"""
        context = ref.get("context", "").lower()
        ref_type = ref.get("reference_type", "")

        if ref_type == "call" or "(" in context:
            return "call"
        if "=" in context and context.index("=") > context.find(ref.get("symbol", "")):
            return "assignment"
        if "def " in context or "function" in context:
            return "parameter"
        if "return " in context:
            return "return"
        if "." in context:
            return "attribute_access"
        return "other"

    def _extract_signature(self, refs: list) -> str:
        """패턴 시그니처 추출"""
        if not refs:
            return ""

        # 간단한 시그니처: 첫 번째 사용의 컨텍스트 정규화
        context = refs[0].get("context", "")
        # 변수명/리터럴 제거하여 패턴화
        import re

        signature = re.sub(r'"[^"]*"', '""', context)
        signature = re.sub(r"'[^']*'", "''", signature)
        signature = re.sub(r"\d+", "N", signature)
        return signature[:100]


class AnalyzeFileStructureTool(StepTool, IRAnalyzerMixin):
    """
    파일 구조 분석 Tool

    SOTA: Aider RepoMap의 파일 구조 + 심볼 밀도 분석

    분석 내용:
    - 클래스/함수/변수 목록
    - Import/Export 관계
    - 복잡도 점수
    """

    @property
    def name(self) -> str:
        return "analyze_file_structure"

    @property
    def description(self) -> str:
        return "파일의 구조를 분석합니다 (클래스, 함수, import 등)"

    def __init__(self, ir_analyzer: Any = None):
        self.ir_analyzer = ir_analyzer

    def execute(
        self,
        target: str = "",
        **kwargs,
    ) -> StepToolResult:
        """
        파일 구조 분석

        Args:
            target: 분석 대상 파일/디렉토리 경로
        """
        if not target:
            return StepToolResult(success=False, error="No target path provided")

        try:
            import os

            # 디렉토리인 경우 하위 파일들 분석
            if os.path.isdir(target):
                structures = []
                for root, _, files in os.walk(target):
                    for file in files:
                        if file.endswith((".py", ".ts", ".js", ".java")):
                            file_path = os.path.join(root, file)
                            structure = self._analyze_single_file(file_path)
                            if structure:
                                structures.append(structure)
                            if len(structures) >= 50:  # 최대 50개
                                break

                return StepToolResult(
                    success=True,
                    data={
                        "type": "directory",
                        "path": target,
                        "file_count": len(structures),
                        "files": structures,
                        "summary": self._summarize_structures(structures),
                    },
                    confidence=0.9,
                )

            # 단일 파일
            structure = self._analyze_single_file(target)
            if not structure:
                return StepToolResult(
                    success=False,
                    error=f"Failed to analyze file: {target}",
                )

            return StepToolResult(
                success=True,
                data={
                    "type": "file",
                    "structure": structure,
                },
                confidence=0.9,
            )

        except Exception as e:
            logger.exception("File structure analysis failed")
            return StepToolResult(success=False, error=str(e))

    def _analyze_single_file(self, file_path: str) -> dict | None:
        """단일 파일 분석"""
        try:
            # IR 분석기 사용
            if self.ir_analyzer:
                ir_doc = self._analyze_file(file_path, self.ir_analyzer)
                if ir_doc:
                    return self._extract_structure_from_ir(file_path, ir_doc)

            # Fallback: AST 직접 파싱
            return self._parse_file_ast(file_path)

        except Exception as e:
            logger.warning(f"Failed to analyze {file_path}: {e}")
            return None

    def _extract_structure_from_ir(self, file_path: str, ir_doc: Any) -> dict:
        """IR에서 구조 추출"""
        classes = []
        functions = []
        imports = []

        # IR 노드 순회
        if hasattr(ir_doc, "nodes"):
            for node in ir_doc.nodes:
                node_type = getattr(node, "type", "") or getattr(node, "kind", "")

                if "class" in str(node_type).lower():
                    classes.append(
                        {
                            "name": getattr(node, "name", ""),
                            "line": getattr(node, "line", 0),
                            "methods": self._get_methods(node),
                        }
                    )
                elif "function" in str(node_type).lower() or "def" in str(node_type).lower():
                    functions.append(
                        {
                            "name": getattr(node, "name", ""),
                            "line": getattr(node, "line", 0),
                            "params": self._get_params(node),
                        }
                    )
                elif "import" in str(node_type).lower():
                    imports.append(getattr(node, "module", "") or getattr(node, "name", ""))

        return {
            "file_path": file_path,
            "language": self._detect_language(file_path),
            "classes": classes,
            "functions": functions,
            "imports": imports,
            "line_count": getattr(ir_doc, "line_count", 0),
            "complexity_score": self._calculate_complexity(ir_doc),
        }

    def _parse_file_ast(self, file_path: str) -> dict | None:
        """AST 직접 파싱 (Fallback)"""
        if file_path.endswith(".py"):
            return self._parse_python_ast(file_path)
        return None

    def _parse_python_ast(self, file_path: str) -> dict | None:
        """Python AST 파싱"""
        try:
            import ast

            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()

            tree = ast.parse(content)

            classes = []
            functions = []
            imports = []

            for node in ast.walk(tree):
                if isinstance(node, ast.ClassDef):
                    methods = [n.name for n in node.body if isinstance(n, ast.FunctionDef)]
                    classes.append(
                        {
                            "name": node.name,
                            "line": node.lineno,
                            "methods": methods,
                        }
                    )
                elif isinstance(node, ast.FunctionDef) and not isinstance(getattr(node, "parent", None), ast.ClassDef):
                    functions.append(
                        {
                            "name": node.name,
                            "line": node.lineno,
                            "params": [arg.arg for arg in node.args.args],
                        }
                    )
                elif isinstance(node, ast.Import):
                    for alias in node.names:
                        imports.append(alias.name)
                elif isinstance(node, ast.ImportFrom):
                    module = node.module or ""
                    imports.append(module)

            return {
                "file_path": file_path,
                "language": "python",
                "classes": classes,
                "functions": functions,
                "imports": imports,
                "line_count": len(content.splitlines()),
                "complexity_score": self._calculate_python_complexity(tree),
            }

        except Exception as e:
            logger.warning(f"Python AST parsing failed for {file_path}: {e}")
            return None

    def _detect_language(self, file_path: str) -> str:
        """언어 감지"""
        ext_map = {
            ".py": "python",
            ".ts": "typescript",
            ".tsx": "typescript",
            ".js": "javascript",
            ".jsx": "javascript",
            ".java": "java",
            ".kt": "kotlin",
            ".go": "go",
            ".rs": "rust",
        }
        import os

        _, ext = os.path.splitext(file_path)
        return ext_map.get(ext, "unknown")

    def _get_methods(self, class_node: Any) -> list[str]:
        """클래스의 메서드 목록"""
        if hasattr(class_node, "methods"):
            return [m.name for m in class_node.methods]
        if hasattr(class_node, "body"):
            return [n.name for n in class_node.body if hasattr(n, "name")]
        return []

    def _get_params(self, func_node: Any) -> list[str]:
        """함수의 파라미터 목록"""
        if hasattr(func_node, "parameters"):
            return [p.name for p in func_node.parameters]
        if hasattr(func_node, "params"):
            return func_node.params
        return []

    def _calculate_complexity(self, ir_doc: Any) -> float:
        """복잡도 계산"""
        if hasattr(ir_doc, "complexity"):
            return ir_doc.complexity

        # 간단한 휴리스틱
        node_count = len(getattr(ir_doc, "nodes", []))
        return min(10.0, node_count / 10.0)

    def _calculate_python_complexity(self, tree: Any) -> float:
        """Python Cyclomatic Complexity"""
        import ast

        complexity = 1  # 기본
        for node in ast.walk(tree):
            if isinstance(node, (ast.If, ast.While, ast.For, ast.ExceptHandler)):
                complexity += 1
            elif isinstance(node, ast.BoolOp):
                complexity += len(node.values) - 1

        return min(10.0, complexity / 5.0)

    def _summarize_structures(self, structures: list[dict]) -> dict:
        """구조 요약"""
        total_classes = sum(len(s.get("classes", [])) for s in structures)
        total_functions = sum(len(s.get("functions", [])) for s in structures)
        total_lines = sum(s.get("line_count", 0) for s in structures)
        avg_complexity = sum(s.get("complexity_score", 0) for s in structures) / max(len(structures), 1)

        return {
            "total_files": len(structures),
            "total_classes": total_classes,
            "total_functions": total_functions,
            "total_lines": total_lines,
            "average_complexity": round(avg_complexity, 2),
        }


class ResolveImportsTool(StepTool, IRAnalyzerMixin):
    """
    Import 관계 분석 Tool

    SOTA: CodeQL의 Import Resolution

    분석 내용:
    - 파일의 import 관계 해석
    - 외부/내부 의존성 구분
    - 순환 참조 탐지
    """

    @property
    def name(self) -> str:
        return "resolve_imports"

    @property
    def description(self) -> str:
        return "파일의 import 관계를 분석합니다"

    def __init__(self, ir_analyzer: Any = None, project_root: str = ""):
        self.ir_analyzer = ir_analyzer
        self.project_root = project_root

    def execute(
        self,
        target: str = "",
        from_analyze_file_structure: Any = None,
        **kwargs,
    ) -> StepToolResult:
        """
        Import 관계 분석

        Args:
            target: 분석 대상
            from_analyze_file_structure: 이전 Step 결과
        """
        try:
            # 이전 Step 결과 활용
            if from_analyze_file_structure:
                structures = from_analyze_file_structure
                if isinstance(structures, dict):
                    if structures.get("type") == "directory":
                        structures = structures.get("files", [])
                    else:
                        structures = [structures.get("structure", {})]
            else:
                # 직접 분석
                structures = [{"file_path": target, "imports": []}]

            # Import 관계 추출
            relations: list[ImportRelation] = []
            all_modules: set[str] = set()

            for structure in structures:
                file_path = structure.get("file_path", "")
                imports = structure.get("imports", [])

                for imp in imports:
                    relation = ImportRelation(
                        source_file=file_path,
                        target_module=imp,
                        import_type=self._classify_import_type(imp),
                        imported_symbols=[],  # TODO: 상세 분석
                        is_external=self._is_external(imp),
                    )
                    relations.append(relation)
                    all_modules.add(imp)

            # 순환 참조 탐지
            circular_deps = self._detect_circular_dependencies(relations)

            # 외부/내부 의존성 통계
            external_deps = [r for r in relations if r.is_external]
            internal_deps = [r for r in relations if not r.is_external]

            return StepToolResult(
                success=True,
                data={
                    "total_imports": len(relations),
                    "unique_modules": len(all_modules),
                    "external_dependencies": len(external_deps),
                    "internal_dependencies": len(internal_deps),
                    "circular_dependencies": circular_deps,
                    "relations": [
                        {
                            "source": r.source_file,
                            "target": r.target_module,
                            "type": r.import_type,
                            "is_external": r.is_external,
                        }
                        for r in relations[:100]  # 최대 100개
                    ],
                },
                confidence=0.85,
            )

        except Exception as e:
            logger.exception("Import resolution failed")
            return StepToolResult(success=False, error=str(e))

    def _classify_import_type(self, module: str) -> str:
        """Import 타입 분류"""
        if module.startswith("."):
            return "relative"
        if "*" in module:
            return "star"
        return "absolute"

    def _is_external(self, module: str) -> bool:
        """외부 패키지 여부"""
        # 내부 모듈 패턴
        internal_patterns = ["src.", "app.", "lib.", "internal.", ".", ".."]

        for pattern in internal_patterns:
            if module.startswith(pattern):
                return False

        # 표준 라이브러리
        stdlib = {"os", "sys", "json", "re", "datetime", "typing", "collections", "functools", "itertools"}
        top_level = module.split(".")[0]

        if top_level in stdlib:
            return False  # 표준 라이브러리는 외부로 치지 않음

        return True

    def _detect_circular_dependencies(self, relations: list[ImportRelation]) -> list[list[str]]:
        """순환 참조 탐지 (DFS)"""
        # 그래프 구성
        graph: dict[str, set[str]] = {}
        for r in relations:
            if r.source_file not in graph:
                graph[r.source_file] = set()
            graph[r.source_file].add(r.target_module)

        # DFS로 사이클 탐지
        cycles: list[list[str]] = []
        visited: set[str] = set()
        rec_stack: list[str] = []

        def dfs(node: str) -> bool:
            visited.add(node)
            rec_stack.append(node)

            for neighbor in graph.get(node, set()):
                if neighbor not in visited:
                    if dfs(neighbor):
                        return True
                elif neighbor in rec_stack:
                    # 사이클 발견
                    cycle_start = rec_stack.index(neighbor)
                    cycles.append(rec_stack[cycle_start:] + [neighbor])
                    return True

            rec_stack.pop()
            return False

        for node in graph:
            if node not in visited:
                dfs(node)

        return cycles[:5]  # 최대 5개


class BuildDependencyGraphTool(StepTool):
    """
    의존성 그래프 구축 Tool

    SOTA: PageRank 기반 모듈 중요도 분석

    분석 내용:
    - 모듈 간 의존성 그래프
    - 중요도(Centrality) 점수
    - Entry point / Leaf 모듈 식별
    """

    @property
    def name(self) -> str:
        return "build_dependency_graph"

    @property
    def description(self) -> str:
        return "모듈 의존성 그래프를 구축합니다"

    def __init__(self):
        pass

    def execute(
        self,
        target: str = "",
        from_resolve_imports: Any = None,
        **kwargs,
    ) -> StepToolResult:
        """
        의존성 그래프 구축

        Args:
            target: 분석 대상
            from_resolve_imports: 이전 Step 결과
        """
        try:
            if not from_resolve_imports:
                return StepToolResult(
                    success=False,
                    error="No import relations provided",
                )

            relations = from_resolve_imports.get("relations", [])

            # 그래프 구성
            nodes: dict[str, DependencyNode] = {}
            edges: list[tuple[str, str]] = []

            for r in relations:
                source = r.get("source", "")
                target_mod = r.get("target", "")

                if source not in nodes:
                    nodes[source] = DependencyNode(
                        module_path=source,
                        dependencies=[],
                        dependents=[],
                        is_entry_point=True,  # 초기값
                        is_leaf=True,
                        centrality_score=0.0,
                    )

                if target_mod not in nodes:
                    nodes[target_mod] = DependencyNode(
                        module_path=target_mod,
                        dependencies=[],
                        dependents=[],
                        is_entry_point=True,
                        is_leaf=True,
                        centrality_score=0.0,
                    )

                nodes[source].dependencies.append(target_mod)
                nodes[target_mod].dependents.append(source)
                nodes[source].is_leaf = False  # 의존성이 있으므로 leaf 아님
                nodes[target_mod].is_entry_point = False  # 의존되므로 entry point 아님

                edges.append((source, target_mod))

            # PageRank 계산 (간단 버전)
            self._calculate_pagerank(nodes)

            # Entry points와 Leaves 식별
            entry_points = [n.module_path for n in nodes.values() if n.is_entry_point]
            leaves = [n.module_path for n in nodes.values() if n.is_leaf]

            # 가장 중요한 모듈들
            sorted_by_centrality = sorted(nodes.values(), key=lambda x: x.centrality_score, reverse=True)
            top_modules = [
                {"module": n.module_path, "centrality": round(n.centrality_score, 4)} for n in sorted_by_centrality[:10]
            ]

            return StepToolResult(
                success=True,
                data={
                    "node_count": len(nodes),
                    "edge_count": len(edges),
                    "entry_points": entry_points[:10],
                    "leaf_modules": leaves[:10],
                    "top_central_modules": top_modules,
                    "graph": {
                        "nodes": [
                            {
                                "id": n.module_path,
                                "dependencies": len(n.dependencies),
                                "dependents": len(n.dependents),
                                "centrality": round(n.centrality_score, 4),
                            }
                            for n in list(nodes.values())[:50]
                        ],
                        "edges": edges[:100],
                    },
                },
                confidence=0.9,
            )

        except Exception as e:
            logger.exception("Dependency graph construction failed")
            return StepToolResult(success=False, error=str(e))

    def _calculate_pagerank(self, nodes: dict[str, DependencyNode], iterations: int = 10, damping: float = 0.85):
        """간단한 PageRank 계산"""
        n = len(nodes)
        if n == 0:
            return

        # 초기값
        for node in nodes.values():
            node.centrality_score = 1.0 / n

        # 반복 계산
        for _ in range(iterations):
            new_scores: dict[str, float] = {}

            for path, node in nodes.items():
                # 들어오는 링크의 가중 합
                incoming_score = 0.0
                for dep_path in node.dependents:
                    if dep_path in nodes:
                        dep_node = nodes[dep_path]
                        out_degree = len(dep_node.dependencies)
                        if out_degree > 0:
                            incoming_score += dep_node.centrality_score / out_degree

                new_scores[path] = (1 - damping) / n + damping * incoming_score

            # 점수 업데이트
            for path, score in new_scores.items():
                nodes[path].centrality_score = score
