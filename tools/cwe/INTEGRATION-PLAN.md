# CWE Integration Plan

**목표**: Level 1 (CWE ID) → Level 2 (변종 패턴) → Level 3 (실서비스)

---

## Level 1: CWE ID 커버 (완료) ✅

### 달성
- 25개 CWE ID
- 기본 Source/Sink/Sanitizer
- Top25 View 커버

### 완성도
**100%** (CWE ID 수준)

---

## Level 2: 변종 패턴 커버 (6개월)

### 목표
각 CWE당 5-10개 변종 패턴

### 작업

#### Phase 1: 프레임워크별 (2개월)
```
CWE-89 (SQL):
  - SQLite3 ✅
  - PostgreSQL ✅
  - MySQL ✅
  - SQLAlchemy ORM (추가)
  - Django ORM (추가)
  - Raw SQL (추가)

CWE-78 (Command):
  - os.system ✅
  - subprocess ✅
  - shell=True (추가)
  - shell injection (추가)

CWE-79 (XSS):
  - Flask template ✅
  - Django template (추가)
  - React (추가)
  - Vue (추가)
```

#### Phase 2: 컨텍스트별 (2개월)
```
- 동기/비동기
- 일반 함수/메서드
- 클래스/인스턴스
- Generator/Coroutine
```

#### Phase 3: 언어별 (2개월)
```
- Python ✅
- TypeScript (추가)
- Java (추가)
```

### 예상 완성도
**60-70%** (변종 패턴 수준)

---

## Level 3: 실서비스 공격면 (1년)

### 목표
실제 코드베이스에서 발생 가능한 흐름 커버

### 작업

#### Inter-procedural (3개월)
```
- 함수 경계 넘는 데이터 플로우
- Call graph 기반 traverse
- Context-sensitive (k=2)
```

#### Control Flow (2개월)
```
- allowlist/denylist 인식
- early return guard
- conditional sanitizer
```

#### 프레임워크 모델링 (4개월)
```
Flask:
  - Request → Route → Handler → Response
  - Session management
  - Template rendering

Django:
  - ORM query
  - Template engine
  - Middleware

FastAPI:
  - Dependency injection
  - Pydantic validation
```

#### 비즈니스 로직 (3개월)
```
- 가격/수량 변조 패턴
- 환불/쿠폰 우회
- 권한 상승 흐름
```

### 예상 완성도
**80-90%** (실서비스 수준)

---

## 타임라인

```
현재:      Level 1 (100%)
+ 6개월:   Level 2 (60-70%)
+ 12개월:  Level 3 (80-90%)
```

---

## 우선순위

### P0 (즉시)
- Level 1 유지 ✅

### P1 (3개월)
- CWE-89 변종 5개 (SQLAlchemy, Django ORM, etc.)
- CWE-78 변종 3개
- CWE-79 변종 4개

### P2 (6개월)
- Inter-procedural
- Control flow
- 나머지 CWE 변종

### P3 (1년)
- 프레임워크 모델링
- 비즈니스 로직

---

## 측정 기준

### Level 2 체크리스트
- [ ] 각 CWE당 변종 5개 이상
- [ ] 프레임워크별 커버 (Flask/Django/FastAPI)
- [ ] Source/Sink/Sanitizer 명확
- [ ] Test suite 각 변종별 존재

### Level 3 체크리스트
- [ ] Inter-proc 기본 동작
- [ ] Control flow guard 인식
- [ ] 프레임워크 핵심 추상 모델링
- [ ] 실제 코드베이스 fixture

---

## 결론

**현재 완성도**:
- Level 1 (ID): 100%
- Level 2 (패턴): 20%
- Level 3 (실서비스): 10%
- **종합**: 40-50%

**다음 단계**: Level 2 (변종 패턴) 구현
