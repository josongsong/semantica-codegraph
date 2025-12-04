"""
Incremental IR Builder

Delta 기반 incremental update
"""

from pathlib import Path
from typing import Dict, Set, List, Optional
from dataclasses import dataclass

from src.contexts.code_foundation.infrastructure.incremental.change_tracker import ChangeTracker
from src.contexts.code_foundation.infrastructure.generators.python_generator import PythonIRGenerator
from src.contexts.code_foundation.infrastructure.parsing import AstTree, SourceFile
from src.contexts.code_foundation.infrastructure.ir.models import IRDocument


@dataclass
class IncrementalResult:
    """Incremental update 결과"""

    changed_files: Set[str]
    affected_files: Set[str]
    rebuilt_files: Set[str]
    ir_documents: Dict[str, IRDocument]
    skipped_files: int


class IncrementalBuilder:
    """
    Incremental IR Builder

    기능:
    - 변경된 파일만 재빌드
    - 의존성 기반 affected files 계산
    - IR cache 유지 및 업데이트
    """

    def __init__(self, repo_id: str):
        self.repo_id = repo_id
        self._change_tracker = ChangeTracker()
        self._ir_cache: Dict[str, IRDocument] = {}

    def build_incremental(
        self,
        files: List[Path],
        language: str = "python",
    ) -> IncrementalResult:
        """
        Incremental build

        Args:
            files: 처리할 파일 목록
            language: 프로그래밍 언어

        Returns:
            IncrementalResult with delta info
        """
        changed_files = set()

        # 1. 변경 감지
        for file_path in files:
            try:
                content = file_path.read_text()
                last_modified = file_path.stat().st_mtime

                is_changed = self._change_tracker.register_file(
                    str(file_path),
                    content,
                    last_modified,
                )

                if is_changed:
                    changed_files.add(str(file_path))

            except Exception as e:
                print(f"⚠️ Failed to read {file_path}: {e}")

        # 2. 영향받는 파일 계산
        affected_files = self._change_tracker.get_affected_files(changed_files)

        # 3. 재빌드
        rebuilt_files = set()
        new_ir_docs = {}

        for file_path_str in affected_files:
            file_path = Path(file_path_str)

            if not file_path.exists():
                # File deleted
                if file_path_str in self._ir_cache:
                    del self._ir_cache[file_path_str]
                continue

            try:
                # Generate IR
                content = file_path.read_text()
                source = SourceFile.from_content(str(file_path), content, language)
                ast = AstTree.parse(source)
                generator = PythonIRGenerator(repo_id=self.repo_id)
                ir_doc = generator.generate(source, self.repo_id, ast)

                # Extract dependencies (IMPORTS edges)
                dependencies = set()
                for edge in ir_doc.edges:
                    if edge.kind.value == "IMPORTS":
                        # Find target file
                        for node in ir_doc.nodes:
                            if node.id == edge.target_id and node.file_path:
                                if node.file_path != str(file_path):
                                    dependencies.add(node.file_path)
                                break

                # Update dependency graph
                self._change_tracker.update_dependencies(file_path_str, dependencies)

                # Cache IR
                self._ir_cache[file_path_str] = ir_doc
                new_ir_docs[file_path_str] = ir_doc
                rebuilt_files.add(file_path_str)

            except Exception as e:
                print(f"⚠️ Failed to build {file_path}: {e}")

        # 4. 결과
        skipped = len(files) - len(rebuilt_files)

        return IncrementalResult(
            changed_files=changed_files,
            affected_files=affected_files,
            rebuilt_files=rebuilt_files,
            ir_documents=new_ir_docs,
            skipped_files=skipped,
        )

    def get_all_ir(self) -> Dict[str, IRDocument]:
        """모든 cached IR documents"""
        return self._ir_cache.copy()

    def clear_cache(self):
        """Cache 초기화"""
        self._change_tracker.clear()
        self._ir_cache.clear()
