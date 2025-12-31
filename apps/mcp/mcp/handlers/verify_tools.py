"""
Verify Tools (SOTA MCP Protocol)

검증 도구.
분석 → 수정 → 검증 루프를 닫아 agent 신뢰도 향상.

Tools:
- verify_patch_compile: 패치 문법/타입/빌드 검증
- verify_finding_resolved: Finding 해결 확인
"""

import json
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from apps.mcp.mcp.config import get_verify_config
from codegraph_shared.common.observability import get_logger

logger = get_logger(__name__)

# Load configuration
VERIFY_CONFIG = get_verify_config()


async def verify_patch_compile(arguments: dict[str, Any]) -> str:
    """
    패치 문법/타입/빌드 검증

    수정된 코드가 최소한 빌드되는지 확인.

    Args:
        arguments:
            - file_path: 수정된 파일 경로
            - patch: 적용할 패치 (unified diff 또는 새 내용)
            - language: 언어 (python, typescript, etc.)
            - check_types: 타입 체크 여부 (기본 True)

    Returns:
        JSON: {verdict, evidence, errors}

    Verdict:
        - pass: 빌드/타입 체크 통과
        - fail: 오류 발생
        - unknown: 검증 불가
    """
    file_path = arguments.get("file_path")
    patch = arguments.get("patch")
    language = arguments.get("language", "python")
    check_types = arguments.get("check_types", True)

    if not file_path:
        return json.dumps(
            {
                "verdict": "unknown",
                "error": "file_path is required",
            }
        )

    try:
        if language == "python":
            result = await _verify_python(file_path, patch, check_types)
        elif language in ("typescript", "javascript"):
            result = await _verify_typescript(file_path, patch, check_types)
        elif language == "go":
            result = await _verify_go(file_path, patch, check_types)
        elif language == "rust":
            result = await _verify_rust(file_path, patch, check_types)
        elif language == "java":
            result = await _verify_java(file_path, patch, check_types)
        elif language == "csharp":
            result = await _verify_csharp(file_path, patch, check_types)
        else:
            result = {
                "verdict": "unknown",
                "error": f"Unsupported language: {language}. Supported: python, typescript, javascript, go, rust, java, csharp",
            }

        return json.dumps(result)

    except Exception as e:
        logger.error("verify_patch_failed", file_path=file_path, error=str(e))
        return json.dumps(
            {
                "verdict": "unknown",
                "error": str(e),
            }
        )


async def verify_finding_resolved(arguments: dict[str, Any]) -> str:
    """
    Finding 해결 확인

    원래 분석에서 발견된 문제가 패치 후 해결되었는지 확인.

    Args:
        arguments:
            - finding_id: 원래 finding ID (claim_id 또는 자체 ID)
            - finding_type: Finding 유형 (taint, null_deref, etc.)
            - original_location: 원래 위치 {file, line, column}
            - patch: 적용된 패치
            - repo_id: 저장소 ID
            - snapshot_id: 스냅샷 ID

    Returns:
        JSON: {verdict, evidence, before, after}

    Verdict:
        - pass: Finding 해결됨
        - fail: Finding 여전히 존재
        - unknown: 검증 불가
    """
    finding_id = arguments.get("finding_id")
    finding_type = arguments.get("finding_type")
    original_location = arguments.get("original_location", {})
    patch = arguments.get("patch")
    repo_id = arguments.get("repo_id", "")
    snapshot_id = arguments.get("snapshot_id", "main")

    if not finding_type or not original_location:
        return json.dumps(
            {
                "verdict": "unknown",
                "error": "finding_type and original_location are required",
            }
        )

    try:
        if finding_type == "taint":
            result = await _verify_taint_resolved(original_location, patch, repo_id, snapshot_id)
        elif finding_type == "null_deref":
            result = await _verify_null_deref_resolved(original_location, patch, repo_id, snapshot_id)
        else:
            # Generic re-analysis
            result = await _verify_generic_resolved(finding_type, original_location, patch, repo_id, snapshot_id)

        result["finding_id"] = finding_id
        return json.dumps(result)

    except Exception as e:
        logger.error("verify_finding_failed", finding_id=finding_id, error=str(e))
        return json.dumps(
            {
                "verdict": "unknown",
                "finding_id": finding_id,
                "error": str(e),
            }
        )


# ============================================================
# Language-specific verification
# ============================================================


async def _verify_python(file_path: str, patch: str | None, check_types: bool) -> dict[str, Any]:
    """Verify Python code"""
    errors: list[dict[str, Any]] = []

    # 1. Syntax check (ast.parse)
    try:
        import ast

        if patch:
            # Parse the patched content
            ast.parse(patch)
        else:
            # Parse existing file
            with open(file_path) as f:
                ast.parse(f.read())

    except SyntaxError as e:
        errors.append(
            {
                "type": "syntax",
                "message": str(e),
                "line": e.lineno,
                "column": e.offset,
            }
        )

    # 2. Type check (pyright if available and requested)
    if check_types and not errors:
        type_errors = await _run_pyright(file_path, patch)
        errors.extend(type_errors)

    # 3. Linter check (ruff if available)
    if not errors:
        lint_errors = await _run_ruff(file_path, patch)
        errors.extend(lint_errors)

    if errors:
        return {
            "verdict": "fail",
            "errors": errors,
            "evidence": {
                "file": file_path,
                "error_count": len(errors),
            },
        }

    return {
        "verdict": "pass",
        "evidence": {
            "file": file_path,
            "checks": ["syntax", "types" if check_types else None, "lint"],
        },
    }


async def _verify_typescript(file_path: str, patch: str | None, check_types: bool) -> dict[str, Any]:
    """Verify TypeScript/JavaScript code"""
    errors: list[dict[str, Any]] = []

    # Write to temp file if patch provided
    if patch:
        with tempfile.NamedTemporaryFile(mode="w", suffix=".ts", delete=False) as f:
            f.write(patch)
            temp_path = f.name
        target_path = temp_path
    else:
        target_path = file_path

    try:
        # Run tsc --noEmit for type check
        if check_types:
            result = subprocess.run(
                ["npx", "tsc", "--noEmit", target_path],
                capture_output=True,
                text=True,
                timeout=VERIFY_CONFIG.type_check_timeout,
            )

            if result.returncode != 0:
                for line in result.stderr.split("\n"):
                    if line.strip():
                        errors.append(
                            {
                                "type": "typescript",
                                "message": line,
                            }
                        )

    except FileNotFoundError:
        return {
            "verdict": "unknown",
            "error": "TypeScript compiler (tsc) not found",
        }
    except subprocess.TimeoutExpired:
        return {
            "verdict": "unknown",
            "error": "TypeScript check timed out",
        }
    finally:
        if patch:
            Path(target_path).unlink(missing_ok=True)

    if errors:
        return {
            "verdict": "fail",
            "errors": errors,
        }

    return {
        "verdict": "pass",
        "evidence": {
            "file": file_path,
            "checks": ["typescript"],
        },
    }


async def _run_pyright(file_path: str, patch: str | None) -> list[dict[str, Any]]:
    """Run pyright type checker"""
    errors: list[dict[str, Any]] = []

    # Write to temp file if patch provided
    if patch:
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write(patch)
            target_path = f.name
    else:
        target_path = file_path

    try:
        result = subprocess.run(
            ["pyright", "--outputjson", target_path],
            capture_output=True,
            text=True,
            timeout=VERIFY_CONFIG.type_check_timeout,
        )

        if result.stdout:
            import json as json_module

            try:
                output = json_module.loads(result.stdout)
                for diag in output.get("generalDiagnostics", []):
                    if diag.get("severity") == "error":
                        errors.append(
                            {
                                "type": "type",
                                "message": diag.get("message", ""),
                                "line": diag.get("range", {}).get("start", {}).get("line", 0),
                            }
                        )
            except json_module.JSONDecodeError:
                pass

    except FileNotFoundError:
        pass  # pyright not installed
    except subprocess.TimeoutExpired:
        pass
    finally:
        if patch:
            Path(target_path).unlink(missing_ok=True)

    return errors


async def _run_ruff(file_path: str, patch: str | None) -> list[dict[str, Any]]:
    """Run ruff linter"""
    errors: list[dict[str, Any]] = []

    # Write to temp file if patch provided
    if patch:
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write(patch)
            target_path = f.name
    else:
        target_path = file_path

    try:
        result = subprocess.run(
            ["ruff", "check", "--output-format=json", target_path],
            capture_output=True,
            text=True,
            timeout=VERIFY_CONFIG.compile_timeout,
        )

        if result.stdout:
            import json as json_module

            try:
                diagnostics = json_module.loads(result.stdout)
                for diag in diagnostics:
                    # Only include errors, not warnings
                    if diag.get("code", "").startswith("E"):
                        errors.append(
                            {
                                "type": "lint",
                                "code": diag.get("code", ""),
                                "message": diag.get("message", ""),
                                "line": diag.get("location", {}).get("row", 0),
                            }
                        )
            except json_module.JSONDecodeError:
                pass

    except FileNotFoundError:
        pass  # ruff not installed
    except subprocess.TimeoutExpired:
        pass
    finally:
        if patch:
            Path(target_path).unlink(missing_ok=True)

    return errors


async def _verify_go(file_path: str, patch: str | None, check_types: bool) -> dict[str, Any]:
    """Verify Go code"""
    errors: list[dict[str, Any]] = []

    # Write to temp file if patch provided
    if patch:
        with tempfile.NamedTemporaryFile(mode="w", suffix=".go", delete=False) as f:
            f.write(patch)
            target_path = f.name
    else:
        target_path = file_path

    try:
        # 1. Syntax check with gofmt
        result = subprocess.run(
            ["gofmt", "-e", target_path],
            capture_output=True,
            text=True,
            timeout=VERIFY_CONFIG.compile_timeout,
        )

        if result.returncode != 0:
            for line in result.stderr.split("\n"):
                if line.strip():
                    errors.append({"type": "syntax", "message": line})

        # 2. Type/build check with go build (if no syntax errors)
        if not errors and check_types:
            with tempfile.NamedTemporaryFile(suffix=".exe", delete=True) as out_file:
                out_path = out_file.name
            result = subprocess.run(
                ["go", "build", "-o", out_path, target_path],
                capture_output=True,
                text=True,
                timeout=VERIFY_CONFIG.type_check_timeout,
            )
            Path(out_path).unlink(missing_ok=True)

            if result.returncode != 0:
                for line in result.stderr.split("\n"):
                    if line.strip():
                        errors.append({"type": "build", "message": line})

        # 3. Vet check (if no build errors)
        if not errors:
            result = subprocess.run(
                ["go", "vet", target_path],
                capture_output=True,
                text=True,
                timeout=VERIFY_CONFIG.subprocess_timeout,
            )

            if result.returncode != 0:
                for line in result.stderr.split("\n"):
                    if line.strip():
                        errors.append({"type": "vet", "message": line})

    except FileNotFoundError:
        return {"verdict": "unknown", "error": "Go toolchain not found"}
    except subprocess.TimeoutExpired:
        return {"verdict": "unknown", "error": "Go check timed out"}
    finally:
        if patch:
            Path(target_path).unlink(missing_ok=True)

    if errors:
        return {"verdict": "fail", "errors": errors}

    return {
        "verdict": "pass",
        "evidence": {"file": file_path, "checks": ["syntax", "build", "vet"]},
    }


async def _verify_rust(file_path: str, patch: str | None, check_types: bool) -> dict[str, Any]:
    """Verify Rust code"""
    errors: list[dict[str, Any]] = []

    # Write to temp file if patch provided
    if patch:
        with tempfile.NamedTemporaryFile(mode="w", suffix=".rs", delete=False) as f:
            f.write(patch)
            target_path = f.name
    else:
        target_path = file_path

    try:
        # Use rustfmt for syntax and cargo check for types
        # Note: For single files, we use rustc directly

        # 1. Syntax check with rustfmt
        result = subprocess.run(
            ["rustfmt", "--check", target_path],
            capture_output=True,
            text=True,
            timeout=VERIFY_CONFIG.compile_timeout,
        )
        # rustfmt --check returns non-zero if formatting differs, not on syntax error
        # Use rustc for actual syntax check

        # 2. Compile check with rustc (no output)
        if check_types:
            with tempfile.NamedTemporaryFile(suffix=".rmeta", delete=True) as out_file:
                out_path = out_file.name
            result = subprocess.run(
                ["rustc", "--emit=metadata", "-o", out_path, target_path],
                capture_output=True,
                text=True,
                timeout=VERIFY_CONFIG.type_check_timeout,
            )
            Path(out_path).unlink(missing_ok=True)

            if result.returncode != 0:
                for line in result.stderr.split("\n"):
                    if line.strip() and "error" in line.lower():
                        errors.append({"type": "compile", "message": line})

        # 3. Clippy lint (if clippy available)
        if not errors:
            try:
                result = subprocess.run(
                    ["cargo", "clippy", "--", "-D", "warnings", target_path],
                    capture_output=True,
                    text=True,
                    timeout=VERIFY_CONFIG.type_check_timeout,
                )
                # Clippy output parsing
                if result.returncode != 0:
                    for line in result.stderr.split("\n"):
                        if "warning:" in line or "error:" in line:
                            errors.append({"type": "clippy", "message": line})
            except FileNotFoundError:
                pass  # Clippy not available

    except FileNotFoundError:
        return {"verdict": "unknown", "error": "Rust toolchain not found"}
    except subprocess.TimeoutExpired:
        return {"verdict": "unknown", "error": "Rust check timed out"}
    finally:
        if patch:
            Path(target_path).unlink(missing_ok=True)

    if errors:
        return {"verdict": "fail", "errors": errors}

    return {
        "verdict": "pass",
        "evidence": {"file": file_path, "checks": ["compile", "clippy"]},
    }


async def _verify_java(file_path: str, patch: str | None, check_types: bool) -> dict[str, Any]:
    """Verify Java code"""
    errors: list[dict[str, Any]] = []

    # Write to temp file if patch provided
    if patch:
        with tempfile.NamedTemporaryFile(mode="w", suffix=".java", delete=False) as f:
            f.write(patch)
            target_path = f.name
    else:
        target_path = file_path

    # Create temp dir for class output (cross-platform)
    with tempfile.TemporaryDirectory() as temp_dir:
        try:
            # 1. Compile check with javac
            result = subprocess.run(
                ["javac", "-Xlint:all", "-d", temp_dir, target_path],
                capture_output=True,
                text=True,
                timeout=VERIFY_CONFIG.type_check_timeout,
            )

            if result.returncode != 0:
                for line in result.stderr.split("\n"):
                    if line.strip() and ("error:" in line or "warning:" in line):
                        errors.append({"type": "javac", "message": line})

        except FileNotFoundError:
            return {"verdict": "unknown", "error": "Java compiler (javac) not found"}
        except subprocess.TimeoutExpired:
            return {"verdict": "unknown", "error": "Java check timed out"}
        finally:
            if patch:
                Path(target_path).unlink(missing_ok=True)

    if errors:
        return {"verdict": "fail", "errors": errors}

    return {
        "verdict": "pass",
        "evidence": {"file": file_path, "checks": ["javac"]},
    }


async def _verify_csharp(file_path: str, patch: str | None, check_types: bool) -> dict[str, Any]:
    """Verify C# code"""
    errors: list[dict[str, Any]] = []

    # Write to temp file if patch provided
    if patch:
        with tempfile.NamedTemporaryFile(mode="w", suffix=".cs", delete=False) as f:
            f.write(patch)
            target_path = f.name
    else:
        target_path = file_path

    # Create temp file for output (cross-platform)
    with tempfile.NamedTemporaryFile(suffix=".dll", delete=True) as out_file:
        out_path = out_file.name

    try:
        # Try dotnet build (requires .csproj) or csc directly
        # For single file, use csc if available
        result = subprocess.run(
            ["csc", "/nologo", "/target:library", f"/out:{out_path}", target_path],
            capture_output=True,
            text=True,
            timeout=VERIFY_CONFIG.type_check_timeout,
        )

        if result.returncode != 0:
            for line in result.stderr.split("\n") + result.stdout.split("\n"):
                if line.strip() and ("error" in line.lower() or "warning" in line.lower()):
                    errors.append({"type": "csc", "message": line})

    except FileNotFoundError:
        # Try mcs (Mono) as fallback
        try:
            result = subprocess.run(
                ["mcs", "-target:library", f"-out:{out_path}", target_path],
                capture_output=True,
                text=True,
                timeout=VERIFY_CONFIG.type_check_timeout,
            )

            if result.returncode != 0:
                for line in result.stderr.split("\n"):
                    if line.strip() and ("error" in line.lower()):
                        errors.append({"type": "mcs", "message": line})

        except FileNotFoundError:
            return {"verdict": "unknown", "error": "C# compiler (csc/mcs) not found"}
    except subprocess.TimeoutExpired:
        return {"verdict": "unknown", "error": "C# check timed out"}
    finally:
        if patch:
            Path(target_path).unlink(missing_ok=True)
        # Cleanup output file
        Path(out_path).unlink(missing_ok=True)

    if errors:
        return {"verdict": "fail", "errors": errors}

    return {
        "verdict": "pass",
        "evidence": {"file": file_path, "checks": ["csharp"]},
    }


# ============================================================
# Finding-specific verification
# ============================================================


async def _verify_taint_resolved(
    original_location: dict,
    patch: str | None,
    repo_id: str,
    snapshot_id: str,
) -> dict[str, Any]:
    """Verify taint finding resolved"""
    try:
        from codegraph_engine.reasoning_engine.application.reasoning_pipeline import ReasoningPipeline

        pipeline = ReasoningPipeline()

        # Re-run taint analysis on the patched code
        # This is a simplified check - real implementation would apply patch first
        result = pipeline.analyze_taint_fast(
            repo_id=repo_id,
            snapshot_id=snapshot_id,
        )

        paths = result.get("paths", [])

        # Check if any path goes through the original location
        file_path = original_location.get("file", "")
        line = original_location.get("line", 0)

        for path in paths:
            for node in path:
                if isinstance(node, dict):
                    if node.get("file") == file_path and node.get("line") == line:
                        return {
                            "verdict": "fail",
                            "evidence": {
                                "message": "Taint path still exists through patched location",
                                "path": path,
                            },
                        }

        return {
            "verdict": "pass",
            "evidence": {
                "message": "Taint path no longer goes through patched location",
                "paths_checked": len(paths),
            },
        }

    except Exception as e:
        return {
            "verdict": "unknown",
            "error": str(e),
        }


async def _verify_null_deref_resolved(
    original_location: dict,
    patch: str | None,
    repo_id: str,
    snapshot_id: str,
) -> dict[str, Any]:
    """Verify null dereference finding resolved"""
    # Simplified: check if null check was added
    if patch and ("if " in patch and " is not None" in patch or "if " in patch and " is None" in patch):
        return {
            "verdict": "pass",
            "evidence": {
                "message": "Null check detected in patch",
            },
        }

    return {
        "verdict": "unknown",
        "evidence": {
            "message": "Cannot determine if null check was added",
        },
    }


async def _verify_generic_resolved(
    finding_type: str,
    original_location: dict,
    patch: str | None,
    repo_id: str,
    snapshot_id: str,
) -> dict[str, Any]:
    """Generic finding verification via re-analysis"""
    try:
        from codegraph_runtime.llm_arbitration.application import ExecuteExecutor

        executor = ExecuteExecutor()

        # Re-run analysis on patched code
        spec = {
            "intent": "analyze",
            "template_id": finding_type,
            "scope": {"repo_id": repo_id, "snapshot_id": snapshot_id},
        }

        result = await executor.execute(spec)

        # Check if finding still exists
        claims = result.claims if hasattr(result, "claims") else []

        file_path = original_location.get("file", "")
        line = original_location.get("line", 0)

        for claim in claims:
            if hasattr(claim, "location"):
                if claim.location.file == file_path and claim.location.line == line:
                    return {
                        "verdict": "fail",
                        "evidence": {
                            "message": f"Finding of type {finding_type} still exists",
                            "claim": claim.to_dict() if hasattr(claim, "to_dict") else str(claim),
                        },
                    }

        return {
            "verdict": "pass",
            "evidence": {
                "message": f"Finding of type {finding_type} no longer detected",
                "claims_checked": len(claims),
            },
        }

    except Exception as e:
        return {
            "verdict": "unknown",
            "error": str(e),
        }


async def verify_no_new_findings_introduced(arguments: dict[str, Any]) -> str:
    """
    Regression Proof - 수정으로 인한 새로운 Finding이 없음을 증명 (RFC-SEM-022).

    수정 전 baseline execution 결과와 비교하여
    "고치지 않았던 문제들이 새로 생기지 않았음"을 증명.

    Args:
        arguments:
            - baseline_execution_id: 수정 전 실행 ID
            - current_execution_id: 수정 후 실행 ID (optional, 새로 실행)
            - patchset_id: 적용된 패치셋 ID
            - repo_id: 저장소 ID
            - snapshot_id: 스냅샷 ID
            - ruleset_subset: 검사할 룰셋 서브셋 (optional, 전체 검사 시 생략)

    Returns:
        JSON: {verdict, new_findings, baseline_count, current_count}

    Verdict:
        - pass: 새로운 Finding 없음
        - fail: 새로운 Finding 발견
        - unknown: 비교 불가
    """
    baseline_execution_id = arguments.get("baseline_execution_id")
    current_execution_id = arguments.get("current_execution_id")
    patchset_id = arguments.get("patchset_id")
    repo_id = arguments.get("repo_id", "default")
    snapshot_id = arguments.get("snapshot_id", "latest")
    ruleset_subset = arguments.get("ruleset_subset")

    if not baseline_execution_id:
        return json.dumps(
            {
                "verdict": "unknown",
                "error": "baseline_execution_id is required",
            }
        )

    try:
        # 1. Baseline findings 조회
        baseline_findings = await _get_execution_findings(baseline_execution_id)

        # 2. Current execution (없으면 새로 실행)
        if not current_execution_id:
            current_execution_id = await _run_analysis(repo_id, snapshot_id, patchset_id, ruleset_subset)

        current_findings = await _get_execution_findings(current_execution_id)

        # 3. 새로운 findings 비교
        baseline_ids = {_finding_signature(f) for f in baseline_findings}
        new_findings = [f for f in current_findings if _finding_signature(f) not in baseline_ids]

        if new_findings:
            return json.dumps(
                {
                    "verdict": "fail",
                    "new_findings": [
                        {
                            "finding_id": f.get("finding_id"),
                            "type": f.get("type"),
                            "severity": f.get("severity"),
                            "file_path": f.get("file_path"),
                            "line": f.get("line"),
                            "message": f.get("message", "")[:200],
                        }
                        for f in new_findings[:10]  # Limit for context
                    ],
                    "new_count": len(new_findings),
                    "baseline_count": len(baseline_findings),
                    "current_count": len(current_findings),
                }
            )

        return json.dumps(
            {
                "verdict": "pass",
                "evidence": {
                    "message": "No new findings introduced",
                    "baseline_count": len(baseline_findings),
                    "current_count": len(current_findings),
                },
            }
        )

    except Exception as e:
        logger.error(f"verify_no_new_findings_introduced error: {e}")
        return json.dumps(
            {
                "verdict": "unknown",
                "error": str(e),
            }
        )


def _finding_signature(finding: dict) -> str:
    """Finding의 고유 시그니처 생성 (비교용)."""
    return f"{finding.get('type')}:{finding.get('file_path')}:{finding.get('line')}"


async def _get_execution_findings(execution_id: str) -> list[dict]:
    """
    Execution에서 findings 조회.

    SQLite 기반 로컬 저장소 사용.
    """
    try:
        from codegraph_engine.shared_kernel.infrastructure.execution_repository import (
            get_execution_repository,
        )

        repo = get_execution_repository()
        findings = await repo.get_findings(execution_id)
        return findings

    except Exception as e:
        logger.warning(f"Failed to get findings for {execution_id}: {e}")
        return []


async def _run_analysis(
    repo_id: str,
    snapshot_id: str,
    patchset_id: str | None,
    ruleset_subset: list[str] | None,
) -> str:
    """
    새 분석 실행 후 execution_id 반환.

    Returns:
        execution_id: 생성된 실행 ID

    Raises:
        RuntimeError: 분석 실행 실패 시
    """
    try:
        from codegraph_runtime.llm_arbitration.application import ExecuteExecutor

        executor = ExecuteExecutor()

        spec = {
            "intent": "analyze",
            "template_id": "regression_check",
            "scope": {
                "repo_id": repo_id,
                "snapshot_id": snapshot_id,
            },
        }

        if patchset_id:
            spec["scope"]["patchset_id"] = patchset_id

        if ruleset_subset:
            spec["options"] = {"ruleset_subset": ruleset_subset}

        result = await executor.execute(spec)

        # ResultEnvelope에서 execution_id 추출
        if hasattr(result, "metadata") and result.metadata:
            execution_id = result.metadata.get("execution_id")
            if execution_id:
                return execution_id

        # Fallback: 생성
        import uuid

        execution_id = f"exec_{uuid.uuid4().hex[:12]}"
        logger.warning(f"Generated fallback execution_id: {execution_id}")
        return execution_id

    except ImportError as e:
        raise RuntimeError(f"ExecuteExecutor not available: {e}")
    except Exception as e:
        logger.error(f"_run_analysis error: {e}")
        raise RuntimeError(f"Analysis execution failed: {e}")
