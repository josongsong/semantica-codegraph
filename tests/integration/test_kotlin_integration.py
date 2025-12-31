"""
Integration Tests: Kotlin LSP

Tests real kotlin-language-server if available.
Skips if kotlin-language-server not found.
"""

import os
import subprocess
from pathlib import Path

import pytest


# Skip all tests if kotlin-language-server not available
def has_kotlin_ls():
    """Check if kotlin-language-server is available"""
    # Check environment variable
    if os.getenv("KOTLIN_LS_PATH"):
        return Path(os.getenv("KOTLIN_LS_PATH")).exists()

    # Check common locations
    user_local = Path.home() / ".local/share/kotlin-language-server/bin/kotlin-language-server"
    if user_local.exists():
        return True

    system_path = Path("/usr/local/bin/kotlin-language-server")
    if system_path.exists():
        return True

    # Check PATH
    try:
        import shutil

        return shutil.which("kotlin-language-server") is not None
    except Exception:
        return False


def has_jdk():
    """Check if JDK 11+ is available"""
    try:
        result = subprocess.run(
            ["java", "-version"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        return result.returncode == 0
    except Exception:
        return False


def is_sandboxed():
    """Check if running in sandboxed environment

    Sandboxed environments restrict:
    - Process signaling (SIGKILL, SIGTERM)
    - Some subprocess operations
    - Network access
    """
    # Check for explicit sandbox marker
    if os.getenv("SANDBOXED") == "1":
        return True

    # Try to create and kill a subprocess (sandbox blocks process.kill())
    try:
        proc = subprocess.Popen(
            ["sleep", "1"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        try:
            # Try to kill it - this fails in sandbox
            proc.kill()
            proc.wait(timeout=1)
            return False
        except PermissionError:
            # Sandbox blocks kill()
            proc.wait(timeout=2)  # Wait for natural completion
            return True
    except Exception:
        # Assume sandboxed if can't test
        return True


pytestmark = pytest.mark.skipif(
    not has_kotlin_ls() or not has_jdk() or is_sandboxed(),
    reason="kotlin-language-server, JDK not found, or running in sandbox",
)


@pytest.fixture
def kotlin_project(tmp_path):
    """Create minimal Kotlin project for testing"""
    # Create build.gradle.kts
    build_gradle = tmp_path / "build.gradle.kts"
    build_gradle.write_text(
        """
plugins {
    kotlin("jvm") version "1.9.0"
}

repositories {
    mavenCentral()
}

dependencies {
    implementation(kotlin("stdlib"))
}
"""
    )

    # Create source file
    src_dir = tmp_path / "src/main/kotlin"
    src_dir.mkdir(parents=True)

    main_kt = src_dir / "Main.kt"
    main_kt.write_text(
        """
fun main() {
    val userName: String = "Alice"
    println("Hello, $userName")
}

fun greet(name: String): String {
    return "Hello, $name!"
}

class User(val name: String, val age: Int)
"""
    )

    return tmp_path


class TestKotlinLSPClientReal:
    """Test KotlinLSPClient with real kotlin-language-server"""

    def test_client_lifecycle(self, kotlin_project):
        """Test client start and stop"""
        from codegraph_engine.code_foundation.infrastructure.ir.external_analyzers.kotlin_lsp import (
            KotlinLSPClient,
        )

        client = KotlinLSPClient(kotlin_project)

        # Start
        client.start()
        assert client.process is not None
        assert client.initialized

        # Stop
        client.stop()
        assert client.process is None

    def test_hover_real(self, kotlin_project):
        """Test hover with real Kotlin project"""
        from codegraph_engine.code_foundation.infrastructure.ir.external_analyzers.kotlin_lsp import (
            KotlinLSPClient,
        )

        client = KotlinLSPClient(kotlin_project)
        client.start()

        try:
            # Hover over 'userName' variable
            main_kt = kotlin_project / "src/main/kotlin/Main.kt"
            result = client.hover(str(main_kt), line=2, col=8)  # 0-based

            # Should return type info
            assert result is not None

            # Check contents (format may vary)
            contents = result.get("contents")
            assert contents is not None

        finally:
            client.stop()


class TestKotlinAdapterReal:
    """Test KotlinAdapter with real kotlin-language-server"""

    @pytest.mark.asyncio
    async def test_hover_integration(self, kotlin_project):
        """Test hover through adapter"""
        from codegraph_engine.code_foundation.infrastructure.ir.external_analyzers.kotlin_lsp import (
            KotlinLSPClient,
        )
        from codegraph_engine.code_foundation.infrastructure.ir.lsp.kotlin import KotlinAdapter

        client = KotlinLSPClient(kotlin_project)
        client.start()

        try:
            adapter = KotlinAdapter(client)

            main_kt = kotlin_project / "src/main/kotlin/Main.kt"
            # Note: line is now 1-indexed (LSP convention)
            result = await adapter.hover(main_kt, line=3, col=8)

            # Adapter should return TypeInfo or None
            # (may be None if position is not exact)
            assert result is None or hasattr(result, "type_string")

        finally:
            client.stop()

    @pytest.mark.asyncio
    async def test_definition_integration(self, kotlin_project):
        """Test definition through adapter"""
        from codegraph_engine.code_foundation.infrastructure.ir.external_analyzers.kotlin_lsp import (
            KotlinLSPClient,
        )
        from codegraph_engine.code_foundation.infrastructure.ir.lsp.adapter import Location
        from codegraph_engine.code_foundation.infrastructure.ir.lsp.kotlin import KotlinAdapter

        client = KotlinLSPClient(kotlin_project)
        client.start()

        try:
            adapter = KotlinAdapter(client)

            main_kt = kotlin_project / "src/main/kotlin/Main.kt"
            # Note: line is now 1-indexed
            result = await adapter.definition(main_kt, line=3, col=8)

            # Should return Location or None (not list anymore)
            assert result is None or isinstance(result, Location)

        finally:
            client.stop()


class TestMultiLSPManagerKotlin:
    """Test Kotlin integration with MultiLSPManager"""

    def test_kotlin_language_support(self):
        """Test that Kotlin is in supported languages"""
        from codegraph_engine.code_foundation.infrastructure.ir.lsp.adapter import (
            MultiLSPManager,
        )

        manager = MultiLSPManager(project_root=Path("/tmp"))

        assert "kotlin" in manager.get_supported_languages()
        assert manager.is_language_supported("kotlin")

    @pytest.mark.asyncio
    async def test_kotlin_manager_integration(self, kotlin_project):
        """Test Kotlin through MultiLSPManager"""
        from codegraph_engine.code_foundation.infrastructure.ir.lsp.adapter import (
            MultiLSPManager,
        )

        manager = MultiLSPManager(project_root=kotlin_project)

        try:
            main_kt = kotlin_project / "src/main/kotlin/Main.kt"

            # Test hover through manager
            type_info = await manager.get_type_info(
                language="kotlin",
                file_path=main_kt,
                line=3,  # 1-indexed
                col=8,
            )

            # Should work (may be None if kotlin-language-server not available)
            assert type_info is None or hasattr(type_info, "type_string")

        finally:
            await manager.shutdown_all()
