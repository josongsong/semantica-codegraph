"""
Enhanced Mock Indexes with Real AST Parsing

Phase 1 Quick Win: Improve mock symbol index using tree-sitter
to properly parse Python files and build a real symbol table.

This should improve Symbol/Definition queries from 40% → 70%+ precision.
"""

import ast
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class Symbol:
    """A symbol in the codebase."""

    name: str
    kind: str  # "class", "function", "method", "variable", "import"
    file_path: str
    line_number: int
    parent: str | None = None  # For methods, parent class name
    docstring: str | None = None
    is_public: bool = True


class EnhancedMockSymbolIndex:
    """
    Enhanced symbol index using real AST parsing.

    Improvements over basic mock:
    - Actual Python AST parsing (not keyword matching)
    - Symbol table with classes, functions, methods
    - Inheritance tracking
    - Import resolution
    - Public/private distinction
    """

    def __init__(self, src_dir: Path):
        self.src_dir = src_dir
        self.files = list(src_dir.rglob("*.py"))
        self.symbols: dict[str, list[Symbol]] = defaultdict(list)
        self.inheritance: dict[str, list[str]] = defaultdict(list)  # class -> base classes
        self.implementations: dict[str, list[str]] = defaultdict(list)  # interface -> implementations

        # Build symbol table
        self._build_symbol_table()

    def _build_symbol_table(self):
        """Parse all Python files and build symbol table."""
        for file_path in self.files:
            try:
                self._parse_file(file_path)
            except Exception as e:
                # Skip files that fail to parse
                pass

    def _parse_file(self, file_path: Path):
        """Parse a single Python file and extract symbols."""
        try:
            content = file_path.read_text()
            tree = ast.parse(content)
        except Exception:
            return

        rel_path = str(file_path.relative_to(self.src_dir))

        # Visit AST nodes
        for node in ast.walk(tree):
            # Class definitions
            if isinstance(node, ast.ClassDef):
                symbol = Symbol(
                    name=node.name,
                    kind="class",
                    file_path=rel_path,
                    line_number=node.lineno,
                    docstring=ast.get_docstring(node),
                    is_public=not node.name.startswith("_"),
                )
                self.symbols[node.name.lower()].append(symbol)

                # Track inheritance
                for base in node.bases:
                    if isinstance(base, ast.Name):
                        self.inheritance[node.name].append(base.id)
                        self.implementations[base.id].append(node.name)

                # Methods
                for item in node.body:
                    if isinstance(item, ast.FunctionDef):
                        method_symbol = Symbol(
                            name=item.name,
                            kind="method",
                            file_path=rel_path,
                            line_number=item.lineno,
                            parent=node.name,
                            docstring=ast.get_docstring(item),
                            is_public=not item.name.startswith("_"),
                        )
                        # Index by full name: ClassName.method_name
                        full_name = f"{node.name}.{item.name}"
                        self.symbols[full_name.lower()].append(method_symbol)
                        self.symbols[item.name.lower()].append(method_symbol)

            # Top-level functions
            elif isinstance(node, ast.FunctionDef):
                # Check if this is a method (inside a class) or top-level
                # We already handled methods above, so skip those
                is_method = any(
                    isinstance(parent, ast.ClassDef)
                    for parent in ast.walk(tree)
                    if hasattr(parent, "body") and node in getattr(parent, "body", [])
                )

                if not is_method:
                    symbol = Symbol(
                        name=node.name,
                        kind="function",
                        file_path=rel_path,
                        line_number=node.lineno,
                        docstring=ast.get_docstring(node),
                        is_public=not node.name.startswith("_"),
                    )
                    self.symbols[node.name.lower()].append(symbol)

            # Imports
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    symbol = Symbol(
                        name=alias.name,
                        kind="import",
                        file_path=rel_path,
                        line_number=node.lineno,
                        is_public=True,
                    )
                    self.symbols[alias.name.lower()].append(symbol)

            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    for alias in node.names:
                        symbol = Symbol(
                            name=alias.name,
                            kind="import",
                            file_path=rel_path,
                            line_number=node.lineno,
                            parent=node.module,
                            is_public=True,
                        )
                        self.symbols[alias.name.lower()].append(symbol)

    async def search(self, query: str, limit: int = 50) -> list[dict[str, Any]]:
        """
        Search for symbols matching the query.

        Hybrid approach (file-level + symbol-level):
        - Symbol-level matching
        - File-level aggregation (boost files with matching symbols)
        - Path matching (for context)
        """
        query_lower = query.lower()
        keywords = query_lower.split()

        # Phase 1: Symbol-level scoring
        file_scores = {}  # file_path -> (best_symbol, max_score, match_count)

        for name, symbol_list in self.symbols.items():
            for symbol in symbol_list:
                score = 0.0

                # Exact name match (highest score)
                if name == query_lower:
                    score = 1.0
                # Query is full name match (e.g., "Chunk class")
                elif all(kw in symbol.name.lower() or kw in symbol.kind for kw in keywords):
                    score = 0.95
                # Partial name match
                elif any(kw in symbol.name.lower() for kw in keywords):
                    score = 0.85
                # Docstring match
                elif symbol.docstring and any(kw in symbol.docstring.lower() for kw in keywords):
                    score = 0.7

                # File path match (contextual boost)
                if any(kw in symbol.file_path.lower() for kw in keywords):
                    score += 0.20  # Additive boost for path match

                # Boost for public symbols
                if symbol.is_public:
                    score *= 1.05

                if score > 0:
                    file_path = symbol.file_path

                    if file_path not in file_scores:
                        file_scores[file_path] = (symbol, score, 1)
                    else:
                        existing_symbol, existing_score, match_count = file_scores[file_path]
                        # Keep best symbol, but aggregate score for multiple matches
                        if score > existing_score:
                            file_scores[file_path] = (symbol, score, match_count + 1)
                        else:
                            # Boost for additional matches in same file
                            boosted_score = existing_score + (score * 0.2)
                            file_scores[file_path] = (existing_symbol, boosted_score, match_count + 1)

        # Phase 2: Add pure file-path matches (files without symbols but matching path)
        for file_path in self.files:
            rel_path = str(file_path.relative_to(self.src_dir))
            if rel_path not in file_scores:
                # Check if path matches query
                path_score = 0.0
                for kw in keywords:
                    if kw in rel_path.lower():
                        path_score += 0.45  # Moderate score for path match

                if path_score > 0:
                    # Create a dummy symbol for file-level match
                    dummy_symbol = Symbol(
                        name="",
                        kind="file",
                        file_path=rel_path,
                        line_number=1,
                    )
                    file_scores[rel_path] = (dummy_symbol, path_score, 0)

        # Convert to results format
        results = []
        for file_path, (symbol, score, match_count) in file_scores.items():
            results.append(
                {
                    "chunk_id": f"chunk:{file_path}:{symbol.line_number}",
                    "file_path": file_path,
                    "score": score,
                    "rank": 0,
                    "metadata": {
                        "symbol_name": symbol.name,
                        "symbol_kind": symbol.kind,
                        "line_number": symbol.line_number,
                        "parent": symbol.parent,
                        "is_public": getattr(symbol, "is_public", True),
                        "match_count": match_count,
                    },
                }
            )

        # Sort by score
        results.sort(key=lambda x: x["score"], reverse=True)

        # Assign ranks
        for rank, result in enumerate(results[:limit]):
            result["rank"] = rank

        return results[:limit]

    def find_implementations(self, interface_name: str) -> list[str]:
        """Find all classes that implement/inherit from an interface."""
        return self.implementations.get(interface_name, [])

    def find_base_classes(self, class_name: str) -> list[str]:
        """Find base classes of a class."""
        return self.inheritance.get(class_name, [])


class EnhancedMockLexicalIndex:
    """
    Enhanced lexical index with better BM25-like scoring.

    Improvements:
    - TF-IDF approximation
    - Better keyword weighting
    - File type prioritization
    """

    def __init__(self, src_dir: Path):
        self.src_dir = src_dir
        self.files = list(src_dir.rglob("*.py"))

        # Calculate document frequencies for IDF
        self.doc_freq: dict[str, int] = defaultdict(int)
        self._build_doc_freq()

    def _build_doc_freq(self):
        """Build document frequency for IDF calculation."""
        for file_path in self.files:
            try:
                content = file_path.read_text().lower()
                words = set(content.split())
                for word in words:
                    self.doc_freq[word] += 1
            except Exception:
                pass

    def _idf(self, term: str) -> float:
        """Calculate IDF for a term."""
        import math

        df = self.doc_freq.get(term.lower(), 0)
        if df == 0:
            return 0.0
        return math.log((len(self.files) + 1) / (df + 1))

    async def search(self, query: str, limit: int = 50) -> list[dict[str, Any]]:
        """Search with TF-IDF scoring."""
        results = []
        query_lower = query.lower()
        query_terms = query_lower.split()

        for file_path in self.files:
            rel_path = file_path.relative_to(self.src_dir)
            score = 0.0

            # Path scoring (exact matches in path)
            path_str = str(rel_path).lower()
            for term in query_terms:
                if term in path_str:
                    # Boost if in filename vs directory
                    if term in file_path.name.lower():
                        score += 15.0  # Higher boost for filename
                    else:
                        score += 5.0

            # Content scoring with TF-IDF
            try:
                content = file_path.read_text()
                content_lower = content.lower()

                for term in query_terms:
                    # Term frequency
                    tf = content_lower.count(term)
                    if tf > 0:
                        # IDF
                        idf = self._idf(term)

                        # TF-IDF component
                        tf_idf = tf * idf

                        # Position boost (earlier in file = higher score)
                        first_occurrence = content_lower.find(term)
                        if first_occurrence != -1:
                            position_boost = 1.0 - (first_occurrence / len(content_lower))
                            tf_idf *= 1.0 + position_boost * 0.5

                        score += tf_idf

            except Exception:
                pass

            if score > 0:
                results.append(
                    {
                        "chunk_id": f"chunk:{rel_path}",
                        "file_path": str(rel_path),
                        "score": score,
                        "rank": 0,
                    }
                )

        # Sort by score and assign ranks
        results.sort(key=lambda x: x["score"], reverse=True)
        for rank, result in enumerate(results[:limit]):
            result["rank"] = rank

        return results[:limit]


class EnhancedMockVectorIndex:
    """
    Enhanced vector index with better semantic matching.

    Improvements:
    - Contextual keyword matching (class/function names, docstrings)
    - Co-occurrence scoring
    - Domain-specific keyword weighting
    """

    def __init__(self, src_dir: Path):
        self.src_dir = src_dir
        self.files = list(src_dir.rglob("*.py"))

        # Build keyword index
        self.file_keywords: dict[str, set[str]] = {}
        self._build_keyword_index()

    def _build_keyword_index(self):
        """Build keyword index for each file."""
        for file_path in self.files:
            try:
                content = file_path.read_text()
                tree = ast.parse(content)

                keywords = set()

                # Extract class names
                for node in ast.walk(tree):
                    if isinstance(node, ast.ClassDef):
                        keywords.add(node.name.lower())
                    elif isinstance(node, ast.FunctionDef):
                        keywords.add(node.name.lower())

                # Extract from docstrings
                for node in ast.walk(tree):
                    docstring = ast.get_docstring(node)
                    if docstring:
                        keywords.update(docstring.lower().split())

                rel_path = str(file_path.relative_to(self.src_dir))
                self.file_keywords[rel_path] = keywords

            except Exception:
                pass

    async def search(self, query: str, limit: int = 50) -> list[dict[str, Any]]:
        """Search with semantic matching."""
        results = []
        query_lower = query.lower()
        query_terms = set(query_lower.split())

        for file_path in self.files:
            rel_path = str(file_path.relative_to(self.src_dir))
            score = 0.5  # Base score

            # Keyword overlap (Jaccard similarity)
            file_keywords = self.file_keywords.get(rel_path, set())
            if file_keywords:
                overlap = len(query_terms & file_keywords)
                union = len(query_terms | file_keywords)
                jaccard = overlap / union if union > 0 else 0.0

                score += jaccard * 0.3

            # Contextual matching (e.g., "how to build AST" matches "AST" + "build")
            try:
                content = file_path.read_text().lower()

                # Check for co-occurrence (all terms appear in same context window)
                for term in query_terms:
                    if term in content:
                        score += 0.05

                # Boost if terms appear near each other
                # Simple heuristic: all terms in first 500 chars
                first_500 = content[:500]
                if all(term in first_500 for term in query_terms):
                    score += 0.15

            except Exception:
                pass

            # Normalize to [0.5, 0.95] range
            score = min(0.95, max(0.5, score))

            if score >= 0.5:
                results.append(
                    {
                        "chunk_id": f"chunk:{rel_path}",
                        "file_path": rel_path,
                        "score": score,
                        "rank": 0,
                    }
                )

        # Sort by score and assign ranks
        results.sort(key=lambda x: x["score"], reverse=True)
        for rank, result in enumerate(results[:limit]):
            result["rank"] = rank

        return results[:limit]
