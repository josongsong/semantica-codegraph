"""
SQL Injection Detection (CWE-89) - Integrated Version

기존 taint_rules 시스템 활용 + 새로운 Vulnerability model

Architecture:
- 기존: taint_rules (SourceRule, SinkRule, SanitizerRule) → 완성도 높음!
- 기존: TaintSlicer (Program Slicing + Taint Analysis) → SOTA급!
- 새로운: Vulnerability model (CWE, Severity, Evidence)
- 새로운: QueryEngine (orchestration)
- 새로운: ReportGenerator (3 formats)
"""

from typing import List
import logging

from src.contexts.security_analysis.domain.models.security_rule import (
    SecurityRule,
    register_rule,
)
from src.contexts.security_analysis.domain.models.vulnerability import (
    Vulnerability,
    CWE,
    Severity,
    Location,
    Evidence,
)

# 기존 taint_rules 시스템 사용! (이미 완성됨)
from src.contexts.code_foundation.infrastructure.analyzers.taint_rules.base import (
    VulnerabilityType,
    RuleSet,
)
from src.contexts.code_foundation.infrastructure.analyzers.taint_rules.sources.python_core import (
    PYTHON_CORE_SOURCES,
)
from src.contexts.code_foundation.infrastructure.analyzers.taint_rules.sinks.python_core import (
    PYTHON_CORE_SINKS,
)
from src.contexts.code_foundation.infrastructure.analyzers.taint_rules.sanitizers.python_core import (
    PYTHON_CORE_SANITIZERS,
)

# 기존 TaintSlicer 사용! (PDG 기반, 고급)
from src.contexts.code_foundation.infrastructure.analyzers.taint_slicer import (
    TaintSlicer,
    TaintSliceResult,
)
from src.contexts.code_foundation.infrastructure.analyzers.taint_analyzer import (
    TaintAnalyzer,
)

logger = logging.getLogger(__name__)


@register_rule
class SQLInjectionQuery(SecurityRule):
    """
    SQL Injection 탐지 (기존 시스템 통합 버전)

    CWE-89: Improper Neutralization of Special Elements used in SQL Command

    구조:
    - Sources: 기존 PYTHON_CORE_SOURCES 사용 (HTTP, File, Env)
    - Sinks: 기존 PYTHON_CORE_SINKS 중 SQL 관련만 필터
    - Sanitizers: 기존 PYTHON_CORE_SANITIZERS 사용
    - Analysis: 기존 TaintSlicer 사용 (PDG + Slicing)
    - Output: 새로운 Vulnerability model로 변환
    """

    CWE_ID = CWE.CWE_89
    SEVERITY = Severity.CRITICAL

    # 기존 시스템 재사용! (중복 제거)
    # SOURCES, SINKS, SANITIZERS는 런타임에 필터링

    def __init__(self):
        super().__init__()

        # 기존 룰 필터링 (SQL Injection 관련만)
        self.sql_sources = [
            s
            for s in PYTHON_CORE_SOURCES
            # 모든 user input, environment, file은 잠재적 SQL injection source
        ]

        self.sql_sinks = [s for s in PYTHON_CORE_SINKS if s.vuln_type == VulnerabilityType.SQL_INJECTION]

        self.sql_sanitizers = [s for s in PYTHON_CORE_SANITIZERS if VulnerabilityType.SQL_INJECTION in s.sanitizes]

        logger.info(
            f"SQL Injection Query initialized: "
            f"{len(self.sql_sources)} sources, "
            f"{len(self.sql_sinks)} sinks, "
            f"{len(self.sql_sanitizers)} sanitizers"
        )

    def analyze(self, ir_document) -> List[Vulnerability]:
        """
        SQL Injection 분석 (기존 TaintSlicer 사용)

        Algorithm:
        1. IR document → PDG 생성
        2. TaintSlicer로 source → sink 경로 찾기 (기존)
        3. TaintSliceResult → Vulnerability 변환 (새로운)

        Args:
            ir_document: IR document

        Returns:
            List of Vulnerability objects (새로운 모델)
        """
        vulnerabilities = []

        logger.debug(f"Analyzing {ir_document.file_path} for SQL injection")

        try:
            # 기존 TaintSlicer 사용!
            taint_slicer = self._get_taint_slicer(ir_document)

            if taint_slicer:
                # Taint analysis with slicing (기존)
                taint_results = taint_slicer.analyze_taint_with_slicing(
                    ir_document,
                    max_depth=100,
                )

                # TaintSliceResult → Vulnerability 변환 (새로운)
                for result in taint_results:
                    if self._is_sql_injection(result):
                        vuln = self._convert_to_vulnerability(result, ir_document)
                        vulnerabilities.append(vuln)

        except Exception as e:
            logger.error(f"SQL Injection analysis failed: {e}", exc_info=True)

        logger.info(f"Found {len(vulnerabilities)} SQL injection vulnerabilities in {ir_document.file_path}")

        return vulnerabilities

    def _get_taint_slicer(self, ir_document) -> TaintSlicer | None:
        """
        Get TaintSlicer instance

        기존 인프라 사용 (IRDocument에 이미 있음!):
        - ir_document.get_pdg_builder() → PDGBuilder
        - ir_document.get_slicer() → ProgramSlicer
        - TaintAnalyzer (새로 생성, 기존 규칙 사용)

        Returns:
            TaintSlicer instance or None
        """
        try:
            from src.contexts.code_foundation.infrastructure.analyzers.taint_analyzer import TaintAnalyzer

            # 1. IRDocument에서 PDGBuilder, Slicer 가져오기 (이미 있음!)
            pdg_builder = ir_document.get_pdg_builder()
            program_slicer = ir_document.get_slicer()

            if not pdg_builder or not program_slicer:
                logger.warning("PDG or Slicer not available in IR document")
                return None

            # 2. TaintAnalyzer 생성 (기존 규칙 사용)
            taint_analyzer = TaintAnalyzer(
                sources=self._convert_sources(),
                sinks=self._convert_sinks(),
                sanitizers=self._convert_sanitizers(),
            )

            # 3. TaintSlicer 생성
            return TaintSlicer(
                pdg_builder=pdg_builder,
                slicer=program_slicer,
                taint_analyzer=taint_analyzer,
            )

        except Exception as e:
            logger.error(f"Failed to get TaintSlicer: {e}", exc_info=True)
            return None

    def _convert_sources(self) -> dict:
        """Convert SourceRule to TaintAnalyzer format"""
        return {
            rule.pattern: {
                "description": rule.description,
                "severity": rule.severity.value,
                "cwe_id": rule.cwe_id,
            }
            for rule in self.sql_sources
        }

    def _convert_sinks(self) -> dict:
        """Convert SinkRule to TaintAnalyzer format"""
        return {
            rule.pattern: {
                "description": rule.description,
                "severity": rule.severity.value,
                "cwe_id": rule.cwe_id,
                "vuln_type": rule.vuln_type.value,
            }
            for rule in self.sql_sinks
        }

    def _convert_sanitizers(self) -> dict:
        """Convert SanitizerRule to TaintAnalyzer format"""
        return {
            rule.pattern: {
                "description": rule.description,
                "effectiveness": rule.sanitizes,
            }
            for rule in self.sql_sanitizers
        }

    def _is_sql_injection(self, result: TaintSliceResult) -> bool:
        """
        Check if taint result is SQL injection

        Args:
            result: TaintSliceResult from TaintSlicer

        Returns:
            True if SQL injection
        """
        return result.vulnerability_type == "sql_injection" and not result.is_sanitized

    def _convert_to_vulnerability(
        self,
        taint_result: TaintSliceResult,
        ir_document,
    ) -> Vulnerability:
        """
        Convert TaintSliceResult to Vulnerability

        기존 결과 → 새로운 모델로 변환

        Args:
            taint_result: Result from TaintSlicer
            ir_document: IR document

        Returns:
            Vulnerability object (새로운 모델)
        """
        # SliceResult에서 code_fragments 추출
        slice_result = taint_result.slice_result

        # Source location (첫 번째 노드)
        source_fragment = self._find_fragment_by_node(
            taint_result.source_node,
            slice_result.code_fragments,
        )
        source_loc = self._fragment_to_location(source_fragment, ir_document)

        # Sink location (마지막 노드)
        sink_fragment = self._find_fragment_by_node(
            taint_result.sink_node,
            slice_result.code_fragments,
        )
        sink_loc = self._fragment_to_location(sink_fragment, ir_document)

        # Build evidence trail from taint path
        evidence = []
        for i, node_id in enumerate(taint_result.taint_path):
            # Node type
            if i == 0:
                node_type = "source"
            elif i == len(taint_result.taint_path) - 1:
                node_type = "sink"
            else:
                node_type = "propagation"

            # Find code fragment
            fragment = self._find_fragment_by_node(node_id, slice_result.code_fragments)

            evidence.append(
                Evidence(
                    location=self._fragment_to_location(fragment, ir_document),
                    code_snippet=fragment.code if fragment else "",
                    description=f"{node_type.capitalize()} point: {node_id}",
                    node_type=node_type,
                )
            )

        # Create vulnerability (새로운 모델)
        return Vulnerability(
            cwe=self.CWE_ID,
            severity=self._map_severity(taint_result.severity),
            title=f"SQL Injection in {source_loc.file_path}",
            description=self._generate_description(taint_result),
            source_location=source_loc,
            sink_location=sink_loc,
            taint_path=evidence,
            recommendation=self._get_recommendation(),
            references=self._get_references(),
            confidence=0.9 if not taint_result.is_sanitized else 0.3,
            false_positive_risk="low" if len(taint_result.taint_path) > 2 else "medium",
        )

    def _find_fragment_by_node(self, node_id: str, fragments) -> "CodeFragment | None":
        """Find CodeFragment by node ID"""
        for fragment in fragments:
            if fragment.node_id == node_id:
                return fragment
        return None

    def _fragment_to_location(self, fragment, ir_document) -> Location:
        """Convert CodeFragment to Location"""
        if fragment:
            return Location(
                file_path=fragment.file_path,
                start_line=fragment.start_line,
                end_line=fragment.end_line,
            )
        else:
            # Fallback
            return Location(
                file_path=ir_document.repo_id,  # Use repo_id as placeholder
                start_line=0,
                end_line=0,
            )

    def _map_severity(self, taint_severity: str) -> Severity:
        """Map taint severity to Vulnerability severity"""
        mapping = {
            "critical": Severity.CRITICAL,
            "high": Severity.HIGH,
            "medium": Severity.MEDIUM,
            "low": Severity.LOW,
        }
        return mapping.get(taint_severity, Severity.HIGH)

    def _generate_description(self, taint_result: TaintSliceResult) -> str:
        """Generate vulnerability description"""
        return (
            f"Untrusted data flows from source to SQL execution "
            f"without proper sanitization. "
            f"Path length: {len(taint_result.taint_path)} nodes."
        )

    def _get_recommendation(self) -> str:
        """Get SQL injection fix recommendation"""
        return """
Fix SQL Injection:

1. Use parameterized queries (BEST):
   ✓ cursor.execute("SELECT * FROM users WHERE id=?", [user_id])
   ✓ session.execute(text("SELECT * FROM users WHERE id=:id"), {"id": user_id})

2. Use ORM methods:
   ✓ User.objects.filter(id=user_id)
   ✓ session.query(User).filter_by(id=user_id)

3. Validate input:
   ✓ user_id = int(request.args.get("id"))
   ✓ if not user_id.isdigit(): raise ValueError()

AVOID:
   ✗ f"SELECT * FROM users WHERE id={user_id}"
   ✗ "SELECT * FROM users WHERE id=" + user_id
        """.strip()

    def _get_references(self) -> List[str]:
        """Get reference URLs"""
        return [
            "https://cwe.mitre.org/data/definitions/89.html",
            "https://owasp.org/www-community/attacks/SQL_Injection",
            "https://cheatsheetseries.owasp.org/cheatsheets/SQL_Injection_Prevention_Cheat_Sheet.html",
        ]


# Django-specific variant (기존 시스템 활용)


@register_rule
class DjangoSQLInjectionQuery(SQLInjectionQuery):
    """
    Django-specific SQL Injection detection

    기존 taint_rules/frameworks/django.py 활용
    """

    def __init__(self):
        super().__init__()

        # TODO: Django-specific rules from taint_rules/frameworks/django.py
        logger.info("Django SQL Injection Query initialized")
