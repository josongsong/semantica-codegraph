# codegraph-parsers

**Independent parser package for CodeGraph** - Template and document parsing for modern frameworks.

## 🎯 Purpose

Provides **language-agnostic parsers** for:
- **React JSX/TSX** - Component analysis with XSS sink detection
- **Vue SFC** - Single File Component parsing with v-html detection
- **Markdown** - Document section extraction
- **Jupyter Notebooks** - Code block parsing

## 📦 Installation

```bash
pip install -e packages/codegraph-parsers
```

## 🔧 Usage

### Python API

```python
from codegraph_parsers import JSXTemplateParser, MarkdownParser

# React component parsing
jsx_parser = JSXTemplateParser()
template_doc = jsx_parser.parse(source_code, file_path)

# Markdown parsing
md_parser = MarkdownParser()
document = md_parser.parse(file_path, source_code)
```

### Rust API (via PyO3)

```rust
use codegraph_ir::pipeline::preprocessors::TemplatePreprocessor;

let preprocessor = TemplatePreprocessor::new();
let template = preprocessor.parse_template("App.tsx", source)?;
```

## 🏗️ Architecture

```
codegraph-parsers/           # Independent package
├── template/
│   ├── jsx_template_parser.py    # React JSX/TSX
│   └── vue_sfc_parser.py          # Vue SFC
└── document/
    ├── markdown_parser.py         # Markdown
    └── notebook_parser.py         # Jupyter

codegraph-rust/              # Rust engine (depends on parsers)
└── codegraph-ir/
    └── preprocessors/
        └── template_parser.rs    # PyO3 bridge

codegraph-engine/            # Legacy Python engine (depends on parsers)
```

## 🎨 Features

- **XSS Sink Detection**: Auto-detect `dangerouslySetInnerHTML`, `v-html`
- **Severity Scoring**: 0-5 security severity levels
- **Tree-sitter Based**: Fast, incremental parsing
- **Zero Dependencies**: No framework runtime required

## 📚 Documentation

See [TEMPLATE_PIPELINE_INTEGRATION.md](../codegraph-rust/codegraph-ir/TEMPLATE_PIPELINE_INTEGRATION.md) for integration details.

## 🔄 Version History

- **0.1.0** (2025-12-28): Initial release
  - JSX/TSX parser
  - Vue SFC parser
  - Markdown parser
  - Jupyter Notebook parser

## 📄 License

Same as parent CodeGraph project.
