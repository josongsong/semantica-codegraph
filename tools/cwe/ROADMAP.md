# CWE 구현 로드맵

**현재**: 27개 CWE 구현 완료 ✅
**상태**: Level 1 (CWE ID) 100% + Level 2 진행 중

---

## 현재 구현 (27개) ✅

### Injection (10개)
- CWE-89: SQL Injection ✅
- CWE-78: Command Injection ✅
- CWE-79: XSS ✅
- CWE-94: Code Injection ✅
- CWE-95: Eval Injection ✅
- CWE-643: XPath Injection ✅
- CWE-90: LDAP Injection ✅
- CWE-611: XXE ✅ (NEW)
- CWE-943: NoSQL Injection ✅ (NEW)

### Access Control (4개)
- CWE-22: Path Traversal ✅
- CWE-639: IDOR ✅
- CWE-284: Access Control ✅
- CWE-863: Authorization ✅

### Crypto (4개)
- CWE-327: Weak Crypto ✅
- CWE-798: Hardcoded Credentials ✅
- CWE-330: Weak RNG ✅
- CWE-338: Weak PRNG ✅

### Web Security (4개)
- CWE-352: CSRF ✅
- CWE-434: File Upload ✅
- CWE-918: SSRF ✅
- CWE-20: Input Validation ✅

### Other (5개)
- CWE-502: Deserialization ✅
- CWE-200: Info Exposure ✅
- CWE-209: Error Message Leak ✅
- CWE-190: Integer Overflow ✅
- CWE-287: Authentication ✅
- CWE-732: File Permission ✅

---

## 완성도

```
Level 1 (CWE ID): 27/27 = 100% ✅
Level 2 (변종 패턴): 40% (3-5개/CWE)
Level 3 (실서비스): 15%
---
전체 커버리지: 55-60%
FP Rate: 8-12% (Guard Detector 포함)
```

---

## Level 2 진행 상황

### CWE-89 변종 (7개) ✅
- [x] SQLite3
- [x] PostgreSQL (psycopg2)
- [x] MySQL (pymysql)
- [x] SQLAlchemy
- [x] SQLAlchemy ORM
- [x] Django ORM
- [x] Peewee ORM
- [x] Raw SQL patterns

### CWE-78 변종 (6개) ✅
- [x] os.system
- [x] subprocess (shell=True)
- [x] asyncio subprocess
- [x] shell injection patterns
- [x] paramiko SSH
- [x] fabric (run/sudo/local)

### CWE-79 변종 (4개)
- [x] Flask template
- [x] Django template
- [x] Jinja2
- [x] Markup (markupsafe)
- [ ] React dangerouslySetInnerHTML (TypeScript)
- [ ] Vue v-html (TypeScript)

### CWE-611 XXE (2개) ✅ (NEW)
- [x] lxml.etree
- [x] xml.etree.ElementTree
- [x] xml.dom.minidom
- [x] xml.sax

### CWE-943 NoSQL (2개) ✅ (NEW)
- [x] MongoDB (pymongo)
- [x] Redis
- [x] Motor (async MongoDB)

---

## Guard Detector (FP 감소)

### 구현 완료 ✅
- [x] Validation patterns (validate, check, verify, etc.)
- [x] Regex guard (re.match, re.fullmatch, etc.)
- [x] Type guard (isinstance, isdigit, isnumeric, etc.)

### FP 제어 메커니즘
- `arg_type: not_const` - 63개
- `scope: guard` - 41개
- Guard Detector patterns - 20개

---

## Level 3 로드맵 (6개월)

### Inter-procedural
- [ ] 함수 경계 넘는 데이터 플로우
- [ ] Call graph 기반 traverse
- [ ] Context-sensitive (k=2)

### Control Flow
- [x] allowlist/denylist 인식
- [x] early return guard
- [ ] conditional sanitizer

### 프레임워크 모델링
- [ ] Flask 라우팅/템플릿
- [ ] Django ORM/미들웨어
- [ ] FastAPI 의존성 주입

---

## 체크리스트

| 항목 | 현재 | 목표 |
|------|------|------|
| CWE ID | 27개 (100%) | 27개 ✅ |
| 변종 패턴 | 3-5개/CWE (40%) | 5-10개/CWE |
| Inter-proc | 기본 (30%) | 고급 |
| Control flow | Guard (50%) | 완성 |
| 프레임워크 | 기본 (20%) | 모델링 |
| FP Rate | 8-12% | <10% |

---

## 결론

**Level 1 완료** ✅ (2024-12)
**Level 2 진행 중** (40% → 60% 목표)

**다음 목표**:
1. React/Vue XSS 지원 (TypeScript)
2. Inter-procedural 강화
3. FP Rate <10% 달성
