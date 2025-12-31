"""
FileSystem Adapter (pathlib/os 추상화)
"""

import logging
import tempfile
from pathlib import Path

from codegraph_agent.ports.infrastructure import (
    FileSystemEntry,
    IFileSystem,
)

logger = logging.getLogger(__name__)


class PathlibAdapter(IFileSystem):
    """pathlib 기반 FileSystem"""

    async def read_text(self, path: str, encoding: str = "utf-8") -> str:
        """파일 읽기"""

        if not path:
            raise ValueError("path cannot be empty")

        try:
            return Path(path).read_text(encoding=encoding)
        except FileNotFoundError as e:
            raise FileNotFoundError(f"File not found: {path}") from e
        except Exception as e:
            raise OSError(f"Failed to read file {path}: {e}") from e

    async def write_text(self, path: str, content: str, encoding: str = "utf-8") -> None:
        """파일 쓰기"""

        if not path:
            raise ValueError("path cannot be empty")
        if content is None:
            raise ValueError("content cannot be None")

        try:
            Path(path).write_text(content, encoding=encoding)
        except Exception as e:
            raise OSError(f"Failed to write file {path}: {e}") from e

    async def exists(self, path: str) -> bool:
        """파일/디렉토리 존재 여부"""

        if not path:
            return False

        return Path(path).exists()

    async def get_info(self, path: str) -> FileSystemEntry:
        """파일 정보 조회"""

        if not path:
            raise ValueError("path cannot be empty")

        p = Path(path)
        exists = p.exists()

        return FileSystemEntry(
            path=path,
            exists=exists,
            is_file=p.is_file() if exists else False,
            is_directory=p.is_dir() if exists else False,
            size_bytes=p.stat().st_size if exists else 0,
        )

    async def create_temp_file(self, suffix: str = "", prefix: str = "tmp", content: str | None = None) -> str:
        """임시 파일 생성"""

        fd, path = tempfile.mkstemp(suffix=suffix, prefix=prefix, text=True)

        if content is not None:
            with open(fd, "w", encoding="utf-8") as f:
                f.write(content)
        else:
            import os

            os.close(fd)

        return path

    async def delete(self, path: str) -> None:
        """파일/디렉토리 삭제"""

        if not path:
            raise ValueError("path cannot be empty")

        p = Path(path)

        if not p.exists():
            return

        try:
            if p.is_file():
                p.unlink()
            elif p.is_dir():
                import shutil

                shutil.rmtree(p)
        except Exception as e:
            raise OSError(f"Failed to delete {path}: {e}") from e
