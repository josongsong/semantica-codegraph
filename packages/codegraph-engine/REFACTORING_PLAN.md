# codegraph-engine Refactoring Plan - SOTA Execution

**Date:** 2025-12-29
**Duration:** 8 weeks (SOTA speed)
**Goal:** Fix all Critical Issues (God Classes, Anemic Domain, Adapter Collapse, Rust Migration)

---

## Executive Summary

### Scope

**4 Critical Issues** identified in ARCHITECTURE_REVIEW.md:

1. **God Classes** (13 files >1000 LOC) → Split using SRP
2. **Code Duplication** (5,000 LOC in generators) → Extract BaseGenerator
3. **Anemic Domain Model** → Enrich with business logic
4. **Adapter Layer Collapse** → Create proper adapters/ directory
5. **Incomplete Rust Migration** (95% Python) → Migrate high-ROI components

### Expected Impact

| Metric | Before | After | Improvement |
|--------|--------|-------|-------------|
| **God Classes (>1000 LOC)** | 13 files | 0 files | ✅ 100% reduction |
| **Generator Duplication** | 5,000 LOC | 2,500 LOC | ✅ 50% reduction |
| **Domain Behavior** | 0 methods | 50+ methods | ✅ Rich domain |
| **Adapter Layer** | 2 files | 40+ files | ✅ Proper separation |
| **Rust Coverage** | 5% | 60% | ✅ 12x increase |
| **Pipeline Speedup** | 1x baseline | 25-45x | ✅ **SOTA performance** |

### Timeline

```
Week 1-2: God Class Refactoring (P0)
Week 3-4: BaseGenerator Extraction + Domain Enrichment (P0)
Week 5-6: Rust Migration Phase 1 (Generators) (P1)
Week 7-8: Rust Migration Phase 2 (Semantic IR) (P1)
```

---

## Phase 1: God Class Refactoring (Week 1-2)

### 1.1. Target Files (13 files >1000 LOC)

**Priority 1 (Week 1)** - Worst offenders:

| File | LOC | Split Into | Effort |
|------|-----|-----------|--------|
| `java_generator.py` | 2,707 | 5 classes | 3 days |
| `expression/builder.py` | 2,416 | 4 classes | 3 days |
| `semantic_ir/builder.py` | 2,210 | 5 classes | 3 days |

**Priority 2 (Week 2)** - Moderate:

| File | LOC | Split Into | Effort |
|------|-----|-----------|--------|
| `bfg/builder.py` | 1,666 | 3 classes | 2 days |
| `memgraph/store.py` | 1,276 | 2 classes | 1 day |
| `type_enricher.py` | 1,168 | 2 classes | 1 day |
| `typescript_generator.py` | 1,160 | 4 classes | 2 days |

**Priority 3 (Optional)** - Lower priority:

- `ir/models/document.py` (1,143 LOC) - ✅ OK (rich domain model)
- `semantic_cache.py` (1,100 LOC) - Cache impl, acceptable
- Remaining 4 files (1,000-1,080 LOC)

### 1.2. Refactoring Strategy: java_generator.py (2,707 LOC)

**Current Structure** (SRP violation):
```python
# infrastructure/generators/java_generator.py (2,707 LOC)
class JavaGenerator:
    """Generates IR from Java source."""

    def __init__(self): ...

    # Responsibility 1: Parsing (500 LOC)
    def parse(self, source: str) -> ASTDocument: ...
    def visit_class(self, node): ...
    def visit_method(self, node): ...
    # ... 50+ parse methods

    # Responsibility 2: IR Generation (800 LOC)
    def generate_ir(self, ast: ASTDocument) -> IRDocument: ...
    def create_node(self, ast_node): ...
    def create_symbol(self, ast_node): ...
    # ... 30+ IR gen methods

    # Responsibility 3: Edge Building (600 LOC)
    def build_edges(self, ir: IRDocument): ...
    def build_call_edges(self): ...
    def build_inheritance_edges(self): ...
    # ... 20+ edge methods

    # Responsibility 4: Type Inference (500 LOC)
    def infer_types(self, ir: IRDocument): ...
    def resolve_type(self, node): ...
    def propagate_types(self): ...
    # ... 15+ type methods

    # Responsibility 5: Import Resolution (307 LOC)
    def resolve_imports(self, ir: IRDocument): ...
    def find_import(self, name): ...
    # ... 10+ import methods
```

**Target Structure** (SRP compliant):
```
infrastructure/generators/java/
├── __init__.py              # Re-exports
├── parser.py                # JavaParser (500 LOC)
├── ir_generator.py          # JavaIRGenerator (800 LOC)
├── edge_builder.py          # JavaEdgeBuilder (600 LOC)
├── type_inferencer.py       # JavaTypeInferencer (500 LOC)
└── import_resolver.py       # JavaImportResolver (307 LOC)
```

**New Classes**:

```python
# infrastructure/generators/java/parser.py (500 LOC)
class JavaParser:
    """Parses Java source into AST (tree-sitter)."""

    def parse(self, source: str) -> ASTDocument:
        """Parse Java source to AST."""
        tree = self.tree_sitter_parser.parse(source.encode())
        return self._build_ast_document(tree.root_node)

    def visit_class(self, node): ...
    def visit_method(self, node): ...
    # ... 50+ parse methods

# infrastructure/generators/java/ir_generator.py (800 LOC)
class JavaIRGenerator:
    """Generates IR from Java AST."""

    def generate(self, ast: ASTDocument) -> IRDocument:
        """Generate IR from AST."""
        ir = IRDocument.new()
        for node in ast.nodes:
            ir.add_node(self._convert_node(node))
        return ir

    def _convert_node(self, ast_node): ...
    def _create_symbol(self, ast_node): ...
    # ... 30+ IR gen methods

# infrastructure/generators/java/edge_builder.py (600 LOC)
class JavaEdgeBuilder:
    """Builds control/data flow edges for Java IR."""

    def build_edges(self, ir: IRDocument) -> None:
        """Build all edges in IR."""
        self._build_call_edges(ir)
        self._build_inheritance_edges(ir)
        self._build_dataflow_edges(ir)

    def _build_call_edges(self, ir: IRDocument): ...
    def _build_inheritance_edges(self, ir: IRDocument): ...
    # ... 20+ edge methods

# infrastructure/generators/java/type_inferencer.py (500 LOC)
class JavaTypeInferencer:
    """Infers types for Java IR nodes."""

    def infer_types(self, ir: IRDocument) -> None:
        """Infer types for all nodes."""
        for node in ir.nodes.values():
            if node.type is None:
                node.type = self._infer_type(node, ir)

    def _infer_type(self, node, ir): ...
    def _resolve_type(self, type_name): ...
    # ... 15+ type methods

# infrastructure/generators/java/import_resolver.py (307 LOC)
class JavaImportResolver:
    """Resolves Java imports to fully qualified names."""

    def resolve_imports(self, ir: IRDocument) -> None:
        """Resolve all imports in IR."""
        for node in ir.nodes.values():
            if node.kind == NodeKind.IMPORT:
                self._resolve_import(node, ir)

    def _resolve_import(self, node, ir): ...
    def _find_import(self, name, ir): ...
    # ... 10+ import methods
```

**Orchestrator** (Facade pattern):
```python
# infrastructure/generators/java/__init__.py
from .parser import JavaParser
from .ir_generator import JavaIRGenerator
from .edge_builder import JavaEdgeBuilder
from .type_inferencer import JavaTypeInferencer
from .import_resolver import JavaImportResolver

class JavaGeneratorFacade:
    """Facade for Java code generation pipeline."""

    def __init__(self):
        self.parser = JavaParser()
        self.ir_generator = JavaIRGenerator()
        self.edge_builder = JavaEdgeBuilder()
        self.type_inferencer = JavaTypeInferencer()
        self.import_resolver = JavaImportResolver()

    def generate_ir(self, source: str) -> IRDocument:
        """Generate complete IR from Java source."""
        ast = self.parser.parse(source)
        ir = self.ir_generator.generate(ast)
        self.edge_builder.build_edges(ir)
        self.type_inferencer.infer_types(ir)
        self.import_resolver.resolve_imports(ir)
        return ir

# Backward compatibility
JavaGenerator = JavaGeneratorFacade
```

**Benefits**:
- ✅ Each class has **single responsibility**
- ✅ Easier to test (unit test each class independently)
- ✅ Easier to understand (500-800 LOC per file)
- ✅ Easier to extend (OCP - add new type inference without touching parsing)
- ✅ Reusable components (JavaTypeInferencer can be reused for Kotlin)

**Migration Strategy**:
1. Create new directory structure
2. Extract each responsibility into new file
3. Add backward-compatible facade
4. Update imports (backward compatible)
5. Deprecate old monolith
6. Remove old file after 1 release

### 1.3. Refactoring Strategy: expression/builder.py (2,416 LOC)

**Current Structure**:
```python
# infrastructure/semantic_ir/expression/builder.py (2,416 LOC)
class ExpressionBuilder:
    """Builds expression tree for semantic IR."""

    # Responsibility 1: Expression parsing (800 LOC)
    def build_expression(self, node): ...
    def parse_binary_op(self, node): ...
    def parse_unary_op(self, node): ...
    # ... 40+ parse methods

    # Responsibility 2: Type checking (900 LOC)
    def check_type(self, expr): ...
    def unify_types(self, t1, t2): ...
    def infer_expression_type(self, expr): ...
    # ... 30+ type check methods

    # Responsibility 3: SSA conversion (516 LOC)
    def convert_to_ssa(self, expr): ...
    def phi_node_insertion(self): ...
    def rename_variables(self): ...
    # ... 15+ SSA methods

    # Responsibility 4: CFG integration (200 LOC)
    def build_cfg_edges(self, expr): ...
    def link_to_cfg(self, expr, cfg): ...
    # ... 10+ CFG methods
```

**Target Structure**:
```
infrastructure/semantic_ir/expression/
├── __init__.py              # Re-exports + facade
├── parser.py                # ExpressionParser (800 LOC)
├── type_checker.py          # ExpressionTypeChecker (900 LOC)
├── ssa_converter.py         # SSAConverter (516 LOC)
└── cfg_linker.py            # CFGLinker (200 LOC)
```

**Similar refactoring approach** as java_generator.py.

### 1.4. Refactoring Strategy: semantic_ir/builder.py (2,210 LOC)

**Current Structure**:
```python
# infrastructure/semantic_ir/builder.py (2,210 LOC)
class SemanticIRBuilder:
    """Builds complete semantic IR (BFG, CFG, DFG, SSA)."""

    # Responsibility 1: BFG building (600 LOC)
    def build_bfg(self, ir: IRDocument): ...
    def extract_blocks(self): ...
    def build_control_flow(self): ...
    # ... 25+ BFG methods

    # Responsibility 2: CFG building (550 LOC)
    def build_cfg(self, bfg): ...
    def compute_dominators(self): ...
    def build_dominance_tree(self): ...
    # ... 20+ CFG methods

    # Responsibility 3: DFG building (520 LOC)
    def build_dfg(self, cfg): ...
    def compute_def_use(self): ...
    def build_use_def_chains(self): ...
    # ... 20+ DFG methods

    # Responsibility 4: SSA construction (340 LOC)
    def build_ssa(self, dfg): ...
    def insert_phi_nodes(self): ...
    def rename_ssa_vars(self): ...
    # ... 12+ SSA methods

    # Responsibility 5: Type linking (200 LOC)
    def link_types(self, ir): ...
    def resolve_type_refs(self): ...
    # ... 8+ type methods
```

**Target Structure**:
```
infrastructure/semantic_ir/
├── __init__.py              # Re-exports + facade
├── bfg_builder.py           # BFGBuilder (600 LOC)
├── cfg_builder.py           # CFGBuilder (550 LOC)
├── dfg_builder.py           # DFGBuilder (520 LOC)
├── ssa_builder.py           # SSABuilder (340 LOC)
└── type_linker.py           # TypeLinker (200 LOC)
```

**Facade**:
```python
# infrastructure/semantic_ir/__init__.py
class SemanticIRBuilderFacade:
    """Facade for semantic IR pipeline."""

    def __init__(self):
        self.bfg_builder = BFGBuilder()
        self.cfg_builder = CFGBuilder()
        self.dfg_builder = DFGBuilder()
        self.ssa_builder = SSABuilder()
        self.type_linker = TypeLinker()

    def build_semantic_ir(self, ir: IRDocument) -> SemanticIR:
        """Build complete semantic IR."""
        bfg = self.bfg_builder.build_bfg(ir)
        cfg = self.cfg_builder.build_cfg(bfg)
        dfg = self.dfg_builder.build_dfg(cfg)
        ssa = self.ssa_builder.build_ssa(dfg)
        self.type_linker.link_types(ssa)
        return SemanticIR(bfg, cfg, dfg, ssa)
```

### 1.5. Testing Strategy

**For each refactored component**:

1. **Extract existing tests**:
   ```bash
   # Find all tests for java_generator.py
   grep -r "java_generator" tests/
   # Extract to tests/infrastructure/generators/java/
   ```

2. **Add unit tests** for each new class:
   ```python
   # tests/infrastructure/generators/java/test_parser.py
   def test_java_parser_parse_class():
       parser = JavaParser()
       ast = parser.parse("class Foo {}")
       assert len(ast.nodes) == 1
       assert ast.nodes[0].kind == NodeKind.CLASS

   # tests/infrastructure/generators/java/test_ir_generator.py
   def test_java_ir_generator_generate():
       generator = JavaIRGenerator()
       ast = create_sample_ast()
       ir = generator.generate(ast)
       assert len(ir.nodes) > 0
   ```

3. **Integration tests** for facade:
   ```python
   # tests/infrastructure/generators/java/test_facade.py
   def test_java_generator_facade_e2e():
       facade = JavaGeneratorFacade()
       source = "class Foo { void bar() {} }"
       ir = facade.generate_ir(source)
       assert ir.get_node_by_name("Foo") is not None
       assert len(ir.edges) > 0  # Has call edges
   ```

4. **Golden tests** (regression):
   ```python
   # Ensure refactored output matches original
   def test_refactored_matches_original():
       old_generator = LegacyJavaGenerator()  # Keep old for 1 release
       new_generator = JavaGeneratorFacade()

       source = load_golden_test_case("java_sample.java")

       old_ir = old_generator.generate_ir(source)
       new_ir = new_generator.generate_ir(source)

       assert_ir_equivalent(old_ir, new_ir)
   ```

---

## Phase 2: BaseGenerator Extraction (Week 3)

### 2.1. Goal

**Eliminate 5,000 LOC duplication** across 5 language generators by extracting common base class.

### 2.2. Current Duplication Analysis

| Generator | LOC | Duplicated Logic | Unique Logic |
|-----------|-----|------------------|--------------|
| `java_generator.py` | 2,707 | ~1,200 (44%) | ~1,507 (56%) |
| `python_generator.py` | 1,080 | ~450 (42%) | ~630 (58%) |
| `typescript_generator.py` | 1,160 | ~500 (43%) | ~660 (57%) |
| `kotlin_generator.py` | 1,046 | ~450 (43%) | ~596 (57%) |
| `rust_generator.py` | ~800 | ~350 (44%) | ~450 (56%) |
| **Total** | **6,793** | **~2,950 (43%)** | **~3,843 (57%)** |

**Duplicated Patterns**:
1. AST traversal skeleton
2. Edge building (call, inheritance, dataflow)
3. Symbol extraction
4. Import resolution
5. Error handling

### 2.3. BaseGenerator Design (Template Method Pattern)

```python
# infrastructure/generators/base_generator.py (400 LOC)
from abc import ABC, abstractmethod
from typing import Protocol

class BaseGenerator(ABC):
    """Base class for all language generators.

    Uses Template Method pattern:
    - Concrete methods: Common logic (edge building, symbol extraction)
    - Abstract methods: Language-specific logic (parsing, type inference)
    """

    def __init__(self, language: Language):
        self.language = language
        self.tree_sitter_parser = self._create_parser()

    # ========================================================================
    # Template Method (Public API)
    # ========================================================================
    def generate_ir(self, source: str) -> IRDocument:
        """Generate IR from source code (template method).

        Steps:
        1. Parse source to AST (language-specific)
        2. Generate IR from AST (language-specific)
        3. Build edges (common logic)
        4. Infer types (language-specific)
        5. Resolve imports (common logic with language hooks)
        """
        ast = self.parse(source)              # Abstract
        ir = self._generate_ir_from_ast(ast)  # Abstract
        self._build_edges(ir)                  # Concrete (common)
        self._infer_types(ir)                  # Abstract
        self._resolve_imports(ir)              # Concrete (with hooks)
        return ir

    # ========================================================================
    # Abstract Methods (Language-Specific)
    # ========================================================================
    @abstractmethod
    def parse(self, source: str) -> ASTDocument:
        """Parse source code to AST (language-specific)."""
        pass

    @abstractmethod
    def _generate_ir_from_ast(self, ast: ASTDocument) -> IRDocument:
        """Generate IR from AST (language-specific)."""
        pass

    @abstractmethod
    def _infer_types(self, ir: IRDocument) -> None:
        """Infer types for IR nodes (language-specific)."""
        pass

    @abstractmethod
    def _get_import_statement_kind(self) -> NodeKind:
        """Get language-specific import statement kind."""
        pass

    # ========================================================================
    # Concrete Methods (Common Logic)
    # ========================================================================
    def _build_edges(self, ir: IRDocument) -> None:
        """Build all edges (common logic)."""
        self._build_call_edges(ir)
        self._build_inheritance_edges(ir)
        self._build_dataflow_edges(ir)

    def _build_call_edges(self, ir: IRDocument) -> None:
        """Build call edges (common algorithm)."""
        for node in ir.nodes.values():
            if node.kind == NodeKind.CALL:
                caller = node
                callee = ir.get_node_by_name(node.target_name)
                if callee:
                    edge = Edge(
                        from_id=caller.id,
                        to_id=callee.id,
                        kind=EdgeKind.CALL,
                    )
                    ir.add_edge(edge)

    def _build_inheritance_edges(self, ir: IRDocument) -> None:
        """Build inheritance edges (common algorithm)."""
        for node in ir.nodes.values():
            if node.kind == NodeKind.CLASS and node.base_classes:
                for base_name in node.base_classes:
                    base = ir.get_node_by_name(base_name)
                    if base:
                        edge = Edge(
                            from_id=node.id,
                            to_id=base.id,
                            kind=EdgeKind.INHERITS,
                        )
                        ir.add_edge(edge)

    def _build_dataflow_edges(self, ir: IRDocument) -> None:
        """Build dataflow edges (common algorithm)."""
        # Def-use chain construction (language-agnostic)
        for node in ir.nodes.values():
            if node.kind == NodeKind.ASSIGNMENT:
                lhs = node.lhs
                rhs = node.rhs
                # ... dataflow logic

    def _resolve_imports(self, ir: IRDocument) -> None:
        """Resolve imports (common logic with language hook)."""
        import_kind = self._get_import_statement_kind()  # Hook
        for node in ir.nodes.values():
            if node.kind == import_kind:
                self._resolve_import(node, ir)

    def _resolve_import(self, node: Node, ir: IRDocument) -> None:
        """Resolve single import (common logic)."""
        imported_name = node.imported_name
        # ... common import resolution logic

    # ========================================================================
    # Helper Methods (Common Utilities)
    # ========================================================================
    def extract_symbol(self, node: Node) -> Symbol:
        """Extract symbol from node (common logic)."""
        return Symbol(
            name=self._get_node_name(node),
            type=self._infer_node_type(node),
            kind=node.kind,
        )

    def _get_node_name(self, node: Node) -> str:
        """Get node name from AST (common logic)."""
        if hasattr(node, 'name'):
            return node.name
        elif hasattr(node, 'identifier'):
            return node.identifier
        else:
            return f"anonymous_{node.id}"

    def _create_parser(self):
        """Create tree-sitter parser for language."""
        import tree_sitter
        return tree_sitter.Parser()
```

### 2.4. Language-Specific Implementations

**Java Generator** (reduced from 2,707 → ~1,507 LOC):
```python
# infrastructure/generators/java_generator.py (1,507 LOC)
from .base_generator import BaseGenerator

class JavaGenerator(BaseGenerator):
    """Java code generator (inherits common logic)."""

    def __init__(self):
        super().__init__(Language.JAVA)

    # ========================================================================
    # Language-Specific Implementations
    # ========================================================================
    def parse(self, source: str) -> ASTDocument:
        """Parse Java source to AST."""
        tree = self.tree_sitter_parser.parse(source.encode())
        return self._build_ast_from_tree(tree.root_node)

    def _generate_ir_from_ast(self, ast: ASTDocument) -> IRDocument:
        """Generate IR from Java AST."""
        ir = IRDocument.new()
        for ast_node in ast.nodes:
            ir_node = self._convert_ast_node(ast_node)
            ir.add_node(ir_node)
        return ir

    def _infer_types(self, ir: IRDocument) -> None:
        """Infer types for Java IR."""
        # Java-specific type inference (generics, primitives, etc.)
        for node in ir.nodes.values():
            if node.type is None:
                node.type = self._infer_java_type(node, ir)

    def _get_import_statement_kind(self) -> NodeKind:
        """Java imports."""
        return NodeKind.IMPORT

    # ========================================================================
    # Java-Specific Helpers
    # ========================================================================
    def _infer_java_type(self, node: Node, ir: IRDocument) -> Type:
        """Infer Java-specific types (generics, primitives)."""
        if node.kind == NodeKind.PRIMITIVE:
            return PrimitiveType(node.primitive_kind)
        elif node.kind == NodeKind.GENERIC:
            return self._infer_generic_type(node, ir)
        else:
            return self._infer_class_type(node, ir)

    def _infer_generic_type(self, node: Node, ir: IRDocument) -> Type:
        """Infer Java generic type (List<T>, Map<K, V>)."""
        # ... Java-specific generic inference
```

**Python Generator** (reduced from 1,080 → ~630 LOC):
```python
# infrastructure/generators/python_generator.py (630 LOC)
from .base_generator import BaseGenerator

class PythonGenerator(BaseGenerator):
    """Python code generator (inherits common logic)."""

    def __init__(self):
        super().__init__(Language.PYTHON)

    def parse(self, source: str) -> ASTDocument:
        """Parse Python source to AST."""
        # Python-specific parsing (indentation, decorators, etc.)
        ...

    def _generate_ir_from_ast(self, ast: ASTDocument) -> IRDocument:
        """Generate IR from Python AST."""
        # Python-specific IR generation (duck typing, dynamic attrs)
        ...

    def _infer_types(self, ir: IRDocument) -> None:
        """Infer types for Python IR (gradual typing)."""
        # Python-specific type inference (type hints, runtime types)
        ...

    def _get_import_statement_kind(self) -> NodeKind:
        """Python imports (import, from...import)."""
        return NodeKind.IMPORT  # Handles both "import" and "from...import"
```

**Similar for TypeScript, Kotlin, Rust generators**.

### 2.5. Expected Reduction

| Generator | Before | After | Reduction |
|-----------|--------|-------|-----------|
| BaseGenerator (new) | 0 | 400 | +400 (shared) |
| JavaGenerator | 2,707 | 1,507 | -1,200 |
| PythonGenerator | 1,080 | 630 | -450 |
| TypeScriptGenerator | 1,160 | 660 | -500 |
| KotlinGenerator | 1,046 | 596 | -450 |
| RustGenerator | 800 | 450 | -350 |
| **Total** | **6,793** | **4,243** | **-2,550 LOC (38% reduction)** |

**Net savings**: ~2,550 LOC eliminated (accounting for 400 LOC base class).

---

## Phase 3: Domain Model Enrichment (Week 4)

### 3.1. Problem: Anemic Domain Model

**Current State** (domain/models.py):
```python
@dataclass
class IRDocument:
    """IR Document representation."""
    id: str
    nodes: Dict[str, Node]
    edges: List[Edge]
    types: TypeIndex
    # ❌ NO BEHAVIOR! Just data.
```

**Business logic scattered in infrastructure**:
- `semantic_ir/builder.py`: IR construction logic
- `generators/`: Node creation logic
- `graph/builder.py`: Edge building logic

### 3.2. Target: Rich Domain Model

**Enrich IRDocument with behavior**:
```python
# domain/models.py
@dataclass
class IRDocument:
    """IR Document (Aggregate Root)."""
    id: str
    nodes: Dict[str, Node]
    edges: List[Edge]
    types: TypeIndex
    _node_index: Dict[str, Node] = field(default_factory=dict, init=False)
    _edge_index: Dict[str, List[Edge]] = field(default_factory=dict, init=False)

    # ========================================================================
    # Factory Methods
    # ========================================================================
    @classmethod
    def new(cls, id: Optional[str] = None) -> "IRDocument":
        """Create new IR document."""
        return cls(
            id=id or uuid.uuid4().hex,
            nodes={},
            edges=[],
            types=TypeIndex(),
        )

    # ========================================================================
    # Aggregate Operations (Encapsulation)
    # ========================================================================
    def add_node(self, node: Node) -> None:
        """Add node with validation (domain rule)."""
        # Domain rule: No duplicate nodes
        if node.id in self.nodes:
            raise DomainError(f"Duplicate node: {node.id}")

        # Domain rule: Node must have valid kind
        if not isinstance(node.kind, NodeKind):
            raise DomainError(f"Invalid node kind: {node.kind}")

        self.nodes[node.id] = node
        self._rebuild_node_index()

    def add_edge(self, edge: Edge) -> None:
        """Add edge with validation (domain rule)."""
        # Domain rule: Both nodes must exist
        if edge.from_id not in self.nodes:
            raise DomainError(f"Source node not found: {edge.from_id}")
        if edge.to_id not in self.nodes:
            raise DomainError(f"Target node not found: {edge.to_id}")

        # Domain rule: No duplicate edges
        if self._has_edge(edge.from_id, edge.to_id, edge.kind):
            return  # Idempotent

        self.edges.append(edge)
        self._rebuild_edge_index()

    def remove_node(self, node_id: str) -> None:
        """Remove node and all connected edges (domain rule)."""
        if node_id not in self.nodes:
            raise DomainError(f"Node not found: {node_id}")

        # Domain rule: Remove all edges connected to this node
        self.edges = [
            e for e in self.edges
            if e.from_id != node_id and e.to_id != node_id
        ]

        del self.nodes[node_id]
        self._rebuild_indexes()

    # ========================================================================
    # Domain Queries
    # ========================================================================
    def get_node_by_name(self, name: str) -> Optional[Node]:
        """Find node by symbol name (domain query)."""
        return self._node_index.get(name)

    def get_outgoing_edges(self, node_id: str) -> List[Edge]:
        """Get all edges from a node (domain query)."""
        return self._edge_index.get(node_id, [])

    def get_callers(self, function_id: str) -> List[Node]:
        """Get all callers of a function (domain query)."""
        caller_ids = [
            e.from_id for e in self.edges
            if e.to_id == function_id and e.kind == EdgeKind.CALL
        ]
        return [self.nodes[cid] for cid in caller_ids if cid in self.nodes]

    def get_callees(self, function_id: str) -> List[Node]:
        """Get all callees of a function (domain query)."""
        callee_ids = [
            e.to_id for e in self.edges
            if e.from_id == function_id and e.kind == EdgeKind.CALL
        ]
        return [self.nodes[cid] for cid in callee_ids if cid in self.nodes]

    def find_symbol(self, name: str, kind: Optional[NodeKind] = None) -> Optional[Node]:
        """Find symbol by name and kind (domain query)."""
        candidates = [
            node for node in self.nodes.values()
            if node.name == name
        ]

        if kind:
            candidates = [n for n in candidates if n.kind == kind]

        return candidates[0] if candidates else None

    # ========================================================================
    # Domain Invariants
    # ========================================================================
    def validate_invariants(self) -> List[str]:
        """Validate domain invariants (consistency check)."""
        errors = []

        # Invariant 1: All edges reference existing nodes
        for edge in self.edges:
            if edge.from_id not in self.nodes:
                errors.append(f"Edge references missing source node: {edge.from_id}")
            if edge.to_id not in self.nodes:
                errors.append(f"Edge references missing target node: {edge.to_id}")

        # Invariant 2: No duplicate nodes
        if len(self.nodes) != len(set(self.nodes.keys())):
            errors.append("Duplicate node IDs found")

        # Invariant 3: Node names are unique within kind
        name_kind_pairs = [(n.name, n.kind) for n in self.nodes.values() if n.name]
        if len(name_kind_pairs) != len(set(name_kind_pairs)):
            errors.append("Duplicate (name, kind) pairs found")

        return errors

    # ========================================================================
    # Private Helpers
    # ========================================================================
    def _rebuild_indexes(self) -> None:
        """Rebuild all indexes."""
        self._rebuild_node_index()
        self._rebuild_edge_index()

    def _rebuild_node_index(self) -> None:
        """Rebuild node name index."""
        self._node_index = {
            node.name: node
            for node in self.nodes.values()
            if node.name
        }

    def _rebuild_edge_index(self) -> None:
        """Rebuild edge index (outgoing edges per node)."""
        self._edge_index = {}
        for edge in self.edges:
            if edge.from_id not in self._edge_index:
                self._edge_index[edge.from_id] = []
            self._edge_index[edge.from_id].append(edge)

    def _has_edge(self, from_id: str, to_id: str, kind: EdgeKind) -> bool:
        """Check if edge already exists."""
        return any(
            e.from_id == from_id and e.to_id == to_id and e.kind == kind
            for e in self.edges
        )
```

### 3.3. Move Business Logic from Infrastructure to Domain

**Before** (infrastructure knows domain rules):
```python
# infrastructure/semantic_ir/builder.py (WRONG)
class SemanticIRBuilder:
    def add_node_to_ir(self, ir: IRDocument, node: Node):
        # ❌ Business logic in infrastructure
        if node.id in ir.nodes:
            raise ValueError("Duplicate node")  # Domain rule!
        ir.nodes[node.id] = node
```

**After** (domain enforces own rules):
```python
# domain/models.py (CORRECT)
class IRDocument:
    def add_node(self, node: Node):
        # ✅ Business logic in domain
        if node.id in self.nodes:
            raise DomainError("Duplicate node")
        self.nodes[node.id] = node

# infrastructure/semantic_ir/builder.py (CLEAN)
class SemanticIRBuilder:
    def add_node_to_ir(self, ir: IRDocument, node: Node):
        # ✅ Infrastructure uses domain API
        ir.add_node(node)  # Domain enforces rules
```

### 3.4. Domain Services

**Extract complex domain logic into services**:
```python
# domain/services/symbol_resolution.py
class SymbolResolver:
    """Domain service for symbol resolution."""

    def resolve_symbol(
        self,
        name: str,
        scope: Scope,
        ir: IRDocument
    ) -> Optional[Symbol]:
        """Resolve symbol in scope (domain logic)."""
        # 1. Check local scope
        local_symbol = self._find_in_scope(name, scope)
        if local_symbol:
            return local_symbol

        # 2. Check parent scopes
        parent_symbol = self._find_in_parent_scopes(name, scope, ir)
        if parent_symbol:
            return parent_symbol

        # 3. Check imports
        imported_symbol = self._find_in_imports(name, ir)
        return imported_symbol

    def _find_in_scope(self, name: str, scope: Scope) -> Optional[Symbol]:
        """Find symbol in local scope."""
        # ... domain logic

    def _find_in_parent_scopes(self, name: str, scope: Scope, ir: IRDocument) -> Optional[Symbol]:
        """Find symbol in parent scopes (lexical scoping)."""
        # ... domain logic

    def _find_in_imports(self, name: str, ir: IRDocument) -> Optional[Symbol]:
        """Find symbol in imports."""
        # ... domain logic
```

**Usage in infrastructure**:
```python
# infrastructure/generators/java_generator.py
class JavaGenerator:
    def __init__(self):
        self.symbol_resolver = SymbolResolver()  # Domain service

    def resolve_type(self, name: str, scope: Scope, ir: IRDocument) -> Optional[Type]:
        symbol = self.symbol_resolver.resolve_symbol(name, scope, ir)
        return symbol.type if symbol else None
```

---

## Phase 4: Adapter Layer Creation (Week 4)

### 4.1. Problem: Adapter Layer Collapse

**Current State**:
- Only **2 adapter files** for 41 infrastructure subdirectories
- Adapters are **inline in infrastructure** (anti-pattern)

**Example Violation**:
```
infrastructure/generators/python_generator.py  # ❌ Adapter in infrastructure
infrastructure/lsp/pyright_lsp.py             # ❌ Adapter in infrastructure
infrastructure/search/qdrant_adapter.py        # ❌ Adapter in infrastructure
```

### 4.2. Target Structure

```
adapters/
├── __init__.py
├── generators/              # Language generator adapters
│   ├── __init__.py
│   ├── java_adapter.py      # JavaGeneratorAdapter
│   ├── python_adapter.py    # PythonGeneratorAdapter
│   ├── typescript_adapter.py
│   ├── kotlin_adapter.py
│   └── rust_adapter.py
├── semantic_ir/             # Semantic IR adapters
│   ├── __init__.py
│   ├── bfg_adapter.py       # BFGBuilderAdapter
│   ├── cfg_adapter.py
│   ├── dfg_adapter.py
│   └── ssa_adapter.py
├── lsp/                     # LSP client adapters
│   ├── __init__.py
│   ├── pyright_adapter.py
│   └── kotlin_lsp_adapter.py
├── search/                  # Search backend adapters
│   ├── __init__.py
│   ├── qdrant_adapter.py
│   └── tantivy_adapter.py
└── cache/                   # Cache implementation adapters
    ├── __init__.py
    ├── semantic_cache_adapter.py
    └── structural_cache_adapter.py
```

### 4.3. Adapter Pattern Implementation

**Port (defined in domain/ports/)**:
```python
# domain/ports/generator_port.py
class GeneratorPort(Protocol):
    """Port for code generators (DIP)."""

    def generate_ir(self, source: str) -> IRDocument:
        """Generate IR from source code."""
        ...
```

**Infrastructure** (pure implementation, no domain knowledge):
```python
# infrastructure/generators/java/core.py
class JavaGeneratorCore:
    """Core Java generation logic (pure infrastructure).

    No knowledge of domain ports or abstractions.
    """

    def parse_java(self, source: str) -> JavaAST:
        """Parse Java source (infrastructure concern)."""
        ...

    def convert_to_ir(self, ast: JavaAST) -> JavaIR:
        """Convert Java AST to IR (infrastructure)."""
        ...
```

**Adapter** (bridges infrastructure to domain port):
```python
# adapters/generators/java_adapter.py
from domain.ports.generator_port import GeneratorPort
from infrastructure.generators.java.core import JavaGeneratorCore

class JavaGeneratorAdapter(GeneratorPort):
    """Adapter: JavaGeneratorCore → GeneratorPort.

    Bridges infrastructure implementation to domain abstraction.
    """

    def __init__(self):
        self._core = JavaGeneratorCore()

    def generate_ir(self, source: str) -> IRDocument:
        """Generate IR (implements port)."""
        # 1. Use infrastructure to parse
        java_ast = self._core.parse_java(source)

        # 2. Convert to IR
        java_ir = self._core.convert_to_ir(java_ast)

        # 3. Convert infrastructure IR to domain IRDocument
        return self._convert_to_domain_ir(java_ir)

    def _convert_to_domain_ir(self, java_ir: JavaIR) -> IRDocument:
        """Convert infrastructure IR to domain IR."""
        ir_doc = IRDocument.new()
        for node in java_ir.nodes:
            ir_doc.add_node(self._convert_node(node))
        return ir_doc
```

**Dependency Flow** (DIP enforced):
```
Application → GeneratorPort (abstraction) ← JavaGeneratorAdapter → JavaGeneratorCore
                  ↑ (depends on)                ↑ (implements)         ↑ (wraps)
               (Domain)                       (Adapter)              (Infrastructure)
```

### 4.4. Migration Strategy

1. **Create adapters/ directory structure** (Week 4, Day 1)
2. **Move generator adapters** (Week 4, Day 2-3):
   - Extract adapter logic from `infrastructure/generators/`
   - Keep core implementation in infrastructure
   - Create adapter wrapper in `adapters/generators/`
3. **Move LSP adapters** (Week 4, Day 4):
   - Extract LSP client adapters
4. **Move search/cache adapters** (Week 4, Day 5):
   - Extract Qdrant, Tantivy adapters
5. **Update DI container** (Week 4, Day 5):
   ```python
   # DI container now wires adapters
   @cached_property
   def java_generator(self) -> GeneratorPort:
       return JavaGeneratorAdapter()  # ← Adapter, not infrastructure
   ```

---

## Phase 5: Rust Migration (Week 5-8)

**See separate RUST_MIGRATION_PLAN.md** (will be created next).

**Summary**:
- Week 5-6: Migrate generators (Java, Python) → **20-35x speedup**
- Week 7-8: Migrate semantic IR builders → **25-45x speedup**

---

## Testing Strategy

### Regression Testing (Critical)

**Golden Test Suite**:
```python
# tests/golden/test_regression.py
def test_refactored_ir_matches_baseline():
    """Ensure refactored code produces identical IR."""
    baseline_generator = load_baseline_generator()  # Pre-refactor
    refactored_generator = JavaGeneratorFacade()    # Post-refactor

    for test_case in load_golden_test_cases():
        baseline_ir = baseline_generator.generate_ir(test_case.source)
        refactored_ir = refactored_generator.generate_ir(test_case.source)

        assert_ir_equivalent(baseline_ir, refactored_ir)
```

### Unit Testing (Per Component)

**Each refactored component gets unit tests**:
```python
# tests/infrastructure/generators/java/test_parser.py
def test_java_parser_parses_class():
    parser = JavaParser()
    ast = parser.parse("class Foo {}")
    assert len(ast.nodes) == 1

# tests/infrastructure/generators/java/test_ir_generator.py
def test_java_ir_generator_generates_nodes():
    generator = JavaIRGenerator()
    ast = create_sample_ast()
    ir = generator.generate(ast)
    assert len(ir.nodes) > 0
```

### Integration Testing

**Test complete pipeline**:
```python
# tests/integration/test_java_pipeline.py
def test_java_generation_pipeline_e2e():
    facade = JavaGeneratorFacade()
    source = load_sample_java_file()
    ir = facade.generate_ir(source)

    # Verify IR correctness
    assert ir.get_node_by_name("MyClass") is not None
    assert len(ir.edges) > 0
    assert ir.validate_invariants() == []  # No errors
```

---

## Rollout Strategy

### Week 1-2: God Class Refactoring

**Deliverables**:
- [ ] Refactor `java_generator.py` (2,707 → 5 classes)
- [ ] Refactor `expression/builder.py` (2,416 → 4 classes)
- [ ] Refactor `semantic_ir/builder.py` (2,210 → 5 classes)
- [ ] All tests passing (golden + unit + integration)
- [ ] Backward compatibility maintained (facade pattern)

**Success Criteria**:
- ✅ 0 files >1000 LOC in refactored components
- ✅ All existing tests pass
- ✅ Golden tests confirm identical behavior

### Week 3: BaseGenerator Extraction

**Deliverables**:
- [ ] Create `BaseGenerator` abstract class (400 LOC)
- [ ] Migrate all 5 generators to inherit from `BaseGenerator`
- [ ] Remove 2,550 LOC duplication
- [ ] All tests passing

**Success Criteria**:
- ✅ 2,550 LOC duplication eliminated
- ✅ All generator tests pass
- ✅ Golden tests confirm identical behavior

### Week 4: Domain Enrichment + Adapter Layer

**Deliverables**:
- [ ] Enrich `IRDocument` with 50+ methods
- [ ] Move business logic from infrastructure to domain
- [ ] Create `adapters/` directory structure
- [ ] Migrate all adapters (generators, LSP, search, cache)

**Success Criteria**:
- ✅ Domain model has rich behavior (50+ methods)
- ✅ 40+ adapter files created
- ✅ Proper hexagonal architecture (adapters separate from infrastructure)

### Week 5-8: Rust Migration

**See RUST_MIGRATION_PLAN.md**

---

## Risks & Mitigations

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| **Breaking changes** | Medium | High | Golden tests, backward compatibility facades |
| **Performance regression** | Low | High | Benchmark suite, CI performance tests |
| **Incomplete migration** | Low | Medium | Phased rollout, feature flags |
| **Test failures** | Medium | Medium | Comprehensive test coverage before refactoring |

---

## Success Metrics

| Metric | Target | Measurement |
|--------|--------|-------------|
| **God Classes (>1000 LOC)** | 0 files | `find . -name "*.py" | xargs wc -l | awk '$1 > 1000'` |
| **Code Duplication** | <10% | SonarQube, PMD-CPD |
| **Domain Behavior** | 50+ methods | Count public methods in `IRDocument` |
| **Adapter Layer** | 40+ files | `ls adapters/ | wc -l` |
| **Test Coverage** | >80% | pytest-cov |
| **Performance** | No regression | Benchmark suite (golden test runtime) |

---

## Next Steps

1. **Review this plan** with team
2. **Create RUST_MIGRATION_PLAN.md** (Week 5-8 details)
3. **Start Week 1** refactoring (java_generator.py)

---

**Date:** 2025-12-29
**Status:** ✅ Plan Complete
**Next:** Execute Week 1-2 (God Class Refactoring)
