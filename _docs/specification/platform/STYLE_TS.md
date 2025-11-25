# TypeScript / React Style Specification

본 문서는 TypeScript 및 React 코드 스타일에 대한 MUST 규칙을 정의함.

---

## 목적

- TS/React 코드 전역의 일관성 확보
- strict 타입 기반 개발 문화 정착
- 팀 간 협업 시 예측 가능한 코드 스타일 유지

---

## MUST 규칙

1. 모든 TypeScript 프로젝트는 **`strict: true`** 설정을 사용해야 함.
2. React 컴포넌트 파일 확장자는 **`.tsx`** 를 사용해야 함.
3. 함수형 컴포넌트만 허용하며, 클래스형 컴포넌트는 허용하지 않음.
4. props/state에는 반드시 명시적 타입을 선언해야 함.
5. `any` 타입 사용은 금지되며, 불가피한 경우 `unknown` + narrow 패턴을 사용해야 함.
6. 비동기 로직은 `async/await` 기반으로 작성해야 하며, then/catch 체인 사용을 지양함.
7. React 훅은 `useXxx` 네이밍을 따라야 함 (`useSearch`, `useRepo` 등).
8. UI 컴포넌트와 비즈니스 로직을 분리해야 함 (컨테이너/프리젠테이션 패턴 또는 유사 구조).
9. import 순서는 다음 순서를 따라야 함.
   - 외부 라이브러리
   - 내부 공용 모듈 (예: `@/components`, `@/lib`)
   - 상대 경로 모듈

---

## 금지 규칙 (MUST NOT)

1. `any` 타입 상시 허용 (eslint/biome 설정으로 차단해야 함).
2. default export 남용 (특별한 이유가 없으면 named export 사용).
3. JSX 내부에 복잡한 로직/계산 포함 (별도 함수/훅으로 분리해야 함).
4. React 컴포넌트 파일에서 비즈니스 규칙을 직접 구현.
5. 전역 mutable 상태를 직접 사용하는 패턴 (반드시 상태 관리 계층 통해야 함).

---

## 문서 간 경계

- Lint/Format 관련 규칙은 `LINT_FORMAT_SPEC.md` 참고.
- Python 스타일은 `STYLE_PYTHON.md` 에서 별도 정의함.
