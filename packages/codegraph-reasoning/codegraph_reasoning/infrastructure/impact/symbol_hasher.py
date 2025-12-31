"""
Symbol-level Hash System

Salsa-style symbol hash 구현:
- SignatureHash: 이름 + 파라미터 + 반환 타입
- BodyHash: 함수 내부 AST (정규화)
- ImpactHash: Signature + callees' signatures
"""

import hashlib

from codegraph_engine.code_foundation.domain.models import GraphNode as IRNode
from codegraph_engine.code_foundation.infrastructure.ir.models import EdgeKind, IRDocument, NodeKind
from codegraph_reasoning.domain.models import HashBasedImpactLevel, SymbolHash


class SignatureHasher:
    """
    Signature hash 계산.

    Body 변경 없이 signature만 비교 가능하도록.
    """

    def compute(self, node: IRNode) -> str:
        """
        Signature hash 계산.

        포함 요소:
        - 함수명
        - 파라미터 타입 (정렬)
        - 반환 타입
        - Visibility (public/private)
        """
        if node.kind not in (NodeKind.FUNCTION, NodeKind.METHOD):
            return ""

        components = []

        # 1. 함수명
        components.append(node.name or node.fqn)

        # 2. 파라미터 타입 (attrs에서 추출)
        param_types = []
        params = node.attrs.get("params", [])
        if isinstance(params, list):
            for param in params:
                if isinstance(param, dict):
                    type_str = param.get("type_annotation", "Any")
                else:
                    type_str = getattr(param, "type_annotation", "Any") or "Any"
                param_types.append(type_str)

        # 정렬 (순서 변경은 signature 변경 아님)
        param_types.sort()
        components.append("|".join(param_types))

        # 3. 반환 타입
        return_type = node.attrs.get("return_type", "None") or "None"
        components.append(return_type)

        # 4. Visibility (optional)
        visibility = node.attrs.get("visibility")
        if visibility:
            components.append(str(visibility))

        # Hash 계산
        signature_str = "|".join(components)
        return hashlib.sha256(signature_str.encode()).hexdigest()


class BodyHasher:
    """
    Body hash 계산.

    함수 내부 AST를 정규화된 형태로 해싱.
    """

    def compute(self, node: IRNode) -> str:
        """
        Body hash 계산.

        정규화:
        - 변수명 무관 (구조만)
        - 주석 제거
        - 공백 정규화
        """
        if node.kind not in (NodeKind.FUNCTION, NodeKind.METHOD):
            return ""

        # AST 구조를 재귀적으로 순회하며 정규화된 표현 생성
        normalized_body = self._normalize_ast(node)

        # Hash 계산
        return hashlib.sha256(normalized_body.encode()).hexdigest()

    def _normalize_ast(self, node: IRNode) -> str:
        """
        AST를 정규화된 문자열로 변환.

        현재 구현: Statement 타입만 추출 (간단한 구조 해싱)

        향후 개선 가능:
        - 변수명 치환 (v1, v2, v3...)
        - 리터럴 값 정규화 (숫자/문자열 → placeholder)
        - 연산자 정규화 (동등 연산자 통일)

        Args:
            node: IR 노드

        Returns:
            정규화된 AST 문자열
        """
        # attrs에서 body 추출
        body = node.attrs.get("body", [])
        if not body:
            return ""

        # Body의 각 statement를 정규화
        normalized = []

        if isinstance(body, list):
            for stmt in body:
                # Statement 타입 기록 (구조적 해싱)
                stmt_type = stmt.get("type", "unknown") if isinstance(stmt, dict) else "unknown"
                normalized.append(f"stmt:{stmt_type}")

        return "|".join(normalized)


class ImpactHasher:
    """
    Impact hash 계산.

    Signature + callees' signatures를 결합.
    Callee의 signature가 변경되면 caller의 impact hash도 변경됨.
    """

    def __init__(self, ir_document: IRDocument):
        self.ir_doc = ir_document
        self._build_call_graph()

    def _build_call_graph(self):
        """Call graph 구축 (간단한 버전)"""
        self.callees_map: dict[str, list[str]] = {}  # caller_id → [callee_ids]

        for edge in self.ir_doc.edges:
            if edge.kind == EdgeKind.CALLS:
                # v2.1 IRDocument: edge.source_id, edge.target_id
                caller_id = edge.source_id
                callee_id = edge.target_id

                if caller_id not in self.callees_map:
                    self.callees_map[caller_id] = []

                self.callees_map[caller_id].append(callee_id)

    def compute(self, node: IRNode, signature_hash: str, callee_signature_hashes: dict[str, str]) -> str:
        """
        Impact hash 계산.

        ImpactHash(f) = H(
            SignatureHash(f),
            [SignatureHash(c) for c in callees(f)]
        )
        """
        components = [signature_hash]

        # Callees의 signature hash 수집
        callees = self.callees_map.get(node.id, [])
        callee_hashes = []

        for callee_id in callees:
            if callee_id in callee_signature_hashes:
                callee_hashes.append(callee_signature_hashes[callee_id])

        # 정렬 (순서 무관)
        callee_hashes.sort()
        components.extend(callee_hashes)

        # Hash 계산
        impact_str = "|".join(components)
        return hashlib.sha256(impact_str.encode()).hexdigest()


class SymbolHasher:
    """
    Symbol-level hash 통합 계산.

    SignatureHash, BodyHash, ImpactHash를 모두 계산.
    """

    def __init__(self, ir_document: IRDocument):
        self.ir_doc = ir_document
        self.signature_hasher = SignatureHasher()
        self.body_hasher = BodyHasher()
        self.impact_hasher = ImpactHasher(ir_document)

    def compute_all(self) -> dict[str, SymbolHash]:
        """
        모든 함수/메서드의 hash 계산.

        Returns:
            symbol_id → SymbolHash
        """
        result = {}

        # 1단계: 모든 함수의 signature hash 계산
        signature_hashes = {}
        for node in self.ir_doc.nodes:
            if node.kind in (NodeKind.FUNCTION, NodeKind.METHOD):
                sig_hash = self.signature_hasher.compute(node)
                signature_hashes[node.id] = sig_hash

        # 2단계: 각 함수의 body hash와 impact hash 계산
        for node in self.ir_doc.nodes:
            if node.kind not in (NodeKind.FUNCTION, NodeKind.METHOD):
                continue

            sig_hash = signature_hashes[node.id]
            body_hash = self.body_hasher.compute(node)
            impact_hash = self.impact_hasher.compute(node, sig_hash, signature_hashes)

            result[node.id] = SymbolHash(
                symbol_id=node.id, signature_hash=sig_hash, body_hash=body_hash, impact_hash=impact_hash
            )

        return result

    def compute_single(self, node: IRNode) -> SymbolHash:
        """단일 심볼의 hash 계산"""
        if node.kind not in (NodeKind.FUNCTION, NodeKind.METHOD):
            raise ValueError(f"Node {node.id} is not a function/method")

        # Signature hash들을 먼저 수집 (impact hash 계산용)
        signature_hashes = {}
        for n in self.ir_doc.nodes:
            if n.kind in (NodeKind.FUNCTION, NodeKind.METHOD):
                signature_hashes[n.id] = self.signature_hasher.compute(n)

        sig_hash = signature_hashes[node.id]
        body_hash = self.body_hasher.compute(node)
        impact_hash = self.impact_hasher.compute(node, sig_hash, signature_hashes)

        return SymbolHash(symbol_id=node.id, signature_hash=sig_hash, body_hash=body_hash, impact_hash=impact_hash)


class ImpactClassifier:
    """
    Hash 변경 기반으로 Impact Level 분류.

    - Signature 변경 → BREAKING (API 깨짐)
    - Body만 변경 → MAJOR (동작 변경)
    - Impact hash만 변경 → MINOR (간접 영향)
    - 변경 없음 → NONE
    """

    def classify_change(
        self,
        old_signature_hash: str,
        new_signature_hash: str,
        old_body_hash: str,
        new_body_hash: str,
    ) -> "HashBasedImpactLevel":
        """
        Hash 비교 결과로 impact level 분류.
        """
        # 1. Signature 변경 → SIGNATURE_CHANGE
        if old_signature_hash != new_signature_hash:
            return HashBasedImpactLevel.SIGNATURE_CHANGE

        # 2. Body만 변경 → IR_LOCAL
        if old_body_hash != new_body_hash:
            return HashBasedImpactLevel.IR_LOCAL

        # 3. 변경 없음 → NO_IMPACT
        return HashBasedImpactLevel.NO_IMPACT


# =============================================================================
# Helper Functions
# =============================================================================


def compare_hashes(old_hash: SymbolHash, new_hash: SymbolHash) -> tuple[bool, bool, bool]:
    """
    Hash 비교.

    Returns:
        (signature_changed, body_changed, impact_changed)
    """
    sig_changed = old_hash.signature_hash != new_hash.signature_hash
    body_changed = old_hash.body_hash != new_hash.body_hash
    impact_changed = old_hash.impact_hash != new_hash.impact_hash

    return sig_changed, body_changed, impact_changed


def hash_to_json(symbol_hash: SymbolHash) -> dict:
    """SymbolHash를 JSON으로 직렬화"""
    return {
        "symbol_id": symbol_hash.symbol_id,
        "signature_hash": symbol_hash.signature_hash,
        "body_hash": symbol_hash.body_hash,
        "impact_hash": symbol_hash.impact_hash,
    }


def json_to_hash(data: dict) -> SymbolHash:
    """JSON에서 SymbolHash 복원"""
    return SymbolHash(
        symbol_id=data["symbol_id"],
        signature_hash=data["signature_hash"],
        body_hash=data["body_hash"],
        impact_hash=data["impact_hash"],
    )
