# Observability Specification

본 문서는 metrics/tracing/logs 전체를 포함한 관측 가능성 규칙을 정의한다.

---

## 목적

- 시스템 상태를 실시간으로 추적  
- 성능 문제 분석  
- 검색/인덱싱/그래프 쿼리 흐름을 완전하게 추적

---

## MUST 규칙

1. Observability는 **logs + metrics + tracing** 3요소 모두 포함해야 한다.  
2. tracing span에는 아래 필드를 포함해야 한다.  
   - trace_id  
   - repo_id  
   - operation  
   - duration_ms  
3. metrics는 최소 아래 항목을 수집해야 한다.  
   - 요청 수  
   - 실패 수  
   - 평균/최대 latency  
   - 인덱싱 처리량  
4. 로그 구조는 LOGGING_SPEC.md 를 따라야 한다.  
5. fallback 발생 시 tracing span에 `fallback_level` 포함해야 한다.  
6. scenario 테스트는 tracing 기반으로 흐름 일관성을 검증해야 한다.

---

## 금지 규칙

1. 로그 없이 메트릭만 수집  
2. 메트릭 구조를 엔드포인트마다 다르게 정의  
3. trace_id 없이 호출 체인 생성  
4. fallback 사용을 기록하지 않는 패턴

---

## 문서 간 경계

- 로깅 상세 규칙은 LOGGING_SPEC.md  
- 프로파일링 스키마는 codegraph/PROFILING_SPEC.md 참고
