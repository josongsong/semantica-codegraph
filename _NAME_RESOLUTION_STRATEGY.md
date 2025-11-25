# Name Resolution Graph - 구현 전략

**Date:** 2024-11-24
**Status:** 📋 Planning

---

## 🎯 목표

**Name Resolution Graph**: 코드의 모든 심볼(변수, 함수, 클래스)의 정의와 참조를 추적하는 그래프

```python
# Example
def main():
    user = get_user(123)  # user는 어디서 정의? get_user는 어디서 정의?
    print(user.name)      # name은 어디서 정의?
```

**우리가 답해야 할 질문:**
1. "이 심볼은 어디서 정의되었는가?" (Definition)
2. "이 정의는 어디서 사용되는가?" (References)
3. "이 스코프에서 이 이름은 무엇을 가리키는가?" (Binding)

---

## 🔧 Hybrid 구현 전략 (Pyright + 자체 구현)

### Phase 1: 자체 구현 (Tree-sitter 기반) ✅ 70% 완료

**이미 있는 것:**
- ✅ IMPORTS Edge - 파일 간 import 추적
- ✅ CONTAINS Edge - 스코프 계층 구조
- ✅ Node.fqn - Fully Qualified Name
- ✅ Node.parent_id - 스코프 체인

**추가 필요:**
```python
# src/foundation/semantic_ir/name_resolution/
├── models.py           # NameBinding, DefinitionSite, ReferenceSite
├── builder.py          # Name Resolution Graph 구축
├── scope_resolver.py   # Scope chain 분석
└── import_resolver.py  # Import 추적
```

**구현 내용:**
1. **Local Scope Resolution** (함수/클래스 내부)
   - 파라미터 → 정의 위치 매핑
   - 로컬 변수 → 정의 위치 매핑
   - 이미 DFG에서 일부 구현됨!

2. **Module Scope Resolution** (같은 파일 내)
   - 클래스/함수 이름 → Node ID 매핑
   - 이미 TypeResolver에서 `_local_classes`로 일부 구현됨!

3. **Import Resolution** (파일 간)
   - `from foo import Bar` → Bar의 정의 위치
   - IMPORTS Edge 활용

---

### Phase 2: Pyright 연동 (선택적, 정확도 향상) 🚀

**Pyright에서 얻을 정보:**

#### 1. **Definition Lookup** (가장 중요!)
```python
# Pyright LSP: textDocument/definition
# Input: file_path, line, column
# Output: definition_path, definition_line

# Example
symbol = "User"
location = (file="src/main.py", line=10, col=5)

pyright.get_definition(location)
# → {
#     definition_path: "src/models/user.py",
#     definition_line: 25,
#     symbol_name: "User"
# }
```

**활용:**
- Cross-file name resolution
- Import 자동 추적
- Alias 해소 (`import pandas as pd` → `pd.DataFrame` 추적)

#### 2. **References Lookup**
```python
# Pyright LSP: textDocument/references
# Input: symbol definition location
# Output: list of usage locations

pyright.get_references("src/models/user.py", line=25)
# → [
#     {file: "src/main.py", line: 10, col: 5},
#     {file: "src/api.py", line: 45, col: 12},
#     ...
# ]
```

**활용:**
- "이 함수를 누가 호출하는가?"
- "이 클래스를 어디서 사용하는가?"
- Call graph 구축

#### 3. **Symbol Information**
```python
# Pyright LSP: textDocument/hover
pyright.get_symbol_info("src/main.py", line=10, col=5)
# → {
#     name: "User",
#     kind: "class",
#     type: "Type[User]",
#     doc: "User model class",
#     definition: {...}
# }
```

---

## 🏗️ 데이터 구조

```python
@dataclass
class NameBinding:
    """Name → Definition 매핑"""
    name: str                    # "User"
    scope_node_id: str          # 어느 스코프에서?
    definition_node_id: str     # 어느 Node를 가리키는가?
    binding_kind: str           # "local" | "imported" | "builtin"
    source_location: Span       # 이 바인딩이 발생한 위치

@dataclass
class DefinitionSite:
    """심볼 정의 위치"""
    node_id: str                # IR Node ID
    symbol_name: str            # "User"
    file_path: str              # "src/models/user.py"
    span: Span                  # 정의 위치
    kind: str                   # "class" | "function" | "variable"

@dataclass
class ReferenceSite:
    """심볼 참조 위치"""
    definition_node_id: str     # 어떤 정의를 참조하는가?
    file_path: str              # "src/main.py"
    span: Span                  # 참조 위치
    context: str                # "read" | "write" | "call"

@dataclass
class NameResolutionGraph:
    """전체 Name Resolution Graph"""
    bindings: list[NameBinding]           # Name → Definition
    definitions: list[DefinitionSite]     # 모든 정의
    references: list[ReferenceSite]       # 모든 참조

    # Index for fast lookup
    name_to_bindings: dict[str, list[NameBinding]]
    definition_to_references: dict[str, list[ReferenceSite]]
```

---

## 🚀 구현 순서

### Step 1: 자체 구현 (Pyright 없이) - 2주

**우선순위 높음:**
1. Local scope resolution (함수 내 변수)
   - DFG의 VariableEntity 활용
   - Parameter → local variable 매핑

2. Module scope resolution (같은 파일)
   - Class/Function 이름 → Node ID
   - TypeResolver의 `_local_classes` 확장

3. Import resolution (기본)
   - IMPORTS Edge 활용
   - `from X import Y` 추적

**장점:**
- Pyright 의존 없음
- 빠름 (Tree-sitter만 사용)
- 대부분의 케이스 커버

**단점:**
- Cross-file alias 추적 어려움 (`import pandas as pd`)
- Type-based resolution 불가능

---

### Step 2: Pyright 통합 (선택적) - 1주

**Pyright LSP API 추가:**
```python
class PyrightAdapter:
    # 기존
    def analyze_file(...)
    def analyze_symbol(...)

    # NEW
    def get_definition(self, file_path, line, col) -> DefinitionInfo
    def get_references(self, file_path, line, col) -> list[Location]
    def get_hover(self, file_path, line, col) -> HoverInfo
```

**통합 전략:**
```python
class NameResolutionBuilder:
    def __init__(
        self,
        ir_doc: IRDocument,
        external_analyzer: ExternalAnalyzer | None = None
    ):
        self.ir_doc = ir_doc
        self.external_analyzer = external_analyzer

    def build(self) -> NameResolutionGraph:
        # 1. 자체 resolution (local + module scope)
        bindings = self._resolve_local_names()

        # 2. External analyzer로 보강 (if available)
        if self.external_analyzer:
            bindings = self._enhance_with_external(bindings)

        return NameResolutionGraph(bindings=bindings, ...)

    def _enhance_with_external(self, bindings):
        """Pyright로 cross-file 정확도 향상"""
        for binding in bindings:
            if binding.binding_kind == "imported":
                # Pyright에 물어보기
                def_info = self.external_analyzer.get_definition(...)
                if def_info:
                    binding.definition_node_id = def_info.node_id

        return bindings
```

---

## 📊 Pyright 활용 시나리오

### 시나리오 1: Cross-file Import 추적

**코드:**
```python
# src/models/user.py
class User:
    def __init__(self, name: str): ...

# src/main.py
from models.user import User

user = User("Alice")  # User는 어디서 정의?
```

**자체 구현:**
- IMPORTS Edge로 "models.user" 추적
- 하지만 정확한 Node ID 찾기 어려움

**Pyright 활용:**
```python
pyright.get_definition("src/main.py", line=3, col=8)  # "User"
# → definition_path: "src/models/user.py", line: 1
# → Node ID 매핑 가능!
```

---

### 시나리오 2: Alias 해소

**코드:**
```python
import pandas as pd

df = pd.DataFrame(...)  # DataFrame은 어디서?
```

**자체 구현:**
- `pd` → `pandas` 매핑 필요
- `pandas.DataFrame` → 실제 정의 추적 복잡

**Pyright 활용:**
```python
pyright.get_definition("main.py", line=3, col=5)  # "pd.DataFrame"
# → definition_path: "pandas/core/frame.py", line: 123
# → 자동으로 alias 해소!
```

---

### 시나리오 3: Method Resolution

**코드:**
```python
class A:
    def foo(self): ...

class B(A):
    pass

b = B()
b.foo()  # foo는 어디서 정의? A? B?
```

**자체 구현:**
- Inheritance 추적 필요
- Method Resolution Order (MRO) 구현 복잡

**Pyright 활용:**
```python
pyright.get_definition("main.py", line=8, col=2)  # "b.foo"
# → definition_path: "main.py", line: 2  (class A)
# → MRO 자동 해소!
```

---

## 🎯 결론

### Pyright 활용 정보 요약

| 정보 | Pyright API | 용도 |
|------|------------|------|
| **Definition Location** | `textDocument/definition` | Cross-file 추적, Import 해소 |
| **Type Info** | `textDocument/hover` | Type-based resolution |
| **References** | `textDocument/references` | "누가 이걸 쓰는가?" |
| **Symbol Kind** | `hover.kind` | Class/Function 구분 |

### 추천 구현 전략

**Phase 1 (2주):**
- ✅ 자체 구현 (Tree-sitter + IR)
- ✅ Local/Module scope
- ✅ 기본 Import 추적

**Phase 2 (1주):**
- ✅ Pyright LSP API 추가
- ✅ Cross-file 정확도 향상
- ✅ Alias/MRO 해소

**Phase 3 (선택):**
- ✅ Graph 시각화
- ✅ Query API (find-references, go-to-def)

---

## 🔗 기존 구조 활용

**이미 있는 것:**
1. ✅ `TypeInfo.definition_path/line` - Pyright 결과 받을 준비 완료
2. ✅ `IMPORTS Edge` - Import 관계 그래프
3. ✅ `CONTAINS Edge` - Scope 계층
4. ✅ `DFG.VariableEntity` - 변수 정의/사용 추적
5. ✅ `Node.fqn` - Fully Qualified Name

**추가할 것:**
1. 📋 NameBinding 모델
2. 📋 NameResolutionBuilder
3. 📋 Pyright LSP 메서드 (`get_definition`, `get_references`)

---

**Pyright는 선택적 강화제!**
- 기본은 자체 구현으로 동작 (빠르고 독립적)
- Pyright 있으면 정확도 향상 (cross-file, alias, MRO)
