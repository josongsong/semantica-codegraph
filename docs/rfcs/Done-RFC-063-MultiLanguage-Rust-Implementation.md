# RFC-063: Multi-Language Rust Implementation (TypeScript, Java, Kotlin)

**Status**: Draft
**Created**: 2025-12-27
**Author**: Claude (based on Semantica v1 analysis)

## Executive Summary

This RFC outlines the implementation plan for adding TypeScript, Java, and Kotlin support to the Semantica v2 Rust engine (`codegraph-ir`). The goal is to achieve **feature parity with Semantica v1** Python implementation while leveraging Rust's performance advantages (7.6x faster as demonstrated in Python IR generation).

### Target Languages
- **TypeScript/JavaScript** (`.ts`, `.tsx`, `.js`, `.jsx`)
- **Java** (`.java`)
- **Kotlin** (`.kt`, `.kts`)

### Success Criteria
Each language must support:
1. ✅ AST Parsing (tree-sitter)
2. ✅ Symbol Extraction (Functions, Classes, Variables, Imports)
3. ✅ Type Resolution (6 levels: RAW → EXTERNAL)
4. ✅ Cross-file Reference Resolution
5. ✅ Import/Export Handling
6. ✅ Language-Specific Features (Generics, Decorators, Extensions, etc.)

---

## 1. Background

### 1.1 Current State (Semantica v2 Rust)

**✅ Implemented:**
- Python support (full feature parity)
- IR generation pipeline (7.6x faster than Python)
- Arrow IPC serialization (zero-copy)
- Parallel processing (rayon)

**❌ Missing:**
- TypeScript, Java, Kotlin support
- Multi-language orchestration
- Language-specific type systems

### 1.2 Semantica v1 Capabilities (Python Implementation)

Based on comprehensive analysis, v1 provides:

| Feature | TypeScript | Java | Kotlin | Python |
|---------|-----------|------|--------|--------|
| Tree-sitter Parsing | ✓ | ✓ | ✓ | ✓ |
| Symbol Extraction | ✓ Full | ✓ Very Complete | ✓ Full | ✓ Full |
| Type Resolution | ✓ Advanced | ✓ Advanced | ✓ Advanced | ✓ Advanced |
| LSP Integration | ✓ tsserver | ✓ JDT.LS | ✓ kotlin-language-server | ✓ Pyright |
| Cross-file Refs | ✓ | ✓ | ✓ | ✓ |
| Import Handling | ✓ | ✓ | ✓ | ✓ |
| Generics | ✓ | ✓ | ✓ | ✓ |
| Decorators/Annotations | ✓ | ✓ | Partial | N/A |
| Extension Functions | N/A | N/A | ✓ | N/A |
| Null Safety | N/A | Partial | ✓ | N/A |

**Key Insight**: All languages share ~80% common infrastructure (AST parsing, FQN building, edge creation), with 20% language-specific logic.

---

## 2. Architecture Design

### 2.1 Module Structure

```
packages/codegraph-rust/codegraph-ir/
├── src/
│   ├── features/
│   │   ├── parsing/
│   │   │   ├── infrastructure/
│   │   │   │   ├── tree_sitter/
│   │   │   │   │   ├── languages/
│   │   │   │   │   │   ├── mod.rs              # Language registry
│   │   │   │   │   │   ├── python.rs           # ✅ Existing
│   │   │   │   │   │   ├── typescript.rs       # ⚡ NEW
│   │   │   │   │   │   ├── java.rs             # ⚡ NEW
│   │   │   │   │   │   └── kotlin.rs           # ⚡ NEW
│   │   ├── ir_generation/
│   │   │   ├── infrastructure/
│   │   │   │   ├── visitor.rs                  # Generic visitor
│   │   │   │   ├── extractors/
│   │   │   │   │   ├── typescript/             # ⚡ NEW
│   │   │   │   │   │   ├── class.rs           # Interface, Decorators
│   │   │   │   │   │   ├── function.rs        # Arrow functions, async
│   │   │   │   │   │   ├── import.rs          # ESM imports
│   │   │   │   │   │   └── type.rs            # Union/Intersection types
│   │   │   │   │   ├── java/                   # ⚡ NEW
│   │   │   │   │   │   ├── class.rs           # Enums, Annotations
│   │   │   │   │   │   ├── method.rs          # Generics, Throws
│   │   │   │   │   │   ├── import.rs          # Static imports
│   │   │   │   │   │   └── type.rs            # Wildcard bounds
│   │   │   │   │   └── kotlin/                 # ⚡ NEW
│   │   │   │   │       ├── class.rs           # Data/Sealed classes
│   │   │   │   │       ├── function.rs        # Extension/Suspend
│   │   │   │   │       ├── import.rs          # Aliases
│   │   │   │   │       └── type.rs            # Null safety
│   │   ├── type_resolution/
│   │   │   ├── infrastructure/
│   │   │   │   ├── typescript_resolver.rs      # ⚡ NEW
│   │   │   │   ├── java_resolver.rs            # ⚡ NEW
│   │   │   │   └── kotlin_resolver.rs          # ⚡ NEW
```

### 2.2 Language Plugin Trait

```rust
// codegraph-ir/src/shared/ports/language.rs

pub trait LanguagePlugin: Send + Sync {
    // Identity
    fn language(&self) -> &'static str;
    fn supported_extensions(&self) -> &[&'static str];
    fn typing_mode(&self) -> TypingMode;  // Static, Gradual, Dynamic

    // Tree-sitter integration
    fn tree_sitter_language(&self) -> tree_sitter::Language;

    // FQN handling
    fn build_fqn(&self, components: &[&str]) -> String;
    fn parse_fqn(&self, fqn: &str) -> ParsedFQN;
    fn build_lambda_fqn(&self, base_fqn: &str, index: usize) -> String;

    // Type system
    fn is_builtin_type(&self, type_str: &str) -> bool;
    fn builtin_types(&self) -> &HashSet<&'static str>;

    // Symbol extraction
    fn extract_symbols(
        &self,
        tree: &ParsedTree,
        source: &str,
        file_path: &str,
    ) -> Result<Vec<Node>, Error>;

    // Type resolution
    fn resolve_type(
        &self,
        raw_type: &str,
        context: &TypeContext,
    ) -> Result<TypeEntity, Error>;
}

pub enum TypingMode {
    Static,    // Java, Kotlin
    Gradual,   // TypeScript
    Dynamic,   // Python
}
```

---

## 3. Implementation Plan

### 3.1 Phase 1: TypeScript (Weeks 1-2)

**Priority: HIGH** - Most requested, largest user base

#### Dependencies
```toml
# Cargo.toml
tree-sitter-typescript = "0.21"  # Includes TSX
```

#### Tasks

**Week 1: Core IR Generation**
- [ ] Create `typescript.rs` language module
- [ ] Implement `TypeScriptPlugin` trait
- [ ] Extract basic symbols:
  - [ ] Classes (with decorators)
  - [ ] Interfaces
  - [ ] Functions (including arrow functions)
  - [ ] Variables (let/const/var)
  - [ ] Imports/Exports (ESM)
- [ ] FQN builder for TypeScript
- [ ] Unit tests for symbol extraction

**Week 2: Advanced Features**
- [ ] Generic type extraction (`<T extends Base>`)
- [ ] Union/Intersection types (`A | B`, `A & B`)
- [ ] Decorators (`@Component`, `@Injectable`)
- [ ] React hooks detection (useState, useEffect, etc.)
- [ ] Type resolution (6 levels)
- [ ] Integration tests
- [ ] Benchmark against Python implementation

#### Expected Performance
- **Target**: 5-8x faster than Python v1
- **Baseline**: Python IR generation = ~150ms for 1000 LOC
- **Goal**: Rust TypeScript = ~20-30ms for 1000 LOC

#### Validation Criteria
```rust
#[test]
fn test_typescript_class_with_decorators() {
    let source = r#"
        @Component({selector: 'app-root'})
        export class AppComponent {
            @Input() name: string;

            constructor(private service: MyService) {}
        }
    "#;

    let ir = generate_ir(source, "typescript");

    // Verify class node
    assert_eq!(ir.nodes[0].kind, NodeKind::Class);
    assert_eq!(ir.nodes[0].name, Some("AppComponent"));

    // Verify decorators
    assert!(ir.nodes[0].attrs.contains_key("decorators"));

    // Verify field with decorator
    assert_eq!(ir.nodes[1].kind, NodeKind::Field);
    assert!(ir.nodes[1].attrs["decorators"].contains("Input"));
}
```

---

### 3.2 Phase 2: Java (Weeks 3-4)

**Priority: HIGH** - Enterprise demand, Spring ecosystem

#### Dependencies
```toml
tree-sitter-java = "0.21"
```

#### Tasks

**Week 3: Core IR Generation**
- [ ] Create `java.rs` language module
- [ ] Implement `JavaPlugin` trait
- [ ] Extract basic symbols:
  - [ ] Packages
  - [ ] Classes/Interfaces/Enums
  - [ ] Methods (including constructors)
  - [ ] Fields
  - [ ] Imports (including static)
- [ ] FQN builder (handle `$` for inner classes)
- [ ] Unit tests

**Week 4: Advanced Features**
- [ ] Annotations extraction (`@Override`, `@SpringBootApplication`)
- [ ] Generic types with bounds (`<T extends Number>`)
- [ ] Wildcard types (`List<? extends T>`)
- [ ] Lambda expressions (`x -> x * 2`)
- [ ] Method references (`String::valueOf`)
- [ ] Exception tracking (throws clauses)
- [ ] Integration tests
- [ ] Benchmark

#### Java-Specific Challenges

**Inner Classes FQN**
```rust
// Outer.java
class Outer {
    class Inner {}           // FQN: com.example.Outer$Inner
    static class Nested {}   // FQN: com.example.Outer$Nested
}
```

**Annotation Extraction**
```rust
#[derive(Debug, Serialize)]
pub struct JavaAnnotation {
    pub name: String,              // "Override", "Nullable"
    pub attributes: HashMap<String, String>,  // key=value pairs
}
```

#### Validation Criteria
```rust
#[test]
fn test_java_generics_with_bounds() {
    let source = r#"
        public class Container<T extends Number> {
            private List<T> items;

            public <U extends T> void add(U item) {
                items.add(item);
            }
        }
    "#;

    let ir = generate_ir(source, "java");

    // Verify generic parameters
    let class_node = &ir.nodes[0];
    assert!(class_node.attrs.contains_key("type_parameters"));

    let type_params: Vec<String> = serde_json::from_value(
        class_node.attrs["type_parameters"].clone()
    ).unwrap();
    assert_eq!(type_params[0], "T extends Number");
}
```

---

### 3.3 Phase 3: Kotlin (Weeks 5-6)

**Priority: MEDIUM** - Growing adoption, Android ecosystem

#### Dependencies
```toml
tree-sitter-kotlin = "0.3"
```

#### Tasks

**Week 5: Core IR Generation**
- [ ] Create `kotlin.rs` language module
- [ ] Implement `KotlinPlugin` trait
- [ ] Extract basic symbols:
  - [ ] Classes (data, sealed, object)
  - [ ] Functions (regular, extension, suspend)
  - [ ] Properties (val/var)
  - [ ] Imports
- [ ] FQN builder
- [ ] Unit tests

**Week 6: Advanced Features**
- [ ] Extension functions (`fun String.isEmail()`)
- [ ] Companion objects
- [ ] Suspend functions (coroutines)
- [ ] Null safety tracking (`T` vs `T?`)
- [ ] Delegated properties (`by lazy`, `by observable`)
- [ ] Type aliases (`typealias MyMap = Map<String, Int>`)
- [ ] Integration tests
- [ ] Benchmark

#### Kotlin-Specific Features

**Extension Functions**
```rust
// Extension: fun String.isEmail(): Boolean
pub struct ExtensionFunction {
    pub receiver_type: String,  // "String"
    pub function_name: String,  // "isEmail"
    pub fqn: String,            // "com.example.String.isEmail"
}
```

**Data Classes**
```rust
#[test]
fn test_kotlin_data_class() {
    let source = r#"
        data class User(
            val id: Int,
            val name: String?,
            var email: String
        )
    "#;

    let ir = generate_ir(source, "kotlin");

    // Verify data class
    assert_eq!(ir.nodes[0].attrs["class_type"], "data");

    // Verify properties with null safety
    let properties: Vec<&Node> = ir.nodes.iter()
        .filter(|n| n.kind == NodeKind::Field)
        .collect();

    assert_eq!(properties.len(), 3);
    assert_eq!(properties[1].attrs["nullable"], true);  // name: String?
}
```

#### Validation Criteria
- All Kotlin language features extracted
- Extension function FQN format validated
- Null safety information preserved
- Suspend function detection working

---

## 4. Cross-Cutting Concerns

### 4.1 Type Resolution System

Each language needs a type resolver following the 6-level hierarchy:

```rust
pub enum TypeResolutionLevel {
    Raw,        // Just the raw string
    Builtin,    // Language built-ins (int, string, List, etc.)
    Local,      // Same-file definitions
    Module,     // Same-package imports
    Project,    // Cross-package (whole project)
    External,   // Third-party libraries
}

pub trait TypeResolver {
    fn resolve(
        &self,
        raw_type: &str,
        context: &TypeContext,
        level: TypeResolutionLevel,
    ) -> Result<TypeEntity, Error>;
}
```

**Builtin Types per Language:**

```rust
// TypeScript builtins
const TS_BUILTINS: &[&str] = &[
    "string", "number", "boolean", "void", "null", "undefined",
    "any", "unknown", "never", "object",
    "Array", "Map", "Set", "Promise", "Date", "RegExp",
];

// Java builtins
const JAVA_BUILTINS: &[&str] = &[
    "byte", "short", "int", "long", "float", "double", "char", "boolean",
    "String", "Object", "Integer", "Long", "Double", "Boolean",
    "List", "Map", "Set", "ArrayList", "HashMap", "HashSet",
];

// Kotlin builtins
const KOTLIN_BUILTINS: &[&str] = &[
    "Byte", "Short", "Int", "Long", "Float", "Double", "Char", "Boolean",
    "String", "Any", "Unit", "Nothing",
    "List", "Map", "Set", "MutableList", "MutableMap", "MutableSet",
];
```

### 4.2 Import Resolution

```rust
pub struct ImportResolver {
    // Language-specific import parsers
    parsers: HashMap<String, Box<dyn ImportParser>>,
}

pub trait ImportParser {
    fn parse_import(&self, node: &SyntaxNode) -> Vec<ImportStatement>;
}

pub struct ImportStatement {
    pub source_module: String,      // "react", "java.util"
    pub imported_symbols: Vec<ImportedSymbol>,
    pub is_wildcard: bool,          // import * from, import java.util.*
}

pub struct ImportedSymbol {
    pub name: String,               // "useState", "List"
    pub alias: Option<String>,      // import {X as Y}
    pub is_default: bool,           // export default
}
```

### 4.3 FQN Building Patterns

```rust
impl TypeScriptPlugin {
    fn build_fqn(&self, components: &[&str]) -> String {
        components.join(".")  // namespace.Class.method
    }

    fn build_lambda_fqn(&self, base: &str, index: usize) -> String {
        format!("{}.λ{}", base, index)  // module.func.λ0
    }
}

impl JavaPlugin {
    fn build_fqn(&self, components: &[&str]) -> String {
        components.join(".")  // com.example.Class.method
    }

    fn build_inner_class_fqn(&self, outer: &str, inner: &str) -> String {
        format!("{}${}", outer, inner)  // Outer$Inner
    }
}

impl KotlinPlugin {
    fn build_extension_fqn(&self, receiver: &str, func: &str) -> String {
        format!("{}.{}", receiver, func)  // String.isEmail
    }
}
```

### 4.4 Testing Strategy

**Unit Tests** (per language)
- Symbol extraction accuracy
- FQN building correctness
- Type resolution levels
- Import parsing

**Integration Tests** (cross-language)
- End-to-end IR generation
- Performance benchmarks vs Python v1
- Edge case handling (nested generics, complex types)

**Test Data**
```
tests/
├── fixtures/
│   ├── typescript/
│   │   ├── simple_class.ts
│   │   ├── generics.ts
│   │   ├── decorators.ts
│   │   └── react_hooks.tsx
│   ├── java/
│   │   ├── simple_class.java
│   │   ├── generics.java
│   │   ├── annotations.java
│   │   └── spring_boot.java
│   └── kotlin/
│       ├── data_class.kt
│       ├── extensions.kt
│       ├── coroutines.kt
│       └── null_safety.kt
```

---

## 5. Performance Targets

### 5.1 Benchmarks (1000 LOC)

| Language | Python v1 (baseline) | Rust Target | Speedup |
|----------|----------------------|-------------|---------|
| TypeScript | 150ms | 20-30ms | 5-7.5x |
| Java | 120ms | 18-25ms | 4.8-6.7x |
| Kotlin | 140ms | 20-28ms | 5-7x |
| Python | 180ms | 24ms (✅ achieved) | 7.5x |

### 5.2 Memory Usage

- **Target**: < 50MB per 10k LOC file
- **Strategy**: Zero-copy Arrow IPC serialization
- **Benchmark**: Track RSS during IR generation

### 5.3 Parallelism

Leverage rayon for:
- Parallel file processing
- Concurrent symbol extraction
- Parallel type resolution (independent files)

```rust
use rayon::prelude::*;

files.par_iter()
    .map(|file| generate_ir(file, language))
    .collect()
```

---

## 6. Migration Path

### 6.1 Python Fallback Strategy

During initial rollout, support dual execution:

```python
# packages/codegraph-engine/.../ir_builder.py

class LayeredIRBuilder:
    def build_ir(self, file_path: str, language: str) -> IRDocument:
        # Try Rust engine first
        if language in RUST_SUPPORTED_LANGUAGES:
            try:
                return self._rust_engine.generate_ir(file_path, language)
            except Exception as e:
                logger.warning(f"Rust engine failed, falling back to Python: {e}")

        # Fallback to Python generators
        return self._python_generator.generate(file_path, language)

RUST_SUPPORTED_LANGUAGES = {"python", "typescript", "java", "kotlin"}
```

### 6.2 Feature Flags

```python
# codegraph_shared/infra/jobs/handlers/config.py

@dataclass
class RustEngineConfig:
    enabled: bool = True
    languages: set[str] = field(default_factory=lambda: {
        "python",      # ✅ Stable
        # "typescript",  # 🚧 Beta (uncomment when ready)
        # "java",        # 🚧 Beta
        # "kotlin",      # 🚧 Beta
    })
    fallback_on_error: bool = True

DEFAULT_CONFIG.rust_engine = RustEngineConfig()
```

---

## 7. Success Metrics

### 7.1 Functional Completeness

- [ ] All node types extracted (classes, functions, variables, imports)
- [ ] All edge types created (CONTAINS, CALLS, IMPORTS, INHERITS)
- [ ] Type resolution working (6 levels)
- [ ] FQN uniqueness validated
- [ ] Import tracking accurate

### 7.2 Performance

- [ ] 5-8x speedup vs Python v1 (per language)
- [ ] Memory usage < 50MB per 10k LOC
- [ ] Parallel processing working (4+ cores)

### 7.3 Quality

- [ ] Unit test coverage > 80%
- [ ] Integration tests passing
- [ ] Zero regression in Python support
- [ ] Documentation complete

### 7.4 Production Readiness

- [ ] Error handling robust
- [ ] Logging comprehensive
- [ ] Fallback to Python working
- [ ] Feature flags operational

---

## 8. Timeline

**Total Duration**: 6 weeks (with 2-week buffer = 8 weeks)

| Week | Focus | Deliverables |
|------|-------|-------------|
| 1 | TypeScript Core | Basic symbol extraction |
| 2 | TypeScript Advanced | Generics, decorators, React |
| 3 | Java Core | Classes, methods, fields |
| 4 | Java Advanced | Annotations, generics, lambdas |
| 5 | Kotlin Core | Data classes, functions |
| 6 | Kotlin Advanced | Extensions, coroutines, null safety |
| 7-8 | Buffer | Testing, benchmarks, documentation |

---

## 9. Risks & Mitigations

### 9.1 Risk: Tree-sitter Grammar Bugs

**Mitigation**:
- Test with real-world codebases (top GitHub repos)
- Fallback to Python on parse errors
- Contribute fixes upstream if needed

### 9.2 Risk: Type System Complexity

**Mitigation**:
- Start with basic types, iterate
- Reference v1 Python implementation
- Use LSP integration for validation (future)

### 9.3 Risk: Performance Regression

**Mitigation**:
- Benchmark every commit
- Profile with flamegraph
- Compare against Python baseline

### 9.4 Risk: Breaking Changes

**Mitigation**:
- Feature flags for gradual rollout
- Dual execution (Rust + Python fallback)
- Extensive integration tests

---

## 10. Future Work (Out of Scope)

- **LSP Integration**: TypeScript Server, JDT.LS, Kotlin LS (Phase 2)
- **Additional Languages**: Go, Rust, C++, C# (Phase 3)
- **Advanced Analysis**: SSA, CFG, DFG for non-Python languages (Phase 4)
- **Incremental Updates**: File change detection, partial re-indexing (Phase 5)

---

## 11. References

### 11.1 Tree-sitter Grammars
- https://github.com/tree-sitter/tree-sitter-typescript
- https://github.com/tree-sitter/tree-sitter-java
- https://github.com/fwcd/tree-sitter-kotlin

### 11.2 Semantica v1 Implementation
- `/packages/codegraph-engine/codegraph_engine/code_foundation/infrastructure/generators/`
- `/packages/codegraph-engine/codegraph_engine/code_foundation/infrastructure/language_plugin/`

### 11.3 Related RFCs
- RFC-062: CrossFileResolver Rust Optimization
- RFC-RUST-ENGINE: Rust Performance Optimization

---

## 12. Appendix: Code Examples

### 12.1 TypeScript Plugin Skeleton

```rust
// codegraph-ir/src/features/parsing/infrastructure/tree_sitter/languages/typescript.rs

use super::super::parser::TreeSitterParser;
use crate::shared::ports::language::LanguagePlugin;
use tree_sitter_typescript::language_typescript;

pub struct TypeScriptPlugin;

impl LanguagePlugin for TypeScriptPlugin {
    fn language(&self) -> &'static str {
        "typescript"
    }

    fn supported_extensions(&self) -> &[&'static str] {
        &[".ts", ".tsx", ".js", ".jsx"]
    }

    fn typing_mode(&self) -> TypingMode {
        TypingMode::Gradual
    }

    fn tree_sitter_language(&self) -> tree_sitter::Language {
        language_typescript()
    }

    fn builtin_types(&self) -> &HashSet<&'static str> {
        static BUILTINS: Lazy<HashSet<&'static str>> = Lazy::new(|| {
            ["string", "number", "boolean", "void", "any", "unknown", "never"]
                .iter()
                .copied()
                .collect()
        });
        &BUILTINS
    }

    fn extract_symbols(
        &self,
        tree: &ParsedTree,
        source: &str,
        file_path: &str,
    ) -> Result<Vec<Node>, Error> {
        let mut extractor = TypeScriptExtractor::new(source, file_path);
        extractor.extract(tree)
    }
}
```

### 12.2 Java Method Extractor Example

```rust
// codegraph-ir/src/features/ir_generation/infrastructure/extractors/java/method.rs

pub fn extract_method(
    node: &tree_sitter::Node,
    source: &str,
    parent_fqn: &str,
) -> Result<Node, Error> {
    let name = extract_method_name(node, source)?;
    let fqn = format!("{}.{}", parent_fqn, name);

    // Extract modifiers
    let modifiers = extract_modifiers(node, source);

    // Extract generic parameters
    let type_params = extract_type_parameters(node, source)?;

    // Extract parameters
    let params = extract_parameters(node, source)?;

    // Extract throws clause
    let throws = extract_throws_clause(node, source)?;

    // Build node
    let mut attrs = HashMap::new();
    attrs.insert("modifiers", json!(modifiers));
    if !type_params.is_empty() {
        attrs.insert("type_parameters", json!(type_params));
    }
    if !throws.is_empty() {
        attrs.insert("throws", json!(throws));
    }

    Ok(Node {
        id: generate_id(&fqn),
        kind: NodeKind::Method,
        fqn,
        name: Some(name),
        span: node_to_span(node),
        attrs,
        ..Default::default()
    })
}
```

### 12.3 Kotlin Extension Function Extractor

```rust
// codegraph-ir/src/features/ir_generation/infrastructure/extractors/kotlin/function.rs

pub fn extract_extension_function(
    node: &tree_sitter::Node,
    source: &str,
    module_fqn: &str,
) -> Result<Node, Error> {
    // Extension: fun String.isEmail(): Boolean
    let receiver_type = extract_receiver_type(node, source)?;
    let name = extract_function_name(node, source)?;

    // FQN format: receiver.functionName
    let fqn = format!("{}.{}.{}", module_fqn, receiver_type, name);

    let mut attrs = HashMap::new();
    attrs.insert("is_extension", json!(true));
    attrs.insert("receiver_type", json!(receiver_type));

    // Check if suspend function
    if is_suspend_function(node, source) {
        attrs.insert("is_suspend", json!(true));
    }

    Ok(Node {
        id: generate_id(&fqn),
        kind: NodeKind::Function,
        fqn,
        name: Some(name),
        attrs,
        ..Default::default()
    })
}
```

---

## Conclusion

This RFC provides a comprehensive, phased approach to implementing TypeScript, Java, and Kotlin support in the Semantica v2 Rust engine. By following the proven architecture from v1 and leveraging Rust's performance advantages, we can achieve:

- **5-8x performance improvement** over Python implementation
- **Feature parity** with v1 for critical languages
- **Extensible architecture** for future language additions
- **Production-ready** multi-language code analysis

**Recommendation**: Approve for implementation starting with TypeScript (Phase 1).
