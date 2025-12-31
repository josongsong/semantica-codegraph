"""
Wrapper for handbook gap check.

실제 구현은 핸드북 하위에서 관리합니다:
- _docs/system-handbook/_scripts/handbook_gap_check.py
"""

from __future__ import annotations

import runpy
from pathlib import Path


def main() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    target = repo_root / "_docs" / "system-handbook" / "_scripts" / "handbook_gap_check.py"
    runpy.run_path(str(target), run_name="__main__")


if __name__ == "__main__":
    main()
