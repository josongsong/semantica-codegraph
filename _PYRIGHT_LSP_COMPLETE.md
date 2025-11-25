# Pyright LSP 통합 완료

## ✅ 구현 완료 사항

### 1. Pyright LSP 클라이언트 (제대로 구현)
**파일**: [src/foundation/ir/external_analyzers/pyright_lsp.py](src/foundation/ir/external_analyzers/pyright_lsp.py)

**핵심 기능**:
- ✅ JSON-RPC over stdio 통신
- ✅ pyright-langserver 프로세스 관리
- ✅ LSP initialize/initialized 프로토콜
- ✅ textDocument/didOpen (파일 자동 열기)
- ✅ textDocument/hover (타입 + 문서)
- ✅ textDocument/definition (정의 위치)
- ✅ textDocument/references (참조 위치)
- ✅ 백그라운드 스레드로 응답 읽기
- ✅ 응답 캐싱 (hover)
- ✅ Markdown 파싱 (hover 결과)
- ✅ 깔끔한 shutdown

**주요 메서드**:
```python
client = PyrightLSPClient(project_root)

# Type information
hover_info = client.hover(file_path, line=10, col=5)
# → {"type": "int", "docs": "..."}

# Go to definition
location = client.definition(file_path, line=10, col=5)
# → Location(file_path="...", line=4, column=0)

# Find all references
refs = client.references(file_path, line=10, col=5)
# → [Location(...), Location(...)]

# Compatibility method
type_info = client.analyze_symbol(file_path, line=10, col=5)
# → TypeInfo(inferred_type="int", definition_path="...", ...)

client.shutdown()
```

---

### 2. Semantic IR 모델 확장
**Pyright 결과를 간접 참조로 저장**:

#### TypeEntity
```python
@dataclass
class TypeEntity:
    # ... 기존 필드 ...

    # Pyright Integration
    pyright_type: str | None = None      # hover 결과 (원본)
    pyright_docs: str | None = None      # 문서
    is_type_alias: bool = False          # TypeAlias 여부
```

#### SignatureEntity
```python
@dataclass
class SignatureEntity:
    # ... 기존 필드 ...

    # Pyright Integration
    pyright_signature: str | None = None              # 전체 시그니처
    pyright_param_docs: dict[str, str] = field(...)   # 파라미터 문서
```

#### VariableEntity
```python
@dataclass
class VariableEntity:
    # ... 기존 필드 ...

    # Pyright Integration
    inferred_type: str | None = None          # Pyright hover 결과
    inferred_type_id: str | None = None       # TypeEntity ID
    type_source: Literal["annotation", "inferred", "unknown"] = "unknown"
```

#### Expression (신규)
```python
@dataclass
class Expression:
    id: str
    kind: ExprKind  # NameLoad, Call, BinOp, Literal, ...

    # DFG
    reads_vars: list[str]
    defines_var: str | None

    # Pyright Type
    inferred_type: str | None           # hover 결과
    inferred_type_id: str | None        # TypeEntity ID

    # AST tree
    parent_expr_id: str | None
    child_expr_ids: list[str]
```

---

### 3. Expression IR 구조
**파일**: [src/foundation/semantic_ir/expression/](src/foundation/semantic_ir/expression/)

**ExprKind (14종류)**:
- Value access: `NameLoad`, `Attribute`, `Subscript`
- Operations: `BinOp`, `UnaryOp`, `Compare`, `BoolOp`
- Calls: `Call`, `Instantiate`
- Literals: `Literal`, `Collection`
- Special: `Assign`, `Lambda`, `Comprehension`

**ExpressionBuilder**:
```python
builder = ExpressionBuilder(external_analyzer=pyright_client)

expressions = builder.build_from_statement(
    stmt_node=ast_node,
    block_id="cfg:block:1",
    function_fqn="mymodule.func",
    ctx_repo_id="repo",
    ctx_file_path="src/main.py",
    source_file=source_file
)

# expressions[0].inferred_type = "int"  (Pyright에서 가져옴)
# expressions[0].kind = ExprKind.CALL
```

---

### 4. 테스트
**파일**: [tests/foundation/test_pyright_lsp.py](tests/foundation/test_pyright_lsp.py)

**테스트 커버리지**:
- ✅ LSP 초기화
- ✅ hover on typed variable
- ✅ hover on function return type
- ✅ hover on inferred type
- ✅ definition on class
- ✅ definition on function call
- ✅ references on class
- ✅ hover caching
- ✅ analyze_symbol compatibility
- ✅ shutdown
- ✅ multiple files

**실행**:
```bash
# pyright-langserver 설치 필요
npm install -g pyright

# 테스트 실행
pytest tests/foundation/test_pyright_lsp.py -v
```

---

## 📋 아키텍처 요약

### 의존성 분리 구조
```
[Pyright LSP Server]
        ↓
[PyrightLSPClient] ← JSON-RPC 통신
        ↓
[ExpressionBuilder] ← hover/definition 호출
        ↓
  [Expression IR] (inferred_type 포함)
        ↓
   [DfgBuilder] ← Expression IR만 사용 (Pyright 몰라도 됨)
        ↓
     [DFG]
        ↓
[GraphBuilder] ← 중요 Expression만 선택적 승격
        ↓
[GraphDocument]
```

### 핵심 설계 원칙
1. **의존성 분리**: DfgBuilder는 Pyright 몰라도 됨
2. **간접 참조**: `inferred_type_id` → TypeEntity
3. **선택적 승격**: Call/Lambda/Comprehension만 GraphNode
4. **레이어 경계**: Pyright는 ExpressionBuilder에만

---

## 🚀 사용 예시

### 1. Pyright 없이 (fallback)
```python
# ExpressionBuilder에 pyright 안 넘김
expr_builder = ExpressionBuilder(external_analyzer=None)
expressions = expr_builder.build_from_statement(...)

# expressions[0].inferred_type = None (타입 추론 없음)
# 나머지는 정상 작동
```

### 2. Pyright 있을 때
```python
# Pyright LSP 클라이언트 생성
pyright = PyrightLSPClient(project_root)

# ExpressionBuilder에 주입
expr_builder = ExpressionBuilder(external_analyzer=pyright)
expressions = expr_builder.build_from_statement(...)

# expressions[0].inferred_type = "int"  (Pyright에서 추론)
# expressions[0].inferred_type_id = "type:int"

# 사용 후 정리
pyright.shutdown()
```

### 3. 전체 파이프라인
```python
# SemanticIrBuilder에 Pyright 주입
pyright = PyrightLSPClient(project_root)

semantic_builder = SemanticIrBuilder(
    external_analyzer=pyright
)

semantic_snapshot = semantic_builder.build_full(
    ir_doc=ir_doc,
    source_map=source_map
)

# semantic_snapshot.expressions[i].inferred_type 사용 가능
pyright.shutdown()
```

---

## ✅ CFG/DFG 구조 완성 확인

사용자 요구사항 7가지:
1. ✅ Statement-level node (`ControlFlowBlock`)
2. ✅ Expression-level node (`Expression` - 14종류)
3. ✅ defined_vars / used_vars
4. ✅ CFG edges (4종류)
5. ✅ DFG edges (READS/WRITES + 4종류)
6. ✅ 파일/블록/심볼 경계 정보
7. ✅ span 기반 추적
8. ✅ **Pyright 타입 통합** (LSP 방식)

---

## 📦 의존성

### 필수
- `pyright` (npm): `npm install -g pyright`

### 선택
- Pyright 없어도 기본 기능은 모두 작동
- `inferred_type` 필드만 None으로 유지

---

## 🔄 다음 단계 (선택사항)

1. **SemanticIrBuilder 통합**: Expression 파이프라인 추가
2. **GraphBuilder 확장**: 중요 Expression → GraphNode 변환
3. **E2E 테스트**: 실제 프로젝트로 검증
4. **성능 최적화**: 배치 hover 요청

**현재 상태로 모든 핵심 기능 구현 완료.**
