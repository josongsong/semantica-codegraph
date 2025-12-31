"""
Java LSP Adapter (Eclipse JDT Language Server)

Eclipse JDT.LS를 사용한 Java 코드 분석.
"""

import re
from pathlib import Path

from codegraph_shared.common.observability import get_logger
from codegraph_engine.code_foundation.infrastructure.ir.lsp.adapter import Diagnostic, Location, TypeInfo
from codegraph_engine.code_foundation.infrastructure.ir.lsp.jdtls_client import JdtlsClient

logger = get_logger(__name__)


class JdtlsAdapter:
    """
    Java LSP adapter (Eclipse JDT.LS).

    Features:
    - Type information (hover)
    - Go to definition
    - Find references
    - Diagnostics (compile errors, warnings)
    """

    def __init__(self, project_root: Path, jdtls_path: Path | None = None):
        """
        Initialize JDT.LS adapter.

        Args:
            project_root: Project root directory (should contain pom.xml or build.gradle)
            jdtls_path: JDT.LS installation path (optional, auto-detected if None)
        """
        self.project_root = project_root
        self.logger = logger
        self._client: JdtlsClient | None = None
        self._jdtls_path = jdtls_path
        self._started = False

    async def _ensure_started(self) -> None:
        """Ensure JDT.LS client is started"""
        if self._started and self._client:
            return

        try:
            self._client = JdtlsClient(self.project_root, self._jdtls_path)
            await self._client.start()
            self._started = True
            self.logger.info("JDT.LS started successfully")
        except FileNotFoundError as e:
            self.logger.error(f"JDT.LS not found: {e}")
            self.logger.info("Install JDT.LS: https://download.eclipse.org/jdtls/snapshots/")
            raise
        except Exception as e:
            self.logger.error(f"Failed to start JDT.LS: {e}")
            raise

    async def hover(
        self,
        file_path: Path,
        line: int,
        col: int,
    ) -> TypeInfo | None:
        """
        Get type information at position.

        Example:
        - Variable: String message -> "java.lang.String"
        - Method: void printMessage() -> "void"
        - Class: HelloWorld -> "com.example.HelloWorld"
        """
        try:
            await self._ensure_started()

            if not self._client:
                return None

            result = await self._client.hover(file_path, line, col)

            if not result:
                return None

            # Parse hover contents
            contents = result.get("contents")
            if not contents:
                return None

            # Extract type string
            type_string = ""
            documentation = ""

            if isinstance(contents, dict):
                # Markdown content
                value = contents.get("value", "")
                type_string = self._extract_type_from_markdown(value)
                documentation = value
            elif isinstance(contents, str):
                type_string = self._extract_type_from_markdown(contents)
                documentation = contents
            elif isinstance(contents, list):
                # Array of MarkedString
                for item in contents:
                    if isinstance(item, dict):
                        value = item.get("value", "")
                    else:
                        value = str(item)

                    if not type_string:
                        type_string = self._extract_type_from_markdown(value)
                    documentation += value + "\n"

            if not type_string:
                return None

            return TypeInfo(
                type_string=type_string.strip(),
                documentation=documentation.strip(),
                is_nullable=False,  # Java doesn't have native nullable types
                is_union=False,
            )

        except Exception as e:
            self.logger.debug(f"JDT.LS hover failed at {file_path}:{line}:{col}: {e}")
            return None

    def _extract_type_from_markdown(self, markdown: str) -> str:
        """
        Extract type from Java signature in Markdown.

        Example:
        - "```java\nString message\n```" -> "String"
        - "public void printMessage()" -> "void"
        """
        # Remove markdown code blocks
        code = re.sub(r"```\w*\n?", "", markdown)
        code = code.strip()

        # Try to extract type from common patterns

        # Pattern 1: "Type variable" (field/variable)
        match = re.match(r"(\w+(?:\.\w+)*(?:<[^>]+>)?)\s+\w+", code)
        if match:
            return match.group(1)

        # Pattern 2: "modifier Type method(...)" (method)
        match = re.search(r"(?:public|private|protected|static)?\s*(\w+(?:\.\w+)*(?:<[^>]+>)?)\s+\w+\s*\(", code)
        if match:
            return match.group(1)

        # Pattern 3: "class ClassName" or "interface InterfaceName"
        match = re.search(r"(?:class|interface|enum)\s+(\w+)", code)
        if match:
            return match.group(1)

        # Fallback: first word that looks like a type
        words = code.split()
        for word in words:
            if word and word[0].isupper() and word not in ["public", "private", "protected", "static", "final"]:
                return word

        return code

    async def definition(
        self,
        file_path: Path,
        line: int,
        col: int,
    ) -> Location | None:
        """
        Get definition location.

        Example:
        - Go to method definition
        - Go to class declaration
        - Go to variable declaration
        """
        try:
            await self._ensure_started()

            if not self._client:
                return None

            results = await self._client.definition(file_path, line, col)

            if not results:
                return None

            # Return first definition
            loc = results[0]
            uri = loc["uri"]

            # Remove "file://" prefix
            if uri.startswith("file://"):
                uri = uri[7:]

            pos = loc["range"]["start"]

            return Location(
                file_path=uri,
                line=pos["line"] + 1,  # Convert to 1-indexed
                column=pos["character"],
            )

        except Exception as e:
            self.logger.debug(f"JDT.LS definition failed at {file_path}:{line}:{col}: {e}")
            return None

    async def references(
        self,
        file_path: Path,
        line: int,
        col: int,
        include_declaration: bool = True,
    ) -> list[Location]:
        """
        Find all references to symbol.

        Example:
        - Find all calls to a method
        - Find all usages of a field
        """
        try:
            await self._ensure_started()

            if not self._client:
                return []

            results = await self._client.references(file_path, line, col, include_declaration)

            locations = []
            for ref in results:
                uri = ref["uri"]

                # Remove "file://" prefix
                if uri.startswith("file://"):
                    uri = uri[7:]

                pos = ref["range"]["start"]

                locations.append(
                    Location(
                        file_path=uri,
                        line=pos["line"] + 1,  # Convert to 1-indexed
                        column=pos["character"],
                    )
                )

            return locations

        except Exception as e:
            self.logger.debug(f"JDT.LS references failed at {file_path}:{line}:{col}: {e}")
            return []

    async def diagnostics(
        self,
        file_path: Path,
    ) -> list[Diagnostic]:
        """
        Get diagnostics (errors, warnings).

        Note: JDT.LS publishes diagnostics via publishDiagnostics notification.
        This is a placeholder - diagnostics should be collected from notifications.
        """
        # TODO: Implement diagnostics collection from publishDiagnostics notifications
        # For now, return empty list
        return []

    async def shutdown(self) -> None:
        """Shutdown JDT.LS server"""
        if self._client:
            try:
                await self._client.shutdown()
                self.logger.info("JDT.LS shutdown complete")
            except Exception as e:
                self.logger.warning(f"JDT.LS shutdown error: {e}")
            finally:
                self._client = None
                self._started = False


# ============================================================
# Implementation Notes
# ============================================================

"""
JDT.LS 통합 가이드:

1. JDT.LS 설치
   ```bash
   # Download from https://download.eclipse.org/jdtls/snapshots/
   # Or use VSCode's bundled version
   ```

2. LSP 클라이언트 구현
   ```python
   from pygls.lsp.client import LanguageClient

   class JdtlsClient:
       def __init__(self, project_root: Path):
           self.client = LanguageClient()
           # Start JDT.LS server
           self.client.start_io(
               "java",
               ["-jar", "path/to/jdtls/plugins/org.eclipse.equinox.launcher_*.jar"]
           )
   ```

3. Workspace 설정
   - Maven: pom.xml 인식
   - Gradle: build.gradle 인식
   - Classpath: .classpath 자동 생성

4. 성능 고려사항
   - JDT.LS는 초기 인덱싱에 시간이 걸림 (대형 프로젝트: ~30초)
   - 캐싱 사용 권장
   - 백그라운드 초기화

5. 참고 구현
   - vscode-java: https://github.com/redhat-developer/vscode-java
   - coc-java: https://github.com/neoclide/coc-java
"""
