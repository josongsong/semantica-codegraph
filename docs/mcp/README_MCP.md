# MCP 서버 실행 가이드

## 🚀 실행 방법

### 1. 의존성 설치
```bash
pip install watchdog  # 파일 감시용 (optional)
```

### 2. MCP 서버 시작
```bash
# 방법 A: 현재 디렉토리 감시
python server/mcp_server/main.py

# 방법 B: 특정 레포 감시
CODEGRAPH_REPO_PATH=/path/to/project python server/mcp_server/main.py

# 방법 C: File watching 비활성화
CODEGRAPH_WATCH=false python server/mcp_server/main.py
```

---

## 📊 동작 방식

### 실시간 증분 인덱싱

```
1. MCP 서버 시작
   └─ File Watcher 자동 시작
   └─ TARGET_REPO_PATH 감시 시작

2. 코드 수정 (예: auth.py 편집)
   └─ File Watcher 감지 ✅
   └─ 증분 인덱싱 트리거 📦
   └─ DB 업데이트 (1-2초)

3. @codegraph search
   └─ 최신 코드로 검색! ✅
```

### Debouncing
- 같은 파일 1초 내 여러 번 수정 → 1번만 인덱싱
- 과도한 부하 방지

---

## 🎯 Cursor 통합

### Cursor 설정
`~/Library/Application Support/Cursor/User/settings.json`:

```json
{
  "mcpServers": {
    "codegraph": {
      "command": "python",
      "args": [
        "/Users/songmin/Documents/code-jo/semantica-v2/codegraph/server/mcp_server/main.py"
      ],
      "env": {
        "PYTHONPATH": "/Users/songmin/Documents/code-jo/semantica-v2/codegraph",
        "CODEGRAPH_REPO_PATH": "${workspaceFolder}",
        "CODEGRAPH_WATCH": "true"
      }
    }
  }
}
```

### 동작
```
Cursor에서 프로젝트 열면:
1. MCP 서버 자동 시작
2. 프로젝트 폴더 감시 시작
3. 코드 수정 → 자동 인덱싱
4. @codegraph search → 최신 코드 검색
```

---

## 🔧 Process 구조

```
단일 프로세스 (MCP 서버)
├─ Main Thread: MCP Protocol
├─ Async Loop: Tool execution
└─ Background Thread: File Watcher (watchdog)
     ├─ .py 수정 감지 → 증분 인덱싱
     ├─ .ts 수정 감지 → 증분 인덱싱
     └─ Debouncing (1초)
```

**별도 daemon 불필요!** 단일 프로세스로 모두 처리

---

## 💡 인덱싱 최적화

### 초기 인덱싱 (선택)
```bash
# 서버 시작 전에 bulk indexing (빠름)
python -m src.cli.main index /path/to/repo
```

### 증분 인덱싱 (자동)
```
파일 변경 → 해당 파일만 재인덱싱 (1-2초)
```

---

## 🎉 결론

**Daemon 필요 없음!**
- ✅ MCP 서버 = Single process
- ✅ File watcher = Background thread
- ✅ 자동 증분 인덱싱
- ✅ 실시간 반영

**Cursor 재시작만 하면 끝!**
