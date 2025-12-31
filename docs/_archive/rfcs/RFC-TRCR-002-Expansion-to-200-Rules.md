# RFC-TRCR-002: TRCR 200 Rule Categories 확장 계획

## 📊 현황 분석

### 현재 상태 (78 카테고리)
- **Sources**: 6개
- **Sinks**: 44개
- **Sanitizers**: 22개
- **Propagators**: 6개
- **CWE 커버리지**: 24개
- **OWASP 커버리지**: 8/10

### 목표 (200 카테고리)
- **Total**: 200개 (+122개)
- **CWE 커버리지**: 50개 (+26개)
- **OWASP 커버리지**: 10/10 (완전 커버)
- **프레임워크**: Django, Flask, FastAPI 심화 커버

---

## 🎯 확장 전략 (3 Phase)

### **Phase 1: 핵심 CWE 확장 (+50개 카테고리)**

우선순위 높은 CWE 추가:

#### 1.1 Information Disclosure (10개)
```yaml
# CWE-200, CWE-209, CWE-532
- sink.info_leak.stack_trace          # 스택 트레이스 노출
- sink.info_leak.debug_info           # 디버그 정보 노출
- sink.info_leak.error_message        # 상세 에러 메시지
- sink.info_leak.sql_error            # SQL 에러 노출
- sink.info_leak.path_disclosure      # 경로 노출
- sink.info_leak.session_info         # 세션 정보 노출
- sink.info_leak.config_exposure      # 설정 파일 노출
- sink.info_leak.source_code          # 소스 코드 노출
- sink.info_leak.user_enumeration     # 사용자 열거
- sink.info_leak.timing_attack        # 타이밍 공격
```

#### 1.2 Resource Management (10개)
```yaml
# CWE-404, CWE-772, CWE-400
- sink.resource.file_descriptor_leak  # FD 누수
- sink.resource.memory_leak           # 메모리 누수
- sink.resource.connection_leak       # DB 커넥션 누수
- sink.resource.dos_regex             # ReDoS
- sink.resource.dos_zip               # Zip Bomb
- sink.resource.dos_xml               # XML Bomb
- sink.resource.unbounded_allocation  # 무제한 메모리 할당
- sink.resource.unbounded_loop        # 무한 루프
- sink.resource.unbounded_recursion   # 무한 재귀
- sink.resource.thread_exhaustion     # 스레드 고갈
```

#### 1.3 Cryptography Extended (10개)
```yaml
# CWE-326, CWE-327, CWE-328, CWE-759
- sink.crypto.weak_key_size           # 약한 키 크기 (<2048)
- sink.crypto.ecb_mode                # ECB 모드 사용
- sink.crypto.static_iv               # 고정 IV
- sink.crypto.no_integrity_check      # 무결성 검증 없음
- sink.crypto.weak_padding            # 약한 패딩
- sink.crypto.null_cipher             # NULL 암호화
- sink.random.predictable_seed        # 예측 가능한 시드
- sink.random.timestamp_seed          # 타임스탬프 시드
- barrier.crypto.aes_gcm              # AES-GCM (안전)
- barrier.crypto.key_derivation       # PBKDF2/bcrypt
```

#### 1.4 Session & Auth Extended (10개)
```yaml
# CWE-306, CWE-307, CWE-384, CWE-613
- sink.session.fixation               # 세션 고정
- sink.session.no_timeout             # 타임아웃 없음
- sink.session.weak_token             # 약한 토큰
- sink.auth.missing_mfa               # MFA 미사용
- sink.auth.password_plaintext        # 평문 패스워드
- sink.auth.no_rate_limit             # Rate Limit 없음
- sink.auth.default_credentials       # 기본 자격증명
- sink.auth.weak_password_policy      # 약한 패스워드 정책
- barrier.session.secure_cookie       # Secure Cookie
- barrier.auth.constant_time_compare  # Constant-time 비교
```

#### 1.5 Input Validation Extended (10개)
```yaml
# CWE-20, CWE-129, CWE-190
- sink.validation.missing_length_check    # 길이 검증 없음
- sink.validation.missing_type_check      # 타입 검증 없음
- sink.validation.missing_range_check     # 범위 검증 없음
- sink.validation.missing_format_check    # 형식 검증 없음
- sink.validation.integer_overflow        # 정수 오버플로우
- sink.validation.array_index_negative    # 음수 인덱스
- sink.validation.null_pointer            # Null 포인터
- sink.validation.division_by_zero        # 0으로 나누기
- barrier.validation.length_check         # 길이 검증
- barrier.validation.whitelist            # 화이트리스트 검증
```

---

### **Phase 2: 프레임워크 특화 (+50개 카테고리)**

#### 2.1 Django Extended (20개)
```yaml
# 현재 8개 → 28개

# ORM Security
- sink.django.raw_query                   # raw SQL
- sink.django.extra_where                 # extra(where=...)
- sink.django.f_expression_injection      # F() injection
- sink.django.annotate_injection          # annotate() injection
- barrier.django.queryset_filter          # 안전한 filter()

# Template Security
- sink.django.safe_filter_misuse          # |safe 남용
- sink.django.autoescape_off              # autoescape off
- sink.django.mark_safe                   # mark_safe()
- barrier.django.escape_filter            # |escape

# Form Security
- sink.django.form_no_validation          # Form 검증 없음
- sink.django.modelform_exclude_abuse     # exclude 남용
- barrier.django.form_validation          # clean_*()

# Settings Security
- sink.django.debug_true_prod             # DEBUG=True in prod
- sink.django.secret_key_weak             # 약한 SECRET_KEY
- sink.django.allowed_hosts_wildcard      # ALLOWED_HOSTS=['*']
- sink.django.cors_allow_all              # CORS_ALLOW_ALL=True
- sink.django.session_cookie_secure_false # SESSION_COOKIE_SECURE=False

# Middleware Security
- sink.django.middleware_order            # 잘못된 미들웨어 순서
- sink.django.csrf_exempt_abuse           # @csrf_exempt 남용
- barrier.django.csrf_protection          # CSRF 보호
```

#### 2.2 Flask Extended (20개)
```yaml
# 현재 15개 → 35개

# Request Handling
- sink.flask.request_direct_access        # request.args['key'] (no .get)
- sink.flask.request_no_validation        # 검증 없는 입력
- sink.flask.redirect_open                # open redirect
- sink.flask.send_file_path_traversal     # send_file() 경로 순회
- barrier.flask.request_validation        # 안전한 검증

# Session Security
- sink.flask.session_no_secret            # SECRET_KEY 없음
- sink.flask.session_client_side          # 클라이언트 세션 데이터
- sink.flask.permanent_session_misuse     # permanent_session 남용
- barrier.flask.session_server_side       # 서버 사이드 세션

# Template Security
- sink.flask.jinja_autoescape_false       # autoescape=False
- sink.flask.render_string_injection      # render_template_string
- barrier.flask.jinja_autoescape_on       # autoescape=True

# Configuration
- sink.flask.debug_true_prod              # app.debug=True
- sink.flask.testing_true_prod            # app.testing=True
- sink.flask.propagate_exceptions         # app.config['PROPAGATE_EXCEPTIONS']=True

# CORS & Headers
- sink.flask.cors_wildcard                # CORS(origins='*')
- sink.flask.missing_security_headers     # 보안 헤더 없음
- barrier.flask.security_headers          # Talisman, CSP

# Error Handling
- sink.flask.error_handler_info_leak      # 에러 핸들러 정보 노출
- sink.flask.abort_without_handler        # abort() without handler
```

#### 2.3 FastAPI Extended (10개)
```yaml
# 현재 3개 → 13개

# Input Validation
- sink.fastapi.pydantic_bypass            # Pydantic 검증 우회
- sink.fastapi.query_injection            # Query 파라미터 인젝션
- sink.fastapi.path_injection             # Path 파라미터 인젝션
- barrier.fastapi.pydantic_validation     # Pydantic 검증

# Dependency Injection
- sink.fastapi.dependency_injection_abuse # DI 남용
- sink.fastapi.global_dependency_leak     # 전역 의존성 누수

# Security
- sink.fastapi.cors_allow_all             # allow_origins=['*']
- sink.fastapi.oauth2_insecure            # 약한 OAuth2
- barrier.fastapi.oauth2_pkce             # PKCE 사용

# Response
- sink.fastapi.response_model_bypass      # response_model 우회
```

---

### **Phase 3: Advanced Patterns (+22개 카테고리)**

#### 3.1 OWASP A04: Insecure Design (10개)
```yaml
- sink.design.missing_access_control      # 접근 제어 없음
- sink.design.idor                        # IDOR
- sink.design.business_logic_bypass       # 비즈니스 로직 우회
- sink.design.race_condition              # 경쟁 조건
- sink.design.toctou                      # TOCTOU
- sink.design.missing_rate_limit          # Rate Limit 없음
- sink.design.mass_assignment             # Mass Assignment
- sink.design.privilege_escalation        # 권한 상승
- barrier.design.access_control_decorator # @require_permission
- barrier.design.rate_limiter             # Rate Limiter
```

#### 3.2 OWASP A06: Vulnerable Components (5개)
```yaml
- sink.dependency.outdated_package        # 오래된 패키지
- sink.dependency.known_vulnerability     # 알려진 취약점
- sink.dependency.dev_dependency_prod     # 개발 의존성 프로덕션
- sink.dependency.untrusted_source        # 신뢰할 수 없는 소스
- barrier.dependency.version_pinning      # 버전 고정
```

#### 3.3 Advanced Propagators (7개)
```yaml
- prop.string.fstring                     # f-string
- prop.set                                # set operations
- prop.comprehension                      # list/dict comprehension
- prop.async.await                        # async/await
- prop.context_manager                    # with statement
- prop.decorator                          # decorator
- prop.metaclass                          # metaclass
```

---

## 📋 구현 계획

### Step 1: atoms.yaml 구조화 (1일)
```yaml
# 파일 분리
packages/codegraph-trcr/rules/atoms/
├── python.atoms.yaml           # 기존 (78개)
├── python-info-leak.yaml       # Information Disclosure (10개)
├── python-resource.yaml        # Resource Management (10개)
├── python-crypto-ext.yaml      # Crypto Extended (10개)
├── python-session-auth.yaml    # Session & Auth (10개)
├── python-validation.yaml      # Input Validation (10개)
├── python-django-ext.yaml      # Django Extended (20개)
├── python-flask-ext.yaml       # Flask Extended (20개)
├── python-fastapi-ext.yaml     # FastAPI Extended (10개)
├── python-design.yaml          # Insecure Design (10개)
├── python-dependency.yaml      # Vulnerable Components (5개)
└── python-propagators-ext.yaml # Advanced Propagators (7개)
```

### Step 2: 우선순위별 작성 (2주)

**Week 1: 핵심 보안 룰 (50개)**
- Day 1-2: Information Disclosure (10개)
- Day 3-4: Resource Management (10개)
- Day 5-6: Crypto Extended (10개)
- Day 7-8: Session & Auth (10개)
- Day 9-10: Input Validation (10개)

**Week 2: 프레임워크 특화 (50개)**
- Day 1-4: Django Extended (20개)
- Day 5-8: Flask Extended (20개)
- Day 9-10: FastAPI Extended (10개)

**Week 3: Advanced (22개)**
- Day 1-2: Insecure Design (10개)
- Day 3: Vulnerable Components (5개)
- Day 4-5: Advanced Propagators (7개)

### Step 3: 테스트 확장 (3일)
```python
# scripts/test_all_trcr_rules.py 확장
- 현재: 37개 테스트 케이스
- 목표: 200개 테스트 케이스 (각 카테고리당 1개)
```

### Step 4: 벤치마크 & 최적화 (2일)
- 200 카테고리 성능 테스트
- 컴파일 시간 최적화
- 실행 시간 최적화 (목표: <1ms per entity)

---

## 🎯 예상 결과

### 최종 스펙
```
Rule Categories: 200개 (현재 78개 → +122개)
Match Patterns: ~1200개 (현재 488개 → +712개)
Compiled Rules: ~600개 (현재 253개 → +347개)
CWE Coverage: 50개 (현재 24개 → +26개)
OWASP Coverage: 10/10 (현재 8/10 → +2개)
```

### SOTA 비교
| 도구 | Categories | Patterns | CWE | OWASP |
|------|-----------|----------|-----|-------|
| Semgrep | 400 | 2000+ | 40 | 9/10 |
| CodeQL | 300 | 1500+ | 50 | 10/10 |
| **TRCR** | **200** | **1200** | **50** | **10/10** |
| Bandit | 50 | 150 | 20 | 6/10 |

**→ Semgrep/CodeQL 수준 도달!** 🏆

---

## 💡 구현 전략

### 자동화 도구

#### 1. Rule Generator
```python
# scripts/generate_rule.py
"""
YAML 템플릿에서 룰 자동 생성

Usage:
  python scripts/generate_rule.py \
    --category sink \
    --name info_leak.stack_trace \
    --cwe CWE-209 \
    --patterns "traceback.format_exc,sys.exc_info"
"""
```

#### 2. Test Generator
```python
# scripts/generate_test.py
"""
룰에서 테스트 케이스 자동 생성

Usage:
  python scripts/generate_test.py \
    --rules packages/codegraph-trcr/rules/atoms/*.yaml
"""
```

#### 3. Validation Tool
```python
# scripts/validate_rules.py
"""
룰 정합성 검증:
- YAML 문법 체크
- CWE/OWASP 매핑 검증
- 중복 패턴 검출
- 성능 프로파일링
"""
```

---

## 📊 성공 지표

### Phase 1 완료 (50개 추가)
- ✅ 128 카테고리 달성
- ✅ CWE 40개 커버
- ✅ 컴파일 시간 < 100ms
- ✅ 테스트 100% 통과

### Phase 2 완료 (50개 추가)
- ✅ 178 카테고리 달성
- ✅ Django/Flask/FastAPI 심화 커버
- ✅ 프레임워크별 벤치마크

### Phase 3 완료 (22개 추가)
- ✅ 200 카테고리 달성
- ✅ OWASP 10/10 완전 커버
- ✅ CWE 50개 커버
- ✅ **SOTA Tier 1 달성** 🏆

---

## 🚀 시작 방법

### Immediate Next Steps

1. **파일 구조 생성** (30분)
   ```bash
   mkdir -p packages/codegraph-trcr/rules/atoms/extended
   touch packages/codegraph-trcr/rules/atoms/extended/python-{info-leak,resource,crypto-ext,session-auth,validation,django-ext,flask-ext,fastapi-ext,design,dependency,propagators-ext}.yaml
   ```

2. **첫 10개 룰 작성** (2시간)
   - `python-info-leak.yaml` 작성
   - 테스트 케이스 10개 추가
   - 컴파일 & 검증

3. **자동화 도구 개발** (1일)
   - Rule Generator
   - Test Generator
   - Validation Tool

### 예상 소요 시간
- **Total**: 3주
- **Phase 1**: 10일
- **Phase 2**: 8일
- **Phase 3**: 5일

---

## ❓ Questions & Decisions

1. **파일 분리 vs 단일 파일?**
   - ✅ **추천**: 파일 분리 (유지보수성)
   - 단일 파일은 2000줄 넘으면 관리 어려움

2. **자동 생성 vs 수동 작성?**
   - ✅ **추천**: 템플릿 + 자동 생성 (일관성)
   - 핵심 룰은 수동 검토

3. **테스트 커버리지 목표?**
   - ✅ **추천**: 100% (각 카테고리당 1개 이상)

---

## 📚 참고 자료

- [OWASP Top 10 2021](https://owasp.org/Top10/)
- [CWE Top 25](https://cwe.mitre.org/top25/)
- [Semgrep Rules](https://semgrep.dev/r)
- [CodeQL Queries](https://github.com/github/codeql)
- [Bandit Rules](https://bandit.readthedocs.io/en/latest/plugins/)

---

**Status**: 📝 Draft - Ready for Implementation
**Owner**: @codegraph-team
**Timeline**: 3 weeks
**Priority**: High (SOTA Tier 1 달성)
