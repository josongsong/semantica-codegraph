# Serena MCP for Cursor IDE 🎯

> **Semantica v2 Codegraph MCP Server - Production Ready**

[![Python](https://img.shields.io/badge/Python-3.12+-blue.svg)](https://www.python.org/downloads/)
[![MCP](https://img.shields.io/badge/MCP-1.0-green.svg)](https://modelcontextprotocol.io)
[![Status](https://img.shields.io/badge/Status-Production-success.svg)]()

Cursor IDE에서 SOTA 수준의 코드 분석 기능을 사용할 수 있게 해주는 MCP (Model Context Protocol) 서버입니다.

---

## 🚀 빠른 시작 (3분)

```bash
# 1. 설정 스크립트 실행
cd /Users/songmin/Documents/code-jo/semantica-v2/codegraph
./scripts/setup_mcp_cursor.sh

# 2. Cursor 설정 병합 (자동)
./scripts/merge_cursor_settings.sh

# 3. Cursor 재시작하고 테스트
# Cursor에서: @codegraph search "test"
```

**또는 수동 설정:**
- [빠른 시작 가이드](SERENA_QUICK_START.md) 참조

---

## 📚 문서 구조

| 문서 | 설명 | 대상 |
|------|------|------|
| **[SERENA_QUICK_START.md](SERENA_QUICK_START.md)** | 3분 빠른 시작 | 모든 사용자 ⭐ |
| **[SERENA_MCP_SETUP.md](SERENA_MCP_SETUP.md)** | 상세 설정 가이드 | 상세 설정 필요 시 |
| **[SERENA_MCP_SUMMARY.md](SERENA_MCP_SUMMARY.md)** | 설정 요약 및 체크리스트 | 설정 후 확인용 |
| **[README_MCP.md](README_MCP.md)** | MCP 서버 가이드 (기존) | MCP 개발자 |

---

## 🎯 주요 기능

### Tier 0 도구 (기본 진입점)

```
# 1. 하이브리드 검색 (시맨틱 + 렉시컬 + 그래프)
@codegraph search "authentication logic"

# 2. 통합 컨텍스트 조회
@codegraph get_context target="AuthService.login" facets=["definition", "usages", "callers"]

# 3. 시맨틱 슬라이싱 (버그 Root Cause 추출)
@codegraph graph_slice anchor="user_password" direction="backward"
```

### 고급 분석

```
# 비용 복잡도 분석
@codegraph analyze_cost functions=["process_large_file"]

# Race Condition 검출
@codegraph analyze_race functions=["concurrent_update"]

# Taint 분석 (보안)
@codegraph job_submit tool="analyze_taint" args={...}
```

---

## 🛠️ 설치 및 설정

### 방법 1: 자동 설정 (권장) ⭐

```bash
# 전체 자동 설정
./scripts/setup_mcp_cursor.sh
./scripts/merge_cursor_settings.sh

# Cursor 재시작
```

### 방법 2: 수동 설정

1. **의존성 설치**
   ```bash
   cd /Users/songmin/Documents/code-jo/semantica-v2/codegraph
   source .venv/bin/activate
   uv pip install -e .
   ```

2. **Cursor 설정 추가**

   파일: `~/Library/Application Support/Cursor/User/settings.json`

   ```json
   {
     "mcpServers": {
       "codegraph": {
         "command": "/Users/songmin/Documents/code-jo/semantica-v2/codegraph/.venv/bin/python",
         "args": [
           "/Users/songmin/Documents/code-jo/semantica-v2/codegraph/apps/mcp/mcp/main.py"
         ],
         "env": {
           "PYTHONPATH": "/Users/songmin/Documents/code-jo/semantica-v2/codegraph",
           "CODEGRAPH_REPO_PATH": "${workspaceFolder}",
           "CODEGRAPH_WATCH": "true",
           "SEMANTICA_LOG_LEVEL": "INFO"
         }
       }
     }
   }
   ```

3. **Cursor 재시작**

---

## 📊 아키텍처

```
┌─────────────────────────────────────────────────────┐
│              Cursor IDE (Client)                    │
│  ┌────────────────────────────────────────────┐    │
│  │  Chat Interface: @codegraph search "..."   │    │
│  └─────────────────┬──────────────────────────┘    │
└────────────────────┼───────────────────────────────┘
                     │ MCP Protocol (stdio)
                     ▼
┌─────────────────────────────────────────────────────┐
│         MCP Server (apps/mcp/mcp/main.py)          │
│  ┌──────────────────────────────────────────┐      │
│  │  Tool Handlers (Tier 0, Tier 1, Tier 2) │      │
│  │  • search, get_context, graph_slice      │      │
│  │  • analyze_cost, analyze_race            │      │
│  │  • job_submit, force_reindex             │      │
│  └─────────────────┬────────────────────────┘      │
└────────────────────┼───────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────┐
│           Analysis Engine (Rust + Python)           │
│  • IRIndexingOrchestrator (L1-L8 Pipeline)         │
│  • MultiLayerIndexOrchestrator (MVCC)              │
│  • Query Engine (Lexical, Semantic, Graph)         │
│  • Taint Analysis, Points-to, Effects              │
└─────────────────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────┐
│               Storage Layer                         │
│  • PostgreSQL (메타데이터)                          │
│  • Qdrant (벡터 검색)                               │
│  • Tantivy (렉시컬 검색)                            │
│  • Kùzu (그래프 저장소)                             │
└─────────────────────────────────────────────────────┘
```

---

## 🔍 주요 도구 목록

### Tier 0 (에이전트 기본 진입점)

| 도구 | 설명 | 응답 시간 |
|------|------|-----------|
| `search` | 하이브리드 검색 (chunks + symbols) | 1-3초 |
| `get_context` | 통합 컨텍스트 조회 | 1-2초 |
| `graph_slice` | 시맨틱 슬라이싱 (버그 분석) | 2-5초 |

### Tier 1 (고급 분석)

| 도구 | 설명 | 응답 시간 |
|------|------|-----------|
| `analyze_cost` | 비용 복잡도 분석 | 5-15초 |
| `analyze_race` | Race condition 검출 | 10-30초 |
| `graph_dataflow` | Dataflow 분석 | 5-20초 |

### Tier 2 (관리 도구, 승인 필요)

| 도구 | 설명 | 비고 |
|------|------|------|
| `force_reindex` | 강제 재인덱싱 | 모드별 시간 상이 |

### Preview 도구 (경량, 1-2초)

| 도구 | 설명 |
|------|------|
| `preview_taint_path` | Taint 경로 존재성 확인 |
| `preview_impact` | Impact 근사 분석 |
| `preview_callers` | 상위 호출자 프리뷰 |

---

## 🎓 사용 예시

### 1. 코드 검색

```
# 기본 검색
@codegraph search "user authentication"

# 심볼만 검색
@codegraph search "AuthService" types=["symbols"]

# 청크만 검색 (코드 블록)
@codegraph search "password validation" types=["chunks"]
```

### 2. 컨텍스트 조회

```
# 정의 + 사용처 조회
@codegraph get_context target="login" facets=["definition", "usages"]

# 전체 컨텍스트 조회
@codegraph get_context target="AuthService.login" facets=["definition", "usages", "callers", "callees", "tests"]
```

### 3. 버그 분석

```
# Backward slice (원인 추적)
@codegraph graph_slice anchor="null_pointer_error" direction="backward" max_depth=5

# Forward slice (영향도 분석)
@codegraph graph_slice anchor="user_input" direction="forward" max_depth=3
```

### 4. 보안 분석

```
# SQL Injection 경로 확인
@codegraph preview_taint_path source_pattern="request.query" sink_pattern="execute_sql"

# 전체 Taint 분석 (비동기)
@codegraph job_submit tool="analyze_taint" args={"policy": "sql_injection"}
```

---

## 🔧 문제 해결

### MCP 서버가 시작되지 않음

```bash
# 1. Python 경로 확인
which python

# 2. 수동 실행 테스트
cd /Users/songmin/Documents/code-jo/semantica-v2/codegraph
source .venv/bin/activate
python apps/mcp/mcp/main.py
# 정상 시 MCP 프로토콜 초기화 로그 출력

# 3. Cursor 개발자 도구 확인
# Cursor에서 Cmd+Shift+I → Console 탭 → "codegraph" 검색
```

### 검색 결과가 나오지 않음

```bash
# 1. 인덱스 생성
python -m apps.cli.cli.main index /path/to/your/project

# 2. 또는 Cursor에서 강제 재인덱싱
@codegraph force_reindex reason="Initial setup"
```

### API 키 오류

```bash
# .env 파일 확인
cat .env | grep OPENAI_API_KEY

# API 키 추가
echo "OPENAI_API_KEY=sk-your-actual-key-here" >> .env
```

더 많은 문제 해결 방법은 [SERENA_MCP_SETUP.md](SERENA_MCP_SETUP.md#문제-해결)를 참조하세요.

---

## 📦 스크립트

| 스크립트 | 설명 | 사용법 |
|---------|------|--------|
| `setup_mcp_cursor.sh` | 자동 설정 | `./scripts/setup_mcp_cursor.sh` |
| `merge_cursor_settings.sh` | 설정 병합 | `./scripts/merge_cursor_settings.sh` |

---

## 🌟 기능 하이라이트

### 3-Tier Cache 전략

- **L1 (메모리)**: ~0.1ms (LRU 캐시)
- **L2 (Redis)**: ~1ms (분산 캐시)
- **L3 (DB)**: ~10ms (영구 저장소)

### 증분 인덱싱 (MVCC)

- 파일 변경 감지 (File Watcher)
- 자동 증분 업데이트
- Multi-Agent 협업 지원

### SOTA 분석 기능

- **Points-to Analysis**: Andersen 알고리즘
- **Taint Analysis**: Interprocedural, Field-sensitive
- **Effect System**: Biabduction, Separation Logic
- **Cost Analysis**: Amortized 복잡도

---

## 📖 추가 문서

### 프로젝트 문서

- [CLAUDE.md](CLAUDE.md) - 프로젝트 개요 및 아키텍처
- [QUICK_START.md](QUICK_START.md) - 전체 프로젝트 빠른 시작
- [README.md](README.md) - 프로젝트 메인 README

### 기술 문서

- [docs/RUST_ENGINE_API.md](docs/RUST_ENGINE_API.md) - Rust 엔진 API 레퍼런스
- [docs/CLEAN_ARCHITECTURE_SUMMARY.md](docs/CLEAN_ARCHITECTURE_SUMMARY.md) - 아키텍처 설계
- [docs/adr/](docs/adr/) - Architecture Decision Records

---

## 🤝 기여 및 지원

### 이슈 제보

GitHub Issues: [codegraph/issues](https://github.com/semantica/codegraph/issues)

### 문의

- 이메일: songmin@semantica.dev
- 슬랙: [semantica.slack.com](https://semantica.slack.com)

---

## 📜 라이선스

MIT License - 자세한 내용은 [LICENSE](LICENSE) 파일 참조

---

## 🎉 설정 완료 체크리스트

- [ ] 의존성 설치 (`uv pip install -e .`)
- [ ] `.env` 파일 설정 (`OPENAI_API_KEY`)
- [ ] Cursor 설정 업데이트 (`mcp_settings.json` 병합)
- [ ] Cursor 재시작
- [ ] 첫 테스트 (`@codegraph search "test"`)
- [ ] 인덱싱 확인 (필요 시 `force_reindex`)

**모든 체크리스트 완료 시 사용 준비 완료!** 🚀

---

**생성 일시:** 2025-12-28
**버전:** 1.0
**상태:** Production Ready ✅
