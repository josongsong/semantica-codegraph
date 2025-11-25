# Pyright 파이프라인 최적화 완료

## ✅ 구현 완료

사용자 요청에 따라 성능 최적화를 구현했습니다.

---

## 📊 최적화 항목

### 1. Generic 타입 파라미터 추출 ✅

**파일**: [src/foundation/semantic_ir/typing/builder.py](src/foundation/semantic_ir/typing/builder.py)

**문제**: Generic 타입이 TODO로 남아 있었음
```python
# 기존: TODO
if "[" in pyright_type:
    type_entity.flavor = TypeFlavor.GENERIC
    # TODO: Extract generic parameters
```

**해결책**:
```python
# 새로운 구현
def _parse_pyright_type(self, type_entity: TypeEntity, pyright_type: str):
    # Generic 타입 파라미터 추출
    param_types = self._extract_generic_params(pyright_type)
    for param_type in param_types:
        param_entity = self._get_or_create_type_entity(param_type)
        type_entity.generic_param_ids.append(param_entity.id)

def _extract_generic_params(self, pyright_type: str) -> list[str]:
    """
    Examples:
    - "List[User]" → ["User"]
    - "Dict[str, int]" → ["str", "int"]
    - "List[Dict[str, User]]" → ["Dict[str, User]"]
    """
    # 중첩된 bracket 처리
    # comma로 split (bracket depth 고려)

def _split_generic_params(self, params_str: str) -> list[str]:
    """
    Examples:
    - "str, int" → ["str", "int"]
    - "Dict[str, int], User" → ["Dict[str, int]", "User"]
    """
    # bracket depth 추적하며 split
```

**추가 기능**:
```python
def _get_or_create_type_entity(self, type_str: str) -> TypeEntity:
    """타입 엔티티 캐싱 및 재사용"""
    type_id = f"type:{type_str}"
    if type_id in self._type_cache:
        return self._type_cache[type_id]

    # 새로 생성
    type_entity = TypeEntity(id=type_id, raw=type_str, flavor=flavor)
    self._type_cache[type_id] = type_entity

    # 재귀적으로 파싱 (nested generics)
    if "[" in type_str:
        self._parse_pyright_type(type_entity, type_str)

    return type_entity

def _determine_type_flavor(self, type_str: str) -> TypeFlavor:
    """타입 문자열에서 TypeFlavor 자동 결정"""
    # Primitives: int, str, float, bool, bytes, None
    # Builtins: list, dict, set, tuple, frozenset
    # Generic: List[...], Dict[...], Optional[...]
    # Callable: (x: int) -> str
    # User: 나머지
```

**효과**:
- ✅ `List[User]` → TypeEntity(id="type:List", generic_param_ids=["type:User"])
- ✅ `Dict[str, int]` → TypeEntity(id="type:Dict", generic_param_ids=["type:str", "type:int"])
- ✅ `Optional[List[User]]` → 중첩된 generic 재귀 파싱
- ✅ `int | str` → Union 멤버 추출

**성능 개선**:
- 타입 중복 제거 (캐싱)
- 재사용 가능한 TypeEntity

---

### 2. 타입 정규화 및 중복 제거 ✅

**파일**: [src/foundation/semantic_ir/typing/builder.py](src/foundation/semantic_ir/typing/builder.py)

**문제**: 같은 타입을 여러 번 생성
```python
# 기존: 중복 생성
type1 = TypeEntity(id="type:int", raw="int")
type2 = TypeEntity(id="type:int", raw="int")  # 중복!
```

**해결책**:
```python
# _type_cache로 중복 제거
def _get_or_create_type_entity(self, type_str: str) -> TypeEntity:
    type_id = f"type:{type_str}"

    # 캐시 확인
    if type_id in self._type_cache:
        return self._type_cache[type_id]  # 재사용

    # 새로 생성하고 캐싱
    type_entity = TypeEntity(id=type_id, ...)
    self._type_cache[type_id] = type_entity
    return type_entity

# build_full에서 모든 타입 수집
def build_full(self, ir_doc, source_map):
    # ...
    # 캐시에서 모든 타입 수집 (중복 제거됨)
    types = list(self._type_cache.values())
    return types, type_index
```

**효과**:
- ✅ 타입 중복 제거
- ✅ 메모리 절약
- ✅ 타입 그래프 일관성

---

### 3. Expression AST 캐싱 ✅

**파일**: [src/foundation/semantic_ir/expression/builder.py](src/foundation/semantic_ir/expression/builder.py)

**문제**: 같은 파일을 여러 블록에서 중복 파싱
```python
# 기존: 매번 파싱
for block in bfg_blocks:
    ast_tree = AstTree.parse(source_file)  # ❌ 중복 파싱!
    expressions = extract_from_ast(ast_tree)
```

**해결책**:
```python
class ExpressionBuilder:
    def __init__(self, external_analyzer=None):
        self.pyright = external_analyzer
        self._expr_counter = 0
        self._ast_cache: dict[str, "AstTree"] = {}  # ← AST 캐시

    def build_from_block(self, block, source_file):
        # 파일별 캐싱
        file_path = source_file.path
        if file_path not in self._ast_cache:
            self._ast_cache[file_path] = AstTree.parse(source_file)
        ast_tree = self._ast_cache[file_path]  # ✅ 재사용
```

**성능 개선**:
- **Before**: N개 블록 × 1회 파싱 = N회 파싱
- **After**: 파일당 1회 파싱 (블록 수와 무관)
- **예시**: 10개 블록, 2개 파일 → 10회 → **2회** (80% 감소)

---

### 4. Pyright 호출 최적화 (Batch Enrichment) ✅

**파일**: [src/foundation/semantic_ir/expression/builder.py](src/foundation/semantic_ir/expression/builder.py)

**문제**: Expression 생성 중 Pyright 개별 호출
```python
# 기존: 순차 호출
for stmt in statements:
    for expr in extract_expressions(stmt):
        hover = pyright.hover(file, line, col)  # ❌ N번 호출
        expr.inferred_type = hover["type"]
```

**해결책**: Deferred Enrichment + Position Deduplication
```python
def build_from_block(self, block, source_file):
    # Step 1: Expression 먼저 다 생성 (Pyright 없이)
    expressions = []
    for stmt_node in statements:
        stmt_exprs = self.build_from_statement(
            ...,
            source_file=None  # ← Pyright 건너뜀
        )
        expressions.extend(stmt_exprs)

    # Step 2: Batch enrichment
    if self.pyright and expressions:
        self._batch_enrich_with_pyright(expressions, source_file)

    return expressions

def _batch_enrich_with_pyright(self, expressions, source_file):
    """중복 제거 + 배치 처리"""
    # Group by unique (line, col)
    unique_positions: dict[tuple[int, int], list[Expression]] = {}
    for expr in expressions:
        pos = (expr.span.start_line, expr.span.start_col)
        if pos not in unique_positions:
            unique_positions[pos] = []
        unique_positions[pos].append(expr)

    # 위치별로 한 번만 호출
    for (line, col), exprs_at_pos in unique_positions.items():
        hover_info = self.pyright.hover(file, line, col)  # ✅ 중복 제거

        # 같은 위치의 모든 표현식에 적용
        for expr in exprs_at_pos:
            expr.inferred_type = hover_info["type"]
```

**성능 개선**:
- **Position deduplication**: 같은 위치 중복 호출 제거
- **Pyright 캐싱 효과**: 이미 PyrightLSPClient에서 hover 캐싱
- **예시**: 100개 표현식, 50개 unique 위치 → 100회 → **50회** (50% 감소)

---

## 📈 전체 성능 개선 요약

### Before (최적화 전)
```
파일 10개, 각 5개 블록, 블록당 20개 표현식
= 50개 블록, 1000개 표현식

- AST 파싱: 50회 (블록마다)
- Pyright hover: 1000회 (표현식마다)
- TypeEntity: 중복 생성
```

### After (최적화 후)
```
- AST 파싱: 10회 (파일당 1회) ✅ 80% 감소
- Pyright hover: ~500회 (중복 제거) ✅ 50% 감소
- TypeEntity: 중복 제거됨 ✅
```

---

## 🎯 아키텍처 개선

### 1. 타입 그래프 지원
```python
# Generic 파라미터 추출로 타입 그래프 구축 가능
List[User] → TypeEntity(id="type:List")
           → generic_param_ids=["type:User"]
           → TypeEntity(id="type:User")

# 타입 관계 추적
Dict[str, List[User]] → type:Dict
                      → type:str
                      → type:List → type:User
```

### 2. 메모리 효율
```python
# 타입 재사용
int가 100번 나와도 TypeEntity는 1개만 생성
type_cache = {"type:int": TypeEntity(...)}
```

### 3. 캐싱 레이어
```
[AST Cache]      → 파일별 캐싱
    ↓
[Type Cache]     → 타입별 캐싱
    ↓
[Pyright Cache]  → 위치별 캐싱 (LSP 클라이언트)
```

---

## ✅ 변경된 파일

1. ✅ [src/foundation/semantic_ir/typing/builder.py](src/foundation/semantic_ir/typing/builder.py)
   - Generic 타입 파라미터 추출
   - 타입 정규화 및 캐싱
   - TypeFlavor 자동 결정

2. ✅ [src/foundation/semantic_ir/expression/builder.py](src/foundation/semantic_ir/expression/builder.py)
   - AST 캐싱
   - Batch Pyright enrichment
   - Position deduplication

---

## 🧪 테스트 시나리오

### Generic 타입 파싱
```python
# Input: "List[Dict[str, User]]"
type_entity = builder._get_or_create_type_entity("List[Dict[str, User]]")

# Output:
# type_entity.id = "type:List[Dict[str, User]]"
# type_entity.flavor = TypeFlavor.GENERIC
# type_entity.generic_param_ids = ["type:Dict[str, User]"]
#
# type_cache:
#   "type:List[Dict[str, User]]": TypeEntity(...)
#   "type:Dict[str, User]": TypeEntity(generic_param_ids=["type:str", "type:User"])
#   "type:str": TypeEntity(...)
#   "type:User": TypeEntity(...)
```

### AST 캐싱
```python
# 같은 파일의 여러 블록
blocks = [block1, block2, block3]  # 모두 같은 file_path

for block in blocks:
    exprs = builder.build_from_block(block, source_file)
    # AST는 첫 번째만 파싱, 나머지는 캐시 사용
```

### Pyright 배치 호출
```python
# 100개 표현식, 50개 unique 위치
expressions = builder.build_from_block(block, source_file)

# 내부적으로:
# 1. 100개 표현식 먼저 생성
# 2. 위치별로 그룹핑 (50개 그룹)
# 3. Pyright hover 50회만 호출
# 4. 각 그룹의 표현식에 결과 적용
```

---

## 🎉 최적화 완료

모든 최적화 구현 완료:

1. ✅ Generic 타입 파라미터 추출
2. ✅ 타입 정규화 및 중복 제거
3. ✅ Expression AST 캐싱
4. ✅ Pyright 호출 최적화 (Batch + Deduplication)

**예상 성능 개선**:
- AST 파싱: **80% 감소**
- Pyright 호출: **50% 감소**
- 메모리: **타입 중복 제거**

**구조 개선**:
- 타입 그래프 구축 가능
- 캐싱 레이어 명확
- 확장 가능한 아키텍처

---

## 🔄 다음 개선 사항 (선택)

1. **비동기 Pyright 호출**: asyncio로 병렬 처리
2. **타입 그래프 쿼리**: generic_param_ids로 타입 관계 탐색
3. **타입 정규화 강화**: `List` vs `list` 통일
4. **캐시 만료 정책**: LRU 캐시로 메모리 관리
