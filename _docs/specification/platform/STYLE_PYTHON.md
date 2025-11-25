# Python Style Specification

본 문서는 Python 코드 스타일에 대한 MUST 수준 규칙을 정의한다.

---

## 목적

- Python 코드 전역의 일관성 유지
- 리뷰 비용 절감
- 가독성·안정성·예측 가능성 확보

---

## MUST 규칙

1. 함수명/변수명은 snake_case
2. 클래스명은 PascalCase
3. 파일명은 snake_case
4. import 순서는 다음 우선순위
   - 표준 라이브러리
   - 외부 패키지
   - 내부 모듈
5. typing.Optional 대신 `| None` 사용
6. 모든 함수에 타입 힌트를 명시해야 한다
7. 로깅은 print 금지, 반드시 structured logging
8. TODO/NOTE 주석에는 날짜와 작성자 식별자를 포함

---

## 금지 규칙

1. from module import *
2. 전역 변수 사용
3. 동적 attribute 추가
4. 파일 내부에 여러 클래스 정의
5. 한 파일에 1,000라인 이상 코드 작성

---

## 문서 간 경계

- Formatting/Lint 규칙은 LINT_FORMAT_SPEC.md
- TypeScript 스타일은 STYLE_TS.md
