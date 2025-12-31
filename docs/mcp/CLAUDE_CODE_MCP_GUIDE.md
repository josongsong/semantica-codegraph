# Claude Code MCP 설정 가이드 🤖

> **Semantica v2 Codegraph MCP Server for Claude Code CLI**

Claude Code CLI에서 SOTA 수준의 코드 분석 기능을 사용할 수 있게 해주는 MCP 서버 설정 가이드입니다.

---

## 🚀 빠른 시작 (3분)

```bash
# 1. 설정 스크립트 실행
cd /Users/songmin/Documents/code-jo/semantica-v2/codegraph
./scripts/setup_mcp_claude.sh

# 2. Claude Code 실행
cd /path/to/your/project
claude

# 3. Claude Code에서 MCP 도구 사용
> Can you search for authentication code using the codegraph tool?
```

---

## 📋 목차

1. [사전 요구사항](#사전-요구사항)
2. [자동 설정](#자동-설정)
3. [수동 설정](#수동-설정)
4. [사용 방법](#사용-방법)
5. [문제 해결](#문제-해결)

---

## 사전 요구사항

### 1. Claude Code CLI 설치

```bash
# npm으로 설치 (권장)
npm install -g @anthropic-ai/claude-code

# 또는 Homebrew로 설치 (macOS)
brew install anthropic/tap/claude-code

# 설치 확인
claude --version
```

**참고:** Claude Code CLI 설치 문서는 [공식 문서](https://docs.anthropic.com/claude/docs/claude-code)를 참조하세요.

### 2. Python 3.10 이상

```bash
python3 --version
# Python 3.12.11 권장
```

### 3. OpenAI API Key

- 계정 생성: https://platform.openai.com/api-keys
- API 키 발급

---

## 자동 설정

### 1. 설정 스크립트 실행

```bash
cd /Users/songmin/Documents/code-jo/semantica-v2/codegraph
./scripts/setup_mcp_claude.sh
```

스크립트는 자동으로:
- ✅ Python 가상환경 생성
- ✅ 의존성 설치
- ✅ `.env` 파일 생성 (없는 경우)
- ✅ Claude Code MCP 설정 파일 생성
- ✅ MCP 서버 테스트

### 2. 설정 확인

```bash
# Claude Code 설정 파일 확인
cat ~/.claude/mcp_settings.json
```

**예상 출력:**
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
        "CODEGRAPH_WATCH": "false",
        "SEMANTICA_LOG_LEVEL": "INFO"
      }
    }
  }
}
```

---

## 수동 설정

### 1. 가상환경 및 의존성 설치

```bash
cd /Users/songmin/Documents/code-jo/semantica-v2/codegraph

# 가상환경 생성
python3 -m venv .venv
source .venv/bin/activate

# 의존성 설치
uv pip install -e .
# 또는
pip install -e .
```

### 2. 환경 변수 설정

`.env` 파일 생성 또는 확인:

```bash
cat > .env <<EOF
# OpenAI API Key (필수)
OPENAI_API_KEY=sk-your-api-key-here

# 임베딩 모델 설정
SEMANTICA_EMBEDDING_MODEL=text-embedding-3-small
SEMANTICA_EMBEDDING_DIMENSION=1536

# 로그 레벨
SEMANTICA_LOG_LEVEL=INFO
EOF
```

### 3. Claude Code MCP 설정 생성

```bash
# Claude Code 설정 디렉토리 생성
mkdir -p ~/.claude

# MCP 설정 파일 생성
cat > ~/.claude/mcp_settings.json <<'EOF'
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
        "CODEGRAPH_WATCH": "false",
        "SEMANTICA_LOG_LEVEL": "INFO"
      }
    }
  }
}
EOF
```

### 4. MCP 서버 테스트

```bash
cd /Users/songmin/Documents/code-jo/semantica-v2/codegraph
source .venv/bin/activate
python apps/mcp/mcp/main.py

# Ctrl+C로 종료
```

**정상 출력 예시:**
```
Target Repository: /Users/songmin/Documents/code-jo/semantica-v2/codegraph
File Watching: Disabled
...
```

---

## 사용 방법

### 1. Claude Code 시작

```bash
# 분석할 프로젝트 디렉토리로 이동
cd /path/to/your/project

# Claude Code 시작
claude
```

### 2. MCP 도구 사용

Claude Code는 자동으로 MCP 서버를 인식하고 사용합니다. 자연어로 요청하면 됩니다:

#### 코드 검색
```
User: Can you search for authentication related code?
Claude: [Uses codegraph search tool automatically]
```

```
User: Find all functions related to user login
Claude: [Uses codegraph search with "login" query]
```

#### 컨텍스트 분석
```
User: Analyze the AuthService.login function - show me its definition, usages, and callers
Claude: [Uses codegraph get_context tool]
```

#### 버그 분석
```
User: I have a null pointer error on line 42 in auth.py. Can you trace back to find the root cause?
Claude: [Uses codegraph graph_slice tool with backward direction]
```

#### 보안 분석
```
User: Check if there are any SQL injection vulnerabilities in this codebase
Claude: [Uses codegraph preview_taint_path or job_submit for taint analysis]
```

### 3. 사용 가능한 도구 확인

```
User: What MCP tools are available for code analysis?
Claude: [Lists all available codegraph tools]
```

### 4. 직접 도구 호출 (선택)

Claude Code에서 도구를 명시적으로 호출할 수도 있습니다:

```
User: Use the codegraph search tool to find "authentication"
```

---

## 주요 도구 목록

### Tier 0 (기본 도구)

| 도구 | 설명 | 사용 예시 |
|------|------|----------|
| `search` | 하이브리드 검색 | "Search for auth code" |
| `get_context` | 컨텍스트 조회 | "Analyze login function" |
| `graph_slice` | 버그 분석 | "Find root cause of error" |

### 분석 도구

| 도구 | 설명 | 사용 예시 |
|------|------|----------|
| `analyze_cost` | 복잡도 분석 | "Check time complexity" |
| `analyze_race` | Race condition | "Find race conditions" |
| `preview_taint_path` | 보안 분석 | "Check SQL injection" |

### 관리 도구

| 도구 | 설명 | 사용 예시 |
|------|------|----------|
| `force_reindex` | 재인덱싱 | "Reindex the codebase" |
| `job_submit` | 비동기 작업 | "Run full taint analysis" |

---

## 실전 사용 예시

### 예시 1: 새 프로젝트 분석

```bash
# 1. 프로젝트로 이동
cd ~/projects/my-web-app

# 2. Claude Code 시작
claude

# 3. Claude Code에서
User: I just opened this project. Can you help me understand the authentication flow?

Claude: I'll search for authentication-related code using the codegraph tool.
[Uses: codegraph search "authentication flow"]

Here's what I found:
1. AuthService.login (services/auth.py:42)
2. AuthMiddleware (middleware/auth.py:15)
...

User: Show me all the places where AuthService.login is called

Claude: [Uses: codegraph get_context target="AuthService.login" facets=["usages", "callers"]]

The login function is called from:
1. LoginView (views/auth.py:28)
2. APIAuthHandler (api/handlers/auth.py:15)
...
```

### 예시 2: 버그 디버깅

```bash
User: I'm getting a NullPointerException in getUserProfile() at line 156. Can you help me find why?

Claude: Let me trace back to find the root cause of this null pointer error.
[Uses: codegraph graph_slice anchor="user_profile:156" direction="backward"]

I found the issue. The null pointer originates from:
1. Line 142: user object is not initialized when session is expired
2. Line 98: Session.get_user() returns None if token is invalid
...

User: How should I fix this?

Claude: Here's a fix with proper null checking:
[Suggests code with null guards]
```

### 예시 3: 보안 검사

```bash
User: Can you check if this codebase has any SQL injection vulnerabilities?

Claude: I'll run a taint analysis to check for SQL injection paths.
[Uses: codegraph preview_taint_path source_pattern="request" sink_pattern="execute"]

Found 2 potential SQL injection vulnerabilities:
1. user_search.py:45 - User input flows directly to SQL query
2. report_generator.py:78 - Request parameter concatenated into SQL
...

User: Show me the full path for the first one

Claude: [Uses: codegraph graph_dataflow source="request.query" sink="execute_sql"]

Here's the data flow:
request.query → sanitize_input() → build_query() → execute_sql()
                     ↑
                  MISSING VALIDATION!
...
```

---

## 문제 해결

### MCP 서버가 시작되지 않음

**증상:**
- Claude Code가 codegraph 도구를 인식하지 못함
- "Tool not found" 오류

**해결:**

1. **설정 파일 확인**
   ```bash
   cat ~/.claude/mcp_settings.json
   ```

2. **Python 경로 확인**
   ```bash
   which python
   # 설정 파일의 "command"와 일치해야 함
   ```

3. **수동 테스트**
   ```bash
   cd /Users/songmin/Documents/code-jo/semantica-v2/codegraph
   source .venv/bin/activate
   python apps/mcp/mcp/main.py
   ```

4. **Claude Code 재시작**
   ```bash
   # Claude Code 완전 종료 후 재시작
   claude
   ```

### 검색 결과가 나오지 않음

**증상:**
- 검색 도구 사용 시 "No results found"

**해결:**

1. **인덱스 생성**
   ```bash
   cd /Users/songmin/Documents/code-jo/semantica-v2/codegraph
   source .venv/bin/activate
   python -m apps.cli.cli.main index /path/to/your/project
   ```

2. **Claude Code에서 재인덱싱 요청**
   ```
   User: Can you reindex this codebase?
   Claude: [Uses: codegraph force_reindex]
   ```

### API 키 오류

**증상:**
- "Invalid API key" 오류
- 임베딩 생성 실패

**해결:**

1. **.env 파일 확인**
   ```bash
   cat .env | grep OPENAI_API_KEY
   ```

2. **API 키 업데이트**
   ```bash
   echo "OPENAI_API_KEY=sk-your-actual-key-here" >> .env
   ```

3. **API 키 유효성 테스트**
   ```bash
   curl https://api.openai.com/v1/models \
     -H "Authorization: Bearer $OPENAI_API_KEY"
   ```

### Claude Code가 도구를 자동으로 사용하지 않음

**증상:**
- 도구가 있지만 Claude가 사용하지 않음

**해결:**

1. **명시적으로 요청**
   ```
   User: Use the codegraph search tool to find "authentication"
   ```

2. **도구 목록 확인 요청**
   ```
   User: What tools do you have access to?
   ```

3. **MCP 설정 재확인**
   ```bash
   cat ~/.claude/mcp_settings.json
   ```

---

## 고급 설정

### 1. 여러 프로젝트 동시 사용

각 프로젝트마다 별도의 `repo_id` 사용:

```json
{
  "mcpServers": {
    "codegraph": {
      "command": "...",
      "args": ["..."],
      "env": {
        "CODEGRAPH_REPO_PATH": "${workspaceFolder}",
        "CODEGRAPH_REPO_ID": "${workspaceFolderBasename}"
      }
    }
  }
}
```

### 2. 로그 레벨 조정

디버깅 시 로그 레벨 변경:

```json
{
  "env": {
    "SEMANTICA_LOG_LEVEL": "DEBUG"
  }
}
```

### 3. 커스텀 인덱싱 모드

```json
{
  "env": {
    "CODEGRAPH_INDEX_MODE": "fast"
  }
}
```

**모드:**
- `fast`: ~5초 (기본 IR만)
- `balanced`: ~2분 (권장)
- `deep`: ~30분 (전체 분석)

---

## 성능 최적화

### 1. 사전 인덱싱

Claude Code 사용 전에 프로젝트를 미리 인덱싱:

```bash
python -m apps.cli.cli.main index /path/to/project --mode balanced
```

### 2. 캐시 활용

3-Tier Cache가 자동으로 작동:
- L1 (메모리): ~0.1ms
- L2 (Redis): ~1ms
- L3 (DB): ~10ms

### 3. 대용량 프로젝트

10K+ 파일 프로젝트:
1. `fast` 모드로 시작
2. 필요시 `balanced` 모드로 업그레이드
3. 보안 분석은 비동기 작업 (`job_submit`) 사용

---

## FAQ

### Q1: Claude Code CLI는 어디서 다운로드하나요?

**A:**
```bash
npm install -g @anthropic-ai/claude-code
```

공식 문서: https://docs.anthropic.com/claude/docs/claude-code

### Q2: Cursor IDE 설정과 다른 점은?

**A:**
- **Cursor**: VSCode 기반, GUI, 실시간 파일 감시
- **Claude Code CLI**: 터미널 기반, 자연어 대화, 파일 감시 비활성화

설정 파일 위치도 다릅니다:
- Cursor: `~/Library/Application Support/Cursor/User/settings.json`
- Claude Code: `~/.claude/mcp_settings.json`

### Q3: 인덱싱은 얼마나 걸리나요?

**A:**
- **fast**: ~5초 (1K 파일)
- **balanced**: ~2분 (10K 파일)
- **deep**: ~30분 (10K 파일)

### Q4: OpenAI API 비용은?

**A:**
- 임베딩 생성: ~$0.0001/1K 토큰
- 10K 파일 프로젝트: ~$1-2 (1회)
- 증분 업데이트: 거의 무료

### Q5: 오프라인에서 사용 가능한가요?

**A:**
- 인덱싱: 인터넷 필요 (OpenAI API)
- 검색/분석: 인덱스 생성 후 오프라인 가능
- 로컬 임베딩 모델 사용 가능 (별도 설정)

---

## 추가 리소스

### 문서

- [SERENA_MCP_SETUP.md](SERENA_MCP_SETUP.md) - Cursor IDE 설정
- [README_MCP.md](README_MCP.md) - MCP 서버 가이드
- [CLAUDE.md](CLAUDE.md) - 프로젝트 개요

### 소스 코드

- MCP 서버: [apps/mcp/mcp/main.py](apps/mcp/mcp/main.py)
- MCP 핸들러: [apps/mcp/mcp/handlers/](apps/mcp/mcp/handlers/)
- 설정 스크립트: [scripts/setup_mcp_claude.sh](scripts/setup_mcp_claude.sh)

---

## 🎉 시작하기

```bash
# 1. 설정 스크립트 실행
./scripts/setup_mcp_claude.sh

# 2. 프로젝트로 이동
cd /path/to/your/project

# 3. Claude Code 시작
claude

# 4. 첫 요청
> Can you help me understand this codebase? Start by searching for the main entry point.
```

**Happy Coding with Claude! 🚀**
