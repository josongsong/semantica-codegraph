# Serena MCP 빠른 시작 가이드

> **3분 안에 Cursor IDE에서 Codegraph 사용하기**

## 🚀 빠른 설정 (자동)

```bash
# 1. 저장소로 이동
cd /Users/songmin/Documents/code-jo/semantica-v2/codegraph

# 2. 설정 스크립트 실행
./scripts/setup_mcp_cursor.sh

# 3. 생성된 mcp_settings.json을 Cursor 설정에 병합
# macOS: ~/Library/Application Support/Cursor/User/settings.json
```

## 📝 수동 설정 (상세)

### 1. 의존성 설치

```bash
cd /Users/songmin/Documents/code-jo/semantica-v2/codegraph
source .venv/bin/activate
uv pip install -e .
```

### 2. Cursor 설정 파일 편집

**파일 경로:**
- macOS: `~/Library/Application Support/Cursor/User/settings.json`
- Linux: `~/.config/Cursor/User/settings.json`
- Windows: `%APPDATA%\Cursor\User\settings.json`

**설정 추가:**

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

### 3. Cursor 재시작

1. Cursor 완전 종료
2. Cursor 다시 실행
3. 프로젝트 열기

## 🎯 기본 사용법

### Tier 0 도구 (가장 자주 사용)

```
# 1. 하이브리드 검색
@codegraph search "authentication logic"

# 2. 컨텍스트 조회
@codegraph get_context target="AuthService.login" facets=["definition", "usages", "callers"]

# 3. 그래프 슬라이싱 (버그 분석)
@codegraph graph_slice anchor="user_password" direction="backward"
```

## 🔧 문제 해결

### MCP 서버가 시작되지 않음

```bash
# Python 경로 확인
which python

# 수동 테스트
cd /Users/songmin/Documents/code-jo/semantica-v2/codegraph
source .venv/bin/activate
python apps/mcp/mcp/main.py
# Ctrl+C로 종료
```

### 검색 결과가 나오지 않음

```bash
# 수동 인덱싱
cd /Users/songmin/Documents/code-jo/semantica-v2/codegraph
source .venv/bin/activate
python -m apps.cli.cli.main index /path/to/your/project
```

또는 Cursor에서:

```
@codegraph force_reindex reason="Initial setup"
```

### API 키 오류

`.env` 파일 확인:

```bash
cat .env | grep OPENAI_API_KEY
```

없으면 추가:

```bash
echo "OPENAI_API_KEY=sk-your-actual-key-here" >> .env
```

## 📚 추가 문서

- **상세 가이드**: [SERENA_MCP_SETUP.md](SERENA_MCP_SETUP.md)
- **MCP 서버 가이드**: [README_MCP.md](README_MCP.md)
- **프로젝트 개요**: [CLAUDE.md](CLAUDE.md)

## 🎉 완료!

이제 Cursor에서 `@codegraph`를 사용하여 코드 분석을 시작할 수 있습니다!

**첫 시도:**
```
@codegraph search "main function"
```
