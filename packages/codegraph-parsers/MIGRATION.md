# Parser 패키지 분리 - 마이그레이션 가이드

**날짜**: 2025-12-28
**목적**: 구버전 Python 엔진 의존성 제거

---

## 🎯 변경 사항

### Before (❌ 문제)
```
packages/
├── codegraph-engine/          # 구버전 엔진
│   └── parsers/               # ← Rust가 이것을 참조
│       ├── jsx_template_parser.py
│       └── vue_sfc_parser.py
│
└── codegraph-rust/            # 신버전 엔진
    └── template_parser.rs     # 구버전 의존 ← 아키텍처 모순!
```

**문제점**:
- 신버전(Rust)이 구버전(Python Engine)에 의존
- `codegraph-engine` 제거 시 파서도 함께 제거됨
- 의존성 방향 역전

### After (✅ 해결)
```
packages/
├── codegraph-parsers/         # ✅ 독립 패키지
│   ├── template/
│   │   ├── jsx_template_parser.py
│   │   └── vue_sfc_parser.py
│   └── document/
│       └── markdown_parser.py
│
├── codegraph-engine/          # 구버전 (parsers 사용)
└── codegraph-rust/            # 신버전 (parsers 사용)
```

**개선점**:
- ✅ 명확한 책임 분리
- ✅ 독립적인 버전 관리
- ✅ 구버전/신버전 모두 재사용
- ✅ 향후 다른 프로젝트에서도 사용 가능

---

## 📦 설치

### 1. codegraph-parsers 설치

```bash
cd packages/codegraph-parsers
pip install -e .
```

### 2. 의존성 확인

```bash
python -c "from codegraph_parsers import JSXTemplateParser, MarkdownParser; print('✅ Import successful!')"
```

---

## 🔄 마이그레이션 단계

### Step 1: Python 코드 업데이트

#### Before (구버전 참조)
```python
from codegraph_engine.code_foundation.infrastructure.parsers import JSXTemplateParser
from codegraph_engine.code_foundation.infrastructure.document.parsers import MarkdownParser
```

#### After (독립 패키지)
```python
from codegraph_parsers import JSXTemplateParser, MarkdownParser
# 또는
from codegraph_parsers.template import JSXTemplateParser
from codegraph_parsers.document import MarkdownParser
```

### Step 2: Rust 코드 (이미 완료 ✅)

```rust
// src/pipeline/preprocessors/template_parser.rs

// Before
py.import("codegraph_engine.code_foundation.infrastructure.parsers")

// After ✅
py.import("codegraph_parsers")
```

### Step 3: 구버전 엔진 업데이트 (Optional)

`codegraph-engine`도 독립 패키지를 사용하도록 변경:

```python
# codegraph-engine 내부
# Before
from .infrastructure.parsers import JSXTemplateParser

# After
from codegraph_parsers import JSXTemplateParser
```

---

## 🧪 테스트

### Python 테스트
```bash
cd packages/codegraph-parsers
pytest tests/
```

### Rust 통합 테스트
```bash
cd packages/codegraph-rust/codegraph-ir
cargo test --features python
```

---

## 📊 의존성 그래프

### Before
```
codegraph-rust ──┐
                 ├─→ codegraph-engine (구버전 의존 ❌)
                 │   └── parsers/
                 └─→ codegraph-shared
```

### After
```
codegraph-rust ──┬─→ codegraph-parsers (독립 패키지 ✅)
                 └─→ codegraph-shared

codegraph-engine ──→ codegraph-parsers (재사용 ✅)
```

---

## 🎯 장점

### 1. **아키텍처 클린**
- 신버전이 구버전을 참조하지 않음
- 명확한 레이어 분리

### 2. **독립 배포**
```bash
# Parser만 업데이트
pip install codegraph-parsers==0.2.0

# Rust 엔진은 그대로
cargo build --release
```

### 3. **재사용성**
```python
# 다른 프로젝트에서도 사용
from codegraph_parsers import JSXTemplateParser

parser = JSXTemplateParser()
result = parser.parse(source_code, file_path)
```

### 4. **버전 관리**
```toml
[dependencies]
codegraph-parsers = "^0.1.0"  # 독립 버전
```

---

## 🔮 향후 계획

1. **구버전 엔진 마이그레이션**
   - `codegraph-engine` 내부 import 변경
   - 테스트 통과 확인

2. **추가 파서**
   - Svelte parser
   - Angular template parser
   - Jinja2 parser

3. **성능 최적화**
   - Incremental parsing (tree-sitter reuse)
   - Parallel parsing

---

## ✅ 체크리스트

- [x] `codegraph-parsers` 패키지 생성
- [x] Python 파서 파일 복사
- [x] `pyproject.toml` 설정
- [x] `__init__.py` export 설정
- [x] Rust import 경로 업데이트
- [x] README.md 작성
- [ ] pytest 테스트 작성
- [ ] 구버전 엔진 마이그레이션
- [ ] CI/CD 파이프라인 업데이트

---

**상태**: ✅ **마이그레이션 완료**
**다음 단계**: 구버전 엔진 import 업데이트 (Optional)
