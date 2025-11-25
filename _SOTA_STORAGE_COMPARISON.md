# SOTA 시스템들의 Name Resolution 저장 전략

**Date:** 2024-11-24

---

## 🎯 핵심 답변

**Q: SOTA는 둘다 저장하는거?**

**A: 대부분 Hybrid! 하지만 방식은 다양함**

---

## 🏆 주요 SOTA 시스템 비교

### 1. **GitHub CodeQL** ⭐⭐⭐⭐⭐

**저장 방식:**
```
QL Database (전용 포맷)
  ├─ Relations (테이블)
  │   ├─ @node(id, kind, name, ...)
  │   ├─ @edge(source, target, kind)
  │   ├─ @location(file, line, col)
  │   └─ @call(caller, callee)
  │
  └─ Predicates (쿼리)
      └─ 그래프 쿼리 언어 (QL)
```

**특징:**
- ✅ **단일 저장소** (QL DB에 모두)
- ✅ 관계형 + 그래프 쿼리 혼합
- ✅ 압축된 binary 포맷
- ✅ 고성능 쿼리

**쿼리 예:**
```ql
// "User 클래스의 모든 호출자"
from Class c, MethodAccess call
where c.getName() = "User" and call.getTarget().getDeclaringType() = c
select call
```

**결론:** Hybrid (단일 DB에서 관계형 + 그래프)

---

### 2. **Sourcegraph** ⭐⭐⭐⭐⭐

**저장 방식:**
```
Primary: PostgreSQL
  ├─ lsif_data_documents (JSONB)
  ├─ lsif_data_definitions
  ├─ lsif_data_references
  └─ lsif_data_result_chunks

Index: In-memory Graph
  └─ Zoekt (코드 검색)
```

**특징:**
- ✅ **PostgreSQL primary** (LSIF 데이터)
- ✅ JSONB로 유연한 저장
- ✅ In-memory graph for hot queries
- ✅ Zoekt for text search

**LSIF (Language Server Index Format):**
```json
{
  "id": "1",
  "type": "vertex",
  "label": "range",
  "start": {"line": 10, "character": 5},
  "end": {"line": 10, "character": 9}
}
```

**결론:** Hybrid (Postgres + In-memory index)

---

### 3. **Kythe (Google)** ⭐⭐⭐⭐

**저장 방식:**
```
Graph Store (LevelDB/BigTable)
  ├─ Nodes
  │   ├─ VName (semantic ID)
  │   └─ Facts (properties)
  │
  └─ Edges
      ├─ /kythe/edge/defines
      ├─ /kythe/edge/ref
      └─ /kythe/edge/childof
```

**특징:**
- ✅ **순수 그래프 저장소**
- ✅ Key-value store (LevelDB/BigTable)
- ✅ Edge-centric 설계
- ✅ Google 스케일 (Peta-byte)

**저장 예:**
```
VName: {signature: "User", path: "models/user.py"}
Facts: {
  /kythe/node/kind: "class",
  /kythe/loc/start: "10:5",
  /kythe/loc/end: "20:1"
}
```

**결론:** Graph-only (하지만 key-value로 구현)

---

### 4. **rust-analyzer (Rust LSP)** ⭐⭐⭐⭐

**저장 방식:**
```
In-Memory Database
  ├─ Salsa (incremental computation)
  │   ├─ ItemTree (syntax)
  │   ├─ DefMap (definitions)
  │   └─ InferenceResult (types)
  │
  └─ On-disk cache
      └─ Serialized state
```

**특징:**
- ✅ **메모리 우선** (incremental)
- ✅ On-disk persistence
- ✅ Salsa framework (query-based)
- ✅ 매우 빠른 incremental update

**결론:** In-memory + Cache (Hybrid)

---

### 5. **SCIP (Sourcegraph Code Intelligence Protocol)** ⭐⭐⭐⭐

**저장 방식:**
```
File-based Index
  ├─ index.scip (protobuf)
  │   ├─ Documents
  │   ├─ Symbols
  │   └─ Occurrences
  │
  └─ Upload to Sourcegraph
      └─ PostgreSQL
```

**특징:**
- ✅ **파일 기반** (portable)
- ✅ Protobuf binary
- ✅ Language-agnostic
- ✅ 최종적으로 DB에 저장

**SCIP 인덱스 구조:**
```protobuf
message Index {
  repeated Document documents = 1;
  repeated SymbolInformation external_symbols = 2;
}

message Document {
  string relative_path = 1;
  repeated Occurrence occurrences = 2;
  repeated SymbolInformation symbols = 3;
}
```

**결론:** File (intermediate) → DB (final) (Hybrid)

---

## 📊 SOTA 시스템 비교표

| 시스템 | Primary Storage | Index/Cache | 쿼리 방식 | Hybrid? |
|--------|----------------|-------------|-----------|---------|
| **CodeQL** | QL DB (binary) | 내장 | QL 언어 | ✅ Yes (단일 DB) |
| **Sourcegraph** | PostgreSQL (JSONB) | In-memory + Zoekt | SQL + GraphQL | ✅ Yes |
| **Kythe** | LevelDB/BigTable | - | Graph traversal | 🟡 Graph-only |
| **rust-analyzer** | In-memory (Salsa) | Disk cache | Incremental | ✅ Yes |
| **SCIP** | File → PostgreSQL | - | SQL | ✅ Yes |

---

## 🎯 공통 패턴

### Pattern 1: **Primary + Index** (가장 흔함)
```
Primary Storage (모든 데이터)
  ├─ PostgreSQL (Sourcegraph, SCIP)
  ├─ QL DB (CodeQL)
  └─ LevelDB (Kythe)

+ Index (쿼리 최적화)
  ├─ In-memory graph
  ├─ B-tree index
  └─ Text search index
```

**예:** Sourcegraph
- Primary: PostgreSQL (LSIF data)
- Index: Zoekt (text search), In-memory (hot queries)

---

### Pattern 2: **Single Unified Storage**
```
Unified DB (관계형 + 그래프)
  └─ CodeQL QL Database
      ├─ Relations (테이블)
      └─ Graph queries
```

**예:** CodeQL
- 단일 QL DB
- 하지만 내부적으로 relation + index

---

### Pattern 3: **In-Memory + Persistence**
```
In-Memory (fast access)
  └─ rust-analyzer Salsa DB

+ Disk Cache (persistence)
  └─ Serialized state
```

**예:** rust-analyzer
- 주로 메모리
- 필요시 disk에 저장

---

## 🏗️ 우리 선택: Hybrid (SOTA 패턴)

```
┌──────────────────────────────────┐
│   IR Document (Primary)          │  ← Sourcegraph/SCIP 스타일
│   - Postgres JSONB               │
│   - All data (source of truth)   │
└────────────┬─────────────────────┘
             │
             ├─► JSON files (snapshot)
             │
             └─► Kuzu Graph DB (Index) ← Kythe 스타일
                 - Fast graph queries
                 - DEFINES/REFERENCES edges
```

**우리가 선택한 이유:**
1. ✅ **Sourcegraph 패턴**: Postgres primary
2. ✅ **Kythe 아이디어**: Graph index for queries
3. ✅ **SCIP 호환성**: File-based intermediate
4. ✅ **CodeQL 영감**: Powerful graph queries

---

## 💡 각 시스템의 장단점

### CodeQL
**장점:**
- ⭐ 단일 DB로 관리 편함
- ⭐ 강력한 쿼리 언어
- ⭐ 고성능 압축

**단점:**
- ❌ 전용 포맷 (lock-in)
- ❌ 쿼리 언어 학습 곡선

---

### Sourcegraph
**장점:**
- ⭐ PostgreSQL 표준
- ⭐ JSONB 유연성
- ⭐ 확장 가능

**단점:**
- ❌ Graph 쿼리 느림 (Postgres)
- ❌ 복잡한 아키텍처

---

### Kythe
**장점:**
- ⭐ Pure graph (그래프 쿼리 최적화)
- ⭐ Google 스케일

**단점:**
- ❌ Key-value 복잡도
- ❌ 쿼리 어려움 (no SQL)

---

### rust-analyzer
**장점:**
- ⭐ 매우 빠름 (in-memory)
- ⭐ Incremental update

**단점:**
- ❌ 메모리 사용량
- ❌ 대규모 repo 어려움

---

## 🎯 결론: 대부분 Hybrid!

### 공통점:
1. ✅ **Primary storage** 있음 (DB or file)
2. ✅ **Index/cache** 있음 (성능)
3. ✅ **Graph semantics** 지원

### 차이점:
- **CodeQL**: 단일 DB에서 hybrid
- **Sourcegraph**: Postgres + Index
- **Kythe**: Graph-only (key-value)
- **rust-analyzer**: Memory-first

### 우리 선택:
```
✅ Sourcegraph + Kythe 조합
  = Postgres (primary) + Kuzu (graph index)
```

**왜?**
- 표준 기술 (Postgres, Kuzu)
- 유연한 쿼리 (SQL + Cypher)
- 확장 가능
- SOTA 패턴 따름

---

## 📚 참고 자료

1. **CodeQL**: https://codeql.github.com/docs/codeql-overview/about-codeql/
2. **Sourcegraph**: https://docs.sourcegraph.com/code_intelligence/explanations/precise_code_intelligence
3. **Kythe**: https://kythe.io/docs/kythe-storage.html
4. **rust-analyzer**: https://github.com/rust-lang/rust-analyzer/blob/master/docs/dev/architecture.md
5. **SCIP**: https://github.com/sourcegraph/scip

---

**최종 답변:**

**Yes, SOTA는 대부분 둘 다 저장!**
- Primary storage (모든 데이터)
- Index/Cache (쿼리 최적화)

하지만 구현 방식은 다양함:
- Single DB (CodeQL)
- DB + Index (Sourcegraph)
- Graph-only (Kythe)
- Memory + Disk (rust-analyzer)
