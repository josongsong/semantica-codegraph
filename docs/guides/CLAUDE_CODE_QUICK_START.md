# Claude Code MCP 빠른 시작 ⚡

> **3분 안에 Claude Code에서 Codegraph 사용하기**

---

## 🚀 초간단 설정 (1분)

```bash
cd /Users/songmin/Documents/code-jo/semantica-v2/codegraph
./scripts/setup_mcp_claude.sh
```

✅ 끝! 이제 바로 사용 가능합니다.

---

## 💬 첫 사용

### 1. Claude Code 시작

```bash
# 분석할 프로젝트로 이동
cd /path/to/your/project

# Claude Code 실행
claude
```

### 2. 자연어로 요청

```
User: Can you search for authentication code?

Claude: I'll search for authentication-related code using the codegraph tool.
[검색 결과 표시...]
```

```
User: Show me all the places where the login function is called

Claude: [codegraph get_context 도구 자동 사용]
[호출 위치 목록 표시...]
```

```
User: I have a bug on line 42. Can you find the root cause?

Claude: [codegraph graph_slice 도구로 역추적]
[버그 원인 분석 표시...]
```

---

## 🎯 자주 사용하는 요청

### 코드 이해
```
> Help me understand this codebase. Start by finding the main entry point.
> What does the AuthService class do?
> Show me all API endpoints in this project.
```

### 버그 디버깅
```
> I'm getting a null pointer error at line 156. Find the cause.
> Why is this function returning undefined?
> Trace back the data flow for this variable.
```

### 보안 분석
```
> Check for SQL injection vulnerabilities
> Are there any race conditions in this async code?
> Find all places where user input is not validated
```

### 리팩토링
```
> Find all usages of the old login method
> Show me the impact if I change this function signature
> What functions call getUserProfile?
```

---

## 🛠️ 사용 가능한 도구

Claude Code가 자동으로 적절한 도구를 선택합니다:

| 요청 유형 | 자동 선택되는 도구 |
|-----------|-------------------|
| "search for...", "find..." | `search` |
| "show me where...", "list all..." | `get_context` |
| "why...", "find the cause..." | `graph_slice` |
| "check for SQL injection..." | `preview_taint_path` |
| "analyze complexity..." | `analyze_cost` |

---

## 🔧 설정 확인

### MCP 서버 상태 확인

```bash
# 설정 파일 확인
cat ~/.claude/mcp_settings.json

# 수동 테스트
cd /Users/songmin/Documents/code-jo/semantica-v2/codegraph
source .venv/bin/activate
python apps/mcp/mcp/main.py
# Ctrl+C로 종료
```

### Claude Code에서 도구 확인

```
User: What tools do you have for code analysis?

Claude: I have access to the following codegraph tools:
- search: Hybrid search across code
- get_context: Get definition, usages, callers
- graph_slice: Analyze bug root causes
- analyze_cost: Check time/space complexity
...
```

---

## ❌ 문제 해결

### MCP 도구가 안 보임

```bash
# 1. 설정 재확인
cat ~/.claude/mcp_settings.json

# 2. Claude Code 재시작
# Ctrl+C로 종료 후 다시 실행
claude
```

### 검색 결과 없음

```bash
# 프로젝트 인덱싱
python -m apps.cli.cli.main index /path/to/your/project
```

또는 Claude Code에서:

```
User: Can you reindex this codebase?
```

---

## 📚 더 알아보기

- **상세 가이드**: [CLAUDE_CODE_MCP_GUIDE.md](CLAUDE_CODE_MCP_GUIDE.md)
- **Cursor IDE용**: [SERENA_MCP_SETUP.md](SERENA_MCP_SETUP.md)
- **MCP 서버**: [README_MCP.md](README_MCP.md)

---

## 💡 팁

### 1. 명시적 도구 호출

```
User: Use the codegraph search tool to find "authentication"
```

### 2. 상세 분석 요청

```
User: Give me a detailed analysis of the login flow, including all callers and data flow
```

### 3. 여러 단계 작업

```
User: 1. Search for user authentication code
      2. Show me where it's called
      3. Check for security vulnerabilities
```

---

## 🎉 시작하기

```bash
# 1. 설정 (1회만)
./scripts/setup_mcp_claude.sh

# 2. 사용
cd /path/to/your/project
claude

# 3. 첫 요청
> Help me understand this codebase
```

**Happy Coding! 🚀**
