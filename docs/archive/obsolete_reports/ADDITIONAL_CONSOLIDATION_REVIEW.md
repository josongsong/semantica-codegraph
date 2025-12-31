# 추가 통합/분리 검토

**Date**: 2025-12-28
**Status**: Review

---

## 현재 패키지 상태

```
packages/
├── codegraph-rust/              # 🦀 Rust Engine
├── codegraph-parsers/           # 📝 Parsers
├── codegraph-shared/            # 🔧 Infrastructure
├── codegraph-runtime/           # 🚀 Runtime
├── codegraph-analysis/          # 🔍 Analysis (이미 존재!)
├── codegraph-agent/             # 🤖 Agent
├── codegraph-ml/                # 🧠 ML
├── codegraph-search/            # 🔍 Search
├── codegraph-engine/            # ⚠️ DEPRECATED
├── codegraph-taint/             # 🗑️ TO DELETE
├── codegraph-security/          # 🗑️ TO DELETE
└── security-rules/              # 🗑️ TO DELETE
```

---

## 발견사항

### 1. `codegraph-analysis` 이미 존재! ✅

**현재 구조**:
```
packages/codegraph-analysis/
└── codegraph_analysis/
    ├── security_analysis/       # ~3,168 LOC
    │   ├── domain/
    │   ├── infrastructure/
    │   │   └── adapters/
    │   │       └── taint_analyzer_adapter.py
    │   └── ports/
    └── verification/
        └── repair_ranking/
```

**현재 의존성**:
```toml
dependencies = [
    "codegraph-engine>=0.1.0",  # ⚠️ Deprecated engine에 의존
]
```

**문제점**:
- `codegraph-engine` (deprecated)에 의존
- `codegraph-ir` (Rust)를 사용하지 않음
- Taint analyzer adapter가 있는데 무엇을 wrapping?

**조치 필요**:
1. ✅ **이 패키지를 그대로 활용**하되 내용 정리
2. 의존성 변경: `codegraph-engine` → `codegraph-ir`
3. Security patterns 통합할 때 기존 `security_analysis/`와 merge

---

## 추가 통합/분리 검토

### Option 1: 현재 구조 유지 (권장) ✅

**장점**:
- 각 패키지가 명확한 역할
- 이미 잘 분리되어 있음
- 추가 작업 최소

**단점**:
- 없음 (현재 구조가 합리적)

**패키지별 역할**:

| Package | Role | Keep/Merge/Delete |
|---------|------|-------------------|
| `codegraph-rust` | Rust analysis engine | ✅ Keep |
| `codegraph-parsers` | Tree-sitter parsers | ✅ Keep (+ merge engine parsers) |
| `codegraph-shared` | Infrastructure (DB, jobs, storage) | ✅ Keep |
| `codegraph-runtime` | Orchestration (session, memory) | ✅ Keep |
| `codegraph-analysis` | Analysis features | ✅ Keep (+ merge security) |
| `codegraph-agent` | Autonomous agent | ✅ Keep |
| `codegraph-ml` | ML features (embeddings) | ✅ Keep |
| `codegraph-search` | Search features | ✅ Keep |
| `codegraph-engine` | Legacy IR/analyzers | ⚠️ Partial delete |
| `codegraph-taint` | Legacy taint | 🗑️ Delete |
| `codegraph-security` | Security patterns | 🔄 Merge → analysis |
| `security-rules` | Security rules | 🔄 Merge → analysis |

### Option 2: 대규모 통합 (비권장) ❌

**통합 시나리오**:
```
packages/
├── codegraph-rust/              # Rust only
├── codegraph-parsers/           # Parsers only
├── codegraph-core/              # Everything else
│   ├── shared/                  # From codegraph-shared
│   ├── runtime/                 # From codegraph-runtime
│   ├── analysis/                # From codegraph-analysis
│   ├── agent/                   # From codegraph-agent
│   ├── ml/                      # From codegraph-ml
│   └── search/                  # From codegraph-search
```

**단점**:
- 거대한 단일 패키지 (복잡도 증가)
- 모듈 간 경계 흐려짐
- 선택적 설치 불가능 (agent 없이 analysis만 쓰고 싶은 경우)
- 마이그레이션 부담 (모든 import 변경)

**Verdict**: ❌ 비권장

### Option 3: 레포 분리 (비권장) ❌

**분리 시나리오**:
```
Repo 1: codegraph-engine (Rust)
  └── codegraph-rust/

Repo 2: codegraph-core (Python)
  └── shared, runtime, analysis, parsers

Repo 3: codegraph-apps (Applications)
  └── agent, ml, search
```

**단점**:
- Version coordination 복잡
- Testing 어려움 (cross-repo dependencies)
- Monorepo의 장점 상실
- CI/CD 복잡도 증가

**Verdict**: ❌ 비권장 (Monorepo 유지가 낫다)

---

## 권장: 최소한의 정리만

### 통합할 것

1. **`codegraph-security` + `security-rules` → `codegraph-analysis/security/`**
   ```
   codegraph-analysis/
   └── codegraph_analysis/
       ├── security_analysis/       # 기존 (keep)
       ├── security/                # 신규 (merge)
       │   ├── crypto.py            # From codegraph-security
       │   ├── auth.py              # From codegraph-security
       │   ├── patterns/            # From security-rules
       │   └── framework_adapters/
       ├── api_misuse/              # 신규
       ├── patterns/                # 신규
       └── verification/            # 기존 (keep)
   ```

2. **`codegraph-engine/parsers/` → `codegraph-parsers/`**
   ```
   codegraph-parsers/
   └── codegraph_parsers/
       ├── parsing/         # 기존
       ├── template/        # 기존 + vue/jsx from engine
       └── document/        # 기존
   ```

### 삭제할 것

1. **`codegraph-taint/`** - Rust로 완전 대체됨
2. **`codegraph-security/`** - codegraph-analysis로 통합 후
3. **`security-rules/`** - codegraph-analysis로 통합 후
4. **`codegraph-engine/analyzers/`** - Rust로 대체됨
5. **`codegraph-engine/ir/layered_ir_builder.py`** - Rust로 대체됨

### 유지할 것 (변경 없음)

1. **`codegraph-rust/`** - Rust engine
2. **`codegraph-parsers/`** - Parsers
3. **`codegraph-shared/`** - Infrastructure
4. **`codegraph-runtime/`** - Orchestration
5. **`codegraph-analysis/`** - Analysis (security 추가)
6. **`codegraph-agent/`** - Agent
7. **`codegraph-ml/`** - ML
8. **`codegraph-search/`** - Search

---

## 의존성 정리

### Before (현재)

```
codegraph-runtime
  └── codegraph-engine (deprecated!)

codegraph-analysis
  └── codegraph-engine (deprecated!)

codegraph-agent
  └── codegraph-runtime
      └── codegraph-engine (deprecated!)

codegraph-ml
  └── ...

codegraph-search
  └── ...
```

**문제**: 많은 패키지가 `codegraph-engine` (deprecated)에 의존

### After (목표)

```
codegraph-runtime
  ├── codegraph-ir (Rust)
  ├── codegraph-analysis
  ├── codegraph-parsers
  └── codegraph-shared

codegraph-analysis
  ├── codegraph-ir (Rust)
  └── codegraph-shared

codegraph-agent
  └── codegraph-runtime

codegraph-ml
  └── codegraph-runtime

codegraph-search
  └── codegraph-runtime
```

**개선**: 모든 의존성이 `codegraph-ir` (Rust)로 향함

---

## 패키지별 상세 검토

### `codegraph-runtime` (🚀 유지)

**역할**: Orchestration, session memory, codegen loop

**구조**:
```
codegraph_runtime/
├── codegen_loop/        # Code generation loop
├── llm_arbitration/     # LLM orchestration
├── replay_audit/        # Audit replay
└── session_memory/      # Session state management
```

**LOC**: ~10,000+ (추정)

**의존성 변경 필요**:
- `codegraph-engine` → `codegraph-ir` (Rust)
- `codegraph-analysis` 추가 (for plugins)

**조치**: ✅ Keep (의존성만 업데이트)

---

### `codegraph-agent` (🤖 유지)

**역할**: Autonomous coding agent

**구조**:
```
codegraph_agent/
├── assistant/           # Assistant features
├── autonomous/          # Autonomous features
├── ports/               # Interfaces
└── shared/              # Shared utilities
```

**조치**: ✅ Keep (변경 없음)

---

### `codegraph-ml` (🧠 유지)

**역할**: ML features (adaptive embeddings)

**구조**:
```
codegraph_ml/
└── adaptive_embeddings/ # Adaptive embedding system
```

**조치**: ✅ Keep (변경 없음)

---

### `codegraph-search` (🔍 유지)

**역할**: Search features

**조치**: ✅ Keep (변경 없음)

---

### `codegraph-shared` (🔧 유지)

**역할**: Infrastructure (DB, storage, jobs, config)

**LOC**: ~15,000+ (추정)

**주요 기능**:
- Database connections (PostgreSQL, Redis, Qdrant)
- Job handlers (IR, chunk, vector, lexical)
- Configuration management
- Observability (logging, metrics)

**의존성 변경 필요**:
- `codegraph-engine` → `codegraph-ir` (Rust)

**조치**: ✅ Keep (의존성만 업데이트)

---

### `codegraph-engine` (⚠️ 부분 삭제)

**삭제할 것**:
```
codegraph_engine/
└── code_foundation/
    └── infrastructure/
        ├── analyzers/           # 🗑️ DELETE
        │   ├── interprocedural_taint.py  # → Rust
        │   ├── path_sensitive_taint.py   # → Rust
        │   └── deep_security_analyzer.py # → codegraph-analysis
        ├── ir/
        │   └── layered_ir_builder.py     # 🗑️ DELETE → Rust
        └── parsers/             # 🔄 MOVE → codegraph-parsers
```

**유지할 것** (확인 필요):
```
codegraph_engine/
└── code_foundation/
    └── infrastructure/
        ├── chunk/               # ✅ Keep? (chunk builder)
        ├── generators/          # ✅ Keep? (code generators)
        ├── heap/                # ✅ Keep? (heap analysis)
        ├── semantic_ir/         # ✅ Keep? (semantic IR)
        ├── storage/             # ✅ Keep? (memgraph store)
        └── type_inference/      # ✅ Keep? (type inference)
```

**조치 필요**:
1. 삭제할 것 명확히 확인
2. 유지할 것 Rust에 있는지 확인
3. 중복이면 삭제, 없으면 유지 또는 Rust 포팅

---

## 최종 권장사항

### ✅ DO: 최소한의 통합

1. **Security 통합**: `codegraph-security` + `security-rules` → `codegraph-analysis/security/`
2. **Parser 통합**: `codegraph-engine/parsers/` → `codegraph-parsers/`
3. **중복 삭제**: `codegraph-taint/`, deprecated analyzers

### ✅ DO: 의존성 정리

모든 패키지의 의존성을 `codegraph-engine` → `codegraph-ir` (Rust)로 변경:
- `codegraph-runtime/pyproject.toml`
- `codegraph-analysis/pyproject.toml`
- `codegraph-shared/pyproject.toml`

### ❌ DON'T: 대규모 재구성

- ❌ 패키지 통합 (codegraph-core 같은 거대 패키지)
- ❌ 레포 분리
- ❌ 잘 작동하는 패키지 건드리기 (agent, ml, search)

---

## 추가 조사 필요

### `codegraph-engine`의 나머지 기능

다음 디렉토리들이 Rust에 있는지 확인 필요:

1. **`chunk/`** (1,582 + 1,281 = 2,863 LOC)
   - Chunk builder, incremental chunking
   - Rust에 있나? → 확인 필요

2. **`generators/`** (2,707 + 1,160 = 3,867 LOC)
   - Java, TypeScript code generators
   - Rust에 있나? → 확인 필요

3. **`heap/`** (1,169 LOC)
   - Separation logic (sep_logic.py)
   - Rust에 heap_analysis/ 있음 → 비교 필요

4. **`semantic_ir/`** (2,416 + 2,210 + 1,666 = 6,292 LOC)
   - Expression builder, BFG builder
   - Rust에 있나? → 확인 필요

5. **`storage/`** (1,276 LOC)
   - Memgraph store
   - 별도 유지? → 확인 필요

6. **`type_inference/`** (1,486 LOC)
   - Builtin types generator
   - Rust에 있나? → 확인 필요

**조치**: 각각 Rust 구현 여부 확인 후 결정

---

## 결론

### 통합/분리는 최소한으로

**현재 구조가 이미 합리적**:
- 각 패키지가 명확한 역할
- 적절한 크기
- 잘 분리되어 있음

**필요한 작업**:
1. ✅ Security 통합 (3개 패키지 → 1개)
2. ✅ Parser 통합 (중복 제거)
3. ✅ 의존성 정리 (engine → ir)
4. ✅ 중복 코드 삭제

**추가 작업 불필요**:
- ❌ 패키지 대규모 통합
- ❌ 레포 분리
- ❌ 구조 재설계

**추가 조사**:
- `codegraph-engine`의 나머지 기능 (chunk, generators, etc.) Rust 구현 여부 확인

---

**Last Updated**: 2025-12-28
**Status**: Recommendation
**Decision**: 최소한의 정리만, 추가 통합/분리 불필요
