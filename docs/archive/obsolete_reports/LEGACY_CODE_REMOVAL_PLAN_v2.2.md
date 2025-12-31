# Legacy Code Removal Plan - v2.2.0

**Target Release**: v2.2.0 (Q1 2025)
**Date**: 2025-12-28
**Status**: Planning

---

## Overview

v2.2.0에서 Python IR 빌드 관련 레거시 코드를 완전히 제거합니다.
v2.1.0에서 deprecation warning을 표시했으므로, 사용자들은 Rust engine으로 마이그레이션 완료 예상.

**목표**: Python → Rust 의존성을 완전히 제거하고 코드베이스 단순화

---

## 삭제 대상 파일 및 코드

### 1. LayeredIRBuilder 및 관련 Python IR 빌드 코드

#### 1.1. 핵심 파일 (완전 삭제)

```bash
# 주요 IR Builder 파일
packages/codegraph-engine/codegraph_engine/code_foundation/infrastructure/ir/layered_ir_builder.py

# 관련 빌더 파일
packages/codegraph-engine/codegraph_engine/code_foundation/infrastructure/ir/collection_builder.py
packages/codegraph-engine/codegraph_engine/code_foundation/infrastructure/ir/interprocedural_builder.py

# Config 파일 (Rust로 완전 이전)
packages/codegraph-engine/codegraph_engine/code_foundation/infrastructure/ir/build_config.py
```

**확인 필요**: 다른 곳에서 import하는지 체크
```bash
grep -r "from.*layered_ir_builder import" packages/ tests/
grep -r "LayeredIRBuilder" packages/ tests/
```

#### 1.2. 지원 모듈 (검토 후 삭제)

```bash
# Type enrichment (LSP 기반)
packages/codegraph-engine/codegraph_engine/code_foundation/infrastructure/ir/type_enricher.py
packages/codegraph-engine/codegraph_engine/code_foundation/infrastructure/ir/lsp/

# Occurrence generator (SCIP)
packages/codegraph-engine/codegraph_engine/code_foundation/infrastructure/ir/occurrence_generator.py

# Diagnostic collector
packages/codegraph-engine/codegraph_engine/code_foundation/infrastructure/ir/diagnostic_collector.py

# Package analyzer
packages/codegraph-engine/codegraph_engine/code_foundation/infrastructure/ir/package_analyzer.py
```

**검토 이유**: 일부는 Rust에서 재사용 가능하거나 다른 모듈에서 사용 중일 수 있음

#### 1.3. Python Cross-File Resolver (Fallback 제거)

```bash
# Python 구현 제거 (Rust L3가 대체)
packages/codegraph-engine/codegraph_engine/code_foundation/infrastructure/ir/cross_file_resolver.py
```

**확인**: `CrossFileHandler`가 fallback으로 사용 중
- v2.2.0에서 Python fallback 완전 제거
- Rust 실패 시 에러 반환 (fallback 없음)

---

### 2. 테스트 파일

#### 2.1. LayeredIRBuilder 테스트 (완전 삭제)

```bash
# 단위 테스트
tests/unit/code_foundation/infrastructure/ir/test_layered_ir_builder.py
tests/unit/code_foundation/infrastructure/ir/test_determinism.py  # LayeredIRBuilder 사용

# 통합 테스트
tests/integration/code_foundation/test_ir_builder_*.py
tests/integration/code_foundation/test_ir_cache_performance.py  # LayeredIRBuilder 사용
```

#### 2.2. 업데이트 필요한 테스트

```bash
# Mock 업데이트 필요 (LayeredIRBuilder → codegraph_ir)
tests/infra/jobs/handlers/test_handlers.py  # ✅ 이미 업데이트됨
tests/infra/jobs/handlers/test_orchestrator.py  # 확인 필요
tests/unit/ir/test_stable_merge_rfc037.py  # 확인 필요
tests/integration/test_querydsl_complex_scenarios.py  # 확인 필요
```

---

### 3. Handler 코드 정리

#### 3.1. IRBuildHandler

**현재 상태** (v2.1):
```python
# packages/codegraph-shared/codegraph_shared/infra/jobs/handlers/ir_handler.py
# ✅ 이미 Rust만 사용 (LayeredIRBuilder 제거됨)
```

**v2.2.0 변경사항**: 없음 (이미 정리됨)

#### 3.2. CrossFileHandler

**현재 상태** (v2.1):
```python
# Rust 우선, Python fallback 있음
if RUST_AVAILABLE:
    try:
        result = self._resolve_with_rust(ir_documents)
    except Exception:
        # Fallback to Python
        from ...cross_file_resolver import CrossFileResolver
        resolver = CrossFileResolver()
```

**v2.2.0 변경사항**:
```python
# Python fallback 제거
if not RUST_AVAILABLE:
    raise RuntimeError(
        "Rust engine (codegraph_ir) is required for cross-file resolution. "
        "Install with: pip install codegraph-ir"
    )

result = self._resolve_with_rust(ir_documents)
# No fallback - raise error if Rust fails
```

---

### 4. Import 정리

#### 4.1. 제거할 import

```python
# packages/codegraph-shared/codegraph_shared/infra/jobs/handlers/ir_handler.py
# (이미 제거됨)

# packages/codegraph-shared/codegraph_shared/infra/jobs/handlers/cross_file_handler.py
from codegraph_engine.code_foundation.infrastructure.ir.cross_file_resolver import CrossFileResolver
# ↑ 삭제 (fallback 제거)
```

#### 4.2. 의존성 확인

```bash
# 어디서 LayeredIRBuilder를 import하는지 전체 검색
rg "from.*layered_ir_builder" -t py
rg "LayeredIRBuilder" -t py

# BuildConfig 사용처 확인
rg "from.*build_config import" -t py
rg "BuildConfig" -t py
```

---

### 5. 문서 업데이트

#### 5.1. 삭제할 문서

```bash
# 더 이상 유효하지 않은 Python IR 관련 문서
docs/handbook/system-handbook/modules/ir-builder.md  # 있다면
README 섹션에서 LayeredIRBuilder 언급 제거
```

#### 5.2. 업데이트할 문서

```bash
# Migration guide 업데이트
docs/MIGRATION_GUIDE_v2.1.md
→ docs/MIGRATION_GUIDE_v2.2.md (v2.2 변경사항 추가)

# CLAUDE.md
CLAUDE.md  # LayeredIRBuilder 언급 제거 (이미 Rust만 언급 중)

# Changelog
CHANGELOG.md  # v2.2.0 섹션에 breaking changes 기록
```

---

## 삭제 체크리스트

### Phase 1: 코드 분석 (1주차)

- [ ] LayeredIRBuilder 사용처 전체 검색
  ```bash
  rg "LayeredIRBuilder" -t py --stats
  rg "from.*layered_ir_builder" -t py
  ```

- [ ] 의존성 그래프 생성
  ```bash
  # Python imports 분석
  pydeps packages/codegraph-engine --show-deps
  ```

- [ ] 영향받는 테스트 식별
  ```bash
  pytest --collect-only | grep -i "layered\|ir.*build"
  ```

### Phase 2: 테스트 마이그레이션 (2주차)

- [ ] LayeredIRBuilder 테스트 완전 삭제
  - [ ] `test_layered_ir_builder.py`
  - [ ] `test_determinism.py` (LayeredIRBuilder 사용 부분)
  - [ ] `test_ir_builder_*.py`

- [ ] 남은 테스트에서 mock 업데이트
  - [ ] `test_handlers.py` (✅ 완료)
  - [ ] `test_orchestrator.py`
  - [ ] `test_stable_merge_rfc037.py`
  - [ ] `test_querydsl_complex_scenarios.py`

- [ ] 전체 테스트 실행 확인
  ```bash
  pytest tests/ -v --tb=short
  ```

### Phase 3: 코드 삭제 (3주차)

#### 3.1. 핵심 파일 삭제

```bash
# LayeredIRBuilder 및 관련 파일
rm packages/codegraph-engine/codegraph_engine/code_foundation/infrastructure/ir/layered_ir_builder.py
rm packages/codegraph-engine/codegraph_engine/code_foundation/infrastructure/ir/build_config.py
rm packages/codegraph-engine/codegraph_engine/code_foundation/infrastructure/ir/collection_builder.py
rm packages/codegraph-engine/codegraph_engine/code_foundation/infrastructure/ir/interprocedural_builder.py
```

#### 3.2. Python Cross-File Resolver 삭제

```bash
rm packages/codegraph-engine/codegraph_engine/code_foundation/infrastructure/ir/cross_file_resolver.py

# CrossFileHandler에서 fallback 제거
vim packages/codegraph-shared/codegraph_shared/infra/jobs/handlers/cross_file_handler.py
```

#### 3.3. 지원 모듈 삭제 (검토 후)

```bash
# 다른 곳에서 사용하지 않으면 삭제
rm packages/codegraph-engine/codegraph_engine/code_foundation/infrastructure/ir/type_enricher.py
rm packages/codegraph-engine/codegraph_engine/code_foundation/infrastructure/ir/occurrence_generator.py
rm packages/codegraph-engine/codegraph_engine/code_foundation/infrastructure/ir/diagnostic_collector.py
rm packages/codegraph-engine/codegraph_engine/code_foundation/infrastructure/ir/package_analyzer.py
rm -rf packages/codegraph-engine/codegraph_engine/code_foundation/infrastructure/ir/lsp/
```

### Phase 4: Import 정리 (3주차)

- [ ] 모든 `from ... import LayeredIRBuilder` 제거
- [ ] 모든 `from ... import BuildConfig` 제거 (Rust 사용)
- [ ] 모든 `from ... import CrossFileResolver` 제거
- [ ] Unused imports 정리
  ```bash
  ruff check packages/ --select F401 --fix
  ```

### Phase 5: 문서 업데이트 (4주차)

- [ ] MIGRATION_GUIDE_v2.2.md 작성
- [ ] CHANGELOG.md 업데이트
- [ ] README 업데이트 (LayeredIRBuilder 언급 제거)
- [ ] 관련 ADR 업데이트

### Phase 6: 검증 (4주차)

- [ ] 전체 테스트 통과
  ```bash
  pytest tests/ -v
  ```

- [ ] Type checking 통과
  ```bash
  pyright packages/
  ```

- [ ] Linting 통과
  ```bash
  ruff check packages/ tests/
  black --check packages/ tests/
  ```

- [ ] 빌드 성공
  ```bash
  pip install -e .
  ```

- [ ] 통합 테스트
  ```bash
  pytest tests/integration/ -v
  ```

---

## 예상 삭제 코드량

### Python 파일

| Category | Files | Lines |
|----------|-------|-------|
| LayeredIRBuilder 핵심 | 4 files | ~3,000 LOC |
| 지원 모듈 | 6 files | ~2,000 LOC |
| Python CrossFileResolver | 1 file | ~800 LOC |
| 테스트 파일 | 8 files | ~2,500 LOC |
| **Total** | **~19 files** | **~8,300 LOC** |

### 예상 영향

- ✅ **긍정적**: 코드베이스 단순화, 유지보수 용이
- ⚠️ **주의**: 일부 사용자가 아직 Python IR 사용 중일 수 있음
- 📝 **완화**: v2.1.0에서 충분한 deprecation warning 제공

---

## 위험 관리

### 위험 1: 사용자가 아직 마이그레이션 안 함

**완화 방안**:
- v2.1.0 릴리스 후 최소 3개월 유예 기간
- 명확한 deprecation warning
- 상세한 마이그레이션 가이드 제공

### 위험 2: Rust engine에 버그 발견

**완화 방안**:
- v2.1.x에서 충분한 테스트 기간
- Issue tracker로 버그 보고 수집
- v2.2.0 전에 모든 critical 버그 수정

### 위험 3: 숨겨진 의존성

**완화 방안**:
- 코드 분석 도구 사용 (pydeps, rg)
- 전체 테스트 커버리지 확인
- Pre-release 버전 배포 (v2.2.0-rc1)

---

## 릴리스 타임라인

### v2.1.0 (Current)
- ✅ Rust engine 기본값
- ✅ Deprecation warnings
- ✅ 마이그레이션 가이드

### v2.1.x (3개월 유예)
- 사용자 피드백 수집
- Rust engine 버그 수정
- 마이그레이션 지원

### v2.2.0-rc1 (Pre-release)
- 레거시 코드 삭제
- 테스트 및 검증
- Early adopters 피드백

### v2.2.0 (Final)
- 레거시 코드 완전 제거
- Breaking changes 문서화
- 릴리스 노트 공개

---

## 삭제 스크립트 (자동화)

```bash
#!/bin/bash
# remove_legacy_ir.sh

set -e

echo "🗑️  Removing legacy Python IR code..."

# 1. LayeredIRBuilder 및 관련 파일
echo "Removing LayeredIRBuilder..."
rm -f packages/codegraph-engine/codegraph_engine/code_foundation/infrastructure/ir/layered_ir_builder.py
rm -f packages/codegraph-engine/codegraph_engine/code_foundation/infrastructure/ir/build_config.py
rm -f packages/codegraph-engine/codegraph_engine/code_foundation/infrastructure/ir/collection_builder.py
rm -f packages/codegraph-engine/codegraph_engine/code_foundation/infrastructure/ir/interprocedural_builder.py

# 2. CrossFileResolver
echo "Removing Python CrossFileResolver..."
rm -f packages/codegraph-engine/codegraph_engine/code_foundation/infrastructure/ir/cross_file_resolver.py

# 3. 지원 모듈 (선택적)
read -p "Remove support modules (type_enricher, occurrence_generator, etc.)? [y/N] " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    rm -f packages/codegraph-engine/codegraph_engine/code_foundation/infrastructure/ir/type_enricher.py
    rm -f packages/codegraph-engine/codegraph_engine/code_foundation/infrastructure/ir/occurrence_generator.py
    rm -f packages/codegraph-engine/codegraph_engine/code_foundation/infrastructure/ir/diagnostic_collector.py
    rm -f packages/codegraph-engine/codegraph_engine/code_foundation/infrastructure/ir/package_analyzer.py
    rm -rf packages/codegraph-engine/codegraph_engine/code_foundation/infrastructure/ir/lsp/
fi

# 4. 테스트 파일
echo "Removing legacy tests..."
rm -f tests/unit/code_foundation/infrastructure/ir/test_layered_ir_builder.py
rm -f tests/unit/code_foundation/infrastructure/ir/test_determinism.py

# 5. Import 정리
echo "Cleaning up imports..."
ruff check packages/ --select F401 --fix

# 6. 검증
echo "Running tests..."
pytest tests/ -v -x

echo "✅ Legacy code removal complete!"
echo "📝 Don't forget to update documentation!"
```

---

## 커밋 메시지 템플릿

```
feat!: Remove legacy Python IR building code (v2.2.0)

BREAKING CHANGE: LayeredIRBuilder and Python IR building code removed.

All IR building now uses Rust engine (codegraph_ir).

Removed:
- LayeredIRBuilder and related Python IR builders
- Python CrossFileResolver (use Rust L3 pipeline)
- Legacy tests and support modules

Migration:
See docs/MIGRATION_GUIDE_v2.2.md for upgrade instructions.

Users must migrate to Rust engine before upgrading to v2.2.0.

Refs: ADR-072
```

---

## FAQ

### Q1: v2.1.0에서 LayeredIRBuilder를 사용 중인데?

**A**: v2.2.0으로 업그레이드하기 전에 Rust engine으로 마이그레이션 필요.
[MIGRATION_GUIDE_v2.1.md](./MIGRATION_GUIDE_v2.1.md) 참고.

### Q2: Rust engine에 버그가 있으면?

**A**: v2.1.x에서 버그 수정 후 v2.2.0 릴리스. Issue 보고 권장.

### Q3: 일부 기능이 Rust에 없으면?

**A**: 필요한 기능을 Rust에 추가 후 삭제 진행.

### Q4: 롤백 가능한가?

**A**: v2.1.x로 다운그레이드 가능. v2.2.0은 breaking change.

---

## 체크리스트 요약

### 삭제 전 (v2.1.x)
- [x] Rust engine 안정화
- [x] Deprecation warnings 추가
- [x] 마이그레이션 가이드 작성
- [ ] 사용자 피드백 수집 (3개월)
- [ ] 모든 critical 버그 수정

### 삭제 작업 (v2.2.0)
- [ ] 코드 분석 및 의존성 확인
- [ ] 테스트 마이그레이션
- [ ] 레거시 코드 삭제
- [ ] Import 정리
- [ ] 문서 업데이트
- [ ] 전체 검증

### 릴리스 (v2.2.0)
- [ ] Pre-release 테스트
- [ ] CHANGELOG 작성
- [ ] 릴리스 노트 공개
- [ ] 마이그레이션 지원

---

**Last Updated**: 2025-12-28
**Status**: Planning (for v2.2.0)
