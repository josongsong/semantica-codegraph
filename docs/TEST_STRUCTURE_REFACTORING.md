# 테스트 구조 리팩토링 계획

## Executive Summary

**현재**: 185개 테스트, 19개 최상위 디렉토리, 분류 기준 혼재  
**목표**: SOTA급 계층 구조, 명확한 분류, 확장 가능한 설계  
**영향**: 테스트 발견성 ↑, 유지보수성 ↑, 실행 효율 ↑

---

## 1. 현재 구조 분석

### 1.1 현황
```
총 테스트: 185개
최상위 디렉토리: 19개

분포:
- foundation:         44개 (23.7%) ⚠️
- v6:                31개 (16.8%) 🔴
- [루트]:            25개 (13.5%) 🔴
- retriever:         16개 (8.6%)
- integration:       11개 (5.9%)
- 기타:              58개 (31.4%)
```

### 1.2 심각한 문제점

#### P0: 확장성 부족 (Critical)
```
v6/ (31개 테스트)
├── unit/
├── integration/
├── sota/
└── production/

문제: v7, v8 출시 시 어떻게?
→ 버전은 git 태그로 관리해야 함
```

#### P0: 계층 혼재 (Critical)
```
tests/
├── unit/          ← 테스트 레벨
├── integration/   ← 테스트 레벨
├── foundation/    ← 기능
├── contexts/      ← 기능
└── v6/            ← 버전

같은 계층에 다른 분류 기준 → 혼란
```

#### P1: 과도한 집중 (High)
```
foundation/: 44개 (23.7%)
- IR, graph, parser, storage, chunk...
→ 너무 많은 책임, 세분화 필요
```

#### P1: 미분류 테스트 (High)
```
tests/ 루트: 25개
- test_overlay_basic.py
- test_container.py
- test_git_manager.py
...

어디로 갈지 불명확
```

#### P2: 중복 계층 (Medium)
```
integration/ (최상위)
v6/integration/
analysis_indexing/integration/

일관성 부족
```

#### P2: 네이밍 비일관성 (Medium)
```
security_analysis vs analyzers
chunking vs graph_construction
repomap vs retriever

혼란스러운 네이밍
```

---

## 2. SOTA급 설계 원칙

### 2.1 테스트 피라미드
```
      /\
     /E2E\    10% - 느림, 비용 높음
    /------\
   /Integ. \  20% - 중간
  /----------\
 /   Unit     \ 70% - 빠름, 많음
/--------------\

Unit: 빠른 피드백, 격리된 테스트
Integration: 모듈 간 상호작용
E2E: 실제 사용자 시나리오
```

### 2.2 DDD 정렬
```
도메인 컨텍스트 존중:
- code_foundation
- indexing_pipeline
- retrieval_search
- session_memory

테스트도 같은 구조 따름
```

### 2.3 확장성
```
❌ 버전별: v6/, v7/, v8/
✅ 기능별: taint_analysis/, code_graph/

새 기능 추가: 새 디렉토리
새 버전: git 태그/브랜치
```

### 2.4 명확성
```
한 가지 분류 기준:
1차: 테스트 레벨 (unit/integration/e2e)
2차: 도메인/기능
3차: 세부 모듈

test_<feature>_<aspect>.py
```

---

## 3. 제안 구조

### 3.1 최상위 구조
```
tests/
├── unit/              # 70% - 격리된 단위 테스트
├── integration/       # 20% - 모듈 간 통합
├── e2e/              # 10% - 전체 시나리오
├── performance/      # 성능/벤치마크
├── security/         # 보안 테스트
├── contract/         # API 계약
├── fixtures/         # 공유 픽스처
└── helpers/          # 테스트 유틸리티
```

### 3.2 Unit 구조 (70%)
```
unit/
├── domain/                 # 도메인 로직
│   ├── code_graph/        # 코드 그래프
│   │   ├── test_ir_models.py
│   │   ├── test_cfg.py
│   │   └── test_dfg.py
│   │
│   ├── analysis/          # 분석
│   │   ├── test_taint_engine.py
│   │   └── test_impact_analyzer.py
│   │
│   ├── indexing/          # 인덱싱
│   │   └── test_delta_calculator.py
│   │
│   └── retrieval/         # 검색
│       └── test_ranking.py
│
├── infrastructure/         # 인프라
│   ├── parsers/           # 파서
│   │   ├── test_python_parser.py
│   │   └── test_java_parser.py
│   │
│   ├── generators/        # IR 생성기
│   │   ├── test_python_generator.py
│   │   └── test_java_generator.py
│   │
│   ├── storage/           # 스토리지
│   │   ├── test_postgres_store.py
│   │   ├── test_redis_cache.py
│   │   └── test_kuzu_graph.py
│   │
│   └── cache/             # 캐시
│       └── test_bloom_filter.py
│
├── application/            # 애플리케이션
│   ├── indexing_service/
│   ├── search_service/
│   └── analysis_service/
│
└── shared/                 # 공유
    ├── models/
    └── helpers/
```

### 3.3 Integration 구조 (20%)
```
integration/
├── database/               # DB 통합
│   ├── postgres/
│   ├── redis/
│   └── kuzu/
│
├── external_services/      # 외부 서비스
│   ├── llm/               # LLM
│   ├── git/               # Git
│   └── lsp/               # LSP (pyright, jdtls)
│
├── workflows/              # 워크플로우
│   ├── indexing_pipeline/
│   ├── search_pipeline/
│   └── analysis_pipeline/
│
└── api/                    # API
    ├── rest/
    └── mcp/
```

### 3.4 E2E 구조 (10%)
```
e2e/
├── user_scenarios/         # 사용자 시나리오
│   ├── java_project/      # Java 프로젝트 인덱싱
│   ├── python_project/    # Python 프로젝트
│   └── multi_language/    # 다중 언어
│
├── critical_paths/         # 크리티컬 경로
│   ├── first_indexing/    # 최초 인덱싱
│   ├── incremental_update/ # 증분 업데이트
│   └── search_accuracy/   # 검색 정확도
│
└── system_verification/    # 시스템 검증
    ├── comprehensive/     # 종합 (v6/sota → 여기로)
    └── regression/        # 리그레션
```

### 3.5 Security 구조
```
security/
├── taint_analysis/         # Taint 분석
│   ├── rules/             # 룰 테스트
│   ├── engines/           # 엔진 테스트
│   └── integration/       # 통합
│
├── vulnerability/          # 취약점
│   ├── sql_injection/
│   ├── xss/
│   └── path_traversal/
│
└── compliance/             # 컴플라이언스
    └── cwe/               # CWE 매핑
```

### 3.6 Performance 구조
```
performance/
├── benchmarks/             # 벤치마크
│   ├── indexing/
│   ├── search/
│   └── analysis/
│
├── load/                   # 부하 테스트
│   ├── concurrent_users/
│   └── large_repos/
│
├── profiling/              # 프로파일링
│   ├── memory/
│   └── cpu/
│
└── stress/                 # 스트레스
```

---

## 4. 마이그레이션 전략

### Phase 1: P0 즉시 실행 (1일)

#### 1.1 security_analysis → security
```bash
mv tests/security_analysis tests/security
```

#### 1.2 루트 테스트 분류 (25개)
```bash
# 분석
tests/test_overlay_basic.py → tests/unit/domain/code_graph/
tests/test_container.py → tests/integration/workflows/
tests/test_git_manager.py → tests/unit/infrastructure/git/

# 전체 매핑 생성
cat > /tmp/root_migration.txt << 'EOF'
test_overlay_basic.py → unit/domain/code_graph/
test_overlay_integration.py → integration/workflows/
test_container.py → integration/workflows/
test_git_manager.py → unit/infrastructure/git/
...
EOF
```

#### 1.3 v6/ 해체 계획
```bash
# v6/ 구조 분석
find tests/v6 -name "test_*.py" | while read f; do
  if [[ "$f" == *"/unit/"* ]]; then
    echo "$f → tests/unit/"
  elif [[ "$f" == *"/integration/"* ]]; then
    echo "$f → tests/integration/"
  elif [[ "$f" == *"/sota/"* ]]; then
    echo "$f → tests/e2e/system_verification/"
  fi
done > /tmp/v6_migration.txt
```

### Phase 2: P1 1주 내

#### 2.1 foundation/ 세분화 (44개)
```
foundation/test_ir_*.py → unit/domain/code_graph/
foundation/test_parser_*.py → unit/infrastructure/parsers/
foundation/test_*_store.py → unit/infrastructure/storage/
foundation/test_chunk_*.py → unit/domain/indexing/
```

#### 2.2 integration 통합
```
integration/ (최상위)
v6/integration/ → integration/workflows/
analysis_indexing/integration/ → integration/workflows/
```

#### 2.3 네이밍 컨벤션
```python
# Unit
test_<component>_<aspect>.py
예: test_ir_builder_basic.py

# Integration
test_<workflow>_integration.py
예: test_indexing_pipeline_integration.py

# E2E
test_<scenario>_e2e.py
예: test_java_project_e2e.py

# Performance
test_<component>_benchmark.py
예: test_search_benchmark.py

# Security
test_<vulnerability>_security.py
예: test_sql_injection_security.py
```

### Phase 3: P2 2주 내

#### 3.1 Fixtures 정리
```
fixtures/
├── repos/           # test_fixtures/scenario* → 여기로
├── data/
└── mocks/
```

#### 3.2 Helpers 구축
```
helpers/
├── builders/        # TestDataBuilder
├── factories/       # Factory 패턴
├── assertions/      # 커스텀 assert
└── utilities/       # 유틸
```

#### 3.3 문서화
```
tests/README.md      # 테스트 가이드
tests/CONVENTIONS.md # 네이밍 컨벤션
각 디렉토리/README.md # 세부 설명
```

---

## 5. 구체적 실행 계획

### 5.1 P0: 즉시 (오늘)

```bash
# 1. security 이름 변경
mv tests/security_analysis tests/security
mkdir -p tests/security/{taint_analysis,vulnerability,compliance}
mv tests/security/test_taint_*.py tests/security/taint_analysis/
mv tests/security/test_sql_*.py tests/security/vulnerability/

# 2. 기본 구조 생성
mkdir -p tests/{unit,integration,e2e,performance,contract,fixtures,helpers}
mkdir -p tests/unit/{domain,infrastructure,application,shared}
mkdir -p tests/integration/{database,external_services,workflows,api}
mkdir -p tests/e2e/{user_scenarios,critical_paths,system_verification}

# 3. README 생성
cat > tests/README.md << 'MDEOF'
# 테스트 구조

## 디렉토리 설명
- `unit/`: 단위 테스트 (70%)
- `integration/`: 통합 테스트 (20%)
- `e2e/`: E2E 테스트 (10%)
- `performance/`: 성능 테스트
- `security/`: 보안 테스트

## 네이밍 컨벤션
- Unit: `test_<component>_<aspect>.py`
- Integration: `test_<workflow>_integration.py`
- E2E: `test_<scenario>_e2e.py`
MDEOF
```

### 5.2 P1: 1주 (다음 주)

```bash
# v6/ 해체 스크립트
python3 << 'EOF'
import shutil
from pathlib import Path

v6_path = Path('tests/v6')
mappings = {
    'unit': 'tests/unit/domain/speculative',
    'integration': 'tests/integration/workflows/speculative',
    'sota': 'tests/e2e/system_verification/sota',
    'production': 'tests/e2e/user_scenarios/production'
}

for src_dir, dst_dir in mappings.items():
    src = v6_path / src_dir
    if src.exists():
        Path(dst_dir).mkdir(parents=True, exist_ok=True)
        for f in src.glob('test_*.py'):
            shutil.move(str(f), dst_dir)

print("v6/ 마이그레이션 완료")
EOF

# foundation/ 세분화
python3 << 'EOF'
import shutil
from pathlib import Path

foundation = Path('tests/foundation')
rules = [
    ('test_ir_*.py', 'tests/unit/domain/code_graph'),
    ('test_*_parser*.py', 'tests/unit/infrastructure/parsers'),
    ('test_*_generator*.py', 'tests/unit/infrastructure/generators'),
    ('test_*_store*.py', 'tests/unit/infrastructure/storage'),
    ('test_chunk*.py', 'tests/unit/domain/indexing'),
]

for pattern, dst in rules:
    dst_path = Path(dst)
    dst_path.mkdir(parents=True, exist_ok=True)
    for f in foundation.glob(pattern):
        shutil.move(str(f), dst_path)
EOF
```

### 5.3 P2: 2주

```bash
# Fixtures 정리
mv test_fixtures tests/fixtures/repos

# Helpers 구축
cat > tests/helpers/builders.py << 'PY'
"""Test data builders"""
class IRDocumentBuilder:
    def __init__(self):
        self.repo_id = "test"
        # ...
    
    def with_repo_id(self, repo_id):
        self.repo_id = repo_id
        return self
    
    def build(self):
        return IRDocument(repo_id=self.repo_id)
PY
```

---

## 6. 검증 및 측정

### 6.1 성공 지표

```python
# Before
find tests -name "test_*.py" | wc -l  # 185
ls tests/ | wc -l                     # 19

# After
find tests/unit -name "test_*.py" | wc -l        # ~130 (70%)
find tests/integration -name "test_*.py" | wc -l # ~37 (20%)
find tests/e2e -name "test_*.py" | wc -l         # ~18 (10%)
ls tests/ | wc -l                                # 8
```

### 6.2 품질 체크

```bash
# 1. 모든 테스트 실행 가능
pytest tests/ -v

# 2. 레벨별 실행
pytest tests/unit/ --maxfail=1
pytest tests/integration/ --maxfail=1
pytest tests/e2e/ --maxfail=1

# 3. 도메인별 실행
pytest tests/unit/domain/code_graph/
pytest tests/security/taint_analysis/

# 4. 네이밍 검증
find tests -name "test_*.py" | grep -v -E "^tests/(unit|integration|e2e|performance|security)/"
# → 0개여야 함
```

---

## 7. 기대 효과

### 7.1 개발자 경험
```
Before: "이 테스트 어디에 있지?"
After: "tests/unit/domain/code_graph/ 에 당연히 있겠지"

Before: "새 테스트 어디에 넣지?"
After: "Integration이니까 tests/integration/workflows/"

Before: "v6 테스트는 뭐지?"
After: "버전별 디렉토리 없음, 기능으로만 분류"
```

### 7.2 CI/CD
```bash
# 빠른 피드백 (PR)
pytest tests/unit/ --maxfail=5

# 중간 검증 (Merge)
pytest tests/unit/ tests/integration/

# 전체 검증 (Nightly)
pytest tests/
```

### 7.3 유지보수
```
- 테스트 찾기: 5분 → 30초
- 새 테스트 위치 결정: 3분 → 즉시
- 중복 제거: 명확한 구조로 쉽게 발견
- 리팩토링: 영향 범위 명확
```

---

## 8. 리스크 및 대응

### 8.1 리스크
1. **대규모 이동**: 185개 파일
2. **임포트 깨짐**: 경로 변경
3. **CI 실패**: 경로 하드코딩

### 8.2 대응
1. **점진적 마이그레이션**: P0 → P1 → P2
2. **자동화 스크립트**: Python으로 자동 이동
3. **검증**: 각 단계마다 pytest 실행
4. **롤백 계획**: Git 브랜치로 관리

---

## 9. 액션 아이템

### 오늘 (P0)
- [ ] `tests/security_analysis` → `tests/security`
- [ ] 기본 디렉토리 구조 생성
- [ ] tests/README.md 작성

### 다음 주 (P1)
- [ ] v6/ 해체
- [ ] foundation/ 세분화
- [ ] 네이밍 컨벤션 적용

### 2주 내 (P2)
- [ ] fixtures 정리
- [ ] helpers 구축
- [ ] 문서화 완료

---

## 10. 결론

**현재**: 혼재된 구조, 확장성 부족, 185개 테스트 분산  
**목표**: SOTA급 계층 구조, 명확한 분류, 유지보수성 향상  
**방법**: 3단계 점진적 마이그레이션  
**결과**: 개발자 경험 향상, CI/CD 효율화, 코드 품질 향상
