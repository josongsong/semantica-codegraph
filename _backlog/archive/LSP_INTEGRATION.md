# Java LSP 통합 상태

## 현황

### ✓ 완료
1. **LSP Adapter Skeleton 생성**
   - 파일: `src/contexts/code_foundation/infrastructure/ir/lsp/jdtls.py`
   - JdtlsAdapter 클래스 정의
   - 인터페이스: hover, definition, references, diagnostics

2. **MultiLSPManager 통합**
   - `adapter.py`에 Java 언어 추가
   - `get_supported_languages()`에 "java" 추가
   - 자동 라우팅 지원

3. **SOTAIRBuilder 통합**
   - `_detect_language()`에 `.java` 확장자 추가
   - Type enrichment 파이프라인에 Java 포함

### ⏳ Skeleton (실제 구현 필요)

**JDT.LS (Eclipse JDT Language Server) 구현 필요**:

```python
# 현재 상태: Skeleton
async def hover(self, file_path: Path, line: int, col: int) -> TypeInfo | None:
    # TODO: Implement hover request
    return None

# 필요한 구현:
async def hover(self, file_path: Path, line: int, col: int) -> TypeInfo | None:
    result = await self.client.request("textDocument/hover", {
        "textDocument": {"uri": f"file://{file_path}"},
        "position": {"line": line - 1, "character": col}
    })
    # Parse and return TypeInfo
```

## 구현 가이드

### 1. JDT.LS 설치

```bash
# Option 1: Maven Central에서 다운로드
wget https://download.eclipse.org/jdtls/snapshots/jdt-language-server-latest.tar.gz
tar -xzf jdt-language-server-latest.tar.gz

# Option 2: VSCode에서 추출
# ~/.vscode/extensions/redhat.java-*/server/
```

### 2. LSP 클라이언트 구현

**Option A: pygls 사용** (권장)

```python
from pygls.lsp.client import LanguageClient
from pathlib import Path

class JdtlsClient:
    def __init__(self, project_root: Path):
        self.project_root = project_root
        self.client = LanguageClient()
        
        # JDT.LS 시작
        java_cmd = [
            "java",
            "-Declipse.application=org.eclipse.jdt.ls.core.id1",
            "-Dosgi.bundles.defaultStartLevel=4",
            "-jar", str(jdtls_launcher_jar),
            "-configuration", str(config_dir),
            "-data", str(workspace_dir)
        ]
        
        self.client.start_io(*java_cmd)
        
    async def initialize(self):
        await self.client.initialize(
            processId=os.getpid(),
            rootUri=f"file://{self.project_root}",
            capabilities={...}
        )
```

**Option B: subprocess + JSON-RPC**

```python
import subprocess
import json

class JdtlsClient:
    def __init__(self, project_root: Path):
        self.process = subprocess.Popen(
            java_cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
        self._send_request("initialize", {...})
```

### 3. 주요 메서드 구현

**Hover (타입 정보)**:

```python
async def hover(self, file_path: Path, line: int, col: int) -> TypeInfo | None:
    params = {
        "textDocument": {"uri": f"file://{file_path}"},
        "position": {"line": line - 1, "character": col}
    }
    
    result = await self.client.request("textDocument/hover", params)
    
    if not result:
        return None
    
    # Parse Markdown content
    contents = result.get("contents", {})
    if isinstance(contents, dict):
        value = contents.get("value", "")
    else:
        value = str(contents)
    
    # Extract type from Java signature
    # Example: "String message" -> "java.lang.String"
    type_string = self._extract_type(value)
    
    return TypeInfo(
        type_string=type_string,
        documentation=value,
        is_nullable=False,  # Java doesn't have native nullable types
        is_union=False,
    )
```

**Definition**:

```python
async def definition(self, file_path: Path, line: int, col: int) -> Location | None:
    params = {
        "textDocument": {"uri": f"file://{file_path}"},
        "position": {"line": line - 1, "character": col}
    }
    
    result = await self.client.request("textDocument/definition", params)
    
    if not result or not isinstance(result, list):
        return None
    
    # Return first definition
    loc = result[0]
    uri = loc["uri"].replace("file://", "")
    pos = loc["range"]["start"]
    
    return Location(
        file_path=uri,
        line=pos["line"] + 1,
        column=pos["character"],
    )
```

**References**:

```python
async def references(
    self,
    file_path: Path,
    line: int,
    col: int,
    include_declaration: bool = True,
) -> list[Location]:
    params = {
        "textDocument": {"uri": f"file://{file_path}"},
        "position": {"line": line - 1, "character": col},
        "context": {"includeDeclaration": include_declaration}
    }
    
    results = await self.client.request("textDocument/references", params)
    
    locations = []
    for ref in results or []:
        uri = ref["uri"].replace("file://", "")
        pos = ref["range"]["start"]
        locations.append(Location(
            file_path=uri,
            line=pos["line"] + 1,
            column=pos["character"],
        ))
    
    return locations
```

### 4. 워크스페이스 설정

JDT.LS는 Maven/Gradle 프로젝트 인식:

```python
def _detect_build_system(self, project_root: Path) -> str:
    if (project_root / "pom.xml").exists():
        return "maven"
    elif (project_root / "build.gradle").exists() or (project_root / "build.gradle.kts").exists():
        return "gradle"
    else:
        return "unknown"
```

### 5. 성능 최적화

```python
class JdtlsAdapter:
    def __init__(self, project_root: Path):
        # Lazy initialization
        self._client = None
        self._initialized = False
        
    async def _ensure_initialized(self):
        if not self._initialized:
            self._client = JdtlsClient(self.project_root)
            await self._client.initialize()
            self._initialized = True
            
    async def hover(self, ...):
        await self._ensure_initialized()
        return await self._client.hover(...)
```

## 테스트

```python
# test_jdtls_integration.py
async def test_java_hover():
    adapter = JdtlsAdapter(Path("test_project"))
    
    type_info = await adapter.hover(
        Path("src/main/java/Example.java"),
        line=5,
        col=10
    )
    
    assert type_info is not None
    assert "String" in type_info.type_string
```

## 검증

```bash
python verify_java_support.py
```

추가 확인 항목:
- [ ] JDT.LS 서버 시작
- [ ] Hover 응답
- [ ] Definition 응답
- [ ] References 응답
- [ ] Diagnostics 수신

## 참고 자료

- [Eclipse JDT.LS](https://github.com/eclipse/eclipse.jdt.ls)
- [LSP Specification](https://microsoft.github.io/language-server-protocol/)
- [pygls Documentation](https://pygls.readthedocs.io/)
- [VSCode Java Extension](https://github.com/redhat-developer/vscode-java)

## 현재 상태 요약

| 컴포넌트 | 상태 | 비고 |
|---------|------|------|
| IR Generator | ✅ 완료 | JavaIRGenerator 구현됨 |
| Parser | ✅ 완료 | tree-sitter-java |
| LSP Skeleton | ✅ 완료 | jdtls.py 생성됨 |
| LSP Implementation | ⏳ TODO | JDT.LS 클라이언트 필요 |
| Type Enrichment | ⏳ Partial | Skeleton 연동됨, 실제 타입은 안 옴 |

**추정 작업 시간**: 4-6시간 (JDT.LS 클라이언트 구현)
