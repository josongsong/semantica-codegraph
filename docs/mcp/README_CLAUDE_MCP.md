# Serena MCP for Claude Code CLI 🤖

> **Semantica v2 Codegraph MCP Server for Claude Code - Production Ready**

[![Python](https://img.shields.io/badge/Python-3.12+-blue.svg)](https://www.python.org/downloads/)
[![MCP](https://img.shields.io/badge/MCP-1.0-green.svg)](https://modelcontextprotocol.io)
[![Claude Code](https://img.shields.io/badge/Claude_Code-2.0+-purple.svg)](https://docs.anthropic.com/claude/docs/claude-code)
[![Status](https://img.shields.io/badge/Status-Production-success.svg)]()

Claude Code CLI에서 SOTA 수준의 코드 분석 기능을 자연어로 사용할 수 있게 해주는 MCP 서버입니다.

---

## ✨ 핵심 특징

### 🗣️ 자연어 인터페이스

```bash
User: Can you search for authentication code?
Claude: [자동으로 codegraph search 도구 사용]

User: Find the root cause of the null pointer error on line 42
Claude: [자동으로 codegraph graph_slice 도구로 역추적]
```

**명령어 암기 불필요** - 자연어로 요청하면 Claude가 알아서 적절한 도구를 선택합니다.

### 🚀 초고속 설정

```bash
./scripts/setup_mcp_claude.sh
```

1분 안에 모든 설정 완료!

### 🎯 강력한 분석 기능

- **하이브리드 검색**: 시맨틱 + 렉시컬 + 그래프 통합
- **컨텍스트 분석**: 정의, 참조, 호출 그래프
- **버그 추적**: Root Cause 자동 분석
- **보안 검사**: Taint 분석, Race condition 검출
- **복잡도 분석**: 시간/공간 복잡도 계산

---

## 📚 문서 구조

| 문서 | 설명 | 대상 |
|------|------|------|
| **[CLAUDE_CODE_QUICK_START.md](CLAUDE_CODE_QUICK_START.md)** | 3분 빠른 시작 ⚡ | 모든 사용자 ⭐ |
| **[CLAUDE_CODE_MCP_GUIDE.md](CLAUDE_CODE_MCP_GUIDE.md)** | 상세 가이드 | 심화 학습 |
| **[README_MCP.md](README_MCP.md)** | MCP 서버 개요 | MCP 개발자 |

---

## 🚀 빠른 시작

### 1. 설정 (1회만)

```bash
cd /Users/songmin/Documents/code-jo/semantica-v2/codegraph
./scripts/setup_mcp_claude.sh
```

### 2. 사용

```bash
# 프로젝트로 이동
cd /path/to/your/project

# Claude Code 시작
claude

# 자연어로 요청
User: Can you help me understand this codebase?
```

---

## 💬 사용 예시

### 코드 검색

```
User: Search for all authentication related code

Claude: I'll search for authentication-related code...
[codegraph search 도구 자동 사용]

Found 15 results:
1. AuthService.login (services/auth.py:42)
2. AuthMiddleware (middleware/auth.py:15)
...
```

### 버그 디버깅

```
User: I have a null pointer error at line 156 in user_profile.py. Find the root cause.

Claude: Let me trace back to find the root cause...
[codegraph graph_slice 도구로 backward 분석]

Found the issue! The null pointer originates from:
- Line 142: user object not initialized when session expired
- Line 98: Session.get_user() returns None for invalid tokens
...
```

### 보안 분석

```
User: Check if this codebase has SQL injection vulnerabilities

Claude: I'll run a taint analysis...
[codegraph preview_taint_path 도구 사용]

Found 2 potential SQL injection vulnerabilities:
1. user_search.py:45 - User input → SQL query (UNSAFE)
2. report_generator.py:78 - Request param → SQL (UNSAFE)
...
```

### 코드 이해

```
User: What does the login function do and where is it called from?

Claude: Let me analyze the login function...
[codegraph get_context 도구 사용]

Definition (services/auth.py:42):
def login(username, password):
    # Validates credentials and creates session

Called from 3 locations:
1. LoginView (views/auth.py:28)
2. APIAuthHandler (api/handlers/auth.py:15)
3. TestAuth (tests/test_auth.py:55)
...
```

---

## 🛠️ 설정 확인

### 설정 파일

```bash
cat ~/.claude/mcp_settings.json
```

**정상 설정:**
```json
{
  "mcpServers": {
    "codegraph": {
      "command": "/Users/songmin/.../codegraph/.venv/bin/python",
      "args": [".../apps/mcp/mcp/main.py"],
      "env": {
        "PYTHONPATH": "/Users/songmin/.../codegraph",
        "CODEGRAPH_REPO_PATH": "${workspaceFolder}",
        "CODEGRAPH_WATCH": "false",
        "SEMANTICA_LOG_LEVEL": "INFO"
      }
    }
  }
}
```

### MCP 서버 테스트

```bash
cd /Users/songmin/Documents/code-jo/semantica-v2/codegraph
source .venv/bin/activate
python apps/mcp/mcp/main.py
# Ctrl+C로 종료
```

**정상 출력:**
```
Target Repository: /Users/songmin/Documents/code-jo/semantica-v2/codegraph
File Watching: Disabled
[INFO] MCP Server initialized
...
```

---

## 🎯 주요 도구

### 자동 선택 (Claude가 알아서 선택)

| 요청 패턴 | 선택되는 도구 | 기능 |
|-----------|--------------|------|
| "search for...", "find..." | `search` | 코드 검색 |
| "show me where...", "list all..." | `get_context` | 컨텍스트 조회 |
| "why...", "find cause..." | `graph_slice` | 버그 추적 |
| "check for SQL injection..." | `preview_taint_path` | 보안 분석 |
| "analyze complexity..." | `analyze_cost` | 복잡도 분석 |

### 사용 가능한 모든 도구

#### Tier 0 (기본)
- `search` - 하이브리드 검색
- `get_context` - 통합 컨텍스트
- `graph_slice` - 시맨틱 슬라이싱

#### 분석 도구
- `analyze_cost` - 복잡도 분석
- `analyze_race` - Race condition
- `preview_taint_path` - Taint 경로
- `graph_dataflow` - 데이터 흐름

#### 관리 도구
- `force_reindex` - 재인덱싱
- `job_submit` - 비동기 작업

---

## 🔧 문제 해결

### MCP 도구가 보이지 않음

```
User: What tools do you have?
Claude: [MCP 도구 목록이 나타나지 않음]
```

**해결:**
```bash
# 1. 설정 확인
cat ~/.claude/mcp_settings.json

# 2. Claude Code 재시작
claude
```

### 검색 결과 없음

```
User: Search for "login"
Claude: No results found
```

**해결:**
```bash
# 인덱싱 실행
python -m apps.cli.cli.main index /path/to/project
```

또는:
```
User: Can you reindex this codebase?
```

### API 키 오류

```bash
# .env 파일 확인
cat .env | grep OPENAI_API_KEY

# API 키 추가
echo "OPENAI_API_KEY=sk-your-key-here" >> .env
```

---

## 📖 실전 워크플로우

### 새 프로젝트 온보딩

```bash
cd ~/projects/new-project
claude
```

```
User: I just joined this project. Can you help me understand the codebase?

Claude: I'll help you understand the codebase. Let me start by searching for the main entry point...
[분석 시작...]

User: What's the authentication flow?

Claude: [auth 관련 코드 검색 및 분석...]

User: Show me all API endpoints

Claude: [API 엔드포인트 검색 및 목록 표시...]
```

### 버그 수정

```
User: I'm getting error "TypeError: Cannot read property 'id' of undefined" at line 156 in getUserProfile(). Help me fix it.

Claude: Let me trace back to find where this undefined value comes from...
[graph_slice로 역추적...]

Found the issue! The error occurs because:
1. Line 142: 'user' is undefined when session is expired
2. Fix: Add null check before accessing user.id

Here's the fix:
[코드 수정 제안...]
```

### 리팩토링

```
User: I want to rename the old 'authenticate' function to 'validateCredentials'. Show me all the places I need to change.

Claude: [get_context로 모든 사용처 검색...]

Found 12 usages across 8 files:
1. services/auth.py:42 (definition)
2. views/login.py:28 (call)
3. api/handlers.py:15 (call)
...

I'll also check the impact of this change...
[preview_impact로 영향도 분석...]
```

### 보안 감사

```
User: I need to do a security audit. Check for:
1. SQL injection vulnerabilities
2. XSS vulnerabilities
3. Race conditions in async code

Claude: I'll run a comprehensive security analysis...

1. SQL Injection Check:
[preview_taint_path 실행...]
Found 2 vulnerabilities...

2. XSS Check:
[taint 분석...]
Found 1 vulnerability...

3. Race Conditions:
[analyze_race 실행...]
Found 3 potential race conditions...
```

---

## 🌟 고급 기능

### 1. 프로젝트별 인덱싱

```bash
# 프로젝트 A 인덱싱
python -m apps.cli.cli.main index ~/projects/project-a

# 프로젝트 B 인덱싱
python -m apps.cli.cli.main index ~/projects/project-b

# Claude Code는 현재 디렉토리의 인덱스 자동 선택
```

### 2. 인덱싱 모드 선택

```bash
# Fast (5초) - 기본 IR만
python -m apps.cli.cli.main index /path --mode fast

# Balanced (2분) - 권장
python -m apps.cli.cli.main index /path --mode balanced

# Deep (30분) - 전체 분석
python -m apps.cli.cli.main index /path --mode deep
```

### 3. 비동기 분석 (대용량)

```
User: Run a full taint analysis on this codebase (it's very large)

Claude: This will take a while. I'll submit it as a background job...
[job_submit 사용...]

Job ID: job_abc123
Status: Running...

I'll notify you when it's done.
```

나중에:
```
User: Check the status of job job_abc123

Claude: [job_status 확인...]
Status: Completed
Results: [결과 표시...]
```

---

## 💡 팁과 트릭

### 1. 명시적 도구 지정

Claude가 잘못된 도구를 선택하면:

```
User: Use the codegraph search tool to find "authentication"
```

### 2. 상세 분석 요청

```
User: Give me a detailed analysis of the login function including:
- Definition and implementation
- All call sites
- Data flow
- Potential security issues
```

### 3. 여러 작업 한 번에

```
User: Please do the following:
1. Search for SQL query construction code
2. Check each result for SQL injection vulnerabilities
3. List the vulnerable functions with severity
4. Suggest fixes for each
```

### 4. 컨텍스트 유지

Claude Code는 대화 컨텍스트를 유지하므로:

```
User: Search for authentication code
Claude: [검색 결과...]

User: Now analyze the first result in detail
Claude: [첫 번째 결과 상세 분석...]

User: Check if it has security issues
Claude: [보안 분석...]
```

---

## 📊 성능 & 비용

### 인덱싱 시간

| 프로젝트 규모 | Fast | Balanced | Deep |
|--------------|------|----------|------|
| 1K 파일 | 5초 | 30초 | 5분 |
| 10K 파일 | 20초 | 2분 | 30분 |
| 100K 파일 | 2분 | 20분 | 5시간 |

### API 비용 (OpenAI)

| 작업 | 비용 (근사) |
|------|------------|
| 초기 인덱싱 (10K 파일) | $1-2 |
| 증분 업데이트 (100 파일) | $0.01-0.05 |
| 검색 쿼리 | 무료 (로컬) |
| 분석 도구 | 무료 (로컬) |

---

## 🤝 커뮤니티

### 이슈 & 질문

- GitHub Issues: [codegraph/issues](https://github.com/semantica/codegraph/issues)
- 슬랙: [semantica.slack.com](https://semantica.slack.com)

### 기여

Pull requests welcome!

---

## 📜 라이선스

MIT License

---

## 🎉 시작 체크리스트

설정 완료 후:

- [ ] 설정 스크립트 실행 (`./scripts/setup_mcp_claude.sh`)
- [ ] `.env` 파일에 `OPENAI_API_KEY` 설정
- [ ] `~/.claude/mcp_settings.json` 확인
- [ ] MCP 서버 수동 테스트 통과
- [ ] Claude Code에서 도구 인식 확인
- [ ] 첫 검색 성공
- [ ] 프로젝트 인덱싱 완료

**모든 체크리스트 완료 시 사용 준비 완료!** 🚀

---

**생성 일시:** 2025-12-28
**버전:** 1.0
**상태:** Production Ready ✅

**Happy Coding with Claude! 🤖**
