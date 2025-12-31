"""
IRProvider Adapter - Hexagonal Architecture Compliant

Domain에서 정의한 IRProvider Protocol의 실제 구현체.
IRDocument를 래핑하여 CFG/DFG 접근 제공.

Architecture:
- Domain: IRProvider (Protocol in semantic_sanitizer_detector.py)
- Infrastructure: IRProviderAdapter (this file)

Supports both:
- Domain IRDocument (symbols field) - DEPRECATED
- Infrastructure IRDocument (nodes field) - PREFERRED
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

if TYPE_CHECKING:
    from codegraph_engine.code_foundation.domain.models import Symbol

logger = logging.getLogger(__name__)


@runtime_checkable
class IRDocumentLike(Protocol):
    """Duck-typed IRDocument protocol for transition period"""

    pass  # Accept any object, we'll check attributes dynamically


class IRProviderAdapter:
    """
    IRProvider protocol의 실제 구현체

    IRDocument를 래핑하여 CFG/DFG 접근 인터페이스 제공.

    Supports:
    - Infrastructure IRDocument (nodes) - PREFERRED
    - Domain IRDocument (symbols) - DEPRECATED, will be removed
    """

    def __init__(self, ir_document: Any):
        """
        Args:
            ir_document: IR 문서 (Infrastructure 또는 Domain)
        """
        self.ir_document = ir_document

        # CFG/DFG 캐시 (필요시 lazy 생성)
        self._cfg_cache: dict[str, Any] = {}
        self._dfg_cache: dict[str, Any] = {}
        self._signature_cache: dict[str, dict[str, Any]] = {}

    def _get_nodes_or_symbols(self) -> list[Any]:
        """Get nodes (preferred) or symbols (deprecated) from IR document.

        Type Detection:
        - Infrastructure: has 'repo_id' + 'nodes' field
        - Domain: has 'symbols' field (DEPRECATED)
        """
        # Infrastructure IRDocument: repo_id + nodes
        if hasattr(self.ir_document, "repo_id") and hasattr(self.ir_document, "nodes"):
            return self.ir_document.nodes
        # Domain IRDocument: symbols (DEPRECATED)
        if hasattr(self.ir_document, "symbols"):
            return self.ir_document.symbols
        return []

    def _get_body_from_item(self, item: Any) -> str:
        """Extract body from Node or Symbol"""
        # Infrastructure Node: attrs dict
        if hasattr(item, "attrs"):
            attrs = item.attrs
            if isinstance(attrs, dict):
                return attrs.get("body", "")
        # Domain Symbol: metadata dict (DEPRECATED)
        if hasattr(item, "metadata"):
            metadata = item.metadata
            if isinstance(metadata, dict):
                return metadata.get("body", "")
        return ""

    def get_function_cfg(self, function_id: str) -> Any:
        """
        Get control flow graph for function

        Args:
            function_id: 함수 식별자 (예: "function:path:module.func_name")

        Returns:
            CFG 객체 또는 None
        """
        if function_id in self._cfg_cache:
            return self._cfg_cache[function_id]

        # function_id에서 함수명 추출
        func_name = self._extract_function_name(function_id)
        if not func_name:
            logger.debug(f"Cannot extract function name from {function_id}")
            return None

        # IRDocument에서 함수 symbol 찾기
        symbol = self._find_function_symbol(func_name)
        if not symbol:
            logger.debug(f"Function not found: {func_name}")
            return None

        # CFG 생성 (여기서는 symbol의 metadata에서 body 추출)
        cfg = self._build_cfg_from_symbol(symbol)
        self._cfg_cache[function_id] = cfg

        return cfg

    def get_function_dfg(self, function_id: str) -> Any:
        """
        Get data flow graph for function

        Args:
            function_id: 함수 식별자

        Returns:
            DFG 객체 또는 None
        """
        if function_id in self._dfg_cache:
            return self._dfg_cache[function_id]

        func_name = self._extract_function_name(function_id)
        if not func_name:
            return None

        symbol = self._find_function_symbol(func_name)
        if not symbol:
            return None

        # DFG 생성
        dfg = self._build_dfg_from_symbol(symbol)
        self._dfg_cache[function_id] = dfg

        return dfg

    def get_function_signature(self, function_id: str) -> Any:
        """
        Get function signature (params, return type)

        Args:
            function_id: 함수 식별자

        Returns:
            Signature dict {"params": [...], "return_type": "..."}
        """
        if function_id in self._signature_cache:
            return self._signature_cache[function_id]

        func_name = self._extract_function_name(function_id)
        if not func_name:
            return None

        symbol = self._find_function_symbol(func_name)
        if not symbol:
            return None

        # Signature 추출
        signature = self._extract_signature_from_symbol(symbol)
        self._signature_cache[function_id] = signature

        return signature

    def _extract_function_name(self, function_id: str) -> str:
        """
        function_id에서 함수명 추출

        Args:
            function_id: "function:path:module.func_name" 형식

        Returns:
            함수명 (예: "func_name")
        """
        if not function_id:
            return ""

        # function:path:module.func_name에서 func_name 추출
        parts = function_id.split(":")
        if len(parts) >= 2:
            name = parts[-1]
            if "." in name:
                return name.split(".")[-1]
            return name

        return function_id

    def _find_function_symbol(self, func_name: str) -> Symbol | Any | None:
        """
        IRDocument에서 함수 symbol/node 찾기

        Supports:
        - Infrastructure IRDocument (nodes with kind)
        - Domain IRDocument (symbols with type) - DEPRECATED

        Args:
            func_name: 함수명

        Returns:
            Symbol/Node 또는 None
        """
        for item in self._get_nodes_or_symbols():
            # Infrastructure Node: has 'kind' attribute
            if hasattr(item, "kind"):
                kind = item.kind
                # Handle both string and enum kinds
                kind_str = kind.value if hasattr(kind, "value") else str(kind)
                if kind_str.upper() in ("FUNCTION", "METHOD") and getattr(item, "name", "") == func_name:
                    return item
            # Domain Symbol: has 'type' attribute (DEPRECATED)
            elif hasattr(item, "type"):
                if item.type == "function" and item.name == func_name:
                    return item

        return None

    def _build_cfg_from_symbol(self, symbol: Any) -> dict[str, Any]:
        """
        Symbol/Node로부터 CFG 구축

        간단한 구현: body의 각 statement를 노드로, 순차 실행을 엣지로.

        Supports:
        - Infrastructure Node (attrs.body or attrs["body"])
        - Domain Symbol (metadata.body) - DEPRECATED

        Args:
            symbol: 함수 symbol/node

        Returns:
            CFG dict {"nodes": [...], "edges": [...]}
        """
        # Extract body from symbol/node
        body = self._get_body_from_item(symbol)
        if not body or not isinstance(body, str):
            return {"nodes": [], "edges": []}

        # 간단한 파싱: 줄 단위로 노드 생성
        lines = body.split("\n")
        nodes = []
        edges = []

        for i, line in enumerate(lines):
            line_stripped = line.strip()
            if not line_stripped or line_stripped.startswith("#"):
                continue

            node_id = f"node_{i}"
            nodes.append(
                {
                    "id": node_id,
                    "statement": line_stripped,
                    "line": i,
                }
            )

            # 순차 엣지
            if i > 0 and nodes:
                prev_id = f"node_{i - 1}"
                edges.append({"from": prev_id, "to": node_id})

        return {
            "nodes": nodes,
            "edges": edges,
            "entry": "node_0" if nodes else None,
        }

    def _build_dfg_from_symbol(self, symbol: Any) -> dict[str, Any]:
        """
        Symbol/Node로부터 DFG 구축

        간단한 구현: 변수 정의-사용 관계 추적.

        Supports:
        - Infrastructure Node (attrs.body)
        - Domain Symbol (metadata.body) - DEPRECATED

        Args:
            symbol: 함수 symbol/node

        Returns:
            DFG dict {"nodes": [...], "edges": [...]}
        """
        body = self._get_body_from_item(symbol)
        if not body or not isinstance(body, str):
            return {"nodes": [], "edges": [], "params": [], "returns": []}

        lines = body.split("\n")
        nodes = []
        edges = []
        variables = {}  # var_name -> node_id (마지막 정의 위치)
        params = []
        returns = []

        for i, line in enumerate(lines):
            line_stripped = line.strip()
            if not line_stripped or line_stripped.startswith("#"):
                continue

            node_id = f"dfg_node_{i}"
            nodes.append(
                {
                    "id": node_id,
                    "statement": line_stripped,
                    "line": i,
                }
            )

            # 간단한 패턴 매칭
            # 변수 할당: x = ...
            if "=" in line_stripped and not line_stripped.startswith("return"):
                parts = line_stripped.split("=", 1)
                if len(parts) == 2:
                    var_name = parts[0].strip()
                    rhs = parts[1].strip()

                    # 정의
                    variables[var_name] = node_id

                    # RHS에서 사용된 변수 찾기 (간단한 휴리스틱)
                    for var in variables:
                        if var in rhs:
                            # 데이터 플로우 엣지
                            edges.append(
                                {
                                    "from": variables[var],
                                    "to": node_id,
                                    "var": var,
                                }
                            )

            # return 문
            if line_stripped.startswith("return"):
                returns.append(node_id)
                # return 문에서 사용된 변수
                return_expr = line_stripped.replace("return", "").strip()
                for var in variables:
                    if var in return_expr:
                        edges.append(
                            {
                                "from": variables[var],
                                "to": node_id,
                                "var": var,
                            }
                        )

        # 파라미터 추출 (symbol metadata/attrs에서)
        meta = self._get_metadata_or_attrs(symbol)
        if "params" in meta:
            params = meta["params"]

        return {
            "nodes": nodes,
            "edges": edges,
            "params": params,
            "returns": returns,
        }

    def _get_metadata_or_attrs(self, item: Any) -> dict:
        """Get metadata (Domain Symbol) or attrs (Infrastructure Node)"""
        if hasattr(item, "attrs") and isinstance(item.attrs, dict):
            return item.attrs
        if hasattr(item, "metadata") and isinstance(item.metadata, dict):
            return item.metadata
        return {}

    def _extract_signature_from_symbol(self, symbol: Any) -> dict[str, Any]:
        """
        Symbol/Node로부터 함수 signature 추출

        Supports:
        - Infrastructure Node (attrs)
        - Domain Symbol (metadata) - DEPRECATED

        Args:
            symbol: 함수 symbol/node

        Returns:
            {"params": [...], "return_type": "..."}
        """
        meta = self._get_metadata_or_attrs(symbol)
        params = meta.get("params", [])
        return_type = meta.get("return_type", "Any")

        return {
            "params": params if isinstance(params, list) else [],
            "return_type": return_type,
        }
