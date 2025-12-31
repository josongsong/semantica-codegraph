"""
Document-Code Linker

Links document code blocks and references to actual code symbols.
Creates REFERENCES_CODE edges for ADVANCED/SOTA profiles.
"""

import re
from dataclasses import dataclass

from codegraph_engine.code_foundation.infrastructure.document.chunker import DocumentChunk
from codegraph_engine.code_foundation.infrastructure.document.profile import DocIndexProfile
from codegraph_engine.code_foundation.infrastructure.ir.models.document import IRDocument


@dataclass
class CodeReference:
    """
    A reference from document to code.

    Attributes:
        doc_chunk_id: Document chunk ID
        symbol_name: Referenced symbol name (function/class/variable)
        symbol_type: Type of symbol (function, class, variable, import)
        context: Surrounding context (e.g., code snippet)
        confidence: Confidence score (0.0-1.0)
    """

    doc_chunk_id: str
    symbol_name: str
    symbol_type: str  # function, class, variable, import
    context: str
    confidence: float = 1.0


@dataclass
class CodeLink:
    """
    A resolved link from document chunk to IR node/symbol.

    Attributes:
        doc_chunk_id: Document chunk ID
        target_node_id: Target IR Node ID
        target_symbol_id: Target Symbol ID (if available)
        reference_type: Type of reference
        confidence: Link confidence (0.0-1.0)
    """

    doc_chunk_id: str
    target_node_id: str
    target_symbol_id: str | None
    reference_type: str  # code_example, api_reference, import_reference
    confidence: float


class DocumentCodeLinker:
    """
    Links document chunks to code symbols.

    Extracts code references from documents and resolves them to actual
    IR nodes and symbols.
    """

    def __init__(self, profile: DocIndexProfile):
        """
        Initialize linker.

        Args:
            profile: Document indexing profile
        """
        self.profile = profile
        self.should_link = profile in [DocIndexProfile.ADVANCED, DocIndexProfile.SOTA]

    def extract_code_references(self, doc_chunks: list[DocumentChunk]) -> list[CodeReference]:
        """
        Extract code references from document chunks.

        Args:
            doc_chunks: List of document chunks

        Returns:
            List of code references found
        """
        if not self.should_link:
            return []

        references: list[CodeReference] = []

        for chunk in doc_chunks:
            chunk_id = self._generate_chunk_id(chunk)

            # Extract from code blocks
            if chunk.is_code_block():
                refs = self._extract_from_code_block(chunk_id, chunk)
                references.extend(refs)

            # Extract from text (inline code, signatures)
            else:
                refs = self._extract_from_text(chunk_id, chunk)
                references.extend(refs)

        return references

    def resolve_links(self, references: list[CodeReference], ir_doc: IRDocument) -> list[CodeLink]:
        """
        Resolve code references to actual IR nodes/symbols.

        Args:
            references: List of code references
            ir_doc: IR document with nodes and symbols

        Returns:
            List of resolved code links
        """
        if not self.should_link:
            return []

        # Build symbol lookup index
        symbol_index = self._build_symbol_index(ir_doc)

        links: list[CodeLink] = []

        for ref in references:
            # Try to find matching symbol
            matches = self._find_symbol_matches(ref.symbol_name, symbol_index)

            for match in matches:
                link = CodeLink(
                    doc_chunk_id=ref.doc_chunk_id,
                    target_node_id=match["node_id"],
                    target_symbol_id=match.get("symbol_id"),
                    reference_type=self._classify_reference_type(ref),
                    confidence=ref.confidence * match["score"],
                )
                links.append(link)

        return links

    def create_graph_edges(self, links: list[CodeLink]) -> list[dict]:
        """
        Create graph edges from resolved links.

        Args:
            links: List of resolved code links

        Returns:
            List of edge dictionaries for graph
        """
        edges = []

        for link in links:
            if link.confidence < 0.3:  # Skip low-confidence links
                continue

            edge = {
                "edge_type": "REFERENCES_CODE",
                "source_id": link.doc_chunk_id,  # Document chunk
                "target_id": link.target_node_id,  # Code node
                "metadata": {
                    "reference_type": link.reference_type,
                    "confidence": link.confidence,
                    "symbol_id": link.target_symbol_id,
                },
            }
            edges.append(edge)

        return edges

    def _extract_from_code_block(self, chunk_id: str, chunk: DocumentChunk) -> list[CodeReference]:
        """Extract references from code block."""
        references: list[CodeReference] = []

        if not chunk.code_language or not chunk.content:
            return references

        lang = chunk.code_language.lower()

        # Python
        if lang in ["python", "py"]:
            references.extend(self._extract_python_symbols(chunk_id, chunk.content))

        # TypeScript/JavaScript
        elif lang in ["typescript", "ts", "javascript", "js", "tsx", "jsx"]:
            references.extend(self._extract_js_symbols(chunk_id, chunk.content))

        return references

    def _extract_from_text(self, chunk_id: str, chunk: DocumentChunk) -> list[CodeReference]:
        """Extract references from text (inline code, signatures)."""
        references: list[CodeReference] = []

        if not chunk.content:
            return references

        # Extract inline code: `functionName()`
        inline_code_pattern = r"`([a-zA-Z_][a-zA-Z0-9_]*(?:\.[a-zA-Z_][a-zA-Z0-9_]*)*)`"
        matches = re.findall(inline_code_pattern, chunk.content)

        for match in matches:
            # Check if it looks like a function/method call
            if "(" in chunk.content[chunk.content.find(f"`{match}`") :]:
                symbol_type = "function"
            else:
                symbol_type = "variable"

            references.append(
                CodeReference(
                    doc_chunk_id=chunk_id,
                    symbol_name=match,
                    symbol_type=symbol_type,
                    context=self._extract_context(chunk.content, match),
                    confidence=0.7,  # Lower confidence for inline refs
                )
            )

        return references

    def _extract_python_symbols(self, chunk_id: str, code: str) -> list[CodeReference]:
        """Extract Python function/class definitions and calls."""
        references: list[CodeReference] = []

        # Function definitions: def foo(...)
        func_defs = re.findall(r"\bdef\s+([a-zA-Z_][a-zA-Z0-9_]*)\s*\(", code)
        for name in func_defs:
            references.append(
                CodeReference(
                    doc_chunk_id=chunk_id,
                    symbol_name=name,
                    symbol_type="function",
                    context=self._extract_context(code, name),
                    confidence=0.9,
                )
            )

        # Class definitions: class Foo
        class_defs = re.findall(r"\bclass\s+([a-zA-Z_][a-zA-Z0-9_]*)\s*[:\(]", code)
        for name in class_defs:
            references.append(
                CodeReference(
                    doc_chunk_id=chunk_id,
                    symbol_name=name,
                    symbol_type="class",
                    context=self._extract_context(code, name),
                    confidence=0.9,
                )
            )

        # Imports: from foo import bar
        import_matches = re.findall(r"\bfrom\s+([a-zA-Z_][a-zA-Z0-9_.]*)\s+import", code)
        for name in import_matches:
            references.append(
                CodeReference(
                    doc_chunk_id=chunk_id,
                    symbol_name=name,
                    symbol_type="import",
                    context=self._extract_context(code, name),
                    confidence=0.8,
                )
            )

        return references

    def _extract_js_symbols(self, chunk_id: str, code: str) -> list[CodeReference]:
        """Extract JavaScript/TypeScript function/class definitions."""
        references: list[CodeReference] = []

        # Function declarations: function foo()
        func_defs = re.findall(r"\bfunction\s+([a-zA-Z_][a-zA-Z0-9_]*)\s*\(", code)
        for name in func_defs:
            references.append(
                CodeReference(
                    doc_chunk_id=chunk_id,
                    symbol_name=name,
                    symbol_type="function",
                    context=self._extract_context(code, name),
                    confidence=0.9,
                )
            )

        # Arrow functions: const foo = () =>
        arrow_funcs = re.findall(r"\bconst\s+([a-zA-Z_][a-zA-Z0-9_]*)\s*=\s*\(", code)
        for name in arrow_funcs:
            references.append(
                CodeReference(
                    doc_chunk_id=chunk_id,
                    symbol_name=name,
                    symbol_type="function",
                    context=self._extract_context(code, name),
                    confidence=0.9,
                )
            )

        # Class definitions: class Foo
        class_defs = re.findall(r"\bclass\s+([a-zA-Z_][a-zA-Z0-9_]*)\s*[{]", code)
        for name in class_defs:
            references.append(
                CodeReference(
                    doc_chunk_id=chunk_id,
                    symbol_name=name,
                    symbol_type="class",
                    context=self._extract_context(code, name),
                    confidence=0.9,
                )
            )

        return references

    def _build_symbol_index(self, ir_doc: IRDocument) -> dict:
        """
        Build lookup index from IR document.

        Returns:
            Dictionary mapping symbol names to node IDs
        """
        from codegraph_engine.code_foundation.infrastructure.ir.models.core import NodeKind

        index: dict[str, list[dict]] = {}

        for node in ir_doc.nodes:
            # Check if node is a symbol (function, class, method, variable)
            if node.kind in [
                NodeKind.FUNCTION,
                NodeKind.METHOD,
                NodeKind.CLASS,
                NodeKind.VARIABLE,
                NodeKind.FIELD,
            ]:
                name = node.name

                if name not in index:
                    index[name] = []

                index[name].append(
                    {
                        "node_id": node.id,
                        "symbol_id": node.attrs.get("symbol_id"),
                        "kind": node.kind.value,  # Convert Enum to string
                        "fqn": node.fqn,
                    }
                )

        return index

    def _find_symbol_matches(self, symbol_name: str, symbol_index: dict) -> list[dict]:
        """
        Find matching symbols in index.

        Args:
            symbol_name: Symbol name to find
            symbol_index: Symbol lookup index

        Returns:
            List of matches with scores
        """
        matches: list[dict] = []

        # Exact match
        if symbol_name in symbol_index:
            for entry in symbol_index[symbol_name]:
                matches.append({**entry, "score": 1.0})

        # Fuzzy match (e.g., module.function)
        if "." in symbol_name:
            parts = symbol_name.split(".")
            last_part = parts[-1]

            if last_part in symbol_index:
                for entry in symbol_index[last_part]:
                    # Check if FQN contains the full path
                    if symbol_name in entry["fqn"]:
                        matches.append({**entry, "score": 0.9})
                    else:
                        matches.append({**entry, "score": 0.6})

        return matches

    def _classify_reference_type(self, ref: CodeReference) -> str:
        """Classify reference type based on symbol type and context."""
        if ref.symbol_type == "import":
            return "import_reference"
        elif ref.symbol_type in ["function", "class"]:
            return "api_reference"
        else:
            return "code_example"

    def _extract_context(self, content: str, symbol: str, max_length: int = 100) -> str:
        """Extract surrounding context for a symbol."""
        idx = content.find(symbol)
        if idx == -1:
            return ""

        start = max(0, idx - 50)
        end = min(len(content), idx + 50)
        context = content[start:end].strip()

        if len(context) > max_length:
            context = context[:max_length] + "..."

        return context

    def _generate_chunk_id(self, chunk: DocumentChunk) -> str:
        """Generate chunk ID for document chunk."""
        file_path_safe = chunk.file_path.replace("/", "_").replace(".", "_")
        return f"doc:{file_path_safe}:{chunk.line_start}-{chunk.line_end}"
