# File Watcher & Incremental Analysis Guide

**실시간 파일 변경 감지 및 증분 분석 가이드**

---

## 목차
- [개요](#개요)
- [빠른 시작](#빠른-시작)
- [설정 옵션](#설정-옵션)
- [성능 최적화](#성능-최적화)
- [트러블슈팅](#트러블슈팅)

---

## 개요

### 기능
- **실시간 파일 감지**: fswatch/watchdog 기반
- **증분 재분석**: 변경된 파일만 재분석
- **의존성 추적**: import 관계 기반 전파
- **캐시 무효화**: 자동 캐시 업데이트

### 지원 이벤트
- 파일 생성/수정/삭제
- 디렉토리 추가/제거
- 파일 이동/이름 변경

---

## 빠른 시작

### 기본 사용

```python
from codegraph_ir import IncrementalAnalyzer

# Watch 모드로 분석기 생성
analyzer = IncrementalAnalyzer(
    repo_root="/path/to/repo",
    watch_mode=True
)

# 파일 변경 감지 시작
analyzer.watch()  # 백그라운드로 실행

# 수동 재분석 (선택)
analyzer.reanalyze_changed_files()
```

### CLI 사용

```bash
# 기본 watch 모드
codegraph watch /path/to/repo

# 특정 디렉토리만 감시
codegraph watch /path/to/repo --include "src/**/*.py"

# 제외 패턴
codegraph watch /path/to/repo --exclude "tests/**"
```

---

## 설정 옵션

### Watch 설정

```python
analyzer = IncrementalAnalyzer(
    repo_root="/path/to/repo",
    watch_mode=True,
    watch_config={
        # 감시 대상 패턴
        "include": ["src/**/*.py", "lib/**/*.py"],

        # 제외 패턴
        "exclude": ["tests/**", "**/__pycache__/**"],

        # Debounce 시간 (ms)
        "debounce_ms": 500,

        # 배치 처리 크기
        "batch_size": 10,
    }
)
```

### 증분 분석 설정

```python
analyzer = IncrementalAnalyzer(
    repo_root="/path/to/repo",
    incremental_config={
        # 의존성 추적 활성화
        "track_dependencies": True,

        # 캐시 활성화
        "enable_cache": True,

        # 캐시 디렉토리
        "cache_dir": ".codegraph_cache",

        # 전파 깊이 (import chain)
        "propagation_depth": 3,
    }
)
```

---

## 성능 최적화

### 1. Debounce 설정

**문제**: 짧은 시간에 여러 파일 변경 시 중복 분석

**해결**:
```python
watch_config={
    "debounce_ms": 500,  # 500ms 동안 변경 없으면 분석
}
```

### 2. 배치 처리

**문제**: 파일 하나씩 분석 시 오버헤드

**해결**:
```python
watch_config={
    "batch_size": 10,  # 최대 10개 파일 모아서 한 번에 분석
    "batch_timeout_ms": 1000,  # 1초 내 모인 파일 전부 처리
}
```

### 3. 선택적 전파

**문제**: 모든 의존 파일 재분석 시 느림

**해결**:
```python
incremental_config={
    "propagation_depth": 2,  # import 2단계까지만 전파
    "smart_propagation": True,  # AST 변경 없으면 스킵
}
```

### 4. 캐시 최적화

```python
incremental_config={
    "enable_cache": True,
    "cache_strategy": "adaptive",  # LRU + hit rate 기반
    "max_cache_size_mb": 500,
}
```

---

## 고급 사용법

### 이벤트 핸들러 등록

```python
def on_file_changed(event):
    print(f"File changed: {event.path}")
    print(f"Type: {event.event_type}")  # created/modified/deleted

analyzer = IncrementalAnalyzer(repo_root="/path/to/repo")
analyzer.on("file_changed", on_file_changed)
analyzer.watch()
```

### 수동 재분석

```python
# 특정 파일만 재분석
analyzer.reanalyze_files(["src/main.py", "src/utils.py"])

# 전체 재분석 (캐시 유지)
analyzer.reanalyze_all()

# 캐시 무효화 후 전체 재분석
analyzer.invalidate_cache()
analyzer.reanalyze_all()
```

### 의존성 그래프 확인

```python
# 파일의 의존성 확인
deps = analyzer.get_dependencies("src/main.py")
print(f"Direct imports: {deps.direct}")
print(f"Transitive imports: {deps.transitive}")

# 역방향 의존성 (누가 이 파일을 import하나?)
reverse_deps = analyzer.get_reverse_dependencies("src/utils.py")
print(f"Imported by: {reverse_deps}")
```

---

## 성능 벤치마크

### 변경 파일 수에 따른 재분석 시간

| 변경 파일 수 | 전체 재분석 | 증분 재분석 | 개선율 |
|------------|-----------|-----------|-------|
| 1 file | 10s | 0.5s | **20x** |
| 5 files | 10s | 1.2s | **8.3x** |
| 10 files | 10s | 2.5s | **4x** |
| 50 files | 10s | 8s | **1.25x** |

### 캐시 적중률

| 프로젝트 크기 | 캐시 히트율 | 재분석 시간 단축 |
|-------------|----------|---------------|
| <1K LOC | 60% | 2x faster |
| 1K-10K LOC | 75% | 4x faster |
| 10K-100K LOC | 85% | 8x faster |
| >100K LOC | 90% | 10x faster |

---

## 트러블슈팅

### "Too many open files" 에러

**원인**: OS 파일 디스크립터 제한

**해결**:
```bash
# macOS/Linux
ulimit -n 10000

# 영구 설정 (macOS)
echo "ulimit -n 10000" >> ~/.zshrc
```

### 파일 변경 감지 안됨

**확인 사항**:
1. Watch 패턴 확인
```python
print(analyzer.watch_config["include"])
print(analyzer.watch_config["exclude"])
```

2. 파일이 제외되지 않았는지 확인
```python
analyzer.is_watched("src/main.py")  # True/False
```

3. fswatch/watchdog 설치 확인
```bash
# macOS
brew install fswatch

# Linux
pip install watchdog
```

### 캐시가 무효화되지 않음

**강제 캐시 삭제**:
```python
analyzer.invalidate_cache()
# 또는
import shutil
shutil.rmtree(".codegraph_cache")
```

### 메모리 사용량 증가

**캐시 크기 제한**:
```python
incremental_config={
    "max_cache_size_mb": 500,  # 500MB로 제한
    "cache_eviction_policy": "LRU",
}
```

---

## 구현 세부사항

### 의존성 추적 알고리즘

1. **파일 변경 감지**: fswatch/watchdog
2. **AST 파싱**: 변경된 파일의 import 문 추출
3. **그래프 탐색**: BFS로 의존 파일 수집
4. **스마트 전파**: AST diff 기반 선택적 재분석
5. **캐시 업데이트**: 변경된 파일만 캐시 무효화

### 캐시 전략

- **Adaptive Cache**: LRU + hit rate 조합
- **Granularity**: 파일 단위 캐시
- **Invalidation**: AST hash 기반 무효화
- **Persistence**: Disk-backed cache (SQLite)

---

## 참고 자료

- **구현**: `packages/codegraph-ir/src/features/incremental/`
- **캐시**: `packages/codegraph-ir/src/cache/`
- **의존성 추적**: `packages/codegraph-ir/src/features/dependency_graph/`

---

**마지막 업데이트**: 2025-12-29
**상태**: ✅ 프로덕션 준비 완료
