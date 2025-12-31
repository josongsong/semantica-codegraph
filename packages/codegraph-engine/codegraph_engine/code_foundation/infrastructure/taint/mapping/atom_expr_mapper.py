"""
Atom-Expression Mapper

Maps detected atoms to IR expressions for QueryEngine.

Architecture: Bridge Pattern / Resolution Phase (SOTA)
- Atom ID (정적, Policy): "input.builtin"
- Expression ID (동적, Runtime): "expr::/path:line:col:N"
- Mapping (일회용, Transient): atom.id → expr.id

Critical Requirements:
- Column-based precision (한 줄에 여러 call 처리)
- Fuzzy matching (Contains 관계)
- 1:N mapping support
- Unmapped atom logging
"""

from dataclasses import dataclass
from typing import TYPE_CHECKING

from codegraph_shared.common.observability import get_logger

if TYPE_CHECKING:
    from codegraph_engine.code_foundation.domain.taint.models import DetectedAtom
    from codegraph_engine.code_foundation.infrastructure.ir.models import IRDocument
    from codegraph_engine.code_foundation.infrastructure.ir.models.core import Span
    from codegraph_engine.code_foundation.infrastructure.semantic_ir.expression.models import Expression

logger = get_logger(__name__)


@dataclass
class AtomExprMap:
    """
    Mapping from Atom ID to Expression IDs.

    Attributes:
        mapping: atom_id → list[expr_id] (1:N 지원)
        unmapped_atoms: 매핑 실패한 atom IDs (디버깅용)
        stats: 매핑 통계
    """

    mapping: dict[str, list[str]]
    unmapped_atoms: list[str]
    stats: dict[str, int]


class AtomExprMapper:
    """
    Atom-Expression Mapper (Bridge Pattern)

    Maps detected atoms to IR expressions using:
    1. Line matching (fast filter)
    2. Column overlap (precision)
    3. Name matching (semantic)
    4. Distance-based tiebreak

    Example:
        ```python
        mapper = AtomExprMapper()
        atom_map = mapper.map_atoms(ir_doc, detected_atoms)

        # Use in QueryEngine
        expr_ids = atom_map.mapping["input.builtin"]
        # → ["expr::/path:4:17:6"]
        ```
    """

    def __init__(self):
        """Initialize mapper"""
        self._stats = {
            "atoms_mapped": 0,
            "atoms_unmapped": 0,
            "expressions_indexed": 0,
        }

    def map_atoms(
        self,
        ir_doc: "IRDocument",
        detected_atoms: list["DetectedAtom"],
    ) -> AtomExprMap:
        """
        Map detected atoms to IR expressions.

        Args:
            ir_doc: IR document with expressions
            detected_atoms: Detected atoms (sources, sinks, sanitizers)

        Returns:
            AtomExprMap with mapping

        Algorithm:
        1. Build line index (file:line → expressions)
        2. For each atom, find candidate expressions
        3. Best match using: Column overlap > Name > Distance
        4. Log unmapped atoms
        """
        logger.debug("atom_expr_mapping_started", atoms=len(detected_atoms))

        # Step 1: Build line index
        expr_index = self._build_line_index(ir_doc)
        self._stats["expressions_indexed"] = sum(len(exprs) for exprs in expr_index.values())

        # Step 2: Map each atom
        mapping: dict[str, list[str]] = {}
        unmapped: list[str] = []

        for atom in detected_atoms:
            expr_ids = self._find_matching_expressions(atom, expr_index, ir_doc)

            if expr_ids:
                mapping[atom.atom_id] = expr_ids
                self._stats["atoms_mapped"] += 1
                logger.debug("atom_mapped", atom_id=atom.atom_id, expr_count=len(expr_ids))
            else:
                unmapped.append(atom.atom_id)
                self._stats["atoms_unmapped"] += 1
                logger.warning("atom_unmapped", atom_id=atom.atom_id, location=atom.location)

        # Step 3: Build result
        atom_map = AtomExprMap(
            mapping=mapping,
            unmapped_atoms=unmapped,
            stats=self._stats.copy(),
        )

        logger.info(
            "atom_expr_mapping_complete",
            mapped=self._stats["atoms_mapped"],
            unmapped=self._stats["atoms_unmapped"],
        )

        return atom_map

    def _build_line_index(
        self,
        ir_doc: "IRDocument",
    ) -> dict[tuple[str, int], list["Expression"]]:
        """
        Build index: (file_path, line_no) → expressions

        Performance: O(N) where N = expressions
        """
        index: dict[tuple[str, int], list] = {}

        for expr in ir_doc.expressions:
            if expr.span:
                key = (expr.file_path, expr.span.start_line)
                if key not in index:
                    index[key] = []
                index[key].append(expr)

        return index

    def _find_matching_expressions(
        self,
        atom: "DetectedAtom",
        expr_index: dict[tuple[str, int], list["Expression"]],
        ir_doc: "IRDocument",
    ) -> list[str]:
        """
        Find best matching expressions for atom.

        Args:
            atom: Detected atom
            expr_index: Line index
            ir_doc: IR document

        Returns:
            List of matched expression IDs

        Algorithm:
        1. Get candidates from same line
        2. Filter by column overlap (span intersection)
        3. Score by: Name match > Distance
        4. Return best match(es)
        """
        # Parse location: "file.py:line:col"
        file_path, line_no, col_no = self._parse_location(atom.location)
        if file_path is None or line_no is None:
            return []

        # Get candidates from same line
        key = (file_path, line_no)
        candidates = expr_index.get(key, [])

        if not candidates:
            # Try nearby lines (±1)
            nearby_exprs = []
            for delta in [-1, 0, 1]:
                nearby_key = (file_path, line_no + delta)
                nearby_exprs.extend(expr_index.get(nearby_key, []))
            candidates = nearby_exprs

        if not candidates:
            return []

        # Find best match
        best_matches: list[tuple["Expression", float]] = []

        for expr in candidates:
            if not expr.span:
                continue

            # Calculate match score
            score = self._calculate_match_score(atom, expr, col_no)

            if score > 0:
                best_matches.append((expr, score))

        # Sort by score (highest first)
        best_matches.sort(key=lambda x: x[1], reverse=True)

        # Return top matches (threshold: score > 0.5)
        matched_exprs = [expr for expr, score in best_matches if score > 0.5]

        # Return IDs
        return [expr.id for expr in matched_exprs[:3]]  # Max 3 matches

    def _calculate_match_score(
        self,
        atom: "DetectedAtom",
        expr: "Expression",
        atom_col: int | None,
    ) -> float:
        """
        Calculate match score (0.0-1.0)

        Factors:
        1. Name match (highest priority, 60%)
        2. Column overlap (30%)
        3. Distance (10% tiebreaker)

        Returns:
            0.0 = no match
            1.0 = perfect match
        """
        score = 0.0

        # Factor 1: Name match (60% - most important!)
        atom_name = self._extract_call_name(atom)
        expr_name = expr.attrs.get("callee_name", "")

        if atom_name and expr_name:
            # Exact match or last part match
            if atom_name == expr_name or expr_name.endswith(f".{atom_name}"):
                score += 0.6
            elif atom_name in expr_name or expr_name in atom_name:
                score += 0.3  # Partial match

        # Factor 2: Column overlap (30%)
        if atom_col is not None and atom_col > 0 and expr.span:
            if expr.span.start_col <= atom_col <= expr.span.end_col:
                score += 0.3  # Exact overlap
            elif abs(expr.span.start_col - atom_col) <= 2:
                score += 0.15  # Near miss (±2)
        elif atom_col == 0:
            # col=0 means "whole line" - give some base score
            score += 0.1

        # Factor 3: Distance (10% tiebreaker)
        if atom_col is not None and atom_col > 0 and expr.span:
            distance = abs(expr.span.start_col - atom_col)
            if distance == 0:
                score += 0.1
            elif distance <= 5:
                score += 0.05

        return min(score, 1.0)

    def _parse_location(self, location: str) -> tuple[str | None, int | None, int | None]:
        """
        Parse location string.

        Format: "file.py:line:col" or "file.py:line"

        Returns:
            (file_path, line_no, col_no)
        """
        try:
            parts = location.split(":")
            if len(parts) >= 2:
                file_path = parts[0]
                line_no = int(parts[1])
                col_no = int(parts[2]) if len(parts) >= 3 else None
                return (file_path, line_no, col_no)
        except (ValueError, IndexError):
            pass

        return (None, None, None)

    def _extract_call_name(self, atom: "DetectedAtom") -> str | None:
        """
        Extract call name from atom.

        Heuristic:
        - Use match_rule.call if available
        - Extract from atom_id (last part)
        """
        # Try match_rule
        if hasattr(atom, "match_rule") and atom.match_rule:
            if hasattr(atom.match_rule, "call") and atom.match_rule.call:
                return atom.match_rule.call

        # Fallback: Extract from atom_id
        # "input.builtin" → "input"
        # "sink.sql.sqlite3" → "sqlite3" or "execute"
        atom_id = atom.atom_id

        # Known patterns
        if "input" in atom_id:
            return "input"
        if "execute" in atom_id:
            return "execute"
        if "system" in atom_id:
            return "system"

        # Generic: last part
        if "." in atom_id:
            parts = atom_id.split(".")
            # Try last meaningful part
            for part in reversed(parts):
                if part and not part.isdigit():
                    return part

        return atom_id

    def _is_span_overlap(self, span1: "Span", span2: "Span") -> bool:
        """
        Check if two spans overlap.

        Args:
            span1: First span (atom or expression)
            span2: Second span

        Returns:
            True if spans overlap
        """
        if not span1 or not span2:
            return False

        # Line overlap check
        if span1.end_line < span2.start_line or span2.end_line < span1.start_line:
            return False

        # Same line: check column overlap
        if span1.start_line == span1.end_line == span2.start_line == span2.end_line:
            if span1.end_col < span2.start_col or span2.end_col < span1.start_col:
                return False

        return True

    def get_stats(self) -> dict[str, int]:
        """Get mapping statistics"""
        return self._stats.copy()
