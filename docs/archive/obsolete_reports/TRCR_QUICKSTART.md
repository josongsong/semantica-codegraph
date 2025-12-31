# TRCR 퀵스타트 가이드 🚀

**CodeGraph TRCR** (Taint Rule Compiler & Runtime)를 사용한 보안 분석 시작 가이드입니다.

---

## 📊 현재 상태 (2025-12-29)

### 통합된 룰 소스
| 소스 | 룰 개수 | CWE 커버리지 | 품질 | 상태 |
|------|---------|-------------|------|------|
| **TRCR 코어** | 253 | 24 CWEs | ⭐⭐⭐⭐ | ✅ 완료 |
| **CodeQL** | 51 | +25 CWEs | ⭐⭐⭐⭐⭐ | ✅ 완료 |
| **합계** | **304** | **49 CWEs** | ⭐⭐⭐⭐⭐ | ✅ 프로덕션 |

### 성능 메트릭
- 컴파일 속도: **4,123 rules/sec**
- 컴파일 시간: 73.73ms (304 rules)
- 검증 성공률: **100%**

---

## 🚀 5분 안에 TRCR 실행하기

### 1. 빌드 (1분)

```bash
cd packages/codegraph-ir
maturin develop --features python --release
```

### 2. 데모 실행 (30초)

```bash
cd ../..
.venv/bin/python scripts/test_l14_trcr_demo.py
```

**기대 출력:**
```
🔥 L14 TRCR Integration Demo - SQL Injection Detection
======================================================================

[L14 TRCR] Starting taint analysis with TRCR (304 rules + 49 CWE)...
[TRCR] Compiled 304 rules from atoms/ in 73.73ms
[TRCR] Executed 304 rules: 3 matches in 0.27ms ✅
```

### 3. 직접 사용하기 (3분)

```python
import codegraph_ir

# SQL injection 취약점이 있는 코드 작성
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
# 출력: TRCR이 감지한 taint flows
```

## 📊 무엇이 감지되나요?

TRCR은 **304 compiled rules**과 **49 CWE rules**로 다음을 감지합니다:

### 🎯 주요 카테고리 (CodeQL 통합)

#### 🔴 Critical (43개 룰)
- **SQL Injection** (CWE-089): 1 rule
- **Command Injection** (CWE-078): 2 rules
- **Code Injection** (CWE-094): 1 rule
- **XSS** (CWE-079): 2 rules
- **XXE** (CWE-611): 1 rule
- **SSRF** (CWE-918): 2 rules
- **Path Traversal** (CWE-022): 2 rules
- **Template Injection** (CWE-074): 1 rule
- **Deserialization** (CWE-502): 1 rule
- **Crypto Failures** (CWE-327): 4 rules
- 기타 26개 critical 룰

#### 🟡 High (6개 룰)
- **ReDoS** (CWE-730): 3 rules
- **Certificate Validation** (CWE-295): 2 rules
- **Log Injection** (CWE-117): 1 rule

### Sources (사용자 입력)
- `input()` - 표준 입력
- `sys.argv` - 커맨드라인 인자
- `request.GET/POST` - HTTP 요청
- `os.environ` - 환경 변수
- 기타 145개 source 패턴

### Sinks (위험한 함수)
- `sqlite3.Cursor.execute()` - SQL injection
- `subprocess.Popen()` - Command injection
- `eval()` - Code injection
- `open()` - Path traversal
- **CodeQL 추가**: 51개 sink 패턴
- 기타 298개 sink 패턴

### Sanitizers (정화 함수)
- `html.escape()` - XSS 방지
- `urllib.parse.quote()` - URL encoding
- `re.escape()` - Regex escaping
- 기타 45개 sanitizer 패턴

## 🔧 설정 옵션

### 기본 사용
```python
result = codegraph_ir.run_ir_indexing_pipeline(
    repo_root='/path/to/repo',
    repo_name='my-project',
    enable_taint=True,
    use_trcr=True,
)
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

## 📈 성능

| 코드 크기 | TRCR 시간 | Native 시간 |
|----------|-----------|-------------|
| 100 LOC | 150ms | 0.5ms |
| 1K LOC | 500ms | 2ms |
| 10K LOC | 2s | 10ms |
| 100K LOC | 15s | 80ms |

**결론**:
- 소규모 프로젝트: TRCR 사용 권장 (포괄적)
- 대규모 프로젝트: Native 사용 고려 (빠름)

## 🐛 문제 해결

### "No module named 'codegraph_ir'"
```bash
cd packages/codegraph-ir
maturin develop --features python --release
```

### "Failed to import TRCR"
```bash
# TRCR 패키지 설치 확인
pip install -e packages/codegraph-trcr
```

### "Found 0 matches"
- ✅ L1 IR 빌드 확인
- ✅ `use_trcr=True` 설정 확인
- ✅ 로그에서 `[L14 TRCR]` 확인

### "Sources found but no sinks"
- ⚠️ 타입 정보 부족
- ✅ `enable_types=True` 추가
- ✅ import 문 확인 (`import sqlite3`)

## 📚 더 알아보기

### 문서
- **[CodeQL 통합 완료](./CODEQL_INTEGRATION_COMPLETE.md)** ⭐ 신규
- [전체 통합 가이드](./TRCR_INTEGRATION_COMPLETE.md)
- [종합 테스트 결과](./TRCR_COMPREHENSIVE_TEST_RESULTS.md)
- [CWE Catalog](../packages/codegraph-trcr/catalog/cwe/)
- [Python Atoms](../packages/codegraph-trcr/rules/atoms/python.atoms.yaml)

### 도구
- `scripts/crawl_codeql.py` - CodeQL 룰 크롤러
- `scripts/generate_rule.py` - 단일 룰 생성기
- `scripts/generate_from_csv.py` - CSV 배치 생성기
- `scripts/validate_rules.py` - 룰 검증기

## 💡 팁

1. **첫 실행은 느립니다** (304 rules 컴파일, ~73ms)
2. **두 번째부터는 빠릅니다** (캐시 사용)
3. **타입 힌트 추가하면** sink detection 향상
4. **import 명시하면** 정확도 향상
5. **CodeQL 룰 활용** - GitHub 검증된 고품질 룰 49개

## 📈 로드맵

### ✅ 완료
- Phase 1: TRCR 코어 통합 (253 rules, 24 CWEs)
- Phase 2: PyO3 바인딩 (Rust ↔ Python)
- **Phase 3: CodeQL 통합 (51 rules, +25 CWEs)** ⭐ 신규

### 🚧 진행중
- Phase 4: Meta Pysa 통합 (50+ taint rules)
- Phase 5: Semgrep 통합 (high-quality subset)

### 🎯 계획
- Phase 6: 200 rule categories (SOTA Tier 1)
- Phase 7: Multi-language support

---

**마지막 업데이트**: 2025-12-29
**상태**: ✅ 프로덕션 준비 완료
**총 룰 개수**: 304 rules (49 CWEs)
**품질**: ⭐⭐⭐⭐⭐ (GitHub CodeQL 통합)
