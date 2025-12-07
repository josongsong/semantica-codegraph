"""
Complexity Analyzer Adapter

Radon 라이브러리 기반 복잡도 분석
IComplexityAnalyzer Port 구현
"""

import logging
from pathlib import Path

logger = logging.getLogger(__name__)


class RadonComplexityAnalyzer:
    """
    Radon 기반 복잡도 분석 Adapter

    구현: IComplexityAnalyzer Port
    """

    def analyze_cyclomatic(self, code: str) -> float:
        """
        Cyclomatic Complexity 계산

        Uses: radon.complexity.cc_visit
        """
        try:
            from radon.complexity import cc_visit

            results = cc_visit(code)

            if not results:
                return 0.0

            # 평균 복잡도
            total = sum(r.complexity for r in results)
            avg = total / len(results)

            logger.debug(f"Cyclomatic complexity: {avg:.2f}")
            return avg

        except ImportError:
            logger.warning("radon not installed, using fallback")
            return self._fallback_cyclomatic(code)

        except Exception as e:
            logger.error(f"Failed to analyze cyclomatic complexity: {e}")
            return 0.0

    def analyze_cognitive(self, code: str) -> float:
        """
        Cognitive Complexity 계산

        Note: Radon은 cognitive 미지원
        MI (Maintainability Index)로 간접 계산
        """
        try:
            from radon.metrics import mi_visit

            mi = mi_visit(code, multi=True)

            # MI (0-100) → Cognitive (0-50)
            # MI가 낮을수록 복잡함
            cognitive = max(0, (100 - mi) / 2)

            logger.debug(f"Cognitive complexity (from MI): {cognitive:.2f}")
            return cognitive

        except ImportError:
            logger.warning("radon not installed, using fallback")
            return self._fallback_cognitive(code)

        except Exception as e:
            logger.error(f"Failed to analyze cognitive complexity: {e}")
            return 0.0

    def count_impact_nodes(self, file_path: str) -> int:
        """
        CFG 영향 노드 수 계산

        Uses: Code Foundation의 CFG Builder
        """
        try:
            # v7.1 기존 인프라 재사용
            from src.contexts.code_foundation.infrastructure.graph import CFGBuilder

            path = Path(file_path)
            if not path.exists():
                logger.warning(f"File not found: {file_path}")
                return 0

            cfg = CFGBuilder().build(str(path))
            node_count = len(cfg.nodes) if hasattr(cfg, "nodes") else 0

            logger.debug(f"CFG impact nodes: {node_count}")
            return node_count

        except ImportError:
            logger.warning("CFG Builder not available, using fallback")
            return self._fallback_impact_nodes(file_path)

        except Exception as e:
            logger.error(f"Failed to count impact nodes: {e}")
            return 0

    # ======================================================================
    # Fallback Methods (radon 없을 때)
    # ======================================================================

    def _fallback_cyclomatic(self, code: str) -> float:
        """
        Radon 없을 때 간단한 추정

        if/for/while/except 개수 기반
        """
        keywords = ["if ", "for ", "while ", "except ", "elif "]
        count = sum(code.count(kw) for kw in keywords)
        return float(count + 1)  # Base complexity = 1

    def _fallback_cognitive(self, code: str) -> float:
        """
        Radon 없을 때 간단한 추정

        중첩 깊이 기반
        """
        lines = code.split("\n")
        max_indent = 0

        for line in lines:
            if line.strip():
                indent = len(line) - len(line.lstrip())
                max_indent = max(max_indent, indent)

        return float(max_indent / 4)  # 4 spaces = 1 level

    def _fallback_impact_nodes(self, file_path: str) -> int:
        """
        CFG Builder 없을 때 간단한 추정

        함수/클래스 개수 기반
        """
        try:
            path = Path(file_path)
            if not path.exists():
                return 0

            code = path.read_text()

            # def/class 개수
            def_count = code.count("def ")
            class_count = code.count("class ")

            return def_count + class_count * 3  # 클래스 가중치

        except Exception:
            return 0
