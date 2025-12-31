"""
Variant Step Tools (RFC-041)

유사 코드 탐색 도구.
SOTA 참조: CodeQL Variant Analysis, Semgrep, Sourcegraph Code Search

특징:
- AST 기반 패턴 추출
- 구조적 유사도 매칭
- 의미론적 유사도 검색
"""

from dataclasses import dataclass, field
from typing import Any
import ast
import re
from collections import Counter

from .base import StepTool, StepToolResult, QueryDSLMixin


@dataclass
class CodePattern:
    """코드 패턴"""

    name: str
    pattern_type: str  # ast, regex, semantic
    structure: dict[str, Any]  # AST 구조
    tokens: list[str]  # 토큰 시퀀스
    abstractions: list[str]  # 추상화된 패턴
    fingerprint: str  # 해시 기반 지문


@dataclass
class SimilarCode:
    """유사 코드"""

    file_path: str
    line_start: int
    line_end: int
    code: str
    similarity_score: float
    match_type: str  # exact, structural, semantic
    matched_pattern: str


class ExtractCodePatternTool(StepTool):
    """
    코드 패턴 추출 Tool

    SOTA 참조:
    - CodeQL: AST pattern extraction
    - Semgrep: Pattern language
    - Comby: Structural matching

    기능:
    - AST 구조 추출
    - 토큰 시퀀스 추출
    - 패턴 추상화 (변수명 일반화)
    """

    @property
    def name(self) -> str:
        return "extract_code_pattern"

    @property
    def description(self) -> str:
        return "코드 패턴 추출 (AST, 토큰, 추상화)"

    def execute(
        self,
        code: str,
        pattern_name: str = "pattern",
        abstract_names: bool = True,
        abstract_literals: bool = True,
        **kwargs,
    ) -> StepToolResult:
        """
        코드 패턴 추출

        Args:
            code: 패턴으로 추출할 코드
            pattern_name: 패턴 이름
            abstract_names: 변수명 추상화
            abstract_literals: 리터럴 추상화
        """
        try:
            # 1. AST 구조 추출
            ast_structure = self._extract_ast_structure(code)

            # 2. 토큰 시퀀스 추출
            tokens = self._extract_tokens(code)

            # 3. 패턴 추상화
            abstractions = self._create_abstractions(code, abstract_names, abstract_literals)

            # 4. 지문 생성
            fingerprint = self._create_fingerprint(ast_structure, tokens)

            pattern = CodePattern(
                name=pattern_name,
                pattern_type="ast",
                structure=ast_structure,
                tokens=tokens,
                abstractions=abstractions,
                fingerprint=fingerprint,
            )

            return StepToolResult(
                success=True,
                data=self._pattern_to_dict(pattern),
                confidence=0.9,
                metadata={
                    "token_count": len(tokens),
                    "abstraction_count": len(abstractions),
                },
            )

        except Exception as e:
            return StepToolResult(
                success=False,
                error=str(e),
                confidence=0.0,
            )

    def _extract_ast_structure(self, code: str) -> dict[str, Any]:
        """AST 구조 추출"""
        try:
            tree = ast.parse(code)
            return self._ast_to_structure(tree)
        except SyntaxError:
            return {"error": "Cannot parse code"}

    def _ast_to_structure(self, node: ast.AST, depth: int = 0) -> dict[str, Any]:
        """AST 노드를 구조로 변환"""
        if depth > 10:  # 깊이 제한
            return {"type": "truncated"}

        structure: dict[str, Any] = {"type": type(node).__name__}

        # 중요 속성 추출
        if isinstance(node, ast.FunctionDef):
            structure["name"] = node.name
            structure["args_count"] = len(node.args.args)
            structure["decorators"] = [type(d).__name__ for d in node.decorator_list]

        elif isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name):
                structure["func"] = node.func.id
            elif isinstance(node.func, ast.Attribute):
                structure["attr"] = node.func.attr
            structure["args_count"] = len(node.args)

        elif isinstance(node, ast.If):
            structure["has_else"] = len(node.orelse) > 0

        elif isinstance(node, ast.For) or isinstance(node, ast.While):
            structure["has_else"] = len(node.orelse) > 0

        elif isinstance(node, ast.Try):
            structure["handlers_count"] = len(node.handlers)
            structure["has_finally"] = len(node.finalbody) > 0

        # 자식 노드 처리
        children = []
        for child in ast.iter_child_nodes(node):
            children.append(self._ast_to_structure(child, depth + 1))

        if children:
            structure["children"] = children

        return structure

    def _extract_tokens(self, code: str) -> list[str]:
        """토큰 시퀀스 추출"""
        # 간단한 토크나이저
        # Python 키워드 및 연산자
        token_pattern = r"""
            (\b(?:def|class|if|elif|else|for|while|try|except|finally|with|
            return|yield|import|from|as|raise|pass|break|continue|
            and|or|not|in|is|lambda|True|False|None)\b)|  # 키워드
            (\b\w+\b)|  # 식별자
            (==|!=|<=|>=|<|>|\+|-|\*|/|%|=|\.|\(|\)|\[|\]|\{|\}|,|:)  # 연산자
        """

        tokens = []
        for match in re.finditer(token_pattern, code, re.VERBOSE):
            token = match.group(0).strip()
            if token:
                tokens.append(token)

        return tokens

    def _create_abstractions(self, code: str, abstract_names: bool, abstract_literals: bool) -> list[str]:
        """패턴 추상화"""
        abstractions = []

        try:
            tree = ast.parse(code)

            for node in ast.walk(tree):
                if isinstance(node, ast.FunctionDef):
                    # 함수 패턴: def $NAME($ARGS): ...
                    args = ", ".join(["$ARG"] * len(node.args.args))
                    pattern = f"def {'$NAME' if abstract_names else node.name}({args}): ..."
                    abstractions.append(pattern)

                elif isinstance(node, ast.Call):
                    # 호출 패턴: $FUNC(...)
                    if isinstance(node.func, ast.Name):
                        func_name = "$FUNC" if abstract_names else node.func.id
                        args = ", ".join(["$ARG"] * len(node.args))
                        abstractions.append(f"{func_name}({args})")

                    elif isinstance(node.func, ast.Attribute):
                        obj = "$OBJ" if abstract_names else "obj"
                        attr = node.func.attr
                        args = ", ".join(["$ARG"] * len(node.args))
                        abstractions.append(f"{obj}.{attr}({args})")

                elif isinstance(node, ast.Assign):
                    # 할당 패턴: $VAR = $EXPR
                    abstractions.append("$VAR = $EXPR")

                elif isinstance(node, ast.If):
                    # 조건 패턴
                    pattern = "if $COND: ..."
                    if node.orelse:
                        pattern += " else: ..."
                    abstractions.append(pattern)

        except SyntaxError:
            pass

        return list(set(abstractions))  # 중복 제거

    def _create_fingerprint(self, structure: dict[str, Any], tokens: list[str]) -> str:
        """패턴 지문 생성"""
        import hashlib

        # 구조적 요소 추출
        elements = []

        def extract_types(s: dict[str, Any]) -> None:
            if "type" in s:
                elements.append(s["type"])
            if "children" in s:
                for child in s["children"]:
                    extract_types(child)

        extract_types(structure)

        # 토큰 n-gram
        n = 3
        ngrams = []
        for i in range(len(tokens) - n + 1):
            ngrams.append("_".join(tokens[i : i + n]))

        # 해시 생성
        content = "|".join(elements) + "||" + "|".join(ngrams[:20])
        return hashlib.md5(content.encode()).hexdigest()[:16]

    def _pattern_to_dict(self, pattern: CodePattern) -> dict[str, Any]:
        """패턴을 딕셔너리로 변환"""
        return {
            "name": pattern.name,
            "pattern_type": pattern.pattern_type,
            "structure": pattern.structure,
            "tokens": pattern.tokens[:50],  # 토큰 수 제한
            "abstractions": pattern.abstractions,
            "fingerprint": pattern.fingerprint,
        }


class SearchSimilarCodeTool(StepTool, QueryDSLMixin):
    """
    유사 코드 검색 Tool

    SOTA 참조:
    - CodeQL Variant Analysis
    - Sourcegraph structural search
    - GitHub Code Search

    기능:
    - 정확 매칭
    - 구조적 매칭
    - 의미론적 매칭
    """

    @property
    def name(self) -> str:
        return "search_similar_code"

    @property
    def description(self) -> str:
        return "유사 코드 검색 (구조적/의미론적)"

    def execute(
        self,
        pattern: dict[str, Any],
        ir_doc: Any | None = None,
        search_scope: list[str] | None = None,
        min_similarity: float = 0.7,
        max_results: int = 20,
        **kwargs,
    ) -> StepToolResult:
        """
        유사 코드 검색

        Args:
            pattern: 검색할 패턴
            ir_doc: IR 문서 (옵션)
            search_scope: 검색 범위 (파일 경로 목록)
            min_similarity: 최소 유사도
            max_results: 최대 결과 수
        """
        try:
            matches: list[SimilarCode] = []

            if ir_doc:
                # IR 기반 검색
                ir_matches = self._search_in_ir(pattern, ir_doc, min_similarity)
                matches.extend(ir_matches)

            # 패턴 기반 검색 (Semgrep 스타일)
            if pattern.get("abstractions"):
                abstract_matches = self._search_by_abstraction(
                    pattern["abstractions"],
                    search_scope or [],
                    min_similarity,
                )
                matches.extend(abstract_matches)

            # 지문 기반 검색
            if pattern.get("fingerprint"):
                fingerprint_matches = self._search_by_fingerprint(
                    pattern["fingerprint"],
                    search_scope or [],
                    min_similarity,
                )
                matches.extend(fingerprint_matches)

            # 중복 제거 및 정렬
            unique_matches = self._deduplicate_matches(matches)
            sorted_matches = sorted(unique_matches, key=lambda x: x.similarity_score, reverse=True)[:max_results]

            return StepToolResult(
                success=True,
                data={
                    "matches": [self._match_to_dict(m) for m in sorted_matches],
                    "total_found": len(matches),
                    "unique_count": len(unique_matches),
                },
                confidence=0.85,
                metadata={
                    "min_similarity": min_similarity,
                    "pattern_type": pattern.get("pattern_type", "unknown"),
                },
            )

        except Exception as e:
            return StepToolResult(
                success=False,
                error=str(e),
                confidence=0.0,
            )

    def _search_in_ir(self, pattern: dict[str, Any], ir_doc: Any, min_similarity: float) -> list[SimilarCode]:
        """IR 기반 검색"""
        matches = []

        try:
            engine = self._get_query_engine(ir_doc)

            # 패턴 구조에서 검색 조건 추출
            structure = pattern.get("structure", {})
            node_type = structure.get("type", "")

            from codegraph_engine.code_foundation.domain.query import Q

            # 노드 타입별 검색
            if node_type == "FunctionDef":
                query = Q.function().where(lambda n: self._match_structure(n, structure))
            elif node_type == "Call":
                func_name = structure.get("func", "")
                query = Q.call(func_name) if func_name else Q.call()
            else:
                query = Q.any()

            results = engine.execute(query)

            for node in results[:50]:
                similarity = self._calculate_similarity(node, pattern)
                if similarity >= min_similarity:
                    matches.append(
                        SimilarCode(
                            file_path=getattr(ir_doc, "file_path", ""),
                            line_start=getattr(node, "start_line", 0),
                            line_end=getattr(node, "end_line", 0),
                            code=getattr(node, "source", "")[:500],
                            similarity_score=similarity,
                            match_type="structural",
                            matched_pattern=pattern.get("name", "pattern"),
                        )
                    )

        except Exception:
            pass

        return matches

    def _search_by_abstraction(
        self,
        abstractions: list[str],
        search_scope: list[str],
        min_similarity: float,
    ) -> list[SimilarCode]:
        """추상화 패턴 기반 검색"""
        matches = []

        # 추상화 패턴을 정규식으로 변환
        for abstraction in abstractions:
            regex = self._abstraction_to_regex(abstraction)
            if not regex:
                continue

            for file_path in search_scope[:100]:  # 파일 수 제한
                try:
                    with open(file_path) as f:
                        content = f.read()

                    for match in re.finditer(regex, content):
                        line_start = content[: match.start()].count("\n") + 1
                        matches.append(
                            SimilarCode(
                                file_path=file_path,
                                line_start=line_start,
                                line_end=line_start,
                                code=match.group(0),
                                similarity_score=0.8,
                                match_type="abstraction",
                                matched_pattern=abstraction,
                            )
                        )
                except Exception:
                    continue

        return matches

    def _search_by_fingerprint(
        self,
        fingerprint: str,
        search_scope: list[str],
        min_similarity: float,
    ) -> list[SimilarCode]:
        """지문 기반 검색"""
        # 지문 캐시가 있다고 가정
        # 실제 구현에서는 인덱싱된 지문 DB 사용
        return []  # 추후 구현

    def _abstraction_to_regex(self, abstraction: str) -> str | None:
        """추상화 패턴을 정규식으로 변환"""
        try:
            # $ 변수를 정규식으로 변환
            regex = abstraction

            # $NAME, $VAR, $ARG 등을 \w+ 로
            regex = re.sub(r"\$\w+", r"\\w+", regex)

            # ... 을 .*? 로
            regex = regex.replace("...", ".*?")

            # 특수 문자 이스케이프
            regex = re.sub(r"([\(\)\[\]\{\}])", r"\\\1", regex)

            return regex
        except Exception:
            return None

    def _match_structure(self, node: Any, structure: dict[str, Any]) -> bool:
        """구조 매칭"""
        node_type = type(node).__name__
        return node_type == structure.get("type", "")

    def _calculate_similarity(self, node: Any, pattern: dict[str, Any]) -> float:
        """유사도 계산"""
        score = 0.0
        factors = 0

        # 토큰 유사도
        if "tokens" in pattern and hasattr(node, "source"):
            node_tokens = self._tokenize(getattr(node, "source", ""))
            pattern_tokens = pattern["tokens"]
            token_sim = self._jaccard_similarity(node_tokens, pattern_tokens)
            score += token_sim
            factors += 1

        # 구조 유사도
        if "structure" in pattern:
            node_type = type(node).__name__
            pattern_type = pattern["structure"].get("type", "")
            if node_type == pattern_type:
                score += 0.8
            factors += 1

        return score / factors if factors > 0 else 0.0

    def _tokenize(self, code: str) -> list[str]:
        """간단한 토크나이저"""
        return re.findall(r"\b\w+\b", code)

    def _jaccard_similarity(self, a: list[str], b: list[str]) -> float:
        """Jaccard 유사도"""
        set_a = set(a)
        set_b = set(b)

        intersection = len(set_a & set_b)
        union = len(set_a | set_b)

        return intersection / union if union > 0 else 0.0

    def _deduplicate_matches(self, matches: list[SimilarCode]) -> list[SimilarCode]:
        """중복 제거"""
        seen = set()
        unique = []

        for match in matches:
            key = (match.file_path, match.line_start, match.line_end)
            if key not in seen:
                seen.add(key)
                unique.append(match)

        return unique

    def _match_to_dict(self, match: SimilarCode) -> dict[str, Any]:
        """매치를 딕셔너리로 변환"""
        return {
            "file_path": match.file_path,
            "line_start": match.line_start,
            "line_end": match.line_end,
            "code": match.code,
            "similarity_score": match.similarity_score,
            "match_type": match.match_type,
            "matched_pattern": match.matched_pattern,
        }


class RankSimilarityTool(StepTool):
    """
    유사도 순위 Tool

    SOTA 참조:
    - TF-IDF ranking
    - BM25
    - Neural Code Search

    기능:
    - 다중 유사도 메트릭 결합
    - 컨텍스트 기반 리랭킹
    - 보안 관련성 부스팅
    """

    @property
    def name(self) -> str:
        return "rank_similarity"

    @property
    def description(self) -> str:
        return "유사도 기반 순위 매기기"

    def execute(
        self,
        matches: list[dict[str, Any]],
        boost_security: bool = True,
        context: dict[str, Any] | None = None,
        **kwargs,
    ) -> StepToolResult:
        """
        유사도 순위 매기기

        Args:
            matches: 검색 결과
            boost_security: 보안 관련 결과 부스팅
            context: 랭킹 컨텍스트
        """
        try:
            ranked = []

            for match in matches:
                score = match.get("similarity_score", 0.0)

                # 보안 관련성 부스팅
                if boost_security:
                    security_boost = self._calculate_security_boost(match)
                    score *= 1 + security_boost

                # 코드 품질 가중치
                quality_factor = self._calculate_quality_factor(match)
                score *= quality_factor

                # 컨텍스트 관련성
                if context:
                    context_factor = self._calculate_context_relevance(match, context)
                    score *= context_factor

                ranked.append(
                    {
                        **match,
                        "final_score": min(1.0, score),
                        "score_breakdown": {
                            "base": match.get("similarity_score", 0.0),
                            "security_boost": security_boost if boost_security else 0,
                            "quality_factor": quality_factor,
                        },
                    }
                )

            # 최종 점수로 정렬
            ranked.sort(key=lambda x: x["final_score"], reverse=True)

            return StepToolResult(
                success=True,
                data={
                    "ranked_matches": ranked,
                    "top_match": ranked[0] if ranked else None,
                },
                confidence=0.9,
                metadata={
                    "total_ranked": len(ranked),
                    "boost_applied": boost_security,
                },
            )

        except Exception as e:
            return StepToolResult(
                success=False,
                error=str(e),
                confidence=0.0,
            )

    def _calculate_security_boost(self, match: dict[str, Any]) -> float:
        """보안 관련성 부스트 계산"""
        code = match.get("code", "").lower()
        boost = 0.0

        # 보안 관련 키워드
        security_keywords = [
            "password",
            "token",
            "secret",
            "auth",
            "login",
            "session",
            "cookie",
            "encrypt",
            "decrypt",
            "hash",
            "sql",
            "query",
            "execute",
            "shell",
            "command",
            "subprocess",
            "eval",
            "exec",
            "input",
            "request",
            "response",
        ]

        for keyword in security_keywords:
            if keyword in code:
                boost += 0.05

        return min(0.3, boost)  # 최대 30% 부스트

    def _calculate_quality_factor(self, match: dict[str, Any]) -> float:
        """코드 품질 가중치 계산"""
        code = match.get("code", "")
        factor = 1.0

        # 코드 길이 (너무 짧거나 긴 코드 페널티)
        lines = code.count("\n") + 1
        if lines < 2:
            factor *= 0.8
        elif lines > 50:
            factor *= 0.9

        # 주석 존재 (문서화된 코드 선호)
        if "#" in code or '"""' in code or "'''" in code:
            factor *= 1.1

        return min(1.2, factor)

    def _calculate_context_relevance(self, match: dict[str, Any], context: dict[str, Any]) -> float:
        """컨텍스트 관련성 계산"""
        relevance = 1.0

        # 같은 파일 타입 선호
        if "file_type" in context:
            match_ext = match.get("file_path", "").split(".")[-1]
            if match_ext == context["file_type"]:
                relevance *= 1.1

        # 같은 모듈 선호
        if "module" in context:
            if context["module"] in match.get("file_path", ""):
                relevance *= 1.15

        return relevance
