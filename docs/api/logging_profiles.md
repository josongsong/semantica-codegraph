# SOTA급 로그 프로필 시스템

## 환경 변수 설정

### 방법 1: 명시적 프로필

```bash
# 개발
export LOG_PROFILE=dev

# 운영
export LOG_PROFILE=prod

# 벤치마크
export LOG_PROFILE=bench

# 디버깅
export LOG_PROFILE=debug

# 테스트
export LOG_PROFILE=test
```

### 방법 2: 환경 기반 자동 선택

```bash
# 개발 (DEV 프로필)
export ENV=dev

# 운영 (PROD 프로필)
export ENV=production

# 벤치마크 (BENCH 프로필)
export ENV=bench
```

## 프로필별 특성

### DEV (개발)
- **레벨**: INFO
- **Hot path**: 1% 샘플링
- **배치**: 활성화 (샘플 3개)
- **포맷**: 읽기 쉬운 텍스트
- **용도**: 일상 개발

### PROD (운영)
- **레벨**: INFO
- **Hot path**: 비활성화 (성능)
- **배치**: 활성화 (샘플 없음, count만)
- **포맷**: JSON (분석용)
- **비동기**: 활성화
- **용도**: 프로덕션 배포

### BENCH (벤치마크)
- **레벨**: WARNING
- **Hot path**: 비활성화
- **배치**: 비활성화
- **최소 오버헤드**
- **용도**: 성능 측정

### DEBUG (디버깅)
- **레벨**: DEBUG
- **Hot path**: 10% 샘플링
- **배치**: 활성화 (샘플 10개)
- **동기 로깅** (추적 용이)
- **용도**: 문제 분석

### TEST (테스트)
- **레벨**: ERROR
- **모든 로깅 최소화**
- **용도**: 단위 테스트

## 사용 예시

### 자동 설정 (추천)

```python
from src.common.observability import get_logger
from src.common.logging_config import BatchLogger

logger = get_logger(__name__)

# 배치 로깅 (프로필 자동 적용)
with BatchLogger(logger, "processing") as batch:
    for item in items:
        process(item)
        batch.record(item_id=item.id)

# 출력 (DEV):
# [info] processing_complete count=1000 duration_ms=5.2 samples=[...]

# 출력 (PROD):
# {"event": "processing_complete", "count": 1000, "duration_ms": 5.2}

# 출력 (BENCH):
# (없음)
```

### 수동 설정

```python
from src.common.log_profiles import init_logging, LogProfile

# 명시적 프로필
init_logging(LogProfile.PROD)

# 이후 모든 로거가 PROD 설정 사용
logger = get_logger(__name__)
```

## 성능 비교

| 프로필 | Hot Path 로깅 | 오버헤드 | 용도 |
|--------|---------------|----------|------|
| DEV | 1% 샘플링 | 1% | 개발 |
| PROD | 비활성화 | 0.1% | 운영 |
| BENCH | 비활성화 | 0.01% | 벤치마크 |
| DEBUG | 10% 샘플링 | 10% | 디버깅 |
| TEST | 비활성화 | 0.01% | 테스트 |

## 벤치마크 실행

```bash
# 벤치마크 모드 (로깅 최소화)
LOG_PROFILE=bench python benchmark/bench_indexing.py benchmark/core

# 일반 모드 (DEV)
python benchmark/bench_indexing.py benchmark/core

# 디버깅 모드 (상세 로그)
LOG_PROFILE=debug python benchmark/bench_indexing.py benchmark/core
```

