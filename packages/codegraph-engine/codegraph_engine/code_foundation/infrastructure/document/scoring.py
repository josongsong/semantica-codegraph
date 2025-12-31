"""
Document Quality Scoring & Drift Detection

SOTA급 문서 품질 평가 시스템:
- Coverage: API/클래스/config 대비 문서화 비율
- Accuracy & Drift: 코드와 문서 일치성 검사
- Structure: 문서 구조 품질
- Task Fitness: 실제 태스크 완수 가능성
- Freshness: 신선도 (코드 변경 대비 문서 업데이트)
- Findability: 검색 가능성
"""

from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum

from codegraph_engine.code_foundation.infrastructure.document.chunker import DocumentChunk
from codegraph_engine.code_foundation.infrastructure.document.models import ParsedDocument
from codegraph_engine.code_foundation.infrastructure.ir.models.document import IRDocument


class DriftSeverity(Enum):
    """Drift 심각도"""

    NONE = "none"
    WEAK = "weak"  # 약한 불일치 (deprecated 표시 누락 등)
    STRONG = "strong"  # 강한 불일치 (타입 불일치, 필드 누락)
    CRITICAL = "critical"  # 치명적 불일치 (완전히 다른 API)


@dataclass
class DriftResult:
    """
    Drift 감지 결과.

    Attributes:
        severity: Drift 심각도
        doc_chunk_id: 문서 청크 ID
        code_node_id: 코드 노드 ID (있을 경우)
        drift_type: Drift 타입 (type_mismatch, field_missing, enum_mismatch 등)
        description: 상세 설명
        confidence: 신뢰도 (0.0-1.0)
    """

    severity: DriftSeverity
    doc_chunk_id: str
    code_node_id: str | None
    drift_type: str
    description: str
    confidence: float = 1.0


@dataclass
class DocumentScore:
    """
    문서 품질 스코어.

    Attributes:
        coverage: Coverage 점수 (0-100)
        drift_penalty: Drift 패널티 (0-1, 0=no drift)
        structure: 구조 품질 (0-100)
        task_fitness: 태스크 완결성 (0-100)
        freshness: 신선도 (0-100)
        findability: 검색 가능성 (0-100)
        overall: 종합 점수 (0-100)
        grade: 등급 (A/B/C)
    """

    coverage: float
    drift_penalty: float
    structure: float
    task_fitness: float
    freshness: float
    findability: float
    overall: float
    grade: str

    @property
    def is_production_ready(self) -> bool:
        """프로덕션 배포 가능한가?"""
        return self.overall >= 80.0 and self.drift_penalty < 0.3


class DriftDetector:
    """
    문서-코드 Drift 감지기.

    코드 변경이 문서에 반영되지 않은 경우를 탐지합니다.
    """

    def __init__(self):
        """Initialize drift detector."""
        pass

    def detect_drifts(self, doc_chunks: list[DocumentChunk], ir_doc: IRDocument) -> list[DriftResult]:
        """
        문서와 코드 사이의 drift를 감지합니다.

        Args:
            doc_chunks: 문서 청크 리스트
            ir_doc: IR 문서 (코드베이스)

        Returns:
            Drift 결과 리스트
        """
        drifts: list[DriftResult] = []

        # 1. 코드 블록에서 언급된 함수/클래스 추출
        mentioned_symbols = self._extract_mentioned_symbols(doc_chunks)

        # 2. IR에서 실제 심볼 정보 가져오기
        actual_symbols = self._build_symbol_map(ir_doc)

        # 3. 심볼별로 drift 검사
        for symbol_name, doc_info in mentioned_symbols.items():
            if symbol_name not in actual_symbols:
                # 심볼이 코드에 존재하지 않음 (삭제됨?)
                drifts.append(
                    DriftResult(
                        severity=DriftSeverity.STRONG,
                        doc_chunk_id=doc_info["chunk_id"],
                        code_node_id=None,
                        drift_type="symbol_not_found",
                        description=f"Symbol '{symbol_name}' mentioned in docs but not found in code",
                        confidence=0.9,
                    )
                )
            else:
                # 심볼 존재 - 상세 비교
                actual = actual_symbols[symbol_name]
                symbol_drifts = self._compare_symbol(symbol_name, doc_info, actual)
                drifts.extend(symbol_drifts)

        # 4. Deprecated 표시 체크
        deprecated_drifts = self._check_deprecated_markers(doc_chunks, actual_symbols)
        drifts.extend(deprecated_drifts)

        return drifts

    def _extract_mentioned_symbols(self, doc_chunks: list[DocumentChunk]) -> dict[str, dict]:
        """문서에서 언급된 심볼 추출"""
        import re

        symbols: dict[str, dict] = {}

        for chunk in doc_chunks:
            if not chunk.content:
                continue

            # 인라인 코드에서 함수/클래스명 추출
            inline_code = re.findall(r"`([a-zA-Z_][a-zA-Z0-9_]*)`", chunk.content)

            for symbol in inline_code:
                if symbol not in symbols:
                    symbols[symbol] = {
                        "chunk_id": self._get_chunk_id(chunk),
                        "mentions": [],
                    }
                symbols[symbol]["mentions"].append(chunk.content)

        return symbols

    def _build_symbol_map(self, ir_doc: IRDocument) -> dict[str, dict]:
        """IR에서 심볼 맵 생성"""
        from codegraph_engine.code_foundation.infrastructure.ir.models.core import NodeKind

        symbol_map: dict[str, dict] = {}

        for node in ir_doc.nodes:
            if node.kind in [
                NodeKind.FUNCTION,
                NodeKind.METHOD,
                NodeKind.CLASS,
                NodeKind.VARIABLE,
            ]:
                symbol_map[node.name] = {
                    "node_id": node.id,
                    "kind": node.kind,
                    "fqn": node.fqn,
                    "attrs": node.attrs,
                }

        return symbol_map

    def _compare_symbol(self, symbol_name: str, doc_info: dict, _actual_info: dict) -> list[DriftResult]:
        """심볼 상세 비교"""
        drifts: list[DriftResult] = []

        # 타입 불일치 체크 (예: 문서에는 function이라고 했는데 실제로는 class)
        # 간단한 휴리스틱: 문서에 "class"라는 단어가 있는지, "function"이 있는지
        # 실제 구현에서는 더 정교한 파싱 필요

        return drifts

    def _check_deprecated_markers(self, doc_chunks: list[DocumentChunk], actual_symbols: dict) -> list[DriftResult]:
        """Deprecated 표시 체크"""
        drifts: list[DriftResult] = []

        # IR에서 deprecated 심볼 찾기
        deprecated_symbols = {
            name: info for name, info in actual_symbols.items() if info["attrs"].get("deprecated", False)
        }

        # 문서에 deprecated 표시가 있는지 확인
        for symbol_name, symbol_info in deprecated_symbols.items():
            # 문서에서 이 심볼을 언급하는 청크 찾기
            mentioning_chunks = [chunk for chunk in doc_chunks if symbol_name in (chunk.content or "")]

            for chunk in mentioning_chunks:
                # "deprecated"라는 단어가 있는지 확인
                if "deprecated" not in chunk.content.lower():
                    drifts.append(
                        DriftResult(
                            severity=DriftSeverity.WEAK,
                            doc_chunk_id=self._get_chunk_id(chunk),
                            code_node_id=symbol_info["node_id"],
                            drift_type="missing_deprecated_marker",
                            description=f"Symbol '{symbol_name}' is deprecated in code but not marked in docs",
                            confidence=0.8,
                        )
                    )

        return drifts

    def _get_chunk_id(self, chunk: DocumentChunk) -> str:
        """청크 ID 생성"""
        file_path_safe = chunk.file_path.replace("/", "_").replace(".", "_")
        return f"doc:{file_path_safe}:{chunk.line_start}-{chunk.line_end}"


class DocumentScorer:
    """
    문서 품질 스코어링 시스템.

    SOTA급 multi-metric 평가.
    """

    def __init__(
        self,
        coverage_weight: float = 0.25,
        drift_weight: float = 0.25,
        structure_weight: float = 0.20,
        task_fitness_weight: float = 0.20,
        freshness_weight: float = 0.10,
    ):
        """
        Initialize scorer.

        Args:
            coverage_weight: Coverage 가중치
            drift_weight: Drift 가중치
            structure_weight: Structure 가중치
            task_fitness_weight: Task fitness 가중치
            freshness_weight: Freshness 가중치
        """
        self.coverage_weight = coverage_weight
        self.drift_weight = drift_weight
        self.structure_weight = structure_weight
        self.task_fitness_weight = task_fitness_weight
        self.freshness_weight = freshness_weight

    def score_document(
        self,
        doc: ParsedDocument,
        doc_chunks: list[DocumentChunk],
        ir_doc: IRDocument | None = None,
        last_code_change: datetime | None = None,
        last_doc_update: datetime | None = None,
    ) -> DocumentScore:
        """
        문서 품질 점수 계산.

        Args:
            doc: 파싱된 문서
            doc_chunks: 문서 청크 리스트
            ir_doc: IR 문서 (drift 검사용)
            last_code_change: 마지막 코드 변경 시각
            last_doc_update: 마지막 문서 업데이트 시각

        Returns:
            문서 점수
        """
        # 1. Coverage
        coverage = self._calculate_coverage(doc, doc_chunks, ir_doc)

        # 2. Drift penalty
        drift_penalty = 0.0
        if ir_doc:
            drift_penalty = self._calculate_drift_penalty(doc_chunks, ir_doc)

        # 3. Structure
        structure = self._calculate_structure_score(doc, doc_chunks)

        # 4. Task fitness (간단한 휴리스틱)
        task_fitness = self._calculate_task_fitness(doc, doc_chunks)

        # 5. Freshness
        freshness = 100.0
        if last_code_change and last_doc_update:
            freshness = self._calculate_freshness(last_code_change, last_doc_update)

        # 6. Findability (기본값)
        findability = self._calculate_findability(doc, doc_chunks)

        # 종합 점수
        overall = (
            self.coverage_weight * coverage
            + self.drift_weight * (100.0 * (1 - drift_penalty))
            + self.structure_weight * structure
            + self.task_fitness_weight * task_fitness
            + self.freshness_weight * freshness
        )

        # 등급
        grade = self._calculate_grade(overall)

        return DocumentScore(
            coverage=coverage,
            drift_penalty=drift_penalty,
            structure=structure,
            task_fitness=task_fitness,
            freshness=freshness,
            findability=findability,
            overall=overall,
            grade=grade,
        )

    def _calculate_coverage(
        self,
        doc: ParsedDocument,
        doc_chunks: list[DocumentChunk],
        ir_doc: IRDocument | None,
    ) -> float:
        """
        Coverage 계산.

        문서가 코드베이스의 얼마나 많은 부분을 커버하는가?
        """
        if not ir_doc:
            # IR이 없으면 기본 점수
            return 70.0

        # IR의 public 심볼 개수
        from codegraph_engine.code_foundation.infrastructure.ir.models.core import NodeKind

        public_symbols = [
            node
            for node in ir_doc.nodes
            if node.kind in [NodeKind.FUNCTION, NodeKind.CLASS, NodeKind.METHOD, NodeKind.VARIABLE]
            and not node.name.startswith("_")  # public
        ]

        if not public_symbols:
            return 100.0

        # 문서에서 언급된 심볼
        detector = DriftDetector()
        mentioned = detector._extract_mentioned_symbols(doc_chunks)

        coverage_ratio = len(mentioned) / len(public_symbols)
        return min(100.0, coverage_ratio * 100.0)

    def _calculate_drift_penalty(self, doc_chunks: list[DocumentChunk], ir_doc: IRDocument) -> float:
        """
        Drift penalty 계산.

        0.0 = no drift, 1.0 = severe drift
        """
        detector = DriftDetector()
        drifts = detector.detect_drifts(doc_chunks, ir_doc)

        if not drifts:
            return 0.0

        # Severity별 가중치
        severity_weights = {
            DriftSeverity.WEAK: 0.1,
            DriftSeverity.STRONG: 0.5,
            DriftSeverity.CRITICAL: 1.0,
        }

        total_penalty = sum(severity_weights.get(drift.severity, 0.5) * drift.confidence for drift in drifts)

        # 정규화 (최대 1.0)
        # drift 개수에 비례하도록 (청크 개수가 아니라)
        if len(drifts) == 0:
            return 0.0

        # Drift 수와 severity에 따라 패널티 계산
        # 최대 5개 drift까지 선형 증가, 이후 포화
        normalized_penalty = min(1.0, total_penalty / 5.0)

        return normalized_penalty

    def _calculate_structure_score(self, doc: ParsedDocument, doc_chunks: list[DocumentChunk]) -> float:
        """
        Structure 점수 계산.

        - Heading 구조
        - 코드 예제 존재
        - 코드 블록 언어 태그
        """
        score = 0.0

        # 1. Heading 구조 (40점)
        headings = [s for s in doc.sections if s.section_type.value == "heading"]
        if len(headings) >= 3:
            score += 40.0
        elif len(headings) >= 1:
            score += 20.0

        # 2. 코드 블록 존재 (30점)
        code_blocks = [c for c in doc_chunks if c.is_code_block()]
        if code_blocks:
            score += 30.0

            # 언어 태그 비율 (추가 10점)
            with_lang = [c for c in code_blocks if c.code_language]
            if code_blocks:
                lang_ratio = len(with_lang) / len(code_blocks)
                score += 10.0 * lang_ratio

        # 3. 예제와 설명 alignment (20점)
        # 간단한 휴리스틱: 코드 블록 앞/뒤에 텍스트가 있는가?
        for i, chunk in enumerate(doc_chunks):
            if chunk.is_code_block():
                has_context = False
                if i > 0 and not doc_chunks[i - 1].is_code_block():
                    has_context = True
                if i < len(doc_chunks) - 1 and not doc_chunks[i + 1].is_code_block():
                    has_context = True

                if has_context:
                    score += 20.0 / len(code_blocks) if code_blocks else 0

        return min(100.0, score)

    def _calculate_task_fitness(self, doc: ParsedDocument, doc_chunks: list[DocumentChunk]) -> float:
        """
        Task fitness 계산.

        문서만 보고 실제 태스크를 완수할 수 있는가?
        """
        score = 50.0  # 기본 점수

        # 코드 예제가 있으면 +20
        code_blocks = [c for c in doc_chunks if c.is_code_block()]
        if code_blocks:
            score += 20.0

        # 전체 텍스트 한 번만 생성
        all_text = " ".join(c.content for c in doc_chunks if c.content).lower()

        # 에러 핸들링 언급 (+10)
        if any(keyword in all_text for keyword in ["error", "exception", "catch"]):
            score += 10.0

        # 파라미터/옵션 설명 (+10)
        if any(keyword in all_text for keyword in ["parameter", "option", "config"]):
            score += 10.0

        # 예제 결과/응답 (+10)
        if any(keyword in all_text for keyword in ["response", "output", "result"]):
            score += 10.0

        return min(100.0, score)

    def _calculate_freshness(self, last_code_change: datetime, last_doc_update: datetime) -> float:
        """
        Freshness 계산.

        코드가 변경되었는데 문서가 오래되었는가?
        """
        if last_doc_update >= last_code_change:
            # 문서가 더 최신
            return 100.0

        # 시간 차이 계산
        time_diff = last_code_change - last_doc_update

        # 1주일 이내: 90점
        if time_diff < timedelta(days=7):
            return 90.0

        # 1개월 이내: 70점
        if time_diff < timedelta(days=30):
            return 70.0

        # 3개월 이내: 50점
        if time_diff < timedelta(days=90):
            return 50.0

        # 6개월 이내: 30점
        if time_diff < timedelta(days=180):
            return 30.0

        # 6개월 이상: 10점
        return 10.0

    def _calculate_findability(self, doc: ParsedDocument, doc_chunks: list[DocumentChunk]) -> float:
        """
        Findability 계산.

        문서를 쉽게 찾을 수 있는가?
        """
        score = 50.0  # 기본 점수

        # 명확한 제목 (+20)
        if doc.sections and doc.sections[0].section_type.value == "heading":
            title = doc.sections[0].content
            if len(title.split()) >= 2:  # 2단어 이상
                score += 20.0

        # 여러 섹션 (+20)
        headings = [s for s in doc.sections if s.section_type.value == "heading"]
        if len(headings) >= 3:
            score += 20.0

        # 키워드 밀도 (+10)
        # 간단한 휴리스틱: 고유 단어 수 / 전체 단어 수
        all_text = " ".join(c.content for c in doc_chunks if c.content).lower()
        words = all_text.split()
        if words and len(words) > 0:
            unique_ratio = len(set(words)) / len(words)
            score += 10.0 * unique_ratio

        return min(100.0, score)

    def _calculate_grade(self, overall: float) -> str:
        """등급 계산"""
        if overall >= 85.0:
            return "A"
        elif overall >= 70.0:
            return "B"
        else:
            return "C"
