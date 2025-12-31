# 레거시 제거 계획

## ⚠️ 의존성 확인

TaintAnalysisService가 사용 중:
- matching/ (TypeAwareAtomMatcher)
- repositories/ (YAMLAtomRepository)
- compilation/ (PolicyCompiler)
- validation/ (ConstraintValidator)

사용처: 20곳 (application, cwe, tests)

## 📋 안전한 제거 순서

### Step 1: TaintAnalysisService를 trcr 기반으로 재작성
새 클래스: TaintAnalysisServiceV2 (trcr 기반)
기존: TaintAnalysisService (레거시, 유지)

### Step 2: 점진적 전환
cwe/ 테스트부터 V2 사용
통과 확인

### Step 3: 전체 전환
모든 사용처 V2로 변경

### Step 4: 레거시 삭제
V1 제거
matching/, compilation/, repositories/ 삭제

예상: 2-3일 작업

## 🎯 결정

Option A: 점진적 전환 (안전, 2-3일)
Option B: 일괄 전환 (빠름, 위험, 1일)

권장: A
