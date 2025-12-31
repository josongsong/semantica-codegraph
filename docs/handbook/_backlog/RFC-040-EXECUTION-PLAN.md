# RFC-040 실행계획: Multi-Module Architecture

**Status**: Ready for Execution
**Created**: 
**Estimated Duration**: Phase별 진행

---

## 📋 실행 개요

### 목표
codegraph 모놀리스를 4개의 독립 패키지로 분리:
1. **codegraph-core** - IR Builder (Foundation)
2. **codegraph-query** - Q.DSL Query Engine
3. **codegraph-taint** - Taint Analysis
4. **codegraph** - Umbrella CLI

---

## 🚀 Phase 1: Monorepo 구조 설정 (1일)

### Task 1-1: 디렉토리 구조 생성

```bash
# 새 구조
mkdir -p packages/{core,query,taint,cli}

# 각 패키지 기본 구조
for pkg in core query taint cli; do
  mkdir -p packages/$pkg/src/codegraph_$pkg
  mkdir -p packages/$pkg/tests
  touch packages/$pkg/pyproject.toml
  touch packages/$pkg/src/codegraph_$pkg/__init__.py
done
```

### Task 1-2: Workspace pyproject.toml 설정

```toml
# /pyproject.toml (root)
[tool.hatch.envs.default]
features = ["dev"]

[tool.hatch.build]
packages = ["packages/*/src/*"]

[project.optional-dependencies]
core = ["codegraph-core"]
query = ["codegraph-core", "codegraph-query"]
taint = ["codegraph-core", "codegraph-query", "codegraph-taint"]
all = ["codegraph"]

[tool.uv.workspace]
members = ["packages/*"]
```

### Task 1-3: 개별 패키지 pyproject.toml

**packages/core/pyproject.toml**:
```toml
[project]
name = "codegraph-core"
version = "0.1.0"
dependencies = [
    "tree-sitter>=0.20.0",
    "tree-sitter-python>=0.20.0",
    "pydantic>=2.0.0",
]
```

**packages/query/pyproject.toml**:
```toml
[project]
name = "codegraph-query"
version = "0.1.0"
dependencies = [
    "codegraph-core>=0.1.0",
    "rustworkx>=0.13.0",  # optional
]
```

---

## 🚀 Phase 2: codegraph-core 분리 (3일)

### Task 2-1: 핵심 모델 이동

| Source | Destination |
|--------|-------------|
| `src/contexts/code_foundation/infrastructure/ir/models/` | `packages/core/src/codegraph_core/models/` |
| `src/contexts/code_foundation/domain/models.py` | `packages/core/src/codegraph_core/models/` |
| `src/contexts/code_foundation/infrastructure/ir/models/document.py` | `packages/core/src/codegraph_core/models/ir_document.py` |

### Task 2-2: Builder 이동

| Source | Destination |
|--------|-------------|
| `infrastructure/generators/python/` | `packages/core/src/codegraph_core/builders/python/` |
| `infrastructure/generators/typescript/` | `packages/core/src/codegraph_core/builders/typescript/` |
| `infrastructure/generators/java/` | `packages/core/src/codegraph_core/builders/java/` |

### Task 2-3: DFG/CFG 이동

| Source | Destination |
|--------|-------------|
| `infrastructure/dfg/` | `packages/core/src/codegraph_core/semantic/dfg/` |
| `infrastructure/cfg/` | `packages/core/src/codegraph_core/semantic/cfg/` |

### Task 2-4: Protocol 정의

```python
# packages/core/src/codegraph_core/protocols/program_ir.py
from typing import Protocol, Iterator
from codegraph_core.models import Node, Edge

class ProgramIR(Protocol):
    """언어 독립적 IR 인터페이스"""

    @property
    def nodes(self) -> Iterator[Node]: ...

    @property
    def edges(self) -> Iterator[Edge]: ...

    def get_node(self, node_id: str) -> Node | None: ...

    def get_edges_from(self, node_id: str) -> list[Edge]: ...
```

### Task 2-5: Export 정리

```python
# packages/core/src/codegraph_core/__init__.py
from codegraph_core.models.ir_document import IRDocument
from codegraph_core.models.node import Node, NodeKind
from codegraph_core.models.edge import Edge, EdgeKind
from codegraph_core.models.expression import Expression
from codegraph_core.builders.ir_builder import IRBuilder
from codegraph_core.protocols.program_ir import ProgramIR

__all__ = [
    "IRDocument",
    "IRBuilder",
    "Node", "NodeKind",
    "Edge", "EdgeKind",
    "Expression",
    "ProgramIR",
]
```

---

## 🚀 Phase 3: codegraph-query 분리 (2일)

### Task 3-1: Q.DSL 이동

| Source | Destination |
|--------|-------------|
| `domain/query/expressions.py` | `packages/query/src/codegraph_query/dsl/expressions.py` |
| `domain/query/selectors.py` | `packages/query/src/codegraph_query/dsl/selectors.py` |
| `domain/query/types.py` | `packages/query/src/codegraph_query/dsl/types.py` |

### Task 3-2: Query Engine 이동

| Source | Destination |
|--------|-------------|
| `infrastructure/query/query_engine.py` | `packages/query/src/codegraph_query/engine/` |
| `infrastructure/query/traversal_engine.py` | `packages/query/src/codegraph_query/engine/` |
| `infrastructure/query/path_collector.py` | `packages/query/src/codegraph_query/engine/` |

### Task 3-3: Index 이동

| Source | Destination |
|--------|-------------|
| `infrastructure/query/indexes/` | `packages/query/src/codegraph_query/indexes/` |

### Task 3-4: Export 정리

```python
# packages/query/src/codegraph_query/__init__.py
from codegraph_query.dsl.expressions import Q, E, PathQuery
from codegraph_query.engine.query_engine import QueryEngine
from codegraph_query.engine.traversal_engine import TraversalEngine

__all__ = ["Q", "E", "PathQuery", "QueryEngine", "TraversalEngine"]
```

---

## 🚀 Phase 4: codegraph-taint 분리 (2일)

### Task 4-1: Taint 핵심 이동

| Source | Destination |
|--------|-------------|
| `domain/taint/` | `packages/taint/src/codegraph_taint/core/` |
| `application/taint_analysis_service.py` | `packages/taint/src/codegraph_taint/service/` |
| `infrastructure/taint/` | `packages/taint/src/codegraph_taint/infrastructure/` |

### Task 4-2: Guard Detection 이동

| Source | Destination |
|--------|-------------|
| `infrastructure/taint/validation/guard_detector.py` | `packages/taint/src/codegraph_taint/guard/` |

### Task 4-3: Rule Adapter 연결

```python
# packages/taint/src/codegraph_taint/adapters/srcr_adapter.py
from srcr import RuleCompiler, RuleRuntime  # 외부 패키지

class SRCRAdapter:
    """SRCR Rule Engine과의 연동"""

    def __init__(self):
        self.compiler = RuleCompiler()
        self.runtime = RuleRuntime()
```

---

## 🚀 Phase 5: Umbrella 패키지 (1일)

### Task 5-1: CLI 통합

```python
# packages/cli/src/codegraph/__init__.py
# Re-export everything
from codegraph_core import *
from codegraph_query import *
from codegraph_taint import *

__version__ = "1.0.0"
```

### Task 5-2: CLI Entry Point

```python
# packages/cli/src/codegraph/cli.py
import click
from codegraph_core import IRBuilder
from codegraph_query import QueryEngine
from codegraph_taint import TaintAnalyzer

@click.group()
def main():
    pass

@main.command()
@click.argument("path")
def analyze(path: str):
    """Full taint analysis"""
    ...

@main.command()
@click.argument("path")
def build(path: str):
    """Build IR only"""
    ...
```

---

## 🚀 Phase 6: Import 마이그레이션 (2일)

### Task 6-1: 자동 변환 스크립트

```python
# scripts/migrate_imports.py
import re
from pathlib import Path

IMPORT_MAP = {
    "from src.contexts.code_foundation.infrastructure.ir.models.document import IRDocument":
        "from codegraph_core import IRDocument",

    "from src.contexts.code_foundation.domain.query import Q, E":
        "from codegraph_query import Q, E",

    "from src.contexts.code_foundation.application.taint_analysis_service":
        "from codegraph_taint.service import TaintAnalysisService",
}

def migrate_file(path: Path):
    content = path.read_text()
    for old, new in IMPORT_MAP.items():
        content = content.replace(old, new)
    path.write_text(content)
```

### Task 6-2: Compatibility Layer (임시)

```python
# src/contexts/code_foundation/__init__.py
# DEPRECATED: 호환성 유지용 (6개월 후 제거)
import warnings

def __getattr__(name):
    warnings.warn(
        f"Import from contexts.code_foundation is deprecated. "
        f"Use codegraph_core/query/taint instead.",
        DeprecationWarning,
        stacklevel=2
    )
    # Forward to new location
    ...
```

---

## 🚀 Phase 7: 테스트 & 검증 (2일)

### Task 7-1: 패키지별 테스트

```bash
# 각 패키지 독립 테스트
cd packages/core && pytest tests/
cd packages/query && pytest tests/
cd packages/taint && pytest tests/

# 통합 테스트
cd packages/cli && pytest tests/integration/
```

### Task 7-2: 설치 테스트

```bash
# 각 패키지 개별 설치 확인
pip install ./packages/core
python -c "from codegraph_core import IRBuilder; print('OK')"

pip install ./packages/query
python -c "from codegraph_query import Q, E; print('OK')"
```

### Task 7-3: CI 업데이트

```yaml
# .github/workflows/test.yml
jobs:
  test-packages:
    strategy:
      matrix:
        package: [core, query, taint, cli]
    steps:
      - uses: actions/checkout@v4
      - run: cd packages/${{ matrix.package }} && pytest
```

---

## 📊 검증 체크리스트

### Phase 완료 조건

| Phase | 완료 조건 |
|-------|----------|
| 1 | `uv sync` 성공 |
| 2 | `from codegraph_core import IRBuilder` 동작 |
| 3 | `from codegraph_query import Q, E` 동작 |
| 4 | `from codegraph_taint import TaintAnalyzer` 동작 |
| 5 | `pip install codegraph` → 전체 기능 동작 |
| 6 | 기존 코드 import 에러 0개 |
| 7 | 전체 테스트 통과 |

---

## ⚠️ 리스크 & 대응

### Risk 1: 순환 의존성

**증상**: A → B → A 형태의 import
**대응**: Protocol 기반 추상화, dependency injection

### Risk 2: 테스트 실패

**증상**: fixture path 변경으로 테스트 실패
**대응**: conftest.py에 `PACKAGE_ROOT` 환경변수 추가

### Risk 3: 성능 저하

**증상**: cross-package 호출 오버헤드
**대응**: 실측 후 필요시 inline 유지

---

## 📅 일정 요약

| Phase | 작업 | 예상 |
|-------|------|------|
| 1 | Monorepo 설정 | 1일 |
| 2 | codegraph-core | 3일 |
| 3 | codegraph-query | 2일 |
| 4 | codegraph-taint | 2일 |
| 5 | Umbrella CLI | 1일 |
| 6 | Import 마이그레이션 | 2일 |
| 7 | 테스트 & 검증 | 2일 |
| **Total** | | **13일** |

---

## 🎯 즉시 실행 가능한 첫 단계

```bash
# Step 1: 디렉토리 생성
mkdir -p packages/{core,query,taint,cli}/src
mkdir -p packages/{core,query,taint,cli}/tests

# Step 2: pyproject.toml 생성 (위 내용 참조)

# Step 3: core 패키지 모델 복사 시작
cp -r src/contexts/code_foundation/infrastructure/ir/models/ \
      packages/core/src/codegraph_core/models/
```

---

**다음 액션**: Phase 1부터 시작하시겠습니까?
