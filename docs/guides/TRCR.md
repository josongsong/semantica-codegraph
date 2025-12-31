# TRCR (Taint Rule Compiler & Runtime) 가이드

**CodeGraph의 보안 취약점 탐지 엔진**

---

## 목차
- [빠른 시작](#빠른-시작)
- [현재 상태](#현재-상태)
- [주요 기능](#주요-기능)
- [API 사용법](#api-사용법)
- [검출 규칙](#검출-규칙)

---

## 빠른 시작

### 5분 안에 실행하기

```bash
# 1. Rust 엔진 빌드
cd packages/codegraph-ir
maturin develop --features python --release

# 2. 데모 실행
cd ../..
.venv/bin/python scripts/test_l14_trcr_demo.py
```

**예상 출력:**
```
🔥 L14 TRCR Integration Demo - SQL Injection Detection
[L14 TRCR] Starting taint analysis with TRCR (304 rules + 49 CWE)...
[TRCR] Compiled 304 rules from atoms/ in 73.73ms
[TRCR] Executed 304 rules: 3 matches in 0.27ms ✅
```

---

## 현재 상태

### 통합된 룰 소스
| 소스 | 룰 개수 | CWE 커버리지 | 상태 |
|------|---------|-------------|------|
| TRCR 코어 | 253 | 24 CWEs | ✅ 완료 |
| CodeQL (GitHub) | 51 | +25 CWEs | ✅ 완료 |
| **합계** | **304** | **49 CWEs** | ✅ 프로덕션 |

### 성능 메트릭
- 컴파일 속도: 4,123 rules/sec
- 컴파일 시간: 73.73ms (304 rules)
- 검증 성공률: 100%

---

## 주요 기능

### 검출 가능한 취약점

#### Critical (43개 룰)
- **SQL Injection** (CWE-089)
- **Command Injection** (CWE-078)
- **Code Injection** (CWE-094)
- **XSS** (CWE-079)
- **XXE** (CWE-611)
- **SSRF** (CWE-918)
- **Path Traversal** (CWE-022)
- **Template Injection** (CWE-074)
- **Deserialization** (CWE-502)
- **Crypto Failures** (CWE-327): 4 rules

#### High (6개 룰)
- **ReDoS** (CWE-730): 3 rules
- **Certificate Validation** (CWE-295): 2 rules
- **Log Injection** (CWE-117)

### Source 패턴 (145개)
```python
# 사용자 입력 진입점
input()                  # 표준 입력
sys.argv                 # 커맨드라인 인자
request.GET/POST         # HTTP 요청
os.environ               # 환경 변수
```

### Sink 패턴 (298+51 CodeQL)
```python
# 위험한 함수
sqlite3.Cursor.execute()   # SQL injection
subprocess.Popen()         # Command injection
eval()                     # Code injection
open()                     # Path traversal
```

### Sanitizer 패턴 (45개)
```python
# 정화 함수
html.escape()           # XSS 방지
urllib.parse.quote()    # URL encoding
re.escape()             # Regex escaping
```

---

## API 사용법

### 기본 사용

```python
import codegraph_ir

# 취약한 코드 작성
test_code = '''
import sqlite3

def vulnerable(user_input):
    conn = sqlite3.connect(':memory:')
    cursor = conn.cursor()
    query = f"SELECT * FROM users WHERE id={user_input}"
    cursor.execute(query)  # 🔥 SQL Injection!
    return cursor.fetchall()
'''

# 파일 저장
with open('/tmp/test.py', 'w') as f:
    f.write(test_code)

# TRCR로 분석
result = codegraph_ir.run_ir_indexing_pipeline(
    repo_root='/tmp',
    repo_name='test',
    file_paths=['/tmp/test.py'],
    enable_taint=True,
    use_trcr=True,  # 🔥 TRCR 활성화
)

# 결과 확인
print(result['taint_results'])
```

### 고급 사용 (타입 정보 포함)

```python
result = codegraph_ir.run_ir_indexing_pipeline(
    repo_root='/path/to/repo',
    repo_name='my-project',
    enable_taint=True,
    use_trcr=True,
    enable_types=True,       # L6 타입 추론
    enable_points_to=True,   # 별칭 분석
    enable_cross_file=True,  # import 해석
)
```

---

## 검출 규칙

### OWASP Top 10 커버리지 (8/10)

| OWASP | CWE | 규칙 개수 | 상태 |
|-------|-----|---------|------|
| A01:2021 - Broken Access Control | CWE-22, 639 | 5 | ✅ |
| A02:2021 - Cryptographic Failures | CWE-327, 780 | 4 | ✅ |
| A03:2021 - Injection | CWE-89, 78, 79 | 28 | ✅ |
| A04:2021 - Insecure Design | CWE-798 | 2 | ✅ |
| A05:2021 - Security Misconfiguration | CWE-295 | 3 | ✅ |
| A06:2021 - Vulnerable Components | - | - | ⏳ |
| A07:2021 - Authentication Failures | CWE-798 | 2 | ✅ |
| A08:2021 - Data Integrity Failures | CWE-502 | 1 | ✅ |
| A09:2021 - Security Logging Failures | CWE-117 | 1 | ✅ |
| A10:2021 - SSRF | CWE-918 | 2 | ✅ |

### CodeQL 통합 규칙 (51개)

**신규 추가 CWE:**
- CWE-020: Improper Input Validation
- CWE-113: HTTP Response Splitting
- CWE-178: Improper Case Sensitivity
- CWE-326: Inadequate Encryption Strength
- CWE-601: Open Redirect
- +20 more

---

## 성능

| 코드 크기 | TRCR 시간 | Native 시간 |
|----------|-----------|-------------|
| 100 LOC | 150ms | 0.5ms |
| 1K LOC | 500ms | 2ms |
| 10K LOC | 2s | 10ms |
| 100K LOC | 15s | 80ms |

**권장 사용:**
- 소규모 프로젝트 (<10K LOC): TRCR (포괄적)
- 대규모 프로젝트 (>10K LOC): Native (빠름)

---

## 확장 가능성

### 추가 통합 가능 소스

| 소스 | 제공사 | 예상 룰 개수 | 상태 |
|------|--------|-------------|------|
| **Meta Pysa** | Meta | ~200 | 🚧 계획중 |
| **Semgrep** | Semgrep Inc. | ~100 | 🚧 계획중 |

**최종 목표:**
- 총 룰: 600+
- CWE 커버리지: 60+
- OWASP Top 10: 10/10 ✅

---

## 트러블슈팅

### "No module named 'codegraph_ir'"
```bash
cd packages/codegraph-ir
maturin develop --features python --release
```

### "Found 0 matches"
- ✅ `use_trcr=True` 설정 확인
- ✅ 로그에서 `[L14 TRCR]` 확인
- ✅ import 문 확인 (`import sqlite3`)

### "Sources found but no sinks"
- ✅ `enable_types=True` 추가 (타입 정보 필요)
- ✅ 타입 힌트 추가 권장

---

## 참고 자료

- **Rust 구현**: `packages/codegraph-ir/src/features/taint_analysis/`
- **룰 정의**: `packages/codegraph-trcr/rules/atoms/`
- **CWE Catalog**: `packages/codegraph-trcr/catalog/cwe/`
- **데모 스크립트**: `scripts/test_l14_trcr_demo.py`

---

**마지막 업데이트**: 2025-12-29
**상태**: ✅ 프로덕션 준비 완료
**총 룰 개수**: 304 rules (49 CWEs)
