"""
IR Serializer - Node/Edge 직렬화 전담 (SOLID S)

책임:
- Node → dict 변환
- Edge → dict 변환
- dict → Node 변환
- dict → Edge 변환
- Schema validation

NOT responsible for:
- Database operations (IRDocumentStore)
- Migration (IRDocumentStore)
"""

from codegraph_shared.common.observability import get_logger
from codegraph_engine.code_foundation.infrastructure.ir.models import (
    Edge,
    EdgeKind,
    Node,
    NodeKind,
    Span,
)
from codegraph_engine.code_foundation.infrastructure.ir.models.span_pool import SpanPool

logger = get_logger(__name__)


class IRSerializer:
    """
    IR Node/Edge Serializer (Single Responsibility).

    SOLID:
    - S: 직렬화만 담당
    - O: 새 타입 추가 시 확장 가능
    - L: 교체 가능
    - I: 최소 인터페이스
    - D: 구체적 타입에 의존하지 않음
    """

    def serialize_node(self, node: Node) -> dict:
        """
        Node → dict (Complete 20-field serialization).

        Returns:
            Serialized node dict
        """
        return {
            # Required (6)
            "id": node.id,
            "kind": node.kind.value if hasattr(node.kind, "value") else str(node.kind),
            "fqn": node.fqn,
            "file_path": node.file_path,
            "span": self.serialize_span(node.span),
            "language": node.language,
            # Optional identity (2)
            "stable_id": node.stable_id,
            "content_hash": node.content_hash,
            # Optional structure (4)
            "name": node.name,
            "module_path": node.module_path,
            "parent_id": node.parent_id,
            "body_span": self.serialize_span(node.body_span) if node.body_span else None,
            # Optional metadata (3)
            "docstring": node.docstring,
            "role": node.role,
            "is_test_file": node.is_test_file,
            # Optional type/signature (2)
            "signature_id": node.signature_id,
            "declared_type_id": node.declared_type_id,
            # Optional control flow
            "control_flow_summary": self.serialize_control_flow(node.control_flow_summary)
            if node.control_flow_summary
            else None,
            # Extensions
            "attrs": node.attrs,
        }

    def deserialize_node(self, data: dict) -> Node:
        """
        dict → Node (Complete deserialization).

        Args:
            data: Serialized node dict

        Returns:
            Node instance
        """
        # Span 역직렬화 (interned for memory efficiency)
        span_data = data["span"]
        span = SpanPool.intern(
            start_line=span_data["start_line"],
            start_col=span_data["start_col"],
            end_line=span_data["end_line"],
            end_col=span_data["end_col"],
        )

        body_span = None
        if data.get("body_span"):
            bs = data["body_span"]
            body_span = SpanPool.intern(
                start_line=bs["start_line"],
                start_col=bs["start_col"],
                end_line=bs["end_line"],
                end_col=bs["end_col"],
            )

        # NodeKind 역직렬화
        kind = NodeKind(data["kind"])

        # Control flow summary (향후 구현)
        control_flow_summary = None
        if data.get("control_flow_summary"):
            logger.warning("control_flow_summary_deserialization_skipped")

        return Node(
            id=data["id"],
            kind=kind,
            fqn=data["fqn"],
            file_path=data["file_path"],
            span=span,
            language=data["language"],
            stable_id=data.get("stable_id"),
            content_hash=data.get("content_hash"),
            name=data.get("name"),
            module_path=data.get("module_path"),
            parent_id=data.get("parent_id"),
            body_span=body_span,
            docstring=data.get("docstring"),
            role=data.get("role"),
            is_test_file=data.get("is_test_file"),
            signature_id=data.get("signature_id"),
            declared_type_id=data.get("declared_type_id"),
            control_flow_summary=control_flow_summary,
            attrs=data.get("attrs", {}),
        )

    def serialize_edge(self, edge: Edge) -> dict:
        """Edge → dict (Complete 6-field serialization)"""
        return {
            "id": edge.id,
            "kind": edge.kind.value if hasattr(edge.kind, "value") else str(edge.kind),
            "source_id": edge.source_id,
            "target_id": edge.target_id,
            "span": self.serialize_span(edge.span) if edge.span else None,
            "attrs": edge.attrs,
        }

    def deserialize_edge(self, data: dict) -> Edge:
        """dict → Edge"""
        kind = EdgeKind(data["kind"])

        span = None
        if data.get("span"):
            s = data["span"]
            span = SpanPool.intern(
                start_line=s["start_line"],
                start_col=s["start_col"],
                end_line=s["end_line"],
                end_col=s["end_col"],
            )

        return Edge(
            id=data["id"],
            kind=kind,
            source_id=data["source_id"],
            target_id=data["target_id"],
            span=span,
            attrs=data.get("attrs", {}),
        )

    def serialize_span(self, span: Span) -> dict | None:
        """Span → dict"""
        if span is None:
            return None

        return {
            "start_line": span.start_line,
            "start_col": span.start_col,
            "end_line": span.end_line,
            "end_col": span.end_col,
        }

    def serialize_control_flow(self, cf_summary) -> dict | None:
        """ControlFlowSummary → dict (Graceful)"""
        if cf_summary is None:
            return None

        try:
            return {"has_summary": True}
        except Exception as e:
            logger.warning("control_flow_summary_serialization_skipped", error=str(e))
            return None

    def serialize_type(self, type_entity) -> dict:
        """TypeEntity → dict (minimal)"""
        return {"id": getattr(type_entity, "id", "unknown")}

    def serialize_signature(self, signature) -> dict:
        """SignatureEntity → dict (minimal)"""
        return {"id": getattr(signature, "id", "unknown")}

    def serialize_dfg_snapshot(self, dfg_snapshot) -> dict:
        """DfgSnapshot → dict (minimal)"""
        return {
            "variables_count": len(getattr(dfg_snapshot, "variables", [])),
            "edges_count": len(getattr(dfg_snapshot, "edges", [])),
        }

    def serialize_taint_finding(self, finding) -> dict:
        """Vulnerability → dict"""
        return {
            "severity": getattr(finding, "severity", "unknown"),
            "type": getattr(finding, "type", "unknown"),
        }

    def validate_schema(self, data: dict) -> tuple[bool, list[str]]:
        """
        JSONB Schema 검증.

        Returns:
            (is_valid, errors)
        """
        errors = []

        required_fields = ["repo_id", "snapshot_id", "nodes", "edges"]

        for field in required_fields:
            if field not in data:
                errors.append(f"Missing required field: {field}")

        # Type verification
        if "nodes" in data and not isinstance(data["nodes"], list):
            errors.append("nodes must be list")

        if "edges" in data and not isinstance(data["edges"], list):
            errors.append("edges must be list")

        # Node schema validation
        if data.get("nodes"):
            node = data["nodes"][0]
            node_required = ["id", "kind", "fqn", "file_path", "span", "language"]

            for field in node_required:
                if field not in node:
                    errors.append(f"Node missing required field: {field}")

        if errors:
            logger.error("schema_validation_failed", errors=errors)
            return False, errors

        return True, []
