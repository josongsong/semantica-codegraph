# Temporary Documents Directory

**목적**: 작업 중인 임시 문서 보관

---

## 디렉토리 구조

```
_temp/
├── drafts/        작업 중 초안
├── experiments/   실험적 분석 결과
└── notes/         일시적 메모
```

---

## 사용 규칙

### 파일 명명 규칙

**Drafts** (작업 중 문서):
```
DRAFT_FEATURE_NAME.md
DRAFT_RFC_XXX.md
WIP_ANALYSIS.md
```

**Experiments** (실험 결과):
```
EXPERIMENT_BENCHMARK_20251229.md
TEST_PERFORMANCE_ANALYSIS.md
TEMP_VERIFICATION_RESULTS.md
```

**Notes** (일시적 메모):
```
NOTES_MEETING_20251229.md
TODO_IMPLEMENTATION.md
SCRATCH_IDEAS.md
```

### 작업 흐름

1. **작성 시작**:
   ```bash
   # 임시 문서 생성
   echo "# Draft" > docs/_temp/drafts/DRAFT_MY_FEATURE.md
   ```

2. **작업 중**:
   - `_temp/` 내에서 자유롭게 수정
   - 버전 관리 불필요 (git에 커밋 안 함)

3. **완료 시**:
   ```bash
   # 검증 완료 후 최종 위치로 이동
   mv docs/_temp/drafts/DRAFT_MY_FEATURE.md \
      docs/MY_FEATURE.md

   # git에 추가
   git add docs/MY_FEATURE.md
   ```

4. **정리**:
   ```bash
   # 사용 완료한 임시 파일 삭제
   rm docs/_temp/drafts/DRAFT_MY_FEATURE.md
   ```

---

## 정리 주기

**일일**:
- 완료된 임시 파일 삭제
- 불필요한 실험 결과 제거

**주간**:
- `_temp/` 전체 검토
- 1주일 이상 방치된 파일 정리

**월간**:
- 전체 정리 (모든 파일 검토)

---

## 금지 사항

❌ **절대 하지 말 것**:
- `_temp/` 파일을 git에 커밋
- 검증 안 된 문서를 `docs/` 루트로 이동
- 임시 파일을 영구 문서로 사용
- `_temp/` 밖에 임시 파일 생성 (`docs/TEMP_*.md`)

✅ **올바른 사용**:
- 작업 중에만 `_temp/` 사용
- 완료 후 즉시 최종 위치로 이동
- 불필요한 파일 즉시 삭제

---

## .gitignore

이 디렉토리는 git에 추적되지 않습니다:

```gitignore
# .gitignore
docs/_temp/*
!docs/_temp/README.md
```

---

**마지막 업데이트**: 2025-12-29
