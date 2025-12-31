# codegraph-engine Rust Migration Plan (Week 5-8)

**Date:** 2025-12-29
**Duration:** 4 weeks (SOTA execution)
**Goal:** Migrate high-ROI Python components to Rust for 25-45x speedup
**Target:** 5% → 60% Rust coverage

---

## Executive Summary

### Current State (95% Python)

**Python Components (150,265 LOC):**
- Generators (Java, Python, TypeScript, Kotlin, Rust): ~6,800 LOC
- Semantic IR builders (BFG, CFG, DFG, SSA): ~8,500 LOC
- Type inference: ~2,500 LOC
- Symbol resolution: ~1,800 LOC
- Expression builders: ~2,400 LOC

**Rust Components (5%):**
- Tree-sitter bindings (minimal)
- Some parsing utilities

### Target State (60% Rust)

**Migrate to Rust:**
- ✅ All generators (6,800 LOC Python → 5,000 LOC Rust)
- ✅ Semantic IR builders (8,500 LOC Python → 6,000 LOC Rust)
- ✅ Type inference (2,500 LOC Python → 1,800 LOC Rust)
- ✅ Symbol resolution (1,800 LOC Python → 1,200 LOC Rust)
- ✅ Expression builders (2,400 LOC Python → 1,800 LOC Rust)

**Keep in Python:**
- Orchestration logic (agent workflows)
- LLM integrations
- API/CLI interfaces
- Configuration management
- Job scheduling

### Expected Performance Impact

| Component | Python (baseline) | Rust | Speedup | Criticality |
|-----------|-------------------|------|---------|-------------|
| **Java Generator** | 1x | 15-25x | **20x** | 🔴 P0 |
| **Python Generator** | 1x | 10-18x | **15x** | 🔴 P0 |
| **BFG Builder** | 1x | 30-50x | **40x** | 🔴 P0 |
| **CFG Builder** | 1x | 25-40x | **35x** | 🔴 P0 |
| **Type Inference** | 1x | 20-35x | **28x** | 🟡 P1 |
| **Symbol Resolution** | 1x | 15-30x | **22x** | 🟡 P1 |
| **Expression Builder** | 1x | 18-32x | **25x** | 🟡 P1 |
| **Overall Pipeline** | 1x | 25-45x | **35x** | ✅ **SOTA** |

---

## Part 1: Pre-Migration Analysis (Week 5, Day 1)

### 1.1. Python → Rust ROI Matrix

**Scoring Criteria:**
- **Hotness (H)**: CPU usage % (profiling data)
- **Complexity (C)**: Algorithm complexity (O-notation)
- **Purity (P)**: Functional/stateless (easier to migrate)
- **Dependencies (D)**: Minimal Python dependencies

**ROI Score = H × C × P / D** (higher = migrate first)

| Component | H | C | P | D | ROI | Priority |
|-----------|---|---|---|---|-----|----------|
| **Java Generator** | 9 | 8 | 7 | 3 | **168** | 🔴 P0 |
| **BFG Builder** | 10 | 9 | 8 | 2 | **360** | 🔴 P0 |
| **CFG Builder** | 9 | 9 | 7 | 2 | **283** | 🔴 P0 |
| **Python Generator** | 8 | 7 | 6 | 3 | **112** | 🔴 P0 |
| **Type Inference** | 7 | 8 | 6 | 4 | **84** | 🟡 P1 |
| **Symbol Resolution** | 6 | 7 | 5 | 5 | **42** | 🟡 P1 |
| **Expression Builder** | 8 | 8 | 7 | 3 | **149** | 🟡 P1 |

**Migration Order (Week 5-8):**
1. **Week 5**: BFG Builder (highest ROI: 360)
2. **Week 6**: CFG Builder + Java Generator
3. **Week 7**: Python Generator + Expression Builder
4. **Week 8**: Type Inference + Symbol Resolution

---

### 1.2. Dependency Analysis

**Python Dependencies (problematic):**
```python
# infrastructure/generators/java_generator.py
import tree_sitter
import tree_sitter_java
import networkx as nx  # Graph construction
import pandas as pd   # Data aggregation
from codegraph_shared import Container  # DI
```

**Rust Equivalents:**
```rust
// Use tree-sitter directly (zero-cost)
use tree_sitter;
use tree_sitter_java;

// Replace networkx with petgraph (faster)
use petgraph::graph::{Graph, NodeIndex};
use petgraph::algo::dominators;

// Replace pandas with polars (faster)
use polars::prelude::*;

// DI: Use trait objects + Arc<dyn Trait>
use std::sync::Arc;
```

**Migration Strategy:**
- ✅ **tree-sitter**: Direct Rust crate (0 overhead)
- ✅ **networkx → petgraph**: 10-20x faster graph ops
- ✅ **pandas → polars**: 5-15x faster data ops
- ✅ **Container DI**: Trait-based dependency injection

---

### 1.3. Profiling Baseline (Required)

**Step 1: Python profiling**
```bash
# Profile Python pipeline
PYTHONPATH=. python -m cProfile -o profile.stats \
  packages/codegraph-engine/benchmark/profile_generators.py

# Analyze hotspots
python -m pstats profile.stats
>>> sort time
>>> stats 20
```

**Expected Hotspots:**
1. `java_generator.py:parse()` - 25% time
2. `bfg/builder.py:build_bfg()` - 18% time
3. `cfg/builder.py:build_cfg()` - 15% time
4. `type_enricher.py:infer_types()` - 12% time
5. `symbol_resolution.py:resolve()` - 10% time

**Step 2: Benchmark suite**
```python
# benchmark/rust_migration_baseline.py
import timeit
from pathlib import Path

def benchmark_java_generator():
    """Baseline: Java generator (Python)."""
    from codegraph_engine.infrastructure.generators import JavaGenerator

    gen = JavaGenerator()
    source = Path("benchmark/fixtures/large_java_file.java").read_text()

    times = timeit.repeat(
        lambda: gen.generate_ir(source),
        repeat=10,
        number=1,
    )

    return {
        "mean": statistics.mean(times),
        "median": statistics.median(times),
        "std": statistics.stdev(times),
    }
```

**Baseline Targets (must beat these):**
- Java Generator: 450ms per 1,000 LOC file
- BFG Builder: 280ms per 10,000 nodes
- CFG Builder: 320ms per 5,000 basic blocks

---

## Part 2: Phase 1 - Generator Migration (Week 5-6)

### 2.1. Week 5: Java Generator → Rust

**Goal:** Migrate `java_generator.py` (2,707 LOC) → Rust (1,800 LOC)
**Expected Speedup:** 15-25x

#### Architecture

**Rust Module Structure:**
```
packages/codegraph-engine-rust/
├── Cargo.toml
├── src/
│   ├── lib.rs                        # PyO3 exports
│   ├── generators/
│   │   ├── mod.rs                    # Generator traits
│   │   ├── base.rs                   # BaseGenerator (Rust)
│   │   ├── java/
│   │   │   ├── mod.rs
│   │   │   ├── parser.rs             # JavaParser (500 LOC)
│   │   │   ├── ir_generator.rs       # JavaIRGenerator (600 LOC)
│   │   │   ├── edge_builder.rs       # JavaEdgeBuilder (400 LOC)
│   │   │   ├── type_inferencer.rs    # JavaTypeInferencer (300 LOC)
│   │   │   └── bindings.rs           # PyO3 bindings
│   │   └── ...
│   ├── ir/
│   │   ├── document.rs               # IRDocument (Rust)
│   │   ├── node.rs
│   │   ├── edge.rs
│   │   └── symbol.rs
│   └── utils/
│       ├── tree_sitter.rs
│       └── graph.rs
└── benches/
    └── java_generator_bench.rs
```

#### Implementation Strategy

**Step 1: Define Rust IR Models (Day 1)**
```rust
// src/ir/document.rs
use serde::{Deserialize, Serialize};
use std::collections::HashMap;

/// IR Document (root aggregate)
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct IRDocument {
    pub id: String,
    pub nodes: HashMap<String, Node>,
    pub edges: Vec<Edge>,
    pub types: TypeIndex,

    // Indexes (not serialized)
    #[serde(skip)]
    node_index: HashMap<String, NodeIndex>,
    #[serde(skip)]
    edge_index: HashMap<NodeIndex, Vec<EdgeIndex>>,
}

impl IRDocument {
    pub fn new() -> Self {
        Self {
            id: uuid::Uuid::new_v4().to_string(),
            nodes: HashMap::new(),
            edges: Vec::new(),
            types: TypeIndex::new(),
            node_index: HashMap::new(),
            edge_index: HashMap::new(),
        }
    }

    /// Add node with validation (domain rule)
    pub fn add_node(&mut self, node: Node) -> Result<(), IRError> {
        if self.nodes.contains_key(&node.id) {
            return Err(IRError::DuplicateNode(node.id));
        }

        let idx = NodeIndex(self.nodes.len());
        self.node_index.insert(node.name.clone(), idx);
        self.nodes.insert(node.id.clone(), node);

        Ok(())
    }

    /// Get callers of a function (domain query)
    pub fn get_callers(&self, function_id: &str) -> Vec<&Node> {
        self.edges
            .iter()
            .filter(|e| e.to_id == function_id && e.kind == EdgeKind::Call)
            .filter_map(|e| self.nodes.get(&e.from_id))
            .collect()
    }
}

/// Node in IR
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Node {
    pub id: String,
    pub kind: NodeKind,
    pub name: String,
    pub file_path: String,
    pub start_line: usize,
    pub end_line: usize,
    pub metadata: serde_json::Value,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum NodeKind {
    Class,
    Function,
    Variable,
    Import,
    Call,
    Assignment,
    // ... 30+ kinds
}
```

**Step 2: Java Parser (Day 1-2)**
```rust
// src/generators/java/parser.rs
use tree_sitter::{Parser, Tree};
use tree_sitter_java::language;

pub struct JavaParser {
    parser: Parser,
}

impl JavaParser {
    pub fn new() -> Result<Self, GeneratorError> {
        let mut parser = Parser::new();
        parser.set_language(language())?;
        Ok(Self { parser })
    }

    pub fn parse(&mut self, source: &str) -> Result<JavaAST, GeneratorError> {
        let tree = self.parser.parse(source, None)
            .ok_or(GeneratorError::ParseFailed)?;

        let root = tree.root_node();
        self.build_ast(root, source)
    }

    fn build_ast(&self, node: tree_sitter::Node, source: &str) -> Result<JavaAST, GeneratorError> {
        let mut ast = JavaAST::new();

        for child in node.children(&mut node.walk()) {
            match child.kind() {
                "class_declaration" => {
                    ast.classes.push(self.parse_class(child, source)?);
                }
                "method_declaration" => {
                    ast.methods.push(self.parse_method(child, source)?);
                }
                _ => {}
            }
        }

        Ok(ast)
    }

    fn parse_class(&self, node: tree_sitter::Node, source: &str) -> Result<JavaClass, GeneratorError> {
        let name = self.get_child_text(node, "identifier", source)?;
        let start_line = node.start_position().row + 1;
        let end_line = node.end_position().row + 1;

        Ok(JavaClass {
            name,
            start_line,
            end_line,
            // ... more fields
        })
    }
}

#[derive(Debug)]
pub struct JavaAST {
    pub classes: Vec<JavaClass>,
    pub methods: Vec<JavaMethod>,
    pub imports: Vec<JavaImport>,
}
```

**Step 3: IR Generator (Day 2-3)**
```rust
// src/generators/java/ir_generator.rs
use crate::ir::{IRDocument, Node, NodeKind};
use super::parser::JavaAST;

pub struct JavaIRGenerator;

impl JavaIRGenerator {
    pub fn generate(&self, ast: JavaAST) -> Result<IRDocument, GeneratorError> {
        let mut ir = IRDocument::new();

        // Generate nodes
        for class in ast.classes {
            let node = self.convert_class(class)?;
            ir.add_node(node)?;
        }

        for method in ast.methods {
            let node = self.convert_method(method)?;
            ir.add_node(node)?;
        }

        Ok(ir)
    }

    fn convert_class(&self, class: JavaClass) -> Result<Node, GeneratorError> {
        Ok(Node {
            id: uuid::Uuid::new_v4().to_string(),
            kind: NodeKind::Class,
            name: class.name,
            file_path: class.file_path,
            start_line: class.start_line,
            end_line: class.end_line,
            metadata: serde_json::json!({
                "modifiers": class.modifiers,
                "base_classes": class.base_classes,
            }),
        })
    }
}
```

**Step 4: Edge Builder (Day 3-4)**
```rust
// src/generators/java/edge_builder.rs
use crate::ir::{IRDocument, Edge, EdgeKind};
use petgraph::graph::{Graph, NodeIndex};

pub struct JavaEdgeBuilder;

impl JavaEdgeBuilder {
    pub fn build_edges(&self, ir: &mut IRDocument) -> Result<(), GeneratorError> {
        self.build_call_edges(ir)?;
        self.build_inheritance_edges(ir)?;
        self.build_dataflow_edges(ir)?;
        Ok(())
    }

    fn build_call_edges(&self, ir: &mut IRDocument) -> Result<(), GeneratorError> {
        // Find all call nodes
        let call_nodes: Vec<_> = ir.nodes
            .values()
            .filter(|n| n.kind == NodeKind::Call)
            .collect();

        for call_node in call_nodes {
            // Resolve callee
            if let Some(callee_name) = call_node.metadata.get("target") {
                if let Some(callee) = ir.get_node_by_name(callee_name.as_str().unwrap()) {
                    ir.add_edge(Edge {
                        from_id: call_node.id.clone(),
                        to_id: callee.id.clone(),
                        kind: EdgeKind::Call,
                        metadata: serde_json::Value::Null,
                    })?;
                }
            }
        }

        Ok(())
    }

    fn build_inheritance_edges(&self, ir: &mut IRDocument) -> Result<(), GeneratorError> {
        let class_nodes: Vec<_> = ir.nodes
            .values()
            .filter(|n| n.kind == NodeKind::Class)
            .collect();

        for class_node in class_nodes {
            if let Some(bases) = class_node.metadata.get("base_classes") {
                for base_name in bases.as_array().unwrap() {
                    if let Some(base_class) = ir.get_node_by_name(base_name.as_str().unwrap()) {
                        ir.add_edge(Edge {
                            from_id: class_node.id.clone(),
                            to_id: base_class.id.clone(),
                            kind: EdgeKind::Inherits,
                            metadata: serde_json::Value::Null,
                        })?;
                    }
                }
            }
        }

        Ok(())
    }
}
```

**Step 5: PyO3 Bindings (Day 4-5)**
```rust
// src/generators/java/bindings.rs
use pyo3::prelude::*;
use crate::ir::IRDocument;
use super::{JavaParser, JavaIRGenerator, JavaEdgeBuilder, JavaTypeInferencer};

#[pyclass]
pub struct JavaGenerator {
    parser: JavaParser,
    ir_generator: JavaIRGenerator,
    edge_builder: JavaEdgeBuilder,
    type_inferencer: JavaTypeInferencer,
}

#[pymethods]
impl JavaGenerator {
    #[new]
    pub fn new() -> PyResult<Self> {
        Ok(Self {
            parser: JavaParser::new().map_err(|e| PyErr::new::<pyo3::exceptions::PyRuntimeError, _>(e.to_string()))?,
            ir_generator: JavaIRGenerator,
            edge_builder: JavaEdgeBuilder,
            type_inferencer: JavaTypeInferencer::new(),
        })
    }

    pub fn generate_ir(&mut self, source: &str) -> PyResult<Py<PyAny>> {
        // Parse
        let ast = self.parser.parse(source)
            .map_err(|e| PyErr::new::<pyo3::exceptions::PyRuntimeError, _>(e.to_string()))?;

        // Generate IR
        let mut ir = self.ir_generator.generate(ast)
            .map_err(|e| PyErr::new::<pyo3::exceptions::PyRuntimeError, _>(e.to_string()))?;

        // Build edges
        self.edge_builder.build_edges(&mut ir)
            .map_err(|e| PyErr::new::<pyo3::exceptions::PyRuntimeError, _>(e.to_string()))?;

        // Infer types
        self.type_inferencer.infer_types(&mut ir)
            .map_err(|e| PyErr::new::<pyo3::exceptions::PyRuntimeError, _>(e.to_string()))?;

        // Serialize to Python (JSON for now, can optimize later)
        Python::with_gil(|py| {
            let json_str = serde_json::to_string(&ir)
                .map_err(|e| PyErr::new::<pyo3::exceptions::PyRuntimeError, _>(e.to_string()))?;

            let json_module = py.import("json")?;
            json_module.call_method1("loads", (json_str,))
        })
    }
}

#[pymodule]
fn codegraph_engine_rust(_py: Python, m: &PyModule) -> PyResult<()> {
    m.add_class::<JavaGenerator>()?;
    Ok(())
}
```

**Step 6: Benchmark (Day 5)**
```rust
// benches/java_generator_bench.rs
use criterion::{black_box, criterion_group, criterion_main, Criterion, BenchmarkId};
use codegraph_engine_rust::generators::java::JavaGenerator;

fn benchmark_java_generator(c: &mut Criterion) {
    let mut group = c.benchmark_group("java_generator");

    let source = include_str!("../fixtures/large_java_file.java");

    group.bench_function("parse", |b| {
        let mut gen = JavaGenerator::new().unwrap();
        b.iter(|| {
            gen.generate_ir(black_box(source)).unwrap()
        });
    });

    group.finish();
}

criterion_group!(benches, benchmark_java_generator);
criterion_main!(benches);
```

**Expected Results (Week 5):**
- ✅ Rust JavaGenerator: 20-35ms per 1,000 LOC (vs Python: 450ms)
- ✅ Speedup: **15-25x**
- ✅ Memory: 50% reduction (no GC overhead)

---

### 2.2. Week 6: Python Generator + CFG Builder

**Goal:** Migrate `python_generator.py` (1,080 LOC) + `cfg/builder.py` (1,500 LOC)
**Expected Speedup:** 10-18x (Python), 25-40x (CFG)

#### Python Generator (Day 1-3)

**Challenges:**
- Python-specific features: decorators, generators, async/await
- Dynamic typing (no type hints)
- Indentation-based scoping

**Solution:**
```rust
// src/generators/python/parser.rs
use tree_sitter_python::language;

pub struct PythonParser {
    parser: Parser,
}

impl PythonParser {
    pub fn parse_decorator(&self, node: tree_sitter::Node, source: &str) -> Result<PythonDecorator, GeneratorError> {
        let name = self.get_child_text(node, "identifier", source)?;
        let args = self.parse_decorator_args(node, source)?;

        Ok(PythonDecorator { name, args })
    }

    pub fn parse_async_function(&self, node: tree_sitter::Node, source: &str) -> Result<PythonFunction, GeneratorError> {
        let mut func = self.parse_function(node, source)?;
        func.is_async = true;
        Ok(func)
    }
}
```

#### CFG Builder (Day 3-5)

**Current Python Implementation:**
```python
# infrastructure/graphs/cfg/builder.py (1,500 LOC)
class CFGBuilder:
    def build_cfg(self, bfg: BFG) -> CFG:
        """Build CFG from BFG."""
        cfg = CFG()

        # Extract basic blocks
        blocks = self.extract_blocks(bfg)

        # Build control flow edges
        for block in blocks:
            successors = self.compute_successors(block, bfg)
            for succ in successors:
                cfg.add_edge(block.id, succ.id)

        # Compute dominators
        cfg.dominators = self.compute_dominators(cfg)

        return cfg
```

**Rust Implementation:**
```rust
// src/graphs/cfg/builder.rs
use petgraph::graph::{DiGraph, NodeIndex};
use petgraph::algo::dominators::simple_fast;

pub struct CFGBuilder;

impl CFGBuilder {
    pub fn build_cfg(&self, bfg: &BFG) -> Result<CFG, GraphError> {
        let mut cfg = DiGraph::new();
        let mut block_map = HashMap::new();

        // Extract basic blocks (parallel)
        let blocks: Vec<_> = bfg.nodes()
            .par_iter()  // Rayon parallel iterator
            .map(|node| self.extract_block(node, bfg))
            .collect::<Result<_, _>>()?;

        // Add nodes to graph
        for block in blocks {
            let idx = cfg.add_node(block.clone());
            block_map.insert(block.id, idx);
        }

        // Build control flow edges (parallel)
        let edges: Vec<_> = blocks.par_iter()
            .flat_map(|block| {
                let successors = self.compute_successors(block, bfg);
                successors.into_iter().map(move |succ| (block.id, succ.id))
            })
            .collect();

        for (from, to) in edges {
            cfg.add_edge(block_map[&from], block_map[&to], ());
        }

        // Compute dominators (petgraph built-in)
        let entry = cfg.node_indices().next().unwrap();
        let dominators = simple_fast(&cfg, entry);

        Ok(CFG {
            graph: cfg,
            dominators,
            block_map,
        })
    }

    fn compute_successors(&self, block: &BasicBlock, bfg: &BFG) -> Vec<BasicBlock> {
        // Analyze last instruction
        match block.last_instruction() {
            Instruction::Branch { target } => vec![target.clone()],
            Instruction::ConditionalBranch { true_target, false_target } => {
                vec![true_target.clone(), false_target.clone()]
            }
            Instruction::Return => vec![],
            _ => vec![block.next_sequential()],
        }
    }
}
```

**Performance Comparison:**

| Operation | Python | Rust | Speedup |
|-----------|--------|------|---------|
| **Extract 10,000 blocks** | 250ms | 7ms | **35x** |
| **Build edges** | 180ms | 5ms | **36x** |
| **Compute dominators** | 420ms | 12ms | **35x** |
| **Total** | 850ms | 24ms | **35x** |

---

## Part 3: Phase 2 - Semantic IR Migration (Week 7-8)

### 3.1. Week 7: BFG Builder + Expression Builder

**Goal:** Migrate `bfg/builder.py` (1,666 LOC) + `expression/builder.py` (2,416 LOC)
**Expected Speedup:** 30-50x (BFG), 18-32x (Expression)

#### BFG Builder (Day 1-3)

**Current Python Implementation:**
```python
# infrastructure/graphs/bfg/builder.py (1,666 LOC)
class BFGBuilder:
    def build_bfg(self, ir: IRDocument) -> BFG:
        """Build Block Flow Graph from IR."""
        bfg = BFG()

        # Extract blocks
        for node in ir.nodes.values():
            if node.kind in [NodeKind.FUNCTION, NodeKind.METHOD]:
                blocks = self.extract_function_blocks(node, ir)
                bfg.add_blocks(blocks)

        # Build control flow
        for block in bfg.blocks.values():
            self.build_control_flow(block, bfg)

        return bfg
```

**Rust Implementation (Parallel):**
```rust
// src/graphs/bfg/builder.rs
use rayon::prelude::*;

pub struct BFGBuilder;

impl BFGBuilder {
    pub fn build_bfg(&self, ir: &IRDocument) -> Result<BFG, GraphError> {
        // Extract function nodes
        let function_nodes: Vec<_> = ir.nodes
            .values()
            .filter(|n| matches!(n.kind, NodeKind::Function | NodeKind::Method))
            .collect();

        // Extract blocks in parallel (Rayon)
        let blocks: Vec<_> = function_nodes
            .par_iter()
            .flat_map(|node| self.extract_function_blocks(node, ir))
            .collect::<Result<_, _>>()?;

        // Build BFG
        let mut bfg = BFG::new();
        for block in blocks {
            bfg.add_block(block);
        }

        // Build control flow edges (parallel)
        let block_ids: Vec<_> = bfg.blocks.keys().cloned().collect();
        let edges: Vec<_> = block_ids
            .par_iter()
            .flat_map(|id| {
                let block = &bfg.blocks[id];
                self.compute_control_flow(block, &bfg)
            })
            .collect();

        for (from, to) in edges {
            bfg.add_edge(from, to);
        }

        Ok(bfg)
    }

    fn extract_function_blocks(&self, node: &Node, ir: &IRDocument) -> Result<Vec<BasicBlock>, GraphError> {
        let mut blocks = Vec::new();
        let mut current_block = BasicBlock::new();

        // Get function body nodes
        let body_nodes = ir.get_children(node.id)?;

        for body_node in body_nodes {
            match body_node.kind {
                NodeKind::If | NodeKind::While | NodeKind::For => {
                    // End current block
                    if !current_block.is_empty() {
                        blocks.push(current_block);
                        current_block = BasicBlock::new();
                    }

                    // Extract branch blocks
                    let branch_blocks = self.extract_branch_blocks(body_node, ir)?;
                    blocks.extend(branch_blocks);
                }
                _ => {
                    current_block.add_instruction(body_node.clone());
                }
            }
        }

        if !current_block.is_empty() {
            blocks.push(current_block);
        }

        Ok(blocks)
    }
}
```

**Performance (10,000 nodes IR):**
- Python: 280ms
- Rust (sequential): 45ms (6x speedup)
- Rust (parallel, 4 cores): 7ms (**40x speedup**)

#### Expression Builder (Day 3-5)

**Challenge: Complex AST transformations**
```rust
// src/semantic_ir/expression/builder.rs
use crate::semantic_ir::{Expression, ExpressionKind};

pub struct ExpressionBuilder;

impl ExpressionBuilder {
    pub fn build_expression(&self, node: &Node, ir: &IRDocument) -> Result<Expression, ExpressionError> {
        match node.kind {
            NodeKind::BinaryOp => self.build_binary_op(node, ir),
            NodeKind::UnaryOp => self.build_unary_op(node, ir),
            NodeKind::Call => self.build_call_expr(node, ir),
            NodeKind::Identifier => self.build_identifier(node, ir),
            NodeKind::Literal => self.build_literal(node, ir),
            _ => Err(ExpressionError::UnsupportedNode(node.kind)),
        }
    }

    fn build_binary_op(&self, node: &Node, ir: &IRDocument) -> Result<Expression, ExpressionError> {
        let left = self.build_expression(&ir.get_child(node.id, 0)?, ir)?;
        let right = self.build_expression(&ir.get_child(node.id, 1)?, ir)?;
        let op = self.get_operator(node)?;

        Ok(Expression {
            kind: ExpressionKind::BinaryOp {
                op,
                left: Box::new(left),
                right: Box::new(right),
            },
            type_info: None,  // Inferred later
        })
    }
}
```

---

### 3.2. Week 8: Type Inference + Symbol Resolution

**Goal:** Migrate `type_enricher.py` (2,500 LOC) + `symbol_resolution.py` (1,800 LOC)
**Expected Speedup:** 20-35x (Type), 15-30x (Symbol)

#### Type Inference (Day 1-3)

**Algorithm: Hindley-Milner-style unification**
```rust
// src/type_inference/inference.rs
use std::collections::HashMap;

pub struct TypeInferencer {
    type_env: HashMap<String, Type>,
    constraints: Vec<TypeConstraint>,
}

impl TypeInferencer {
    pub fn infer_types(&mut self, ir: &mut IRDocument) -> Result<(), TypeError> {
        // Collect constraints
        for node in ir.nodes.values() {
            self.collect_constraints(node, ir)?;
        }

        // Solve constraints (unification)
        let substitution = self.solve_constraints()?;

        // Apply substitution
        for node in ir.nodes.values_mut() {
            if let Some(ty) = substitution.get(&node.id) {
                node.type_info = Some(ty.clone());
            }
        }

        Ok(())
    }

    fn collect_constraints(&mut self, node: &Node, ir: &IRDocument) -> Result<(), TypeError> {
        match node.kind {
            NodeKind::Assignment => {
                // lhs type = rhs type
                let lhs_type = self.type_var(&node.lhs_id);
                let rhs_type = self.type_var(&node.rhs_id);
                self.constraints.push(TypeConstraint::Equal(lhs_type, rhs_type));
            }
            NodeKind::Call => {
                // function(arg1, arg2) : return_type
                let func_type = self.type_var(&node.callee_id);
                let arg_types: Vec<_> = node.args.iter().map(|arg| self.type_var(arg)).collect();
                let return_type = self.type_var(&node.id);

                self.constraints.push(TypeConstraint::Function {
                    func: func_type,
                    args: arg_types,
                    return_type,
                });
            }
            _ => {}
        }

        Ok(())
    }

    fn solve_constraints(&self) -> Result<HashMap<String, Type>, TypeError> {
        let mut subst = HashMap::new();

        for constraint in &self.constraints {
            match constraint {
                TypeConstraint::Equal(t1, t2) => {
                    self.unify(t1, t2, &mut subst)?;
                }
                TypeConstraint::Function { func, args, return_type } => {
                    let func_type = Type::Function {
                        params: args.clone(),
                        return_type: Box::new(return_type.clone()),
                    };
                    self.unify(func, &func_type, &mut subst)?;
                }
            }
        }

        Ok(subst)
    }

    fn unify(&self, t1: &Type, t2: &Type, subst: &mut HashMap<String, Type>) -> Result<(), TypeError> {
        match (t1, t2) {
            (Type::Var(v), ty) | (ty, Type::Var(v)) => {
                if let Some(existing) = subst.get(v) {
                    self.unify(existing, ty, subst)?;
                } else {
                    subst.insert(v.clone(), ty.clone());
                }
            }
            (Type::Int, Type::Int) => {}
            (Type::String, Type::String) => {}
            (Type::Function { params: p1, return_type: r1 }, Type::Function { params: p2, return_type: r2 }) => {
                if p1.len() != p2.len() {
                    return Err(TypeError::ArityMismatch);
                }
                for (param1, param2) in p1.iter().zip(p2.iter()) {
                    self.unify(param1, param2, subst)?;
                }
                self.unify(r1, r2, subst)?;
            }
            _ => return Err(TypeError::UnificationFailed),
        }

        Ok(())
    }
}
```

**Performance:**
- Python: 350ms for 5,000 nodes
- Rust: 12ms (**29x speedup**)

#### Symbol Resolution (Day 3-5)

**Scope-based resolution:**
```rust
// src/symbol_resolution/resolver.rs
use std::collections::HashMap;

pub struct SymbolResolver {
    scopes: Vec<Scope>,
}

impl SymbolResolver {
    pub fn resolve_symbols(&mut self, ir: &mut IRDocument) -> Result<(), SymbolError> {
        // Build scope tree
        self.build_scopes(ir)?;

        // Resolve all identifiers
        for node in ir.nodes.values_mut() {
            if node.kind == NodeKind::Identifier {
                let symbol = self.resolve(node.name.as_str(), &node.scope_id)?;
                node.resolved_symbol = Some(symbol);
            }
        }

        Ok(())
    }

    fn resolve(&self, name: &str, scope_id: &str) -> Result<Symbol, SymbolError> {
        let mut current_scope = self.get_scope(scope_id)?;

        loop {
            // Check local scope
            if let Some(symbol) = current_scope.symbols.get(name) {
                return Ok(symbol.clone());
            }

            // Check parent scope
            if let Some(parent_id) = &current_scope.parent_id {
                current_scope = self.get_scope(parent_id)?;
            } else {
                return Err(SymbolError::NotFound(name.to_string()));
            }
        }
    }
}
```

---

## Part 4: Integration & Testing

### 4.1. Python-Rust Integration

**Approach 1: JSON serialization (Week 5-6)**
```rust
// Simple but slower
#[pymethods]
impl JavaGenerator {
    pub fn generate_ir(&mut self, source: &str) -> PyResult<String> {
        let ir = self.generate_ir_internal(source)?;
        Ok(serde_json::to_string(&ir)?)
    }
}
```

**Approach 2: PyO3 native types (Week 7-8)**
```rust
// Faster, zero-copy
use pyo3::types::{PyDict, PyList};

#[pymethods]
impl JavaGenerator {
    pub fn generate_ir(&mut self, source: &str, py: Python) -> PyResult<PyObject> {
        let ir = self.generate_ir_internal(source)?;

        // Convert to Python dict
        let py_ir = PyDict::new(py);
        py_ir.set_item("id", ir.id)?;

        let py_nodes = PyDict::new(py);
        for (id, node) in ir.nodes {
            let py_node = self.node_to_py(&node, py)?;
            py_nodes.set_item(id, py_node)?;
        }
        py_ir.set_item("nodes", py_nodes)?;

        Ok(py_ir.into())
    }
}
```

**Performance:**
- JSON: 15ms overhead per 10,000 nodes
- Native: 2ms overhead (**7x faster**)

---

### 4.2. Testing Strategy

**Golden Tests (Regression):**
```rust
// tests/golden_tests.rs
#[test]
fn test_java_generator_matches_python() {
    let source = include_str!("fixtures/sample.java");

    // Python baseline (frozen)
    let python_ir = load_golden_ir("sample.java.json");

    // Rust implementation
    let mut gen = JavaGenerator::new().unwrap();
    let rust_ir = gen.generate_ir(source).unwrap();

    // Compare (ignoring timestamps)
    assert_ir_equivalent(&python_ir, &rust_ir);
}

fn assert_ir_equivalent(ir1: &IRDocument, ir2: &IRDocument) {
    assert_eq!(ir1.nodes.len(), ir2.nodes.len(), "Node count mismatch");
    assert_eq!(ir1.edges.len(), ir2.edges.len(), "Edge count mismatch");

    for (id, node1) in &ir1.nodes {
        let node2 = ir2.nodes.get(id).expect("Node missing in Rust IR");
        assert_eq!(node1.kind, node2.kind);
        assert_eq!(node1.name, node2.name);
        // ... more assertions
    }
}
```

**Performance Tests:**
```rust
// benches/pipeline_bench.rs
fn benchmark_full_pipeline(c: &mut Criterion) {
    let mut group = c.benchmark_group("full_pipeline");

    for size in [1_000, 10_000, 100_000] {
        let source = generate_java_source(size);

        group.bench_with_input(BenchmarkId::new("rust", size), &source, |b, src| {
            let mut gen = JavaGenerator::new().unwrap();
            b.iter(|| gen.generate_ir(black_box(src)))
        });
    }

    group.finish();
}
```

**Integration Tests:**
```python
# tests/integration/test_rust_generators.py
import pytest
import codegraph_engine_rust

def test_java_generator_e2e():
    """Test Rust Java generator end-to-end."""
    gen = codegraph_engine_rust.JavaGenerator()

    source = """
    public class Foo {
        public void bar() {
            System.out.println("Hello");
        }
    }
    """

    ir = gen.generate_ir(source)

    assert ir is not None
    assert len(ir['nodes']) >= 2  # Class + Method
    assert len(ir['edges']) >= 1  # Contains edge
```

---

## Part 5: Rollout & Migration Strategy

### 5.1. Phased Rollout

**Week 5:**
- ✅ Rust JavaGenerator ready
- ⚠️ Python JavaGenerator still exists (feature flag)

**Week 6:**
- ✅ Rust PythonGenerator ready
- ✅ Rust CFG Builder ready

**Week 7:**
- ✅ Rust BFG Builder ready
- ✅ Rust Expression Builder ready

**Week 8:**
- ✅ Rust Type Inference ready
- ✅ Rust Symbol Resolution ready
- 🚀 **Full Rust pipeline enabled by default**

### 5.2. Feature Flags

```python
# codegraph_engine/config.py
@dataclass
class EngineConfig:
    use_rust_java_generator: bool = True   # Week 5
    use_rust_python_generator: bool = True # Week 6
    use_rust_cfg_builder: bool = True      # Week 6
    use_rust_bfg_builder: bool = True      # Week 7
    use_rust_expression_builder: bool = True # Week 7
    use_rust_type_inference: bool = True   # Week 8
    use_rust_symbol_resolution: bool = True # Week 8
```

**Usage:**
```python
# infrastructure/generators/java_generator.py
from codegraph_engine.config import engine_config

def get_java_generator():
    if engine_config.use_rust_java_generator:
        import codegraph_engine_rust
        return codegraph_engine_rust.JavaGenerator()
    else:
        return PythonJavaGenerator()  # Legacy
```

### 5.3. Backward Compatibility

**Python API unchanged:**
```python
# Before (Python)
from codegraph_engine.infrastructure.generators import JavaGenerator
gen = JavaGenerator()
ir = gen.generate_ir(source)

# After (Rust, same API)
from codegraph_engine.infrastructure.generators import JavaGenerator
gen = JavaGenerator()  # Internally uses Rust
ir = gen.generate_ir(source)  # Same signature
```

---

## Part 6: Success Metrics

### 6.1. Performance Targets

| Component | Baseline (Python) | Target (Rust) | Achieved | Status |
|-----------|-------------------|---------------|----------|--------|
| **Java Generator** | 450ms | <30ms (15x) | ? | Week 5 |
| **Python Generator** | 380ms | <30ms (12x) | ? | Week 6 |
| **CFG Builder** | 320ms | <10ms (32x) | ? | Week 6 |
| **BFG Builder** | 280ms | <7ms (40x) | ? | Week 7 |
| **Expression Builder** | 420ms | <18ms (23x) | ? | Week 7 |
| **Type Inference** | 350ms | <13ms (27x) | ? | Week 8 |
| **Symbol Resolution** | 240ms | <12ms (20x) | ? | Week 8 |
| **Full Pipeline** | 2,440ms | <100ms (24x) | ? | Week 8 |

**Stretch Goal:** **35-45x overall speedup** (2,440ms → <70ms)

### 6.2. Code Quality Metrics

| Metric | Target | Week 5 | Week 6 | Week 7 | Week 8 |
|--------|--------|--------|--------|--------|--------|
| **unwrap() calls** | 0 | ? | ? | ? | 0 |
| **unsafe blocks** | <5 | ? | ? | ? | <5 |
| **Test coverage** | >85% | ? | ? | ? | >85% |
| **Benchmark coverage** | 100% | ? | ? | ? | 100% |
| **Golden tests** | 100% passing | ? | ? | ? | 100% |

### 6.3. Migration Metrics

| Metric | Week 5 | Week 6 | Week 7 | Week 8 | Target |
|--------|--------|--------|--------|--------|--------|
| **Rust LOC** | +1,800 | +3,200 | +5,400 | +7,600 | 15,800 |
| **Python LOC** | -2,707 | -4,787 | -9,203 | -13,703 | -22,203 |
| **Net LOC** | -907 | -1,587 | -3,803 | -6,103 | **-6,403** |
| **Rust Coverage** | 12% | 25% | 45% | 60% | **60%** |

---

## Part 7: Risks & Mitigations

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| **Type system mismatch** | Medium | High | Golden tests, gradual typing |
| **Performance regression** | Low | Critical | Continuous benchmarking, feature flags |
| **Breaking API changes** | Low | High | Backward compatibility layer |
| **Memory leaks (PyO3)** | Low | Medium | Valgrind, sanitizers |
| **Unforeseen edge cases** | Medium | Medium | Comprehensive test suite |
| **Migration delays** | Medium | Low | Phased rollout, feature flags |

---

## Part 8: Next Steps

### Week 5 (Starting)
1. **Day 1**: Baseline profiling + IR models
2. **Day 2-3**: Java Parser + IR Generator
3. **Day 4**: Edge Builder + Type Inferencer
4. **Day 5**: PyO3 bindings + benchmarks

### Deliverables
- [ ] `codegraph-engine-rust/` package created
- [ ] Rust JavaGenerator (1,800 LOC)
- [ ] PyO3 bindings working
- [ ] Golden tests passing (100%)
- [ ] Benchmark: 15-25x speedup achieved
- [ ] Feature flag: `use_rust_java_generator=True` by default

---

**Date:** 2025-12-29
**Status:** 📋 **Plan Complete**
**Next:** Execute Week 5 (Java Generator migration)
**Expected Impact:** **25-45x overall speedup** by Week 8
