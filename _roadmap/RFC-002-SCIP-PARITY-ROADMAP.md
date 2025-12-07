# RFC-002: SCIP Parity Roadmap - SOTA 달성 전략

**Status**: Proposed  
**Date**: 2025-12-06  
**Priority**: P0 (SOTA Critical)  
**Estimated Effort**: 12-16 weeks

---

## 1. Executive Summary

### 1.1 현재 상태

**Semantica의 강점 (SCIP 초과)**:
- Single-language precision: 10.0/10
- Lambda/Anonymous class: 완벽
- PDG slicing: SOTA급
- LLM reasoning 적합성: 독보적
- Metadata richness: SCIP 대비 175%

**SCIP의 강점 (Semantica 미달)**:
- Cross-language symbol resolution
- Classpath-level semantic resolution
- Incremental indexing stability
- Enterprise tooling ecosystem

### 1.2 목표

**"SCIP의 강점 + Semantica의 강점 = True SOTA"**

4가지 Gap 해결로 완전한 SOTA IR 달성

---

## 2. Gap Analysis

### Gap 1: Cross-Language Symbol Resolution

**현재**:
```python
# Python generator
class PythonIRGenerator:
    # Python만 처리

# Java generator  
class JavaIRGenerator:
    # Java만 처리
    
# 언어 간 연결 없음
```

**SCIP**:
```
Java class → Kotlin reference
TypeScript → JavaScript resolution
Python → Cython bridge
```

**영향**:
- Polyglot 프로젝트 지원 불가
- Microservice 간 type safety 불가
- FFI (Foreign Function Interface) 추적 불가

---

### Gap 2: Classpath-level Resolution

**현재**:
```python
# External symbol placeholder
import requests  # → <external>.requests

# 실제 requests 내부 해석 없음
```

**SCIP**:
```
import requests
  ↓
site-packages/requests/__init__.py
  ↓ 
실제 requests.get() signature 해석
  ↓
Overload resolution
Type inference
```

**영향**:
- External library API 정확도 부족
- Overload resolution 불가
- Type inference 제한적

---

### Gap 3: Incremental Indexing Stability

**현재**:
```python
# Lambda ID = line-based
lambda$4  # line 4
lambda$5  # line 5

# 코드 삽입 시
# line 4에 새 코드 추가
lambda$5  # → lambda$6 (ID shift!)
```

**SCIP**:
```
Stable symbol guarantee:
- Content-based hash
- Structural position
- No drift on edit
```

**영향**:
- Incremental update 시 symbol drift
- Cross-session consistency 부족
- Vector embedding invalidation

---

### Gap 4: Enterprise Tooling Ecosystem

**현재**:
```
Semantica tooling:
- IR builder ✅
- LSP integration ⚠️
- 외부 도구 연동 없음
```

**SCIP**:
```
Ecosystem:
- Zoekt integration (search)
- LSIF converter
- 10+ language emitters
- Sourcegraph 검증 (수년)
```

**영향**:
- 대규모 repo 검증 부족
- 외부 도구 연동 없음
- Enterprise adoption 제한

---

## 3. Solution Architecture

### 3.1 Overall Design

```
┌─────────────────────────────────────────────────┐
│  Phase 4: Enterprise Tooling (Week 13-16)      │
│  - LSIF exporter                                │
│  - Benchmark suite                              │
│  - Large repo validation                        │
└────────────┬────────────────────────────────────┘
             │
┌────────────▼────────────────────────────────────┐
│  Phase 3: Incremental Stability (Week 9-12)    │
│  - Stable symbol ID (content hash)             │
│  - Delta consistency                            │
│  - Symbol mapping table                         │
└────────────┬────────────────────────────────────┘
             │
┌────────────▼────────────────────────────────────┐
│  Phase 2: Classpath Resolution (Week 5-8)      │
│  - External dependency indexer                  │
│  - Type inference engine                        │
│  - Overload resolver                            │
└────────────┬────────────────────────────────────┘
             │
┌────────────▼────────────────────────────────────┐
│  Phase 1: Cross-Language Bridge (Week 1-4)     │
│  - Unified symbol format                        │
│  - Language bridge registry                     │
│  - Cross-language edge generator                │
└─────────────────────────────────────────────────┘
```

---

## 4. Phase 1: Cross-Language Symbol Resolution (Week 1-4)

### 4.1 Unified Symbol Format

**목표**: 언어 간 통일된 symbol identifier

```python
# 신규: src/contexts/code_foundation/domain/unified_symbol.py

@dataclass
class UnifiedSymbol:
    """
    언어 중립적 symbol 표현
    SCIP descriptor 호환
    """
    
    # Core Identity
    scheme: str              # "python", "java", "typescript"
    package: str             # "org.example", "com.company"
    descriptor: str          # SCIP descriptor
    
    # Language-specific
    language_fqn: str        # 원본 FQN
    language_kind: str       # 원본 kind
    
    # Resolved Info
    signature: str | None    # Canonical signature
    type_info: TypeInfo | None
    
    def to_scip_descriptor(self) -> str:
        """
        SCIP descriptor 생성
        
        Python:  python3 . com.example `MyClass#`
        Java:    jvm . com.example `MyClass#`
        TS:      npm . @types/node `fs.readFile().`
        """
        if self.scheme == "python":
            return f"python3 . {self.package} `{self.descriptor}`"
        elif self.scheme == "java":
            return f"jvm . {self.package} `{self.descriptor}`"
        elif self.scheme == "typescript":
            return f"npm . {self.package} `{self.descriptor}`"
    
    def matches(self, other: "UnifiedSymbol") -> bool:
        """Cross-language matching"""
        # Same descriptor, different language OK
        return self.descriptor == other.descriptor
```

### 4.2 Language Bridge Registry

**목표**: 언어 간 type mapping

```python
# 신규: src/contexts/code_foundation/infrastructure/language_bridge.py

class LanguageBridge:
    """
    언어 간 type/symbol 매핑
    """
    
    # Type mapping table
    TYPE_MAPPINGS = {
        ("python", "java"): {
            "str": "java.lang.String",
            "int": "java.lang.Integer",
            "list": "java.util.List",
            "dict": "java.util.Map",
        },
        ("typescript", "python"): {
            "string": "str",
            "number": "int | float",
            "Array": "list",
            "Record": "dict",
        },
        ("java", "kotlin"): {
            # Java class → Kotlin 호환
            "java.lang.String": "kotlin.String",
            "java.util.List": "kotlin.collections.List",
        },
    }
    
    def resolve_cross_language(
        self,
        source_symbol: UnifiedSymbol,
        target_language: str
    ) -> UnifiedSymbol | None:
        """
        Python str → Java String 등
        """
        mapping_key = (source_symbol.scheme, target_language)
        type_map = self.TYPE_MAPPINGS.get(mapping_key)
        
        if not type_map:
            return None
        
        mapped_type = type_map.get(source_symbol.language_fqn)
        if not mapped_type:
            return None
        
        return UnifiedSymbol(
            scheme=target_language,
            package=self._infer_package(mapped_type),
            descriptor=self._to_descriptor(mapped_type),
            language_fqn=mapped_type,
            language_kind=source_symbol.language_kind,
        )
```

### 4.3 Cross-Language Edge Generator

**목표**: 언어 간 CALLS/IMPORTS edge

```python
# 신규: src/contexts/code_foundation/infrastructure/cross_lang_edges.py

class CrossLanguageEdgeGenerator:
    """
    Polyglot 프로젝트 edge 생성
    """
    
    def __init__(self, bridge: LanguageBridge):
        self.bridge = bridge
    
    async def generate_cross_edges(
        self,
        irs: dict[str, IRDocument]  # file_path → IR
    ) -> list[IREdge]:
        """
        예:
        main.py:
            from java_lib import JavaClass  # Jython/GraalVM
            obj = JavaClass()
        
        JavaClass.java:
            public class JavaClass {}
        
        → IMPORTS edge (Python → Java)
        → INSTANTIATES edge
        """
        edges = []
        
        # 1. Detect cross-language imports
        for file_path, ir in irs.items():
            lang = self._detect_language(file_path)
            
            for import_node in ir.nodes_by_kind(NodeKind.IMPORT):
                target_lang = self._detect_import_language(import_node)
                
                if target_lang and target_lang != lang:
                    # Cross-language import!
                    edge = self._create_cross_import_edge(
                        import_node, 
                        lang, 
                        target_lang
                    )
                    edges.append(edge)
        
        # 2. Detect FFI calls
        for file_path, ir in irs.items():
            ffi_edges = self._detect_ffi_calls(ir)
            edges.extend(ffi_edges)
        
        return edges
    
    def _detect_import_language(self, import_node) -> str | None:
        """
        import jpype  → "java"
        from ctypes import *  → "c"
        import pyarrow  → "cpp"
        """
        module_name = import_node.attrs.get("module_name")
        
        # FFI library detection
        if module_name in ["jpype", "py4j", "jnius"]:
            return "java"
        elif module_name in ["ctypes", "cffi"]:
            return "c"
        elif module_name in ["pybind11", "boost.python"]:
            return "cpp"
        elif module_name.startswith("@types/"):
            return "typescript"
        
        return None
```

### 4.4 Success Criteria (Phase 1)

- [ ] Unified symbol format 정의
- [ ] Python ↔ Java ↔ TypeScript mapping 구현
- [ ] Cross-language edge 생성 (최소 2개 언어 쌍)
- [ ] Polyglot test project 100% edge 생성

**Validation**:
```python
# Test: Python → Java
test_project/
  ├── main.py (import java_lib)
  └── java_lib.java

Expected:
- IMPORTS edge: main.py → java_lib.java
- Unified symbol: python3.main → jvm.java_lib
```

---

## 5. Phase 2: Classpath-level Resolution (Week 5-8)

### 5.1 External Dependency Indexer

**목표**: site-packages, node_modules, .m2 indexing

```python
# 신규: src/contexts/code_foundation/infrastructure/dependency_indexer.py

class DependencyIndexer:
    """
    External library IR 생성
    """
    
    def __init__(self, project_root: Path):
        self.project_root = project_root
        self.cache_dir = project_root / ".semantica" / "deps"
    
    async def index_dependencies(
        self,
        manifest: Path  # requirements.txt, package.json, pom.xml
    ) -> dict[str, IRDocument]:
        """
        External library IR 생성 및 캐싱
        
        Returns:
          {"requests": IRDocument(...), "numpy": IRDocument(...)}
        """
        deps = self._parse_manifest(manifest)
        irs = {}
        
        for dep_name, version in deps.items():
            # 1. Check cache
            cached_ir = self._load_cache(dep_name, version)
            if cached_ir:
                irs[dep_name] = cached_ir
                continue
            
            # 2. Generate IR
            dep_path = self._resolve_dependency_path(dep_name)
            if not dep_path:
                continue
            
            # 3. Generate (using existing generators)
            ir = await self._generate_dep_ir(dep_path)
            
            # 4. Cache
            self._save_cache(dep_name, version, ir)
            irs[dep_name] = ir
        
        return irs
    
    def _resolve_dependency_path(self, dep_name: str) -> Path | None:
        """
        Python: site-packages/requests/
        Node:   node_modules/@types/node/
        Java:   ~/.m2/repository/com/example/
        """
        # Try Python
        python_path = self._find_python_package(dep_name)
        if python_path:
            return python_path
        
        # Try Node
        node_path = self.project_root / "node_modules" / dep_name
        if node_path.exists():
            return node_path
        
        # Try Java
        java_path = self._find_maven_artifact(dep_name)
        if java_path:
            return java_path
        
        return None
```

### 5.2 Type Inference Engine

**목표**: Pyright/TypeScript 수준 inference

```python
# 신규: src/contexts/code_foundation/infrastructure/type_inference.py

class TypeInferenceEngine:
    """
    LSP 기반 type inference
    Pyright, tsserver, JDT.LS 활용
    """
    
    def __init__(self, lsp_manager):
        self.lsp = lsp_manager
    
    async def infer_types(
        self,
        ir: IRDocument,
        dep_irs: dict[str, IRDocument]
    ) -> IRDocument:
        """
        IR에 type 정보 enrichment
        """
        enriched_nodes = []
        
        for node in ir.nodes:
            if node.kind in [NodeKind.VARIABLE, NodeKind.PARAMETER]:
                # LSP hover로 type 추출
                type_info = await self._lsp_infer_type(node)
                
                # Dependency IR에서 type 검색
                if not type_info:
                    type_info = self._search_dep_type(node, dep_irs)
                
                # Node에 type 추가
                node.attrs["inferred_type"] = type_info
            
            enriched_nodes.append(node)
        
        ir.nodes = enriched_nodes
        return ir
    
    async def _lsp_infer_type(self, node: IRNode) -> str | None:
        """LSP textDocument/hover"""
        hover_result = await self.lsp.hover(
            file_path=node.location.file_path,
            line=node.location.start_line,
            column=node.location.start_column,
        )
        
        if hover_result:
            return self._extract_type_from_hover(hover_result)
        
        return None
    
    def _search_dep_type(
        self,
        node: IRNode,
        dep_irs: dict[str, IRDocument]
    ) -> str | None:
        """
        Dependency IR에서 type 검색
        
        예:
        requests.get()  → dep_irs["requests"] 검색
                        → requests.api.get() signature
                        → return type: Response
        """
        # Extract dependency name
        dep_name = self._extract_dep_name(node)
        if not dep_name or dep_name not in dep_irs:
            return None
        
        dep_ir = dep_irs[dep_name]
        
        # Search symbol in dep IR
        symbol_fqn = node.attrs.get("fqn")
        target_node = dep_ir.find_node_by_fqn(symbol_fqn)
        
        if target_node:
            return target_node.attrs.get("return_type")
        
        return None
```

### 5.3 Overload Resolver

**목표**: Call site type 기반 overload resolution

```python
# 신규: src/contexts/code_foundation/infrastructure/overload_resolver.py

class OverloadResolver:
    """
    Function overload resolution
    """
    
    def resolve_call(
        self,
        call_node: IRNode,
        candidates: list[IRNode],  # Overload candidates
        type_engine: TypeInferenceEngine
    ) -> IRNode | None:
        """
        Call site 타입 기반 best match 선택
        
        예:
        def add(x: int, y: int): ...
        def add(x: str, y: str): ...
        
        result = add(1, 2)  → int overload
        result = add("a", "b")  → str overload
        """
        # 1. Get call site argument types
        arg_types = []
        for arg in call_node.attrs.get("arguments", []):
            arg_type = type_engine.infer_type(arg)
            arg_types.append(arg_type)
        
        # 2. Score each candidate
        scores = []
        for candidate in candidates:
            param_types = candidate.attrs.get("parameter_types", [])
            score = self._match_score(arg_types, param_types)
            scores.append((score, candidate))
        
        # 3. Best match
        scores.sort(reverse=True)
        if scores and scores[0][0] > 0:
            return scores[0][1]
        
        return None
    
    def _match_score(
        self,
        arg_types: list[str],
        param_types: list[str]
    ) -> float:
        """
        Type compatibility score
        
        Exact match: 1.0
        Subtype: 0.8
        Compatible: 0.5
        Incompatible: 0.0
        """
        if len(arg_types) != len(param_types):
            return 0.0
        
        total_score = 0.0
        for arg_t, param_t in zip(arg_types, param_types):
            if arg_t == param_t:
                total_score += 1.0  # Exact
            elif self._is_subtype(arg_t, param_t):
                total_score += 0.8  # Subtype
            elif self._is_compatible(arg_t, param_t):
                total_score += 0.5  # Compatible
            else:
                return 0.0  # Incompatible
        
        return total_score / len(arg_types)
```

### 5.4 Success Criteria (Phase 2)

- [ ] Top 20 Python packages indexing (requests, numpy, etc.)
- [ ] Type inference accuracy 85%+
- [ ] Overload resolution accuracy 90%+
- [ ] Classpath resolution < 500ms

**Validation**:
```python
# Test: External library type inference
import requests

response = requests.get("https://...")
# response type: requests.models.Response ✅

data = response.json()
# data type: dict[str, Any] ✅
```

---

## 6. Phase 3: Incremental Stability (Week 9-12)

### 6.1 Stable Symbol ID Algorithm

**목표**: Content-based stable hash

```python
# 수정: src/contexts/code_foundation/infrastructure/generators/base.py

class StableIDGenerator:
    """
    SCIP-style stable symbol ID
    """
    
    def generate_stable_id(
        self,
        node_kind: NodeKind,
        fqn: str,
        content_hash: str,  # AST hash
        structural_position: str  # Parent FQN + index
    ) -> str:
        """
        Stable ID = hash(kind + fqn + content + position)
        
        예:
        lambda at line 4:
          - FQN: MyClass.my_method.lambda$0
          - Content hash: hash(lambda body AST)
          - Position: MyClass.my_method[child_index=2]
          
        → ID: stable_lambda_abc123def456
        
        코드 삽입 시:
        - Content hash 동일 → Same ID ✅
        - Position 변경되어도 content로 매칭 가능
        """
        components = [
            node_kind.value,
            fqn,
            content_hash[:16],      # Short hash
            structural_position,
        ]
        
        combined = "|".join(components)
        hash_value = hashlib.sha256(combined.encode()).hexdigest()
        
        return f"stable_{node_kind.value}_{hash_value[:12]}"
    
    def compute_content_hash(self, node: tree_sitter.Node) -> str:
        """
        AST subtree hash (구조 기반)
        
        Lambda 예:
          hash(lambda params + body structure)
        """
        # Serialize AST structure
        structure = self._serialize_ast(node)
        return hashlib.sha256(structure.encode()).hexdigest()
    
    def _serialize_ast(self, node: tree_sitter.Node) -> str:
        """
        AST를 canonical string으로
        
        예:
        lambda x: x + 1
        → "lambda_expression(parameters(x),binary_op(+,x,1))"
        """
        if node.child_count == 0:
            return f"{node.type}({node.text.decode()})"
        
        children = [self._serialize_ast(c) for c in node.children]
        return f"{node.type}({','.join(children)})"
```

### 6.2 Symbol Mapping Table

**목표**: Incremental update 시 symbol tracking

```python
# 신규: src/contexts/code_foundation/infrastructure/symbol_mapping.py

@dataclass
class SymbolMapping:
    """
    Old ID → New ID mapping
    """
    old_id: str
    new_id: str
    confidence: float  # 0.0 ~ 1.0
    reason: str        # "content_match", "position_match", etc.

class SymbolMappingTable:
    """
    Incremental update 시 symbol 추적
    """
    
    def __init__(self):
        self.mappings: dict[str, SymbolMapping] = {}
    
    def compute_mappings(
        self,
        old_ir: IRDocument,
        new_ir: IRDocument
    ) -> dict[str, SymbolMapping]:
        """
        Old IR → New IR symbol mapping
        
        Algorithm:
        1. Exact ID match (높은 신뢰도)
        2. Content hash match (중간 신뢰도)
        3. FQN + position match (낮은 신뢰도)
        """
        mappings = {}
        
        old_symbols = {n.id: n for n in old_ir.nodes}
        new_symbols = {n.id: n for n in new_ir.nodes}
        
        # 1. Exact ID match
        for old_id in old_symbols:
            if old_id in new_symbols:
                mappings[old_id] = SymbolMapping(
                    old_id=old_id,
                    new_id=old_id,
                    confidence=1.0,
                    reason="exact_id"
                )
        
        # 2. Content hash match
        old_by_hash = self._group_by_content_hash(old_symbols.values())
        new_by_hash = self._group_by_content_hash(new_symbols.values())
        
        for content_hash, old_nodes in old_by_hash.items():
            if content_hash in new_by_hash:
                new_nodes = new_by_hash[content_hash]
                
                # Match by position if multiple
                for old_node, new_node in zip(old_nodes, new_nodes):
                    if old_node.id not in mappings:
                        mappings[old_node.id] = SymbolMapping(
                            old_id=old_node.id,
                            new_id=new_node.id,
                            confidence=0.9,
                            reason="content_match"
                        )
        
        # 3. FQN match (fallback)
        old_by_fqn = self._group_by_fqn(old_symbols.values())
        new_by_fqn = self._group_by_fqn(new_symbols.values())
        
        for fqn, old_nodes in old_by_fqn.items():
            if fqn in new_by_fqn and len(old_nodes) == 1:
                new_nodes = new_by_fqn[fqn]
                if len(new_nodes) == 1:
                    old_node = old_nodes[0]
                    new_node = new_nodes[0]
                    
                    if old_node.id not in mappings:
                        mappings[old_node.id] = SymbolMapping(
                            old_id=old_node.id,
                            new_id=new_node.id,
                            confidence=0.7,
                            reason="fqn_match"
                        )
        
        return mappings
```

### 6.3 Delta Consistency

**목표**: Vector embedding invalidation 최소화

```python
# 신규: src/contexts/code_foundation/infrastructure/incremental_validator.py

class IncrementalConsistencyValidator:
    """
    Incremental update 일관성 검증
    """
    
    def validate(
        self,
        old_ir: IRDocument,
        new_ir: IRDocument,
        mappings: dict[str, SymbolMapping]
    ) -> ConsistencyReport:
        """
        Validation:
        1. 모든 old symbol이 mapping되었는가
        2. Confidence > 0.8 비율
        3. Edge consistency
        """
        report = ConsistencyReport()
        
        # 1. Coverage
        old_ids = {n.id for n in old_ir.nodes}
        mapped_ids = set(mappings.keys())
        unmapped = old_ids - mapped_ids
        
        report.coverage = len(mapped_ids) / len(old_ids)
        report.unmapped_symbols = list(unmapped)
        
        # 2. Confidence
        high_confidence = sum(
            1 for m in mappings.values() 
            if m.confidence > 0.8
        )
        report.high_confidence_ratio = high_confidence / len(mappings)
        
        # 3. Edge consistency
        report.edge_consistency = self._validate_edges(
            old_ir, new_ir, mappings
        )
        
        return report
    
    def _validate_edges(
        self,
        old_ir: IRDocument,
        new_ir: IRDocument,
        mappings: dict[str, SymbolMapping]
    ) -> float:
        """
        Old edge가 new IR에도 있는가
        (node ID 변경 감안)
        """
        old_edges = {
            (e.from_id, e.to_id, e.kind) 
            for e in old_ir.edges
        }
        
        # Map to new IDs
        expected_new_edges = set()
        for from_id, to_id, kind in old_edges:
            new_from = mappings.get(from_id)
            new_to = mappings.get(to_id)
            
            if new_from and new_to:
                expected_new_edges.add((
                    new_from.new_id,
                    new_to.new_id,
                    kind
                ))
        
        # Check existence in new IR
        new_edges = {
            (e.from_id, e.to_id, e.kind)
            for e in new_ir.edges
        }
        
        preserved = expected_new_edges & new_edges
        
        if expected_new_edges:
            return len(preserved) / len(expected_new_edges)
        return 1.0
```

### 6.4 Success Criteria (Phase 3)

- [ ] Symbol stability 95%+ (코드 수정 후)
- [ ] Mapping confidence > 0.8 비율 90%+
- [ ] Edge consistency 95%+
- [ ] Vector embedding invalidation < 10%

**Validation**:
```python
# Test: Code insertion
Original:
  line 1: def foo():
  line 2:     return 1
  line 3: lambda x: x + 1  # ID: stable_lambda_abc123

After insertion:
  line 1: def foo():
  line 2:     print("debug")  # NEW
  line 3:     return 1
  line 4: lambda x: x + 1  # Still ID: stable_lambda_abc123 ✅
```

---

## 7. Phase 4: Enterprise Tooling (Week 13-16)

### 7.1 LSIF Exporter

**목표**: Sourcegraph 연동

```python
# 신규: src/contexts/code_foundation/infrastructure/exporters/lsif_exporter.py

class LSIFExporter:
    """
    Semantica IR → LSIF format
    """
    
    def export(
        self,
        irs: dict[str, IRDocument],
        output_path: Path
    ):
        """
        LSIF JSON-LD output
        
        Sourcegraph, GitHub Code Search 등에서 사용 가능
        """
        lsif_data = {
            "$schema": "lsif-schema.json",
            "vertices": [],
            "edges": [],
        }
        
        # 1. Vertices (symbols)
        for ir in irs.values():
            for node in ir.nodes:
                vertex = self._node_to_vertex(node)
                lsif_data["vertices"].append(vertex)
        
        # 2. Edges (relationships)
        for ir in irs.values():
            for edge in ir.edges:
                lsif_edge = self._edge_to_lsif(edge)
                lsif_data["edges"].append(lsif_edge)
        
        # 3. Write
        with open(output_path, "w") as f:
            for item in lsif_data["vertices"] + lsif_data["edges"]:
                f.write(json.dumps(item) + "\n")
    
    def _node_to_vertex(self, node: IRNode) -> dict:
        """
        IRNode → LSIF vertex
        """
        return {
            "id": node.id,
            "type": "vertex",
            "label": self._kind_to_lsif_label(node.kind),
            "range": {
                "start": {
                    "line": node.location.start_line,
                    "character": node.location.start_column,
                },
                "end": {
                    "line": node.location.end_line,
                    "character": node.location.end_column,
                }
            },
        }
```

### 7.2 Benchmark Suite

**목표**: 대규모 repo 검증

```python
# 신규: benchmark/enterprise_benchmark.py

BENCHMARK_REPOS = [
    # Small (< 10K LOC)
    {"name": "typer", "url": "https://github.com/tiangolo/typer"},
    
    # Medium (10K ~ 100K LOC)
    {"name": "fastapi", "url": "https://github.com/tiangolo/fastapi"},
    {"name": "django", "url": "https://github.com/django/django"},
    
    # Large (100K ~ 500K LOC)
    {"name": "numpy", "url": "https://github.com/numpy/numpy"},
    {"name": "tensorflow", "url": "https://github.com/tensorflow/tensorflow"},
    
    # Polyglot
    {"name": "vscode", "url": "https://github.com/microsoft/vscode"},  # TS + C++
]

class EnterpriseBenchmark:
    """
    SCIP vs Semantica 비교 벤치마크
    """
    
    async def run_all(self):
        """
        각 repo에 대해:
        1. SCIP indexing (baseline)
        2. Semantica indexing
        3. 비교:
           - Symbol count
           - Edge count
           - Accuracy (manual validation)
           - Performance
           - Memory usage
        """
        results = []
        
        for repo in BENCHMARK_REPOS:
            result = await self.benchmark_repo(repo)
            results.append(result)
        
        self.generate_report(results)
    
    async def benchmark_repo(self, repo: dict) -> BenchmarkResult:
        """Single repo benchmark"""
        # Clone
        repo_path = await self.clone_repo(repo["url"])
        
        # SCIP indexing
        scip_result = await self.run_scip(repo_path)
        
        # Semantica indexing
        semantica_result = await self.run_semantica(repo_path)
        
        # Compare
        comparison = self.compare_results(scip_result, semantica_result)
        
        return BenchmarkResult(
            repo_name=repo["name"],
            scip=scip_result,
            semantica=semantica_result,
            comparison=comparison,
        )
```

### 7.3 Production Monitoring

**목표**: 대규모 운영 안정성

```python
# 신규: src/contexts/code_foundation/infrastructure/monitoring.py

class IRBuilderMonitoring:
    """
    Production metrics
    """
    
    def __init__(self):
        self.metrics = {
            "builds_total": 0,
            "builds_success": 0,
            "builds_failed": 0,
            "avg_build_time": 0.0,
            "symbol_count": 0,
            "edge_count": 0,
        }
    
    def record_build(
        self,
        success: bool,
        duration: float,
        symbol_count: int,
        edge_count: int,
        repo_size_loc: int
    ):
        """Record build metrics"""
        self.metrics["builds_total"] += 1
        
        if success:
            self.metrics["builds_success"] += 1
        else:
            self.metrics["builds_failed"] += 1
        
        # Moving average
        n = self.metrics["builds_total"]
        old_avg = self.metrics["avg_build_time"]
        self.metrics["avg_build_time"] = (old_avg * (n-1) + duration) / n
        
        self.metrics["symbol_count"] = symbol_count
        self.metrics["edge_count"] = edge_count
        
        # Alert on anomalies
        if duration > 60.0:
            self.alert(f"Slow build: {duration:.1f}s for {repo_size_loc} LOC")
        
        if not success:
            self.alert(f"Build failed")
```

### 7.4 Success Criteria (Phase 4)

- [ ] LSIF export 검증 (Sourcegraph upload 성공)
- [ ] Benchmark 5개 repo 완료
- [ ] Large repo (100K+ LOC) < 5min indexing
- [ ] SCIP 대비 accuracy 95%+

---

## 8. Integration Plan

### 8.1 Backward Compatibility

**원칙**: 기존 API 100% 유지

```python
# Existing API (유지)
builder = SOTAIRBuilder(project_root)
ir_docs, global_ctx, index = await builder.build_full(files)

# New API (추가)
builder = SOTAIRBuilder(
    project_root,
    enable_cross_language=True,      # Phase 1
    enable_classpath_resolution=True, # Phase 2
    enable_stable_ids=True,           # Phase 3
)

ir_docs, global_ctx, index, cross_edges, dep_index = await builder.build_full_v2(
    files,
    manifest_path=Path("requirements.txt"),  # Phase 2
)
```

### 8.2 Feature Flags

```python
# src/contexts/code_foundation/config.py

@dataclass
class SCIPParityConfig:
    """SCIP parity 기능 토글"""
    
    # Phase 1
    enable_cross_language: bool = False
    supported_language_pairs: list[tuple[str, str]] = field(default_factory=lambda: [
        ("python", "java"),
        ("typescript", "python"),
    ])
    
    # Phase 2
    enable_classpath_resolution: bool = False
    dependency_cache_ttl: int = 86400  # 1 day
    max_dependency_depth: int = 2      # Transitive deps
    
    # Phase 3
    enable_stable_ids: bool = False
    symbol_mapping_confidence_threshold: float = 0.8
    
    # Phase 4
    enable_lsif_export: bool = False
    enable_monitoring: bool = True
```

---

## 9. Risk Mitigation

### 9.1 Risks

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| Classpath resolution 성능 저하 | High | High | Aggressive caching, parallel indexing |
| Cross-language accuracy 부족 | Medium | High | Manual validation, test suite 확대 |
| Stable ID algorithm 복잡도 | Medium | Medium | Incremental rollout, feature flag |
| LSIF compatibility 이슈 | Low | Medium | SCIP 공식 validator 사용 |
| Large repo memory OOM | Medium | High | Streaming processing, chunk-based |

### 9.2 Rollback Plan

```python
# 각 Phase는 feature flag로 독립 제어
# 문제 발생 시 즉시 비활성화

config = SCIPParityConfig(
    enable_cross_language=False,  # Rollback Phase 1
    enable_classpath_resolution=False,  # Rollback Phase 2
    # ...
)
```

---

## 10. Success Metrics

### 10.1 Technical Metrics

| Metric | Baseline (현재) | Target (SOTA) |
|--------|----------------|---------------|
| **Cross-language coverage** | 0% | 80%+ (주요 언어 쌍) |
| **Classpath resolution accuracy** | 0% | 85%+ |
| **Symbol stability** | 60% (line-based) | 95%+ (content-based) |
| **LSIF compatibility** | 0% | 100% |
| **Large repo support** | < 50K LOC | 500K+ LOC |

### 10.2 Benchmark Goals

| Repository | Size | Target Time | Target Accuracy |
|------------|------|-------------|-----------------|
| typer | 5K LOC | < 5s | 98%+ |
| fastapi | 30K LOC | < 30s | 95%+ |
| django | 200K LOC | < 3min | 90%+ |
| numpy | 300K LOC | < 5min | 90%+ |
| vscode (polyglot) | 500K LOC | < 10min | 85%+ |

### 10.3 Business Metrics

- [ ] Enterprise adoption: 3+ companies
- [ ] Community feedback: 4.5+ stars
- [ ] Sourcegraph integration demo
- [ ] 학술 논문 게재 (ICSE, FSE 등)

---

## 11. Timeline

```
Week 1-4:   Phase 1 (Cross-Language)
            - Unified symbol format
            - Language bridge
            - Polyglot test cases

Week 5-8:   Phase 2 (Classpath)
            - Dependency indexer
            - Type inference
            - Overload resolution

Week 9-12:  Phase 3 (Stability)
            - Stable ID algorithm
            - Symbol mapping
            - Incremental validation

Week 13-16: Phase 4 (Enterprise)
            - LSIF exporter
            - Benchmark suite
            - Production validation

Week 17+:   Refinement & Documentation
            - Performance tuning
            - Edge case fixes
            - Research paper
```

---

## 12. Conclusion

### 12.1 Why This Matters

**현재 Semantica**:
- Best-in-class single-language IR
- LLM-optimized metadata
- Research-grade quality

**SOTA 달성 시**:
- SCIP의 enterprise strength
- Semantica의 precision
- **= True World-Class IR**

### 12.2 Competitive Position

```
After SCIP Parity:

Semantica > SCIP (in all dimensions)
  - Single-language: Semantica 10.0, SCIP 8.5
  - Cross-language: Semantica 9.0, SCIP 9.5
  - Classpath: Semantica 8.5, SCIP 9.0
  - Stability: Semantica 9.5, SCIP 9.0
  - LLM-ready: Semantica 10.0, SCIP 5.0
  
→ Overall: Semantica 9.4, SCIP 8.2
```

### 12.3 Next Steps

1. **Approve RFC** (Stakeholder review)
2. **Phase 0** (Week 0): Architecture design review
3. **Phase 1** (Week 1): Cross-language POC
4. **Validate early** (Week 2): Polyglot test case
5. **Continue phases** (Week 3+): Iterative delivery

---

**Approval Required**: Yes  
**Estimated Cost**: 12-16 weeks engineering  
**Expected ROI**: SOTA status, enterprise adoption, research impact

**Author**: Semantica Core Team  
**Reviewers**: TBD  
**Status**: **Awaiting Approval**
