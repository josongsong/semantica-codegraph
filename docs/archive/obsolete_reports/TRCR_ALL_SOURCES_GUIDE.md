# TRCR 전체 소스 통합 가이드 🚀

**CodeGraph TRCR**에 모든 빅테크 보안 룰을 통합하는 완전한 가이드입니다.

---

## 📊 통합 대상 소스

| 소스 | 제공사 | 룰 개수 | 품질 | TRCR 호환성 | 상태 |
|------|--------|---------|------|-------------|------|
| **CodeQL** | GitHub | ~50 | ⭐⭐⭐⭐⭐ | 95% | ✅ 완료 |
| **Pysa** | Meta | ~200 | ⭐⭐⭐⭐⭐ | 98% | 🚧 진행중 |
| **Semgrep** | Semgrep Inc. | ~100 (선별) | ⭐⭐⭐⭐ | 85% | 🚧 진행중 |

**예상 최종 결과**:
- **총 룰**: 304 → **~450+**
- **CWE 커버리지**: 49 → **60+**
- **OWASP Top 10**: 8/10 → **10/10** ✅

---

## 🚀 빠른 시작 (권장)

### 옵션 1: 전체 자동 통합 (한 번에!)
```bash
just trcr-pipeline-all
```

이 명령어는:
1. CodeQL 크롤링 → CSV → TRCR 룰 생성
2. Meta Pysa 크롤링 → CSV → TRCR 룰 생성
3. Semgrep 크롤링 → CSV → TRCR 룰 생성
4. 전체 검증 (450+ rules)

**예상 시간**: 10~15분 (첫 실행, 캐시 이후 ~2분)

### 옵션 2: 개별 소스 통합

#### CodeQL (GitHub)
```bash
just trcr-pipeline-codeql
```
→ 49 rules, 35 CWEs, ~30초

#### Meta Pysa (Facebook)
```bash
just trcr-pipeline-pysa
```
→ ~200 rules, +8 CWEs, ~2분

#### Semgrep (고품질만)
```bash
just trcr-pipeline-semgrep
```
→ ~100 rules, +15 CWEs, ~3분

---

## 📚 각 소스별 상세 설명

### 1. CodeQL (GitHub) ⭐⭐⭐⭐⭐

**특징**:
- GitHub Security Lab에서 관리
- 수백만 repo에서 검증됨
- False Positive 매우 낮음
- OWASP Top 10 + CWE Top 25 커버

**크롤링 대상**:
- Repository: `github.com/github/codeql`
- 위치: `python/ql/src/Security/`
- 파일 타입: `.ql` (CodeQL query language)

**추출 예시**:
```yaml
# CWE-089: SQL Injection
- id: sink.cwe_089.SqlInjection
  kind: sink
  severity: critical
  cwe: ["CWE-089"]
  match:
    - base_type: sqlite3.Cursor
      call: execute
      args: [0]
```

### 2. Meta Pysa (Facebook) ⭐⭐⭐⭐⭐

**특징**:
- Meta (Facebook) 내부 프로덕션 도구
- Taint analysis 전문
- TRCR와 거의 동일한 구조 (98% 호환)
- Python 전용으로 최적화

**크롤링 대상**:
- Repository: `github.com/facebook/pyre-check`
- 위치: `stubs/taint/`
- 파일 타입: `.pysa` (Pyre Static Analyzer)

**추출 예시**:
```yaml
# Remote Code Execution
- id: pysa.remotecodeexecution.eval
  kind: sink
  severity: critical
  cwe: ["CWE-094"]
  match:
    - call: eval
      args: [0]
```

**주요 카테고리**:
- Remote Code Execution (RCE)
- SQL Injection
- Command Injection
- Deserialization
- File System Operations
- Email Send (Header Injection)

### 3. Semgrep (Semgrep Inc.) ⭐⭐⭐⭐

**특징**:
- 커뮤니티 기여 룰 (400+ Python rules)
- 다양한 프레임워크 지원 (Django, Flask, FastAPI)
- OWASP Top 10 전체 커버
- 고품질만 선별 (confidence: high/medium)

**크롤링 대상**:
- Repository: `github.com/semgrep/semgrep-rules`
- 위치: `python/security/`, `python/owasp/`, `python/injection/`
- 파일 타입: `.yaml` (Semgrep rules)

**품질 필터링**:
```python
# High quality only (default)
--quality high
  → confidence: high/medium
  → severity: ERROR/WARNING
  → CWE 매핑 필수

# Medium quality
--quality medium
  → severity: ERROR/WARNING

# All (not recommended)
--quality all
```

**추출 예시**:
```yaml
# Django specific: Mass Assignment
- id: semgrep.django_mass_assignment
  kind: sink
  severity: high
  cwe: ["CWE-915"]
  match:
    - base_type: Model
      call: save
      args: [0]
```

---

## 🛠️ 고급 사용법

### 개별 크롤러 실행

#### CodeQL 크롤러
```bash
# 기본
PYTHONPATH=. python tools/trcr/crawl_codeql.py --output data/codeql_rules.csv

# 캐시 재사용
PYTHONPATH=. python tools/trcr/crawl_codeql.py \
  --output data/codeql_rules.csv \
  --cache-dir ~/.codeql_cache
```

#### Pysa 크롤러
```bash
# 기본
PYTHONPATH=. python tools/trcr/crawl_pysa.py --output data/pysa_rules.csv

# 캐시 재사용
PYTHONPATH=. python tools/trcr/crawl_pysa.py \
  --output data/pysa_rules.csv \
  --cache-dir ~/.pysa_cache
```

#### Semgrep 크롤러
```bash
# 고품질만 (권장)
PYTHONPATH=. python tools/trcr/crawl_semgrep.py \
  --output data/semgrep_rules.csv \
  --quality high

# 중품질 포함
PYTHONPATH=. python tools/trcr/crawl_semgrep.py \
  --output data/semgrep_rules.csv \
  --quality medium

# 전체 (권장 안함)
PYTHONPATH=. python tools/trcr/crawl_semgrep.py \
  --output data/semgrep_rules.csv \
  --quality all
```

### CSV → TRCR 변환

```bash
# CodeQL
just trcr-generate-csv data/codeql_rules.csv packages/codegraph-trcr/rules/atoms/codeql/

# Pysa
just trcr-generate-csv data/pysa_rules.csv packages/codegraph-trcr/rules/atoms/pysa/

# Semgrep
just trcr-generate-csv data/semgrep_rules.csv packages/codegraph-trcr/rules/atoms/semgrep/
```

### 검증

```bash
# 개별 검증
PYTHONPATH=. python tools/trcr/validate_rules.py packages/codegraph-trcr/rules/atoms/codeql/*.yaml
PYTHONPATH=. python tools/trcr/validate_rules.py packages/codegraph-trcr/rules/atoms/pysa/*.yaml
PYTHONPATH=. python tools/trcr/validate_rules.py packages/codegraph-trcr/rules/atoms/semgrep/*.yaml

# 전체 검증
PYTHONPATH=. python tools/trcr/validate_rules.py packages/codegraph-trcr/rules/atoms/**/*.yaml
```

---

## 📊 예상 결과

### Phase 1: CodeQL만 (현재 완료)
```
Total Rules: 304
CWE Coverage: 49
OWASP: 8/10
Compile Time: 73.73ms
```

### Phase 2: CodeQL + Pysa
```
Total Rules: ~500
CWE Coverage: ~55
OWASP: 9/10
Compile Time: ~120ms
```

### Phase 3: CodeQL + Pysa + Semgrep (최종)
```
Total Rules: ~600
CWE Coverage: 60+
OWASP: 10/10 ✅
Compile Time: ~150ms
```

**SOTA Tier 1 달성!** 🎉

---

## 🎯 Just 명령어 요약

```bash
# 개별 크롤링
just trcr-crawl-codeql    # CodeQL
just trcr-crawl-pysa      # Meta Pysa
just trcr-crawl-semgrep   # Semgrep (고품질)

# 개별 파이프라인
just trcr-pipeline-codeql   # CodeQL 전체
just trcr-pipeline-pysa     # Pysa 전체
just trcr-pipeline-semgrep  # Semgrep 전체

# 전체 자동 통합 (권장!)
just trcr-pipeline-all      # 모든 소스 한 번에

# 검증
just trcr-validate          # CodeQL만
just trcr-validate-all      # 전체
```

---

## 🔍 트러블슈팅

### "Git command failed"
```bash
# Git이 설치되어 있는지 확인
git --version

# 캐시 디렉토리 권한 확인
ls -la /tmp/*_cache
```

### "No rules extracted"
```bash
# Repository가 제대로 clone 되었는지 확인
ls -la /tmp/codeql_cache/python/ql/src/Security/
ls -la /tmp/pysa_cache/stubs/taint/
ls -la /tmp/semgrep_cache/python/

# 수동으로 다시 clone
rm -rf /tmp/*_cache
just trcr-pipeline-all
```

### "YAML syntax error"
```bash
# PyYAML 설치 확인
pip install PyYAML

# 파일 인코딩 확인
file data/*.csv
```

### "Compilation failed"
```bash
# TRCR 설치 확인
pip install -e packages/codegraph-trcr

# 룰 구문 검증
PYTHONPATH=. python tools/trcr/validate_rules.py packages/codegraph-trcr/rules/atoms/codeql/*.yaml
```

---

## 📈 로드맵

### ✅ 완료
- Phase 1: TRCR 코어 (253 rules)
- Phase 2: PyO3 바인딩 (Rust ↔ Python)
- Phase 3: CodeQL 통합 (51 rules)

### 🚧 진행중
- **Phase 4: Meta Pysa 통합** ← 현재
- **Phase 5: Semgrep 통합** ← 다음

### 🎯 계획
- Phase 6: SOTA Tier 1 달성 (60+ CWEs, 10/10 OWASP)
- Phase 7: Multi-language support (TypeScript, Go)
- Phase 8: Custom rule authoring guide

---

## 💡 팁

1. **첫 실행은 느립니다** (git clone + 파싱)
   - CodeQL: ~30초
   - Pysa: ~2분
   - Semgrep: ~3분
   - 캐시 이후: 각 ~10초

2. **캐시 재사용**
   ```bash
   # 캐시 위치 확인
   ls -la /tmp/*_cache

   # 영구 캐시로 이동
   mv /tmp/codeql_cache ~/.codeql_cache
   mv /tmp/pysa_cache ~/.pysa_cache
   mv /tmp/semgrep_cache ~/.semgrep_cache
   ```

3. **병렬 실행 (빠름)**
   ```bash
   # 백그라운드로 3개 동시 실행
   just trcr-crawl-codeql &
   just trcr-crawl-pysa &
   just trcr-crawl-semgrep &
   wait

   # 이후 변환 & 검증
   just trcr-generate-csv data/codeql_rules.csv packages/codegraph-trcr/rules/atoms/codeql/
   just trcr-generate-csv data/pysa_rules.csv packages/codegraph-trcr/rules/atoms/pysa/
   just trcr-generate-csv data/semgrep_rules.csv packages/codegraph-trcr/rules/atoms/semgrep/
   just trcr-validate-all
   ```

4. **품질 > 수량**
   - Semgrep은 `--quality high`만 사용 권장
   - False positive 최소화

---

**마지막 업데이트**: 2025-12-29
**상태**: 🚧 Pysa & Semgrep 크롤러 준비 완료
**다음 단계**: `just trcr-pipeline-all` 실행!
