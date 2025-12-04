#!/usr/bin/env python3
"""Debug occurrence file index bug"""

import tempfile
from pathlib import Path
from textwrap import dedent


def main():
    with tempfile.TemporaryDirectory() as tmpdir:
        test_proj = Path(tmpdir)

        # Create test file
        service_py = test_proj / "service.py"
        service_py.write_text(
            dedent("""
            from models import User
            
            class UserService:
                def create_user(self, name: str) -> User:
                    user = User(name)
                    return user
        """).strip()
        )

        from src.contexts.code_foundation.infrastructure.generators.python_generator import PythonIRGenerator
        from src.contexts.code_foundation.infrastructure.parsing import AstTree, SourceFile
        from src.contexts.code_foundation.infrastructure.ir.occurrence_generator import OccurrenceGenerator

        # Generate IR
        content = service_py.read_text()
        source = SourceFile.from_content(str(service_py), content, "python")
        ast = AstTree.parse(source)
        generator = PythonIRGenerator(repo_id="test")
        ir_doc = generator.generate(source, "test", ast)

        print(f"IR Document file_path from first node: {ir_doc.nodes[0].file_path if ir_doc.nodes else 'N/A'}")

        # Generate occurrences
        occ_gen = OccurrenceGenerator()
        occurrences, occ_index = occ_gen.generate(ir_doc)

        print(f"\n생성된 Occurrences: {len(occurrences)}")
        print(f"Index에 등록된 총 occurrences: {occ_index.total_occurrences}")
        print(f"Index.by_id 크기: {len(occ_index.by_id)}")

        # 각 occurrence의 file_path 확인
        file_paths_in_occurrences = set()
        for occ in occurrences:
            file_paths_in_occurrences.add(occ.file_path)

        print(f"\nOccurrence들의 file_path: {len(file_paths_in_occurrences)} unique")
        for fp in file_paths_in_occurrences:
            count = sum(1 for o in occurrences if o.file_path == fp)
            print(f"  - {fp}: {count} occurrences")

        # Index의 by_file 확인
        print(f"\nIndex.by_file 키: {len(occ_index.by_file)} files")
        for fp, occ_ids in occ_index.by_file.items():
            print(f"  - {fp}: {len(occ_ids)} occurrence IDs")

        # File query 결과
        query_file_path = ir_doc.nodes[0].file_path if ir_doc.nodes else ""
        file_occs = occ_index.get_file_occurrences(query_file_path)
        print(f"\nget_file_occurrences('{query_file_path}'): {len(file_occs)} occurrences")

        # 누락된 occurrence 찾기
        missing = len(occurrences) - len(file_occs)
        print(f"\n⚠️ 누락된 occurrences: {missing}")

        if missing > 0:
            print("\n누락된 occurrence들:")
            indexed_ids = set(occ_index.by_file.get(query_file_path, []))
            for occ in occurrences:
                if occ.id not in indexed_ids:
                    print(f"  - {occ.id}")
                    print(f"    file_path: '{occ.file_path}'")
                    print(f"    query_path: '{query_file_path}'")
                    print(f"    Match: {occ.file_path == query_file_path}")


if __name__ == "__main__":
    main()
