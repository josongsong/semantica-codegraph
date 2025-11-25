# Lint & Format Specification

본 문서는 Semantica 레포 전역의 Lint/Type/Format 규칙을 정의한다.

---

## 목적

- 코드 스타일을 자동으로 통일
- 리뷰 과정에서 스타일 논쟁 제거
- 정적 분석 강화로 품질 유지

---

## MUST 규칙

### Python
1. lint는 **ruff**
2. type-check는 **mypy(strict)**
3. formatter는 **ruff format**

### TypeScript
1. lint는 **biome**
2. formatter는 **biome format**
3. TS는 반드시 strict mode 사용

### 공통
1. Import 순서 자동 정렬 필수
2. 사용되지 않는 변수/함수 금지
3. 전역 disable 주석 금지
4. formatting 실패 시 CI 실패

---

## 금지 규칙

1. Black + ruff 병행 사용
2. eslint/prettier (Semantica에서는 biome로 통일)
3. mypy ignore 남용
4. lint 규칙을 파일 내부에서 과도하게 override

---

## 문서 간 경계

- Python 스타일 상세는 STYLE_PYTHON.md
- TS 스타일 상세는 STYLE_TS.md
