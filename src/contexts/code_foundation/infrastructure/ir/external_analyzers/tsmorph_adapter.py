"""
ts-morph External Analyzer Adapter

TypeScript 타입 정보 추출을 위한 ts-morph 기반 어댑터.

Features:
- 타입 정보 조회
- 레퍼런스 찾기
- 정의 찾기
- 인터페이스 구현 관계
"""

import json
import subprocess
from pathlib import Path
from typing import Any

from src.common.observability import get_logger
from src.contexts.code_foundation.infrastructure.ir.external_analyzers.base import (
    ExternalAnalyzer,
    Location,
    TypeInfo,
)

logger = get_logger(__name__)


class TsMorphAdapter(ExternalAnalyzer):
    """
    ts-morph 기반 TypeScript 분석 어댑터.

    Python subprocess로 Node.js ts-morph 스크립트 실행.
    """

    def __init__(self, project_root: str):
        """
        Initialize ts-morph adapter.

        Args:
            project_root: TypeScript 프로젝트 루트 (tsconfig.json 위치)
        """
        self.project_root = Path(project_root)
        self.script_path = Path(__file__).parent / "tsmorph_scripts" / "analyzer.js"

        # Check if script exists
        if not self.script_path.exists():
            logger.warning(f"ts-morph script not found: {self.script_path}")

    def get_type_at_location(
        self,
        file_path: str,
        line: int,
        column: int,
    ) -> TypeInfo | None:
        """
        Get type information at specific location.

        Args:
            file_path: File path
            line: Line number (1-indexed)
            column: Column number (0-indexed)

        Returns:
            TypeInfo or None
        """
        try:
            result = self._run_command(
                "get_type",
                {
                    "file_path": file_path,
                    "line": line,
                    "column": column,
                },
            )

            if not result or "error" in result:
                return None

            return TypeInfo(
                symbol_name=result.get("symbol", ""),
                file_path=file_path,
                line=line,
                column=column,
                inferred_type=result.get("type", "unknown"),
                is_union=result.get("is_union", False),
                union_variants=result.get("union_variants", []),
            )

        except Exception as e:
            logger.debug(f"Failed to get type at {file_path}:{line}:{column}: {e}")
            return None

    def get_definition(
        self,
        file_path: str,
        line: int,
        column: int,
    ) -> list[Location]:
        """
        Get definition locations.

        Args:
            file_path: File path
            line: Line number
            column: Column number

        Returns:
            List of definition locations
        """
        try:
            result = self._run_command(
                "get_definition",
                {
                    "file_path": file_path,
                    "line": line,
                    "column": column,
                },
            )

            if not result or "definitions" not in result:
                return []

            return [
                Location(
                    file_path=d.get("file_path", ""),
                    line=d.get("line", 0),
                    column=d.get("column", 0),
                )
                for d in result["definitions"]
            ]

        except Exception as e:
            logger.debug(f"Failed to get definition: {e}")
            return []

    def get_references(
        self,
        file_path: str,
        line: int,
        column: int,
    ) -> list[Location]:
        """
        Get reference locations.

        Args:
            file_path: File path
            line: Line number
            column: Column number

        Returns:
            List of reference locations
        """
        try:
            result = self._run_command(
                "get_references",
                {
                    "file_path": file_path,
                    "line": line,
                    "column": column,
                },
            )

            if not result or "references" not in result:
                return []

            return [
                Location(
                    file_path=r.get("file_path", ""),
                    line=r.get("line", 0),
                    column=r.get("column", 0),
                )
                for r in result["references"]
            ]

        except Exception as e:
            logger.debug(f"Failed to get references: {e}")
            return []

    def analyze_file(self, file_path: str) -> dict[str, Any]:
        """
        Analyze entire file and extract all symbols.

        Args:
            file_path: File path

        Returns:
            Dictionary with functions, classes, interfaces, etc.
        """
        try:
            result = self._run_command(
                "analyze_file",
                {
                    "file_path": file_path,
                },
            )

            return result or {}

        except Exception as e:
            logger.warning(f"Failed to analyze file {file_path}: {e}")
            return {}

    def _run_command(self, command: str, params: dict[str, Any]) -> dict[str, Any] | None:
        """
        Run ts-morph command via Node.js subprocess.

        Args:
            command: Command name
            params: Command parameters

        Returns:
            Result dictionary or None
        """
        if not self.script_path.exists():
            return None

        try:
            # Build command
            payload = {
                "command": command,
                "params": params,
                "project_root": str(self.project_root),
            }

            # Run Node.js script
            result = subprocess.run(
                ["node", str(self.script_path)],
                input=json.dumps(payload),
                capture_output=True,
                text=True,
                timeout=30,
            )

            if result.returncode != 0:
                logger.debug(f"ts-morph command failed: {result.stderr}")
                return None

            # Parse output
            return json.loads(result.stdout)

        except subprocess.TimeoutExpired:
            logger.warning("ts-morph command timed out")
            return None
        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse ts-morph output: {e}")
            return None
        except Exception as e:
            logger.debug(f"ts-morph command error: {e}")
            return None
