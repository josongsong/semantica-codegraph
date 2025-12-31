# 인덱싱 시스템 설정 가이드

> 환경별 최적 설정

---

## 목차

1. [기본 설정](#1-기본-설정)
2. [모드 설정](#2-모드-설정)
3. [트리거 설정](#3-트리거-설정)
4. [성능 튜닝](#4-성능-튜닝)
5. [환경별 프로파일](#5-환경별-프로파일)

---

## 1. 기본 설정

### 환경 변수

```bash
# .env
# 기본 설정
REPO_PATH=/path/to/repo
REPO_ID=my-repo

# 데이터베이스
DATABASE_URL=postgresql://user:pass@localhost:5432/codegraph
REDIS_URL=redis://localhost:6379/0

# 벡터 DB
QDRANT_MODE=embedded                    # memory|embedded|server
QDRANT_PATH=./data/qdrant_storage
QDRANT_URL=http://localhost:6333

# Lexical 인덱스
ZOEKT_INDEX_DIR=./data/zoekt
TANTIVY_INDEX_DIR=./data/tantivy
```

### 설정 파일

```toml
# semantica.toml
[indexing]
# 모드
default_mode = "fast"
auto_mode_selection = true

# 파일 필터
exclude_patterns = [
    ".git", "node_modules", "__pycache__",
    "*.pyc", "*.log"
]
supported_extensions = [
    ".py", ".ts", ".js", ".java", ".go"
]

[indexing.modes]
# FAST
fast_layers = ["l1", "l2"]
fast_timeout_seconds = 300

# BALANCED
balanced_layers = ["l1", "l2", "l3"]
balanced_max_neighbors = 100
balanced_timeout_seconds = 600

# DEEP
deep_layers = ["l1", "l2", "l3", "l4"]
deep_max_files = 500
deep_timeout_seconds = 1800

[indexing.triggers]
# ShadowFS
enable_shadowfs = true
shadowfs_batch_size = 10
shadowfs_ttl_seconds = 3600

# FileWatcher
enable_file_watcher = true
file_watcher_debounce_ms = 300
file_watcher_max_batch_window_ms = 5000

# BackgroundScheduler
enable_background_scheduler = true
background_idle_minutes = 5
background_balanced_hours = 24
```

---

## 2. 모드 설정

### 자동 모드 선택

```python
# src/contexts/analysis_indexing/infrastructure/mode_manager.py
class ModeTransitionConfig:
    # FAST → BALANCED 조건
    FAST_TO_BALANCED_IDLE_MINUTES = 5       # Idle 5분
    FAST_TO_BALANCED_HOURS_SINCE_LAST = 24  # 24시간마다
    FAST_TO_BALANCED_MIN_CHANGED_FILES = 10 # 변경 10개 이상

    # BALANCED 체크포인트
    BALANCED_CHECKPOINT_INTERVAL_MINUTES = 5  # 5분마다 저장
```

### 수동 모드 지정

```bash
# CLI
python -m src.cli.main index /repo --mode fast
python -m src.cli.main index /repo --mode balanced
python -m src.cli.main index /repo --mode deep
python -m src.cli.main index /repo --mode bootstrap
```

### 레이어 커스터마이징

```toml
[indexing.layers.custom]
# 커스텀 모드: L1+L2+L4 (L3 제외)
my_mode_layers = ["l1", "l2", "l4"]

[indexing.layers.l3]
# L3 세부 설정
cfg_max_nodes = 100
dfg_scope = "single_function"
git_history_commits = 10

[indexing.layers.l4]
# L4 세부 설정
cfg_unlimited = true
dfg_scope = "cross_function"
git_history_all = true
```

---

## 3. 트리거 설정

### ShadowFS Plugin

```python
# config/shadowfs.py
SHADOWFS_CONFIG = {
    "enable": True,

    # Batch 설정
    "batch_size": 10,           # 파일 10개마다 IR delta
    "ttl_seconds": 3600,        # Transaction TTL 1시간

    # 언어별 병렬
    "parallel_languages": True,
    "max_parallel_tasks": 5,
}
```

### FileWatcher

```python
# config/file_watcher.py
FILE_WATCHER_CONFIG = {
    "enable": True,

    # Debouncing
    "debounce_ms": 300,         #  디바운스
    "max_batch_window_ms": 5000,  # 최대 5초 대기

    # 제외 패턴
    "exclude_patterns": [
        ".git", "node_modules", "__pycache__",
        ".venv", "*.pyc", "*.log", ".DS_Store"
    ],

    # 지원 확장자
    "supported_extensions": [
        ".py", ".pyi", ".ts", ".tsx", ".js", ".jsx",
        ".java", ".go", ".rs"
    ],

    # 재귀 감시
    "recursive": True,
}
```

### BackgroundScheduler

```python
# config/background.py
BACKGROUND_SCHEDULER_CONFIG = {
    "enable": True,

    # Idle 감지
    "idle_threshold_minutes": 5,

    # 자동 전환
    "auto_balanced_hours": 24,  # 24시간마다 BALANCED
    "auto_deep_days": 7,        # 7일마다 DEEP

    # 우선순위
    "priority": {
        "repair": 1,    # HIGH
        "balanced": 2,  # MEDIUM
        "deep": 3,      # LOW
    },

    # Graceful stop
    "graceful_stop_timeout": 30,  # 30초
}
```

### Job Orchestrator

```python
# config/job_orchestrator.py
JOB_ORCHESTRATOR_CONFIG = {
    "enable_distributed_lock": True,

    # Lock 설정
    "lock_ttl_seconds": 300,        # 5분
    "lock_extend_interval": 60,     # 1분마다 연장

    # Retry
    "max_retries": 3,
    "retry_backoff_base": 2,        # 2^n seconds

    # Checkpoint
    "checkpoint_interval_files": 100,  # 100파일마다

    # Conflict
    "conflict_strategy": "skip",    # skip|supersede|queue
}
```

---

## 4. 성능 튜닝

### 병렬 처리

```python
# config/performance.py
PERFORMANCE_CONFIG = {
    # 파싱 병렬
    "parsing_workers": 4,           # CPU 코어 수
    "parsing_chunk_size": 50,       # 50파일씩 배치

    # IR 빌딩 병렬
    "ir_workers": 4,
    "ir_chunk_size": 50,

    # 인덱싱 병렬
    "indexing_parallel_indexes": True,  # 3개 인덱스 동시

    # 벡터 임베딩
    "embedding_batch_size": 32,
    "embedding_workers": 2,
}
```

### 메모리 제한

```python
MEMORY_CONFIG = {
    # AST 캐시
    "ast_cache_max_size_mb": 500,
    "ast_cache_ttl_seconds": 3600,

    # IR 캐시
    "ir_cache_max_size_mb": 1000,
    "ir_cache_ttl_seconds": 7200,

    # 청크 캐시
    "chunk_cache_max_size_mb": 2000,
}
```

### 디스크 사용

```python
STORAGE_CONFIG = {
    # Qdrant
    "qdrant_min_disk_space_mb": 1000,   # 최소 1GB 여유
    "qdrant_check_disk_space": True,

    # Tantivy
    "tantivy_max_index_size_gb": 10,    # 최대 10GB
    "tantivy_compaction_trigger": 200,  # 200 파일마다

    # 임시 파일
    "temp_dir": "/tmp/codegraph",
    "cleanup_temp_on_exit": True,
}
```

---

## 5. 환경별 프로파일

### 개발 (Laptop)

```toml
# config/dev.toml
[indexing]
default_mode = "fast"
auto_mode_selection = true

[indexing.triggers]
enable_shadowfs = true          # IDE 편집
enable_file_watcher = true      # git pull
enable_background_scheduler = true  # Idle 자동

[indexing.performance]
parsing_workers = 2             # Laptop: 2 코어
ir_workers = 2
embedding_batch_size = 16       # 메모리 절약

[storage]
database_url = "sqlite:///./codegraph.db"  # SQLite (간편)
qdrant_mode = "embedded"        # Embedded mode
zoekt_disable = true            # 개발 시 불필요
```

### 스테이징 (Server)

```toml
# config/staging.toml
[indexing]
default_mode = "balanced"
auto_mode_selection = false     # 수동 제어

[indexing.triggers]
enable_shadowfs = false         # 서버에서 불필요
enable_file_watcher = true      # 파일 변경 감지
enable_background_scheduler = true

[indexing.performance]
parsing_workers = 8             # 서버: 8 코어
ir_workers = 8
embedding_batch_size = 64

[storage]
database_url = "postgresql://..."  # PostgreSQL
qdrant_mode = "server"          # Qdrant 서버
qdrant_url = "http://qdrant:6333"
zoekt_enable = true
```

### 프로덕션 (Cluster)

```toml
# config/production.toml
[indexing]
default_mode = "balanced"
auto_mode_selection = false

[indexing.triggers]
enable_shadowfs = false
enable_file_watcher = true
enable_background_scheduler = true
enable_job_orchestrator = true  # Job 큐 활성화

[indexing.performance]
parsing_workers = 16            # High-spec
ir_workers = 16
embedding_batch_size = 128
embedding_workers = 4

[job_orchestrator]
enable_distributed_lock = true  # 멀티 워커
worker_count = 10               # 10개 워커
conflict_strategy = "queue"     # 순차 실행

[storage]
database_url = "postgresql://..."
redis_url = "redis://redis:6379/0"
qdrant_mode = "server"
qdrant_url = "http://qdrant:6333"
qdrant_prefer_grpc = true       # gRPC 2-5x 빠름
zoekt_enable = true
zoekt_replicas = 3              # HA
```

### CI/CD (PR 분석)

```toml
# config/ci.toml
[indexing]
default_mode = "fast"           # 빠른 피드백
auto_mode_selection = false

[indexing.scope]
# PR diff만 인덱싱
incremental_only = true
pr_mode = true                  # (미구현)

[indexing.performance]
parsing_workers = 4
timeout_seconds = 300           # 5분 제한

[storage]
database_url = "sqlite:///:memory:"  # In-memory
qdrant_mode = "memory"          # 임시
zoekt_disable = true
```

---

## 설정 우선순위

```
1. CLI 인자 (--mode fast)
2. 환경 변수 (INDEXING_MODE=fast)
3. 설정 파일 (semantica.toml)
4. 기본값 (DEFAULT_MODE)
```

---

## 설정 검증

### CLI

```bash
# 설정 확인
python -m src.cli.main config show

# 설정 테스트
python -m src.cli.main config test

# 설정 생성
python -m src.cli.main config init --profile dev
```

### 프로그래밍

```python
from src.contexts.analysis_indexing.infrastructure.config import load_config

# 설정 로드
config = load_config("config/dev.toml")

# 검증
config.validate()

# 적용
orchestrator = IndexingOrchestrator.from_config(config)
```

---

## 트러블슈팅

### 설정 파일 찾을 수 없음

```bash
# 증상
ERROR: Config file not found: semantica.toml

# 해결
1. 현재 디렉토리 확인: ls -la semantica.toml
2. 환경변수 설정: export SEMANTICA_CONFIG=/path/to/config.toml
3. 기본 설정 생성: python -m src.cli.main config init
```

### 설정 파싱 에러

```bash
# 증상
ERROR: Invalid TOML syntax at line 42

# 해결
1. TOML 검증: python -m toml config.toml
2. 주석 확인: # 사용 (// 아님)
3. 문자열 따옴표: "value" 또는 'value'
```

---

## 참고

### 설정 스키마
```
config/
├── schema.json          # JSON Schema
├── dev.toml
├── staging.toml
├── production.toml
└── ci.toml
```

### 관련 문서
- `pipelines-quick-ref.md` - 빠른 설정
- `job-orchestrator.md` - Job 설정
- `troubleshooting.md` - 문제 해결

---

**Last 
