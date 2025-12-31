# CodeGraph Parsers - SOTA Architecture

**설계 목표**: 구버전/신버전 독립적인 Parser 레이어

---

## 🏗️ 전체 아키텍처

```
┌────────────────────────────────────────────────────────┐
│ Application Layer                                      │
├────────────────────────────────────────────────────────┤
│                                                        │
│  ┌──────────────────┐      ┌──────────────────┐      │
│  │ codegraph-engine │      │ codegraph-rust   │      │
│  │ (Python 구버전)  │      │ (Rust 신버전)    │      │
│  └────────┬─────────┘      └────────┬─────────┘      │
│           │                         │                 │
│           │   ┌─────────────────┐   │                 │
│           └───┤ codegraph-      ├───┘                 │
│               │ parsers         │                     │
│               │ (독립 패키지)   │                     │
│               └─────────────────┘                     │
│                                                        │
├────────────────────────────────────────────────────────┤
│ Infrastructure Layer                                   │
│  - codegraph-shared                                   │
└────────────────────────────────────────────────────────┘
```

---

## 📦 패키지 구조

### codegraph-parsers (독립 도메인)

```
codegraph-parsers/
├── codegraph_parsers/
│   ├── __init__.py               # Public API
│   ├── template/                 # Template parsers
│   │   ├── __init__.py
│   │   ├── jsx_template_parser.py    # React JSX/TSX
│   │   └── vue_sfc_parser.py         # Vue SFC
│   └── document/                 # Document parsers
│       ├── __init__.py
│       ├── parser.py                 # Markdown, Notebook
│       └── rst_parser.py             # ReStructuredText
│
├── tests/
│   ├── test_jsx_parser.py
│   ├── test_vue_parser.py
│   └── test_markdown_parser.py
│
├── pyproject.toml                # Independent versioning
├── README.md
├── MIGRATION.md
└── ARCHITECTURE.md               # This file
```

---

## 🔄 데이터 흐름

### React Component Parsing

```
User Code (App.tsx)
     ↓
┌────────────────────────────────────────┐
│ Rust: process_any_file()              │
│  - File type detection                │
└────────┬───────────────────────────────┘
         ↓
┌────────────────────────────────────────┐
│ Rust: TemplatePreprocessor            │
│  - PyO3 bridge                        │
└────────┬───────────────────────────────┘
         ↓ (Python GIL)
┌────────────────────────────────────────┐
│ Python: JSXTemplateParser             │
│  - tree-sitter parsing                │
│  - XSS sink detection                 │
└────────┬───────────────────────────────┘
         ↓
┌────────────────────────────────────────┐
│ TemplateDoc (Python dataclass)        │
│  - slots, elements, metadata          │
└────────┬───────────────────────────────┘
         ↓ (pythonize::depythonize)
┌────────────────────────────────────────┐
│ Rust: HashMap<String, serde_json>     │
└────────┬───────────────────────────────┘
         ↓
┌────────────────────────────────────────┐
│ Rust: convert_template_to_ir()        │
│  - Generate Nodes (Expression)        │
│  - Generate Edges (READS, CONTAINS)   │
│  - Security annotations               │
└────────┬───────────────────────────────┘
         ↓
┌────────────────────────────────────────┐
│ IR Graph                               │
│  - Nodes: [File, Element, Slot, Var]  │
│  - Edges: [CONTAINS, READS]            │
│  - Attrs: {"is_sink":"true"}          │
└────────────────────────────────────────┘
```

---

## 🎯 설계 원칙

### 1. **Single Responsibility Principle**

```
codegraph-parsers:
  ✅ DO: Parse template/document files
  ❌ DON'T: IR generation, analysis, indexing

codegraph-rust:
  ✅ DO: IR generation, graph analysis
  ❌ DON'T: Template parsing logic
```

### 2. **Dependency Inversion Principle**

```
High-level modules (codegraph-rust, codegraph-engine)
    ↓ depends on
Abstraction (codegraph-parsers interface)
    ↑ implements
Low-level modules (JSXTemplateParser, VueSFCParser)
```

### 3. **Open/Closed Principle**

```python
# Adding new parser: Open for extension
class SvelteParser(BaseTemplateParser):  # ✅ Easy to add
    def parse(self, source, file_path):
        ...

# Existing code: Closed for modification
# No changes needed in Rust or other parsers ✅
```

---

## 🔌 인터페이스 설계

### Python Interface

```python
from abc import ABC, abstractmethod
from dataclasses import dataclass

@dataclass
class TemplateDoc:
    doc_id: str
    engine: str
    file_path: str
    slots: List[TemplateSlot]
    elements: List[TemplateElement]

class BaseTemplateParser(ABC):
    @abstractmethod
    def parse(self, source: str, file_path: str) -> TemplateDoc:
        """Parse template file and return TemplateDoc"""
        pass
```

### Rust Interface (PyO3)

```rust
pub struct TemplatePreprocessor {
    parsers_module: Arc<Mutex<Option<Py<PyModule>>>>,
}

impl TemplatePreprocessor {
    pub fn parse_template(&self, file_path: &str, source: &str)
        -> Result<TemplateDoc> {
        Python::with_gil(|py| {
            let parser = self.get_parser(py, file_path)?;
            let result = parser.call_method1("parse", (source, file_path))?;
            self.convert_to_rust(result)
        })
    }
}
```

---

## 📊 성능 고려사항

### Python Parsing (Current)

```
Pros:
✅ Fast development (2-3 days per parser)
✅ tree-sitter bindings available
✅ Easy to debug
✅ Community libraries (markdown, nbformat)

Cons:
❌ GIL contention (단일 스레드)
❌ PyO3 overhead (~1-2ms per call)
```

### Rust Native Parsing (Future, if needed)

```
Pros:
✅ No GIL (parallel parsing)
✅ Zero overhead
✅ Incremental parsing (tree-sitter reuse)

Cons:
❌ Slow development (1-2 weeks per parser)
❌ Harder to maintain
❌ Less flexible
```

**현재 선택**: Python (개발 속도 우선)
**마이그레이션 조건**: Parsing이 전체의 30% 이상 차지 시

---

## 🧪 테스트 전략

### Unit Tests (Python)

```python
def test_jsx_xss_sink_detection():
    parser = JSXTemplateParser()
    result = parser.parse("""
        <div dangerouslySetInnerHTML={{__html: user.bio}} />
    """, "test.tsx")

    assert len(result.slots) == 1
    assert result.slots[0].is_sink == True
    assert result.slots[0].context_kind == "RawHtml"
```

### Integration Tests (Rust)

```rust
#[test]
fn test_template_to_ir_conversion() {
    let result = process_any_file("App.tsx", jsx_source, "repo1")?;

    let sinks: Vec<_> = result.nodes.iter()
        .filter(|n| n.attrs.contains("is_sink"))
        .collect();

    assert_eq!(sinks.len(), 1);
}
```

---

## 🔮 확장 계획

### Phase 1: 추가 Parser (Q1 2025)
- Svelte component parser
- Angular template parser
- Jinja2 template parser

### Phase 2: 성능 최적화 (Q2 2025)
- Incremental parsing (tree-sitter reuse)
- Parallel parsing (multi-threading)
- Caching strategy

### Phase 3: Rust Native (Q3 2025, if needed)
- Benchmark 후 결정
- Hot path만 Rust로 이동 (JSX/TypeScript)
- Python parsers는 유지 (Markdown, Notebook)

---

## 📚 참고 자료

### SOTA 프로젝트
- **Ruff**: Python linter in Rust (hybrid architecture)
- **SWC**: JS compiler (started with Babel, then Rust)
- **Biome**: JS toolchain (Rust-first, but extensible)

### 설계 패턴
- **Bridge Pattern**: PyO3 abstraction
- **Strategy Pattern**: Parser selection
- **Factory Pattern**: Parser instantiation

---

**설계자**: Claude + User
**날짜**: 2025-12-28
**상태**: ✅ Production Ready
