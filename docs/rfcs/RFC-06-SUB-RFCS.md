# RFC-06 Sub-RFCs - Detailed Specifications

**Version:** 1.0 Final  
**Created:** 2025-12-05  
**Status:** Approved for Implementation

본 문서는 RFC-06 v3.1의 4개 서브 RFC를 상세 정의합니다.

---

## RFC-06-EFFECT: Effect System

### 1. Goal

코드 변화의 **동작 의미(behavioral semantics)**를 감지하기 위해,  
함수/모듈 단위의 **EffectSet**(side-effect signature)을 정적으로 추론하고  
변경 전후의 **EffectDiff**를 산출하는 시스템을 정의한다.

### 2. Problem

텍스트 diff/AST diff는 **"동작 변화"**를 감지하지 못한다.

**예시:**
```python
# Before
def foo():
    x = 1

# After
def foo():
    global_state.counter += 1
    x = 1
```

**의미 변화:** Side Effect 추가 (Global Mutation)  
→ 이를 감지하기 위해 Effect System이 필수

### 3. Effect Domain

#### 3.1 Effect Types   

"""
#### 주요 EffectType 정의

- PURE: 상태 변형/외부 효과 없음. (참조 투명)
- READ_STATE: 글로벌/스태틱/멤버 상태 읽기.
- WRITE_STATE: 글로벌/스태틱/멤버 상태 쓰기.
- GLOBAL_MUTATION: 글로벌/싱글턴 객체 변형.
- IO: 파일/콘솔/시스템 입출력.
- LOG: 로깅 작업 (일반적으로 IO의 하위 범주).
- DB_READ / DB_WRITE: 외부 Database 읽기/쓰기.
- NETWORK: 네트워크 요청 (외부 API 포함).
- UNKNOWN_EFFECT: 정적 분석 불가, 미상 효과.

이 EffectType("순수" → "부수효과 있음")은 Static Analyzer가 함수/메서드의 의미 변화를 구조적으로 감지하는 기반이 된다.
"""


```python
from enum import Enum 

class EffectType(str, Enum):
    """Effect 분류"""
    PURE = "pure"
    
    # State Effects
    READ_STATE = "read_state"
    WRITE_STATE = "write_state"
    GLOBAL_MUTATION = "global_mutation"
    
    # I/O Effects (WriteState의 subtype)
    IO = "io"
    LOG = "log"
    
    # External Effects
    DB_READ = "db_read"
    NETWORK = "network"
    
    
    # Unknown
    UNKNOWN_EFFECT = "unknown_effect"

# Effect Hierarchy (상속 관계)
EFFECT_HIERARCHY = {
    EffectType.IO: EffectType.WRITE_STATE,
    EffectType.LOG: EffectType.WRITE_STATE,
    EffectType.DB_WRITE: EffectType.WRITE_STATE,
    EffectType.DB_READ: EffectType.READ_STATE,
    EffectType.NETWORK: EffectType.WRITE_STATE,
}
```

#### 3.2 Idempotency

```python
@dataclass
class EffectSet:
    """함수의 effect 집합"""
    symbol_id: str
    effects: set[EffectType]
    idempotent: bool
    confidence: float  # 0.0 ~ 1.0
    source: Literal["static", "inferred", "allowlist", "annotation", "unknown"]
    
    def is_pure(self) -> bool:
        return self.effects == {EffectType.PURE}
    
    def has_side_effect(self) -> bool:
        return not self.is_pure()
    
    def includes(self, effect: EffectType) -> bool:
        """Hierarchy 고려한 포함 여부"""
        if effect in self.effects:
            return True
        
        # Check hierarchy
        for e in self.effects:
            if EFFECT_HIERARCHY.get(e) == effect:
                return True
        
        return False
```

**Idempotency 예시:**
```python
cache.set(k, v)      # WriteState + Idempotent
list.append(x)       # WriteState + NonIdempotent
logging.info(msg)    # Log + Idempotent
counter += 1         # GlobalMutation + NonIdempotent
```

### 4. 추론 알고리즘

#### 4.1 Local Effects

```python
class LocalEffectAnalyzer:
    """소스 코드에서 명시적 effect 추출"""
    
    def analyze(self, node: IRNode) -> EffectSet:
        """함수의 local effect 분석"""
        effects = set()
        idempotent = True
        
        for stmt in node.body:
            # Global 변수 수정
            if self._is_global_mutation(stmt):
                effects.add(EffectType.GLOBAL_MUTATION)
                idempotent = False
            
            # I/O 연산
            elif self._is_io_operation(stmt):
                effects.add(EffectType.IO)
                # print는 idempotent, file write는 아님
                if not self._is_idempotent_io(stmt):
                    idempotent = False
            
            # DB 연산
            elif self._is_db_operation(stmt):
                if self._is_read_operation(stmt):
                    effects.add(EffectType.DB_READ)
                else:
                    effects.add(EffectType.DB_WRITE)
                    idempotent = self._is_idempotent_db(stmt)
            
            # Network 연산
            elif self._is_network_operation(stmt):
                effects.add(EffectType.NETWORK)
                idempotent = False
        
        return EffectSet(
            symbol_id=node.id,
            effects=effects or {EffectType.PURE},
            idempotent=idempotent,
            confidence=1.0,
            source="static"
        )
    
    def _is_global_mutation(self, stmt) -> bool:
        """Global 변수 수정 감지"""
        # global keyword
        # module-level variable assignment
        pass
    
    def _is_io_operation(self, stmt) -> bool:
        """I/O 연산 감지"""
        # print, open, write, read
        pass
    
    def _is_idempotent_io(self, stmt) -> bool:
        """Idempotent I/O 판별"""
        # print → True
        # file.write → False
        pass
```

#### 4.2 Interprocedural Propagation

```python
class EffectPropagator:
    """Effect 전파 (callee → caller)"""
    
    def propagate(
        self,
        node: IRNode,
        local_effect: EffectSet,
        callee_effects: dict[str, EffectSet],
        graph: GraphDocument
    ) -> EffectSet:
        """Callee effect를 caller로 전파"""
        
        propagated_effects = set(local_effect.effects)
        min_confidence = local_effect.confidence
        idempotent = local_effect.idempotent
        
        # Callee effect 수집
        for edge in graph.edges:
            if edge.kind == "CALLS" and edge.source_node_id == node.id:
                callee_id = edge.target_node_id
                
                if callee_id in callee_effects:
                    callee_effect = callee_effects[callee_id]
                    propagated_effects.update(callee_effect.effects)
                    min_confidence = min(min_confidence, callee_effect.confidence)
                    
                    if not callee_effect.idempotent:
                        idempotent = False
                else:
                    # Unknown callee → Pessimistic default
                    propagated_effects.add(EffectType.WRITE_STATE)
                    propagated_effects.add(EffectType.GLOBAL_MUTATION)
                    min_confidence = 0.5
                    idempotent = False
        
        return EffectSet(
            symbol_id=node.id,
            effects=propagated_effects,
            idempotent=idempotent,
            confidence=min_confidence,
            source="inferred"
        )
```

**전파 규칙:**
```
Effect(f) = LocalEffect(f) ∪ (∪ Effect(callees))
```

#### 4.3 Unknown Handling (동적 언어)

**기본 원칙:**
- **Pessimistic Default:** Unknown → `WriteState` + `GlobalMutation`

**예외:**
1. **Trusted Library Allowlist** 적용
2. 명시적 annotation이 있는 경우

```python
class UnknownEffectHandler:
    """Unknown call 처리"""
    
    def __init__(self, allowlist: TrustedLibraryDB):
        self.allowlist = allowlist
    
    def handle_unknown_call(
        self,
        callee_name: str,
        call_context: dict
    ) -> EffectSet:
        """Unknown call의 effect 추정"""
        
        # 1. Allowlist 확인
        if callee_name in self.allowlist:
            return self.allowlist.get_effect(callee_name)
        
        # 2. Annotation 확인
        if "effect_annotation" in call_context:
            return self._parse_annotation(call_context["effect_annotation"])
        
        # 3. Pattern matching (휴리스틱)
        pattern_effect = self._match_patterns(callee_name)
        if pattern_effect:
            return pattern_effect
        
        # 4. Pessimistic default
        return EffectSet(
            symbol_id=callee_name,
            effects={EffectType.WRITE_STATE, EffectType.GLOBAL_MUTATION},
            idempotent=False,
            confidence=0.5,
            source="unknown"
        )
    
    def _match_patterns(self, name: str) -> Optional[EffectSet]:
        """패턴 기반 추론"""
        for pattern, effect_spec in EFFECT_PATTERNS:
            if re.match(pattern, name):
                return EffectSet(
                    symbol_id=name,
                    effects=effect_spec["effects"],
                    idempotent=effect_spec["idempotent"],
                    confidence=effect_spec["confidence"],
                    source="inferred"
                )
        return None
```

### 5. Trusted Library Effect DB (Allowlist)

#### 5.1 구조

```python
@dataclass
class LibraryEffectSpec:
    """라이브러리 함수의 effect 명세"""
    library: str
    function: str
    effects: set[EffectType]
    idempotent: bool
    confidence: float = 0.95

class TrustedLibraryDB:
    """Trusted library effect database"""
    
    def __init__(self):
        self.specs: dict[str, LibraryEffectSpec] = {}
        self._load_builtin_specs()
    
    def _load_builtin_specs(self):
        """내장 라이브러리 effect 정의"""
        
        # Python builtin
        self.add_spec(LibraryEffectSpec(
            library="builtins",
            function="print",
            effects={EffectType.IO},
            idempotent=True
        ))
        
        # NumPy (pure functions)
        self.add_spec(LibraryEffectSpec(
            library="numpy",
            function="array",
            effects={EffectType.PURE},
            idempotent=True
        ))
        
        # Logging
        self.add_spec(LibraryEffectSpec(
            library="logging",
            function="info",
            effects={EffectType.LOG},
            idempotent=True
        ))
        
        # Redis
        self.add_spec(LibraryEffectSpec(
            library="redis",
            function="set",
            effects={EffectType.WRITE_STATE},
            idempotent=True
        ))
        
        self.add_spec(LibraryEffectSpec(
            library="redis",
            function="get",
            effects={EffectType.READ_STATE},
            idempotent=True
        ))
        
        # Database (SQLAlchemy)
        self.add_spec(LibraryEffectSpec(
            library="sqlalchemy",
            function="query",
            effects={EffectType.DB_READ},
            idempotent=True
        ))
        
        self.add_spec(LibraryEffectSpec(
            library="sqlalchemy",
            function="add",
            effects={EffectType.DB_WRITE},
            idempotent=False
        ))
```

#### 5.2 정책

1. **Allowlist 수정은 code review 필수**
2. **언어/프레임워크별 관리**
   - `allowlist/python_builtin.yaml`
   - `allowlist/python_stdlib.yaml`
   - `allowlist/python_numpy.yaml`
   - `allowlist/javascript_stdlib.yaml`

```yaml
# allowlist/python_stdlib.yaml
specs:
  - library: "logging"
    function: "info"
    effects: ["log"]
    idempotent: true
    confidence: 0.95
    
  - library: "logging"
    function: "error"
    effects: ["log"]
    idempotent: true
    confidence: 0.95
    
  - library: "json"
    function: "dumps"
    effects: ["pure"]
    idempotent: true
    confidence: 1.0
```

#### 5.3 Pattern Database (보완)

Allowlist만으로 부족한 경우 패턴 매칭:

```python
# Effect Pattern Database
EFFECT_PATTERNS = [
    {
        "pattern": r".*\.set\(",
        "effects": {EffectType.WRITE_STATE},
        "idempotent": True,
        "confidence": 0.8,
        "reason": "set method pattern"
    },
    {
        "pattern": r".*\.append\(",
        "effects": {EffectType.WRITE_STATE},
        "idempotent": False,
        "confidence": 0.8,
        "reason": "append method pattern"
    },
    {
        "pattern": r".*\.log\(",
        "effects": {EffectType.LOG},
        "idempotent": True,
        "confidence": 0.7,
        "reason": "log method pattern"
    },
]
```

### 6. Differential Logic (EffectDiff)

```python
@dataclass
class EffectDiff:
    """Effect 변화"""
    symbol_id: str
    old_effect: EffectSet
    new_effect: EffectSet
    
    added_effects: set[EffectType]
    removed_effects: set[EffectType]
    
    idempotency_changed: bool
    risk_level: Literal["low", "medium", "high"]
    
    def is_behavioral_change(self) -> bool:
        """동작 변화 여부"""
        return len(self.added_effects) > 0 or len(self.removed_effects) > 0

class EffectDiffer:
    """Effect 비교"""
    
    def diff(
        self,
        old_effect: EffectSet,
        new_effect: EffectSet
    ) -> EffectDiff:
        """Effect diff 계산"""
        
        added = new_effect.effects - old_effect.effects
        removed = old_effect.effects - new_effect.effects
        
        idempotency_changed = (old_effect.idempotent != new_effect.idempotent)
        
        # Risk level 계산
        risk = self._calculate_risk(added, removed, idempotency_changed)
        
        return EffectDiff(
            symbol_id=new_effect.symbol_id,
            old_effect=old_effect,
            new_effect=new_effect,
            added_effects=added,
            removed_effects=removed,
            idempotency_changed=idempotency_changed,
            risk_level=risk
        )
    
    def _calculate_risk(
        self,
        added: set[EffectType],
        removed: set[EffectType],
        idempotency_changed: bool
    ) -> str:
        """위험도 계산"""
        
        # High risk: DB_WRITE, NETWORK, GLOBAL_MUTATION 추가
        high_risk_effects = {
            EffectType.DB_WRITE,
            EffectType.NETWORK,
            EffectType.GLOBAL_MUTATION
        }
        
        if added & high_risk_effects:
            return "high"
        
        # Medium risk: WRITE_STATE, IO 추가
        medium_risk_effects = {
            EffectType.WRITE_STATE,
            EffectType.IO
        }
        
        if added & medium_risk_effects or idempotency_changed:
            return "medium"
        
        # Low risk: READ_STATE, LOG 추가 또는 effect 제거
        if len(added) > 0 or len(removed) > 0:
            return "low"
        
        return "low"
```

### 7. 제한사항

**동적 언어에서 "정확한" 추론은 불가능합니다.**

본 RFC는 **Best Effort Static Approximation**을 목표로 합니다.

**False Positive 허용 정책:**
- 의심스러우면 **보수적으로 effect 추가**
- Confidence score로 불확실성 표현
- LLM/Agent가 최종 판단

---

## RFC-06-VFLOW: Cross-Language Value Flow Graph

### 1. Goal

FE → API → BE → DB까지 값(value)의 흐름을  
cross-language로 추적하는 **Cross-Language Value Flow Graph (CVFG)** 정의.

### 2. Problem

```
TS:    interface User { userId: string }
↓
Java:  class UserDTO { String userID; }
↓
Python: class UserModel: user_id: str
↓
SQL:    users.USER_ID VARCHAR(36)
```

**문제:**
- Naming convention 차이 (camelCase, snake_case, UPPER_CASE)
- Type 불일치 (string, String, str, VARCHAR)
- 정적 분석만으로 연결 어려움

### 3. 핵심 요소

#### 3.1 NFN (Normalized Field Name)

```python
def normalize_field_name(name: str) -> str:
    """필드명 정규화"""
    # 1. Lower case
    normalized = name.lower()
    
    # 2. CamelCase → snake_case
    # userId → user_id
    normalized = re.sub(r'([a-z])([A-Z])', r'\1_\2', normalized)
    
    # 3. 여러 언더스코어 제거
    normalized = re.sub(r'_+', '_', normalized)
    
    # 4. 앞뒤 언더스코어 제거
    normalized = normalized.strip('_')
    
    return normalized

# 예시
assert normalize_field_name("userId") == "user_id"
assert normalize_field_name("user_id") == "user_id"
assert normalize_field_name("USER_ID") == "user_id"
assert normalize_field_name("userID") == "user_id"
```

#### 3.2 Type Compatibility Matrix

```python
@dataclass
class TypeCompatibility:
    """타입 호환성"""
    source_type: str
    target_type: str
    compatible: bool
    confidence: float

# Type Compatibility Matrix
TYPE_COMPAT_MATRIX = {
    # String types
    ("string", "String"): TypeCompatibility("string", "String", True, 1.0),
    ("string", "str"): TypeCompatibility("string", "str", True, 1.0),
    ("string", "varchar"): TypeCompatibility("string", "varchar", True, 0.95),
    ("uuid", "string"): TypeCompatibility("uuid", "string", True, 0.9),
    
    # Number types
    ("int", "integer"): TypeCompatibility("int", "integer", True, 1.0),
    ("int", "float"): TypeCompatibility("int", "float", True, 0.8),
    ("int", "decimal"): TypeCompatibility("int", "decimal", True, 0.85),
    
    # Time types
    ("timestamp", "datetime"): TypeCompatibility("timestamp", "datetime", True, 0.95),
    ("date", "datetime"): TypeCompatibility("date", "datetime", True, 0.9),
    
    # Boolean
    ("bool", "boolean"): TypeCompatibility("bool", "boolean", True, 1.0),
}

def are_types_compatible(type1: str, type2: str) -> tuple[bool, float]:
    """두 타입이 호환되는지 확인"""
    key = (type1.lower(), type2.lower())
    
    if key in TYPE_COMPAT_MATRIX:
        compat = TYPE_COMPAT_MATRIX[key]
        return compat.compatible, compat.confidence
    
    # Reverse lookup
    reverse_key = (type2.lower(), type1.lower())
    if reverse_key in TYPE_COMPAT_MATRIX:
        compat = TYPE_COMPAT_MATRIX[reverse_key]
        return compat.compatible, compat.confidence
    
    # Exact match
    if type1.lower() == type2.lower():
        return True, 1.0
    
    # No match
    return False, 0.0
```

#### 3.3 Structural Hash

```python
def compute_structural_hash(
    schema: dict,
    namespace_salt: str
) -> str:
    """구조 기반 해시"""
    
    # 1. 필드 정규화
    normalized_fields = []
    for field_name, field_type in schema.items():
        nfn = normalize_field_name(field_name)
        normalized_fields.append(f"{nfn}:{field_type.lower()}")
    
    # 2. 정렬 (순서 무관)
    normalized_fields.sort()
    
    # 3. Namespace salt 포함
    content = namespace_salt + "|" + ",".join(normalized_fields)
    
    # 4. Hash
    return hashlib.sha256(content.encode()).hexdigest()

# 예시
ts_schema = {"userId": "string", "userName": "string", "age": "number"}
py_schema = {"user_id": "str", "user_name": "str", "age": "int"}

ts_hash = compute_structural_hash(ts_schema, "frontend/types/User.ts")
py_hash = compute_structural_hash(py_schema, "backend/models/user.py")

# 구조가 같으면 hash가 유사 (namespace만 다름)
```

### 4. Edge Confidence

```python
@dataclass
class CrossLangEdge:
    """Cross-language value flow edge"""
    source_id: str
    target_id: str
    field_mappings: list[tuple[str, str]]  # [(source_field, target_field)]
    
    confidence: Literal["high", "medium", "low"]
    confidence_score: float
    reason: str

class EdgeConfidenceCalculator:
    """Edge confidence 계산"""
    
    def calculate(
        self,
        source_schema: dict,
        target_schema: dict,
        source_path: str,
        target_path: str
    ) -> CrossLangEdge:
        """Confidence 계산"""
        
        # 1. NFN matching
        nfn_match_score = self._nfn_match_score(source_schema, target_schema)
        
        # 2. Type compatibility
        type_compat_score = self._type_compat_score(source_schema, target_schema)
        
        # 3. Structural hash
        struct_hash_match = self._struct_hash_match(
            source_schema, source_path,
            target_schema, target_path
        )
        
        # 4. Overall confidence
        overall_score = (
            0.4 * nfn_match_score +
            0.3 * type_compat_score +
            0.3 * float(struct_hash_match)
        )
        
        # Confidence level
        if overall_score >= 0.8 and struct_hash_match:
            confidence = "high"
            reason = "NFN + TypeCompat + StructuralHash + Path match"
        elif overall_score >= 0.6:
            confidence = "medium"
            reason = "StructuralHash match only"
        else:
            confidence = "low"
            reason = "Name similarity only"
        
        return CrossLangEdge(
            source_id=f"{source_path}:{hash(frozenset(source_schema.items()))}",
            target_id=f"{target_path}:{hash(frozenset(target_schema.items()))}",
            field_mappings=self._compute_field_mappings(source_schema, target_schema),
            confidence=confidence,
            confidence_score=overall_score,
            reason=reason
        )
```

**사용 정책:**
- **High confidence:** LLM이 근거로 사용 가능
- **Medium confidence:** 참고 정보로 제공
- **Low confidence:** 사람 확인 필요, LLM은 무시

### 5. Boundary Priority

**우선순위:**
1. **Explicit API spec** (OpenAPI / Protobuf)
2. **DB schema**
3. **코드 annotation**
4. **구조적 유사성**

```python
class BoundaryParser:
    """API Boundary 파싱"""
    
    def parse_openapi(self, spec_file: str) -> list[BoundaryNode]:
        """OpenAPI → Boundary nodes (최고 우선순위)"""
        with open(spec_file) as f:
            spec = yaml.safe_load(f)
        
        boundaries = []
        for path, methods in spec.get("paths", {}).items():
            for method, details in methods.items():
                # Request body schema
                if "requestBody" in details:
                    schema = self._extract_schema(details["requestBody"])
                    boundaries.append(BoundaryNode(
                        id=f"openapi:{method}:{path}:request",
                        name=f"{method.upper()} {path} (request)",
                        schema=schema,
                        source="openapi",
                        priority=1  # 최고 우선순위
                    ))
                
                # Response schema
                if "responses" in details:
                    for status, response in details["responses"].items():
                        schema = self._extract_schema(response)
                        boundaries.append(BoundaryNode(
                            id=f"openapi:{method}:{path}:response:{status}",
                            name=f"{method.upper()} {path} (response {status})",
                            schema=schema,
                            source="openapi",
                            priority=1
                        ))
        
        return boundaries
    
    def parse_db_schema(self, db_url: str) -> list[BoundaryNode]:
        """DB schema → Boundary nodes (2순위)"""
        # SQLAlchemy reflection 등을 사용
        pass
```

### 6. Schema Evolution Tracking

```python
@dataclass
class SchemaVersion:
    """Schema 버전"""
    version: str
    schema: dict
    deprecated: bool
    breaking_changes: list[str]

class SchemaEvolutionTracker:
    """Schema 변경 추적"""
    
    def detect_breaking_change(
        self,
        old_schema: dict,
        new_schema: dict
    ) -> list[str]:
        """Breaking change 감지"""
        breaking_changes = []
        
        # 필드 제거
        for field in old_schema:
            if field not in new_schema:
                breaking_changes.append(f"Field removed: {field}")
        
        # 타입 변경 (호환 불가)
        for field in old_schema.keys() & new_schema.keys():
            old_type = old_schema[field]
            new_type = new_schema[field]
            
            compatible, confidence = are_types_compatible(old_type, new_type)
            if not compatible:
                breaking_changes.append(
                    f"Incompatible type change: {field} ({old_type} → {new_type})"
                )
        
        return breaking_changes
```

---

## RFC-06-STORAGE: Storage Consistency & Crash Recovery

### 1. Goal

Semantica v6의 IR/Graph/Index 저장 시  
**원자성(Atomicity)**, **일관성(Consistency)**, **크래시 복구(Recovery)**를 보장

### 2. Core Mechanisms

#### 2.1 Write-Ahead Log (WAL)

```python
@dataclass
class WALEntry:
    """WAL 항목"""
    entry_id: str
    timestamp: float
    operation: Literal["create", "update", "delete"]
    object_type: Literal["snapshot", "ir", "graph", "index"]
    object_id: str
    data: Optional[bytes]  # Compressed

class WriteAheadLog:
    """Write-Ahead Log"""
    
    def __init__(self, wal_path: str):
        self.wal_path = Path(wal_path)
        self.wal_path.mkdir(parents=True, exist_ok=True)
        self.current_log = self.wal_path / f"wal_{int(time.time())}.log"
    
    def append(self, entry: WALEntry):
        """WAL에 기록"""
        with open(self.current_log, "ab") as f:
            # Entry 직렬화
            serialized = self._serialize_entry(entry)
            
            # Checksum 추가
            checksum = hashlib.sha256(serialized).digest()
            
            # 기록
            f.write(len(serialized).to_bytes(4, 'big'))
            f.write(serialized)
            f.write(checksum)
            f.flush()
            os.fsync(f.fileno())  # Disk에 강제 쓰기
    
    def replay(self) -> list[WALEntry]:
        """WAL replay (crash recovery)"""
        entries = []
        
        for log_file in sorted(self.wal_path.glob("wal_*.log")):
            with open(log_file, "rb") as f:
                while True:
                    # Length 읽기
                    length_bytes = f.read(4)
                    if not length_bytes:
                        break
                    
                    length = int.from_bytes(length_bytes, 'big')
                    
                    # Entry 읽기
                    serialized = f.read(length)
                    expected_checksum = f.read(32)
                    
                    # Checksum 검증
                    actual_checksum = hashlib.sha256(serialized).digest()
                    if actual_checksum != expected_checksum:
                        # Corrupted entry, stop replay
                        break
                    
                    entry = self._deserialize_entry(serialized)
                    entries.append(entry)
        
        return entries
```

#### 2.2 Atomic Update

```python
class AtomicFileWriter:
    """원자적 파일 업데이트"""
    
    def write_atomic(
        self,
        target_path: Path,
        data: bytes
    ):
        """Atomic write (temp → rename)"""
        
        # 1. Temp file 생성
        temp_path = target_path.with_suffix(".tmp")
        
        # 2. Data 쓰기
        with open(temp_path, "wb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        
        # 3. Checksum 기록
        checksum = hashlib.sha256(data).hexdigest()
        checksum_path = temp_path.with_suffix(".checksum")
        with open(checksum_path, "w") as f:
            f.write(checksum)
            f.flush()
            os.fsync(f.fileno())
        
        # 4. Atomic rename (OS-level atomicity)
        os.rename(temp_path, target_path)
        os.rename(checksum_path, target_path.with_suffix(".checksum"))
    
    def verify_integrity(self, file_path: Path) -> bool:
        """Checksum 검증"""
        checksum_path = file_path.with_suffix(".checksum")
        
        if not checksum_path.exists():
            return False
        
        with open(checksum_path) as f:
            expected_checksum = f.read().strip()
        
        with open(file_path, "rb") as f:
            actual_checksum = hashlib.sha256(f.read()).hexdigest()
        
        return expected_checksum == actual_checksum
```

#### 2.3 Versioned Snapshot

```python
@dataclass
class Snapshot:
    """Immutable snapshot"""
    snapshot_id: str
    repo_id: str
    timestamp: float
    parent_snapshot_id: Optional[str]
    
    ir_path: Path
    graph_path: Path
    index_path: Path
    
    is_full: bool  # Full vs Delta
    pinned: bool
    tags: list[str]

class SnapshotStore:
    """Snapshot 관리"""
    
    def create_snapshot(
        self,
        repo_id: str,
        ir_data: bytes,
        graph_data: bytes,
        parent_snapshot_id: Optional[str] = None
    ) -> Snapshot:
        """새 snapshot 생성"""
        
        snapshot_id = f"snap_{int(time.time())}_{uuid.uuid4().hex[:8]}"
        
        # Paths
        snapshot_dir = self.base_path / repo_id / snapshot_id
        snapshot_dir.mkdir(parents=True, exist_ok=True)
        
        ir_path = snapshot_dir / "ir.bin.zst"
        graph_path = snapshot_dir / "graph.bin.zst"
        
        # 1. WAL 기록
        self.wal.append(WALEntry(
            entry_id=snapshot_id,
            timestamp=time.time(),
            operation="create",
            object_type="snapshot",
            object_id=snapshot_id,
            data=None
        ))
        
        # 2. Atomic write
        self.writer.write_atomic(ir_path, ir_data)
        self.writer.write_atomic(graph_path, graph_data)
        
        # 3. Metadata 기록
        snapshot = Snapshot(
            snapshot_id=snapshot_id,
            repo_id=repo_id,
            timestamp=time.time(),
            parent_snapshot_id=parent_snapshot_id,
            ir_path=ir_path,
            graph_path=graph_path,
            index_path=snapshot_dir / "index",
            is_full=parent_snapshot_id is None,
            pinned=False,
            tags=[]
        )
        
        self._save_metadata(snapshot)
        
        return snapshot
    
    def get_latest_valid_snapshot(self, repo_id: str) -> Optional[Snapshot]:
        """가장 최근의 유효한 snapshot"""
        snapshots = self._list_snapshots(repo_id)
        
        for snapshot in reversed(snapshots):
            # Integrity 검증
            if self._verify_snapshot_integrity(snapshot):
                return snapshot
        
        return None
```

### 3. Snapshot Retention Policy

```python
class SnapshotGC:
    """Snapshot Garbage Collector"""
    
    def __init__(
        self,
        keep_last_n: int = 20,
        keep_days: int = 30
    ):
        self.keep_last_n = keep_last_n
        self.keep_days = keep_days
    
    def collect(self, repo_id: str) -> list[str]:
        """GC 실행"""
        snapshots = self._list_snapshots(repo_id)
        
        # 1. Pinned snapshot은 제외
        unpinned = [s for s in snapshots if not s.pinned]
        
        # 2. 최근 N개 유지
        to_keep = set(s.snapshot_id for s in unpinned[-self.keep_last_n:])
        
        # 3. keep_days 이내 유지
        cutoff_time = time.time() - (self.keep_days * 86400)
        for snapshot in unpinned:
            if snapshot.timestamp >= cutoff_time:
                to_keep.add(snapshot.snapshot_id)
        
        # 4. 삭제 대상
        to_delete = [
            s.snapshot_id for s in unpinned
            if s.snapshot_id not in to_keep
        ]
        
        # 5. Cascade 삭제
        for snapshot_id in to_delete:
            self._delete_snapshot_cascade(snapshot_id)
        
        return to_delete
    
    def _delete_snapshot_cascade(self, snapshot_id: str):
        """Cascade 삭제"""
        snapshot = self._get_snapshot(snapshot_id)
        
        # IR, Graph, Index 삭제
        shutil.rmtree(snapshot.ir_path.parent)
```

### 4. Crash Recovery

```python
class CrashRecoveryManager:
    """Crash recovery"""
    
    def recover(self, repo_id: str) -> bool:
        """Crash 후 복구"""
        
        # 1. WAL replay
        entries = self.wal.replay()
        
        # 2. 마지막 성공한 snapshot 찾기
        last_valid = self.snapshot_store.get_latest_valid_snapshot(repo_id)
        
        if not last_valid:
            # 복구 불가
            return False
        
        # 3. Temp 파일 정리
        self._cleanup_temp_files(repo_id)
        
        # 4. Incomplete snapshot 삭제
        self._delete_incomplete_snapshots(repo_id, last_valid.snapshot_id)
        
        # 5. WAL 정리
        self.wal.truncate_before(last_valid.timestamp)
        
        return True
    
    def _cleanup_temp_files(self, repo_id: str):
        """Temp 파일 제거"""
        repo_dir = self.base_path / repo_id
        for temp_file in repo_dir.rglob("*.tmp"):
            temp_file.unlink()
```

### 5. Speculative Isolation

```python
class SpeculativeStorage:
    """Speculative session storage"""
    
    def __init__(self, base_store: SnapshotStore):
        self.base_store = base_store
        self.overlay_cache: dict[str, DeltaLayer] = {}
    
    def create_overlay(
        self,
        base_snapshot_id: str,
        patch_id: str
    ) -> DeltaLayer:
        """Overlay 생성 (base는 변경 안함)"""
        
        delta = DeltaLayer(patch_id=patch_id)
        self.overlay_cache[patch_id] = delta
        
        # Base snapshot은 절대 수정하지 않음
        # Overlay는 메모리에만 존재
        
        return delta
    
    def commit_overlay(
        self,
        base_snapshot_id: str,
        patch_id: str
    ) -> str:
        """Overlay를 새 snapshot으로 승격"""
        
        delta = self.overlay_cache[patch_id]
        base = self.base_store.get_snapshot(base_snapshot_id)
        
        # 1. Base + delta 병합
        merged_ir = self._merge_ir(base, delta)
        merged_graph = self._merge_graph(base, delta)
        
        # 2. 새 snapshot 생성
        new_snapshot = self.base_store.create_snapshot(
            repo_id=base.repo_id,
            ir_data=merged_ir,
            graph_data=merged_graph,
            parent_snapshot_id=base_snapshot_id
        )
        
        # 3. Overlay 제거
        del self.overlay_cache[patch_id]
        
        return new_snapshot.snapshot_id
```

### 6. Incremental Compaction

```python
class SnapshotCompactor:
    """Delta snapshot compaction"""
    
    def should_compact(self, repo_id: str) -> bool:
        """Compaction 필요 여부"""
        snapshots = self._list_snapshots(repo_id)
        
        # Delta가 10개 이상 누적
        delta_count = sum(1 for s in snapshots if not s.is_full)
        
        return delta_count >= 10
    
    def compact(self, repo_id: str) -> str:
        """Compaction 실행"""
        snapshots = self._list_snapshots(repo_id)
        
        # 1. 가장 최근 full snapshot 찾기
        full_snapshots = [s for s in snapshots if s.is_full]
        if not full_snapshots:
            return None
        
        base = full_snapshots[-1]
        
        # 2. 이후의 delta들
        deltas = [
            s for s in snapshots
            if s.timestamp > base.timestamp and not s.is_full
        ]
        
        if len(deltas) < 10:
            return None
        
        # 3. Base + deltas 병합
        merged_state = self._apply_deltas(base, deltas)
        
        # 4. 새 full snapshot 생성
        new_snapshot = self.snapshot_store.create_snapshot(
            repo_id=repo_id,
            ir_data=merged_state.ir,
            graph_data=merged_state.graph,
            parent_snapshot_id=None  # Full snapshot
        )
        new_snapshot.is_full = True
        
        # 5. 기존 delta 삭제
        for delta in deltas:
            self.snapshot_store.delete_snapshot(delta.snapshot_id)
        
        return new_snapshot.snapshot_id
```

---

## RFC-06-OBS: Observability & Debug UI

### 1. Goal

Semantica 엔진의 모든 동작을  
**실시간으로 관찰 가능(observable)**하도록 만들기

### 2. Metrics

#### 2.1 IR/Graph Build Metrics

```python
from opentelemetry import metrics

meter = metrics.get_meter(__name__)

# Latency
parse_duration = meter.create_histogram(
    name="semantica.parse.duration",
    unit="ms",
    description="Parsing duration"
)

ir_build_duration = meter.create_histogram(
    name="semantica.ir.build.duration",
    unit="ms",
    description="IR generation duration"
)

graph_build_duration = meter.create_histogram(
    name="semantica.graph.build.duration",
    unit="ms",
    description="Graph building duration"
)

# Hit rate
incremental_hit_rate = meter.create_gauge(
    name="semantica.incremental.hit_rate",
    description="Incremental rebuild cache hit rate"
)

# Scope
rebuild_scope = meter.create_histogram(
    name="semantica.rebuild.scope",
    unit="nodes",
    description="Number of nodes rebuilt"
)
```

#### 2.2 Speculative Execution Metrics

```python
# Memory
speculative_memory = meter.create_gauge(
    name="semantica.speculative.memory.bytes",
    unit="bytes",
    description="Speculative execution memory usage"
)

# Overlay depth
overlay_depth = meter.create_gauge(
    name="semantica.speculative.overlay.depth",
    description="Number of active overlays"
)

# Rollback cost
rollback_cost = meter.create_histogram(
    name="semantica.speculative.rollback.cost",
    unit="ms",
    description="Rollback operation cost"
)
```

#### 2.3 Slicing Metrics

```python
# Token usage
slice_tokens = meter.create_histogram(
    name="semantica.slice.tokens",
    description="Slice token usage"
)

# Pruning ratio
slice_pruning_ratio = meter.create_gauge(
    name="semantica.slice.pruning.ratio",
    description="Pruned nodes / total nodes"
)

# Depth
slice_depth = meter.create_histogram(
    name="semantica.slice.depth",
    description="Slice depth (PDG hops)"
)
```

### 3. Dashboards

#### 3.1 Graph Explorer UI

```typescript
// Graph Explorer Component
interface GraphExplorerProps {
  repoId: string;
  snapshotId: string;
}

const GraphExplorer: React.FC<GraphExplorerProps> = ({
  repoId,
  snapshotId
}) => {
  const [view, setView] = useState<'call' | 'pdg' | 'slice' | 'diff'>('call');
  const [selectedNode, setSelectedNode] = useState<string | null>(null);
  
  return (
    <div className="graph-explorer">
      <Toolbar>
        <Button onClick={() => setView('call')}>Call Graph</Button>
        <Button onClick={() => setView('pdg')}>PDG</Button>
        <Button onClick={() => setView('slice')}>Slice</Button>
        <Button onClick={() => setView('diff')}>Semantic Diff</Button>
      </Toolbar>
      
      <GraphCanvas
        view={view}
        repoId={repoId}
        snapshotId={snapshotId}
        selectedNode={selectedNode}
        onNodeClick={setSelectedNode}
      />
      
      {selectedNode && (
        <NodeInspector nodeId={selectedNode} />
      )}
    </div>
  );
};
```

#### 3.2 Performance Dashboard

```python
# Grafana Dashboard (JSON)
dashboard = {
    "title": "Semantica v6 Performance",
    "panels": [
        {
            "title": "Build Latency Histogram",
            "targets": [
                {
                    "expr": "histogram_quantile(0.95, semantica_ir_build_duration_bucket)"
                }
            ]
        },
        {
            "title": "Memory Timeline",
            "targets": [
                {
                    "expr": "semantica_speculative_memory_bytes"
                }
            ]
        },
        {
            "title": "Cache Hit Ratio",
            "targets": [
                {
                    "expr": "rate(semantica_cache_hits_total[5m]) / rate(semantica_cache_requests_total[5m])"
                }
            ]
        },
    ]
}
```

### 4. Distributed Tracing

#### 4.1 Trace Structure

```python
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.jaeger import JaegerExporter

# Setup
tracer_provider = TracerProvider()
jaeger_exporter = JaegerExporter(
    agent_host_name="localhost",
    agent_port=6831
)
tracer_provider.add_span_processor(BatchSpanProcessor(jaeger_exporter))
trace.set_tracer_provider(tracer_provider)

tracer = trace.get_tracer(__name__)

# Usage
with tracer.start_as_current_span(
    "build_full",
    attributes={
        "repo_id": repo_id,
        "snapshot_id": snapshot_id,
        "language": "python"
    }
) as span:
    # Parse
    with tracer.start_as_current_span("parse") as parse_span:
        ast = parser.parse(source)
        parse_span.set_attribute("file_count", len(files))
    
    # IR Build
    with tracer.start_as_current_span("ir_build") as ir_span:
        ir_doc = ir_generator.generate(ast)
        ir_span.set_attribute("node_count", len(ir_doc.nodes))
    
    # Graph Build
    with tracer.start_as_current_span("graph_build") as graph_span:
        graph = graph_builder.build(ir_doc)
        graph_span.set_attribute("edge_count", len(graph.edges))
```

### 5. Alert Rules

```python
@dataclass
class AlertRule:
    """알림 규칙"""
    name: str
    condition: str  # Python expression
    severity: Literal["info", "warning", "error", "critical"]
    action: str
    cooldown: int = 300  # 5분

class AlertManager:
    """알림 관리"""
    
    def __init__(self):
        self.rules: list[AlertRule] = []
        self.last_fired: dict[str, float] = {}
        self._load_rules()
    
    def _load_rules(self):
        """규칙 로드"""
        self.rules = [
            AlertRule(
                name="speculative_memory_high",
                condition="speculative_mem_usage > 2 * base_mem_usage",
                severity="warning",
                action="evict_oldest_overlay"
            ),
            AlertRule(
                name="slice_budget_exceeded",
                condition="slice_token_usage > budget * 1.2",
                severity="error",
                action="abort_slice"
            ),
            AlertRule(
                name="incremental_hit_rate_low",
                condition="incremental_hit_rate < 0.5",
                severity="info",
                action="log_warning"
            ),
        ]
    
    def check_alerts(self, metrics: dict):
        """알림 체크"""
        for rule in self.rules:
            # Cooldown 체크
            if rule.name in self.last_fired:
                if time.time() - self.last_fired[rule.name] < rule.cooldown:
                    continue
            
            # Condition 평가
            try:
                if eval(rule.condition, {}, metrics):
                    self._fire_alert(rule, metrics)
                    self.last_fired[rule.name] = time.time()
            except Exception as e:
                logger.error(f"Failed to evaluate alert rule {rule.name}: {e}")
    
    def _fire_alert(self, rule: AlertRule, metrics: dict):
        """알림 발생"""
        logger.log(
            self._severity_to_level(rule.severity),
            f"ALERT: {rule.name} - {rule.condition}",
            extra={"metrics": metrics}
        )
        
        # Action 실행
        if rule.action == "evict_oldest_overlay":
            self._evict_oldest_overlay()
        elif rule.action == "abort_slice":
            self._abort_current_slice()
```

### 6. Anomaly Detection

```python
import statistics
from collections import deque

class AnomalyDetector:
    """통계적 이상 감지"""
    
    def __init__(self, window_size: int = 100):
        self.window_size = window_size
        self.history: dict[str, deque] = {}
    
    def record(self, metric_name: str, value: float):
        """메트릭 기록"""
        if metric_name not in self.history:
            self.history[metric_name] = deque(maxlen=self.window_size)
        
        self.history[metric_name].append(value)
    
    def detect(self, metric_name: str, current_value: float) -> Optional[dict]:
        """이상 감지"""
        if metric_name not in self.history:
            return None
        
        history = list(self.history[metric_name])
        
        if len(history) < 30:
            return None  # 충분한 데이터 필요
        
        mean = statistics.mean(history)
        stdev = statistics.stdev(history)
        
        if stdev == 0:
            return None
        
        z_score = (current_value - mean) / stdev
        
        if abs(z_score) > 3:  # 3-sigma
            return {
                "metric": metric_name,
                "value": current_value,
                "mean": mean,
                "stdev": stdev,
                "z_score": z_score,
                "severity": "high" if abs(z_score) > 4 else "medium",
                "expected_range": (mean - 3*stdev, mean + 3*stdev)
            }
        
        return None

# Usage
detector = AnomalyDetector()

# 정상 동작
for i in range(100):
    detector.record("parse_time", 20 + random.gauss(0, 2))

# 이상 감지
anomaly = detector.detect("parse_time", 200)
if anomaly:
    print(f"Anomaly detected: {anomaly}")
```

---

## 종합 평가

### ✅ 강점

1. **RFC-06-EFFECT:** 실용적이고 구현 가능. Idempotency는 핵심 차별화.
2. **RFC-06-VFLOW:** Edge Confidence가 핵심. Low confidence는 무시 정책이 현명.
3. **RFC-06-STORAGE:** WAL + Atomic Update + Snapshot GC는 업계 표준.
4. **RFC-06-OBS:** Metrics + Tracing + Alerting + Anomaly Detection = 완벽.

### 💡 개선 사항 (본 문서에 반영됨)

1. **Effect System:**
   - Effect Hierarchy 추가
   - Confidence Score 추가
   - Pattern Database 추가

2. **VFLOW:**
   - Schema Evolution Tracking
   - Example-based Mapping Hint

3. **Storage:**
   - Incremental Compaction

4. **Observability:**
   - Alert Rules
   - Anomaly Detection

---

## 구현 우선순위

### Phase 1 (필수):
- ✅ RFC-06-EFFECT (Effect System)
- ✅ RFC-06-STORAGE (Storage Layer)
- ✅ RFC-06-OBS (Basic Metrics)

### Phase 2:
- ✅ RFC-06-OBS (Tracing + Dashboards)

### Phase 3 (Optional):
- ⚠️ RFC-06-VFLOW (MSA 고객 확보 후)

---

**End of Sub-RFCs**

