#!/usr/bin/env python3
"""증분 인덱싱 CLI"""

import asyncio
import sys

from core.core.indexing.incremental import incremental_index
from infra.config.logging import setup_logging

setup_logging()


async def main():
    """증분 인덱싱 실행"""
    if len(sys.argv) < 2:
        print("Usage: index_incremental.py <repo_path>", file=sys.stderr)
        sys.exit(1)

    repo_path = sys.argv[1]
    # TODO: 저장된 해시 조회
    stored_hashes = {}
    stored_paths = set()

    await incremental_index(repo_path, stored_hashes, stored_paths)


if __name__ == "__main__":
    asyncio.run(main())

