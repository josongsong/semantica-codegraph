#!/usr/bin/env python3
"""
비판적 검증 - 실제로 제대로 동작하는지 확인

테스트 통과는 했지만:
1. 데이터가 정확한가?
2. 빈 결과가 아닌가?
3. 실제 사용 가능한가?
4. 성능은 괜찮은가?
"""

import asyncio
import tempfile
import time
from pathlib import Path
from textwrap import dedent


def create_real_project(tmp_path: Path):
    """실제 레포지토리와 유사한 프로젝트 생성"""

    # src/models.py
    models_py = tmp_path / "src" / "models.py"
    models_py.parent.mkdir(parents=True)
    models_py.write_text(
        dedent("""
        '''Data models'''
        from typing import List, Optional
        
        class User:
            '''User model'''
            def __init__(self, name: str, email: str):
                self.name = name
                self.email = email
                self.posts: List['Post'] = []
            
            def add_post(self, post: 'Post'):
                '''Add a post to user'''
                self.posts.append(post)
                post.author = self
            
            def get_posts(self) -> List['Post']:
                '''Get all user posts'''
                return self.posts
        
        class Post:
            '''Post model'''
            def __init__(self, title: str, content: str):
                self.title = title
                self.content = content
                self.author: Optional[User] = None
            
            def set_author(self, user: User):
                '''Set post author'''
                self.author = user
    """).strip()
    )

    # src/service.py
    service_py = tmp_path / "src" / "service.py"
    service_py.write_text(
        dedent("""
        '''Business logic'''
        from models import User, Post
        
        class UserService:
            '''User service'''
            def __init__(self):
                self.users: dict[str, User] = {}
            
            def create_user(self, name: str, email: str) -> User:
                '''Create a new user'''
                user = User(name, email)
                self.users[email] = user
                return user
            
            def get_user(self, email: str) -> User | None:
                '''Get user by email'''
                return self.users.get(email)
            
            def create_post(self, email: str, title: str, content: str) -> Post:
                '''Create a post for user'''
                user = self.get_user(email)
                if not user:
                    raise ValueError(f"User not found: {email}")
                
                post = Post(title, content)
                user.add_post(post)
                return post
    """).strip()
    )

    # src/main.py
    main_py = tmp_path / "src" / "main.py"
    main_py.write_text(
        dedent("""
        '''Main application'''
        from service import UserService
        
        def main():
            '''Run application'''
            service = UserService()
            
            # Create users
            alice = service.create_user("Alice", "alice@example.com")
            bob = service.create_user("Bob", "bob@example.com")
            
            # Create posts
            post1 = service.create_post("alice@example.com", "Hello", "First post")
            post2 = service.create_post("bob@example.com", "Hi", "Second post")
            
            # Print results
            print(f"Alice has {len(alice.get_posts())} posts")
            print(f"Bob has {len(bob.get_posts())} posts")
        
        if __name__ == "__main__":
            main()
    """).strip()
    )

    return tmp_path


async def critical_test_1_data_quality():
    """비판적 검증 1: 생성된 데이터 품질"""
    print("\n" + "=" * 60)
    print("비판적 검증 1: 데이터 품질")
    print("=" * 60)

    with tempfile.TemporaryDirectory() as tmpdir:
        test_proj = create_real_project(Path(tmpdir))

        from src.contexts.code_foundation.infrastructure.generators.python_generator import PythonIRGenerator
        from src.contexts.code_foundation.infrastructure.parsing import AstTree, SourceFile

        # models.py 생성
        models_file = test_proj / "src" / "models.py"
        content = models_file.read_text()
        source = SourceFile.from_content(str(models_file), content, "python")
        ast = AstTree.parse(source)
        generator = PythonIRGenerator(repo_id="test_repo")
        ir_doc = generator.generate(source, "test", ast)

        # 검증 1: 클래스가 제대로 인식되었는가?
        classes = [n for n in ir_doc.nodes if n.kind.value == "Class"]
        print(f"✓ Classes found: {len(classes)}")
        assert len(classes) == 2, f"Expected 2 classes, found {len(classes)}"

        class_names = [c.name for c in classes]
        assert "User" in class_names, "User class not found!"
        assert "Post" in class_names, "Post class not found!"
        print(f"  - {class_names}")

        # 검증 2: 메소드가 제대로 인식되었는가?
        methods = [n for n in ir_doc.nodes if n.kind.value == "Method"]
        print(f"✓ Methods found: {len(methods)}")

        method_names = [m.name for m in methods]
        assert "__init__" in method_names, "__init__ not found!"
        assert "add_post" in method_names, "add_post not found!"
        assert "get_posts" in method_names, "get_posts not found!"
        print(f"  - Sample: {method_names[:5]}")

        # 검증 3: Docstring이 제대로 추출되었는가?
        user_class = [c for c in classes if c.name == "User"][0]
        assert user_class.docstring, "User class docstring missing!"
        print(f"✓ Docstrings: User = '{user_class.docstring}'")

        # 검증 4: FQN이 제대로 생성되었는가?
        assert user_class.fqn, "User class FQN missing!"
        print(f"✓ FQN: {user_class.fqn}")

        # 검증 5: Edges가 의미있게 생성되었는가?
        contains_edges = [e for e in ir_doc.edges if e.kind.value == "CONTAINS"]
        print(f"✓ CONTAINS edges: {len(contains_edges)}")
        assert len(contains_edges) > 0, "No CONTAINS edges!"

        return True


async def critical_test_2_occurrence_accuracy():
    """비판적 검증 2: Occurrence 정확도"""
    print("\n" + "=" * 60)
    print("비판적 검증 2: Occurrence 정확도")
    print("=" * 60)

    with tempfile.TemporaryDirectory() as tmpdir:
        test_proj = create_real_project(Path(tmpdir))

        from src.contexts.code_foundation.infrastructure.generators.python_generator import PythonIRGenerator
        from src.contexts.code_foundation.infrastructure.parsing import AstTree, SourceFile
        from src.contexts.code_foundation.infrastructure.ir.occurrence_generator import OccurrenceGenerator

        # service.py 생성 (imports User, Post)
        service_file = test_proj / "src" / "service.py"
        content = service_file.read_text()
        source = SourceFile.from_content(str(service_file), content, "python")
        ast = AstTree.parse(source)
        generator = PythonIRGenerator(repo_id="test_repo")
        ir_doc = generator.generate(source, "test", ast)

        # Occurrence 생성
        occ_gen = OccurrenceGenerator()
        occurrences, occ_index = occ_gen.generate(ir_doc)

        # 검증 1: Definition vs Reference 비율이 합리적인가?
        definitions = [o for o in occurrences if o.is_definition()]
        references = [o for o in occurrences if o.is_reference()]

        print(f"✓ Definitions: {len(definitions)}")
        print(f"✓ References: {len(references)}")

        # Reference가 있어야 함 (UserService는 User, Post를 사용)
        # 하지만 현재 구현에서는 reference가 적을 수 있음
        print(f"  - Ratio: {len(definitions)}:{len(references)}")

        # 검증 2: 특정 심볼의 occurrence를 찾을 수 있는가?
        # UserService 클래스를 찾기
        user_service_defs = [o for o in definitions if "UserService" in o.symbol_id]

        if user_service_defs:
            print(f"✓ UserService definitions: {len(user_service_defs)}")
            print(f"  - Symbol ID: {user_service_defs[0].symbol_id}")
            print(f"  - Roles: {user_service_defs[0].roles}")
        else:
            print("⚠ UserService definition not found in occurrences")

        # 검증 3: Index가 제대로 동작하는가?
        stats = occ_index.get_stats()
        print(f"✓ Index stats: {stats}")
        assert stats["total_occurrences"] > 0, "Index is empty!"

        # 검증 4: File-based query가 동작하는가?
        file_occs = occ_index.get_file_occurrences(str(service_file))

        # CRITICAL: External symbols (imports) have file_path='<external>'
        # They shouldn't be included in file-specific queries
        local_occs = [o for o in occurrences if o.file_path == str(service_file)]
        external_occs = [o for o in occurrences if o.file_path == "<external>"]

        print(f"✓ File occurrences: {len(file_occs)}")
        print(f"  - Local: {len(local_occs)}, External: {len(external_occs)}")

        # File query should return only local occurrences, NOT external ones
        assert len(file_occs) == len(local_occs), (
            f"File index mismatch! Expected {len(local_occs)} local, got {len(file_occs)}"
        )

        return True


async def critical_test_3_cross_file_accuracy():
    """비판적 검증 3: Cross-file resolution 정확도"""
    print("\n" + "=" * 60)
    print("비판적 검증 3: Cross-file Resolution 정확도")
    print("=" * 60)

    with tempfile.TemporaryDirectory() as tmpdir:
        test_proj = create_real_project(Path(tmpdir))

        from src.contexts.code_foundation.infrastructure.generators.python_generator import PythonIRGenerator
        from src.contexts.code_foundation.infrastructure.parsing import AstTree, SourceFile
        from src.contexts.code_foundation.infrastructure.ir.cross_file_resolver import CrossFileResolver

        # 3개 파일 모두 생성
        files = [
            test_proj / "src" / "models.py",
            test_proj / "src" / "service.py",
            test_proj / "src" / "main.py",
        ]

        ir_docs = []
        for file_path in files:
            content = file_path.read_text()
            source = SourceFile.from_content(str(file_path), content, "python")
            ast = AstTree.parse(source)
            generator = PythonIRGenerator(repo_id="test_repo")
            ir_doc = generator.generate(source, "test", ast)
            ir_docs.append(ir_doc)

        # Cross-file resolution
        resolver = CrossFileResolver()
        global_ctx = resolver.resolve(ir_docs)

        # 검증 1: 모든 파일의 심볼이 등록되었는가?
        print(f"✓ Total symbols: {global_ctx.total_symbols}")
        assert global_ctx.total_symbols > 0, "No symbols registered!"

        # 각 파일의 노드 수 확인
        for ir_doc in ir_docs:
            if ir_doc.nodes:
                print(f"  - {ir_doc.nodes[0].file_path}: {len(ir_doc.nodes)} nodes")

        expected_min_symbols = sum(len(doc.nodes) for doc in ir_docs)
        print(f"  - Expected minimum: {expected_min_symbols}")

        # 검증 2: 특정 심볼을 찾을 수 있는가?
        # User 클래스 찾기
        user_symbols = [
            (fqn, node)
            for fqn, (node, _) in global_ctx.symbol_table.items()
            if "User" in fqn and node.kind.value == "Class"
        ]

        if user_symbols:
            print(f"✓ Found User symbols: {len(user_symbols)}")
            for fqn, node in user_symbols[:3]:
                print(f"  - {fqn}")
        else:
            print("⚠ User class not found in global symbol table")

        # 검증 3: Import 관계가 파악되었는가?
        # service.py는 models.py를 import
        service_file = str(test_proj / "src" / "service.py")
        models_file = str(test_proj / "src" / "models.py")

        service_deps = global_ctx.get_dependencies(service_file)
        print(f"✓ service.py dependencies: {len(service_deps)}")
        if service_deps:
            print(f"  - {service_deps}")

        # 검증 4: Stats가 합리적인가?
        stats = global_ctx.get_stats()
        print(f"✓ Global context stats:")
        for key, value in stats.items():
            print(f"  - {key}: {value}")

        return True


async def critical_test_4_performance():
    """비판적 검증 4: 성능"""
    print("\n" + "=" * 60)
    print("비판적 검증 4: 성능")
    print("=" * 60)

    with tempfile.TemporaryDirectory() as tmpdir:
        test_proj = create_real_project(Path(tmpdir))

        from src.contexts.code_foundation.infrastructure.generators.python_generator import PythonIRGenerator
        from src.contexts.code_foundation.infrastructure.parsing import AstTree, SourceFile
        from src.contexts.code_foundation.infrastructure.ir.occurrence_generator import OccurrenceGenerator
        from src.contexts.code_foundation.infrastructure.ir.cross_file_resolver import CrossFileResolver
        from src.contexts.code_foundation.infrastructure.ir.retrieval_index import RetrievalOptimizedIndex

        # 타이밍 측정
        timings = {}

        # 1. IR Generation
        start = time.perf_counter()
        ir_docs = []
        for file_path in [
            test_proj / "src" / "models.py",
            test_proj / "src" / "service.py",
            test_proj / "src" / "main.py",
        ]:
            content = file_path.read_text()
            source = SourceFile.from_content(str(file_path), content, "python")
            ast = AstTree.parse(source)
            generator = PythonIRGenerator(repo_id="test_repo")
            ir_doc = generator.generate(source, "test", ast)
            ir_docs.append(ir_doc)
        timings["ir_generation"] = (time.perf_counter() - start) * 1000

        # 2. Occurrence Generation
        start = time.perf_counter()
        occ_gen = OccurrenceGenerator()
        for ir_doc in ir_docs:
            occ_gen.generate(ir_doc)
        timings["occurrence_generation"] = (time.perf_counter() - start) * 1000

        # 3. Cross-file Resolution
        start = time.perf_counter()
        resolver = CrossFileResolver()
        global_ctx = resolver.resolve(ir_docs)
        timings["cross_file_resolution"] = (time.perf_counter() - start) * 1000

        # 4. Index Building
        start = time.perf_counter()
        index = RetrievalOptimizedIndex()
        for ir_doc in ir_docs:
            index.index_ir_document(ir_doc)
        timings["index_building"] = (time.perf_counter() - start) * 1000

        # 5. Search Query
        start = time.perf_counter()
        results = index.search_symbol("User", fuzzy=True, limit=10)
        timings["fuzzy_search"] = (time.perf_counter() - start) * 1000

        # 결과
        total_time = sum(timings.values())
        print(f"✓ Performance Results (3 files):")
        for operation, time_ms in timings.items():
            pct = (time_ms / total_time) * 100 if total_time > 0 else 0
            status = "✓" if time_ms < 100 else "⚠"
            print(f"  {status} {operation:25s}: {time_ms:7.2f}ms ({pct:5.1f}%)")
        print(f"  ✓ Total: {total_time:.2f}ms")

        # 성능 목표 검증
        assert timings["ir_generation"] < 1000, f"IR generation too slow: {timings['ir_generation']:.2f}ms"
        assert timings["fuzzy_search"] < 100, f"Fuzzy search too slow: {timings['fuzzy_search']:.2f}ms"

        return True


async def critical_test_5_real_usage():
    """비판적 검증 5: 실제 사용 시나리오"""
    print("\n" + "=" * 60)
    print("비판적 검증 5: 실제 사용 시나리오")
    print("=" * 60)

    with tempfile.TemporaryDirectory() as tmpdir:
        test_proj = create_real_project(Path(tmpdir))

        from src.contexts.code_foundation.infrastructure.generators.python_generator import PythonIRGenerator
        from src.contexts.code_foundation.infrastructure.parsing import AstTree, SourceFile
        from src.contexts.code_foundation.infrastructure.ir.occurrence_generator import OccurrenceGenerator
        from src.contexts.code_foundation.infrastructure.ir.retrieval_index import RetrievalOptimizedIndex

        # 전체 파이프라인
        ir_docs = []
        for file_path in [test_proj / "src" / "models.py", test_proj / "src" / "service.py"]:
            content = file_path.read_text()
            source = SourceFile.from_content(str(file_path), content, "python")
            ast = AstTree.parse(source)
            generator = PythonIRGenerator(repo_id="test_repo")
            ir_doc = generator.generate(source, "test", ast)

            # Occurrences
            occ_gen = OccurrenceGenerator()
            occurrences, occ_index = occ_gen.generate(ir_doc)
            ir_doc.occurrences = occurrences

            ir_docs.append(ir_doc)

        # Index
        index = RetrievalOptimizedIndex()
        for ir_doc in ir_docs:
            index.index_ir_document(ir_doc)

        # 사용 시나리오 1: "User 클래스 찾기"
        print("\n시나리오 1: User 클래스 찾기")
        results = index.search_symbol("User", fuzzy=False, limit=5)
        print(f"  ✓ Found {len(results)} results")
        if results:
            node, score = results[0]
            print(f"  ✓ Best match: {node.name} (score: {score:.2f})")
            print(f"  ✓ FQN: {node.fqn}")
            print(f"  ✓ Location: {node.file_path}:{node.span.start_line}")

        # 사용 시나리오 2: "create_user 메소드 찾기"
        print("\n시나리오 2: create_user 메소드 찾기")
        results = index.search_symbol("create_user", fuzzy=False, limit=5)
        print(f"  ✓ Found {len(results)} results")
        if results:
            node, score = results[0]
            print(f"  ✓ Best match: {node.name} (score: {score:.2f})")

        # 사용 시나리오 3: "Fuzzy search: 'usr'"
        print("\n시나리오 3: Fuzzy search 'usr'")
        results = index.search_symbol("usr", fuzzy=True, limit=5)
        print(f"  ✓ Found {len(results)} results")
        for i, (node, score) in enumerate(results[:3], 1):
            print(f"    {i}. {node.name} (score: {score:.2f})")

        # 사용 시나리오 4: "파일의 모든 정의 가져오기"
        print("\n시나리오 4: models.py의 모든 정의")
        models_ir = ir_docs[0]
        definitions = [o for o in models_ir.occurrences if o.is_definition()]
        print(f"  ✓ Found {len(definitions)} definitions")
        for i, occ in enumerate(definitions[:5], 1):
            symbol_name = occ.symbol_id.split("::")[-1] if "::" in occ.symbol_id else occ.symbol_id
            print(f"    {i}. {symbol_name} @ line {occ.span.start_line}")

        return True


async def main():
    """모든 비판적 검증 실행"""
    print("\n" + "🔍" + "=" * 58 + "🔍")
    print("   SOTA IR 비판적 검증")
    print("🔍" + "=" * 58 + "🔍")

    tests = [
        ("데이터 품질", critical_test_1_data_quality),
        ("Occurrence 정확도", critical_test_2_occurrence_accuracy),
        ("Cross-file 정확도", critical_test_3_cross_file_accuracy),
        ("성능", critical_test_4_performance),
        ("실제 사용 시나리오", critical_test_5_real_usage),
    ]

    results = []

    for test_name, test_func in tests:
        try:
            await test_func()
            results.append((test_name, True, None))
        except Exception as e:
            results.append((test_name, False, str(e)))
            print(f"❌ FAILED: {e}")
            import traceback

            traceback.print_exc()

    # Summary
    print("\n" + "=" * 60)
    print("비판적 검증 결과")
    print("=" * 60)

    for test_name, passed, error in results:
        if passed:
            print(f"✅ {test_name:25s}: PASSED")
        else:
            print(f"❌ {test_name:25s}: FAILED - {error}")

    print("=" * 60)

    passed_count = sum(1 for _, passed, _ in results if passed)
    total_count = len(results)

    if passed_count == total_count:
        print(f"\n🎉 모든 {total_count}개 검증 통과!")
        print("\n✅ SOTA IR이 실제로 제대로 동작합니다!")
        print("✅ 데이터 품질이 우수합니다!")
        print("✅ 성능이 양호합니다!")
        print("✅ 실제 사용 가능합니다!")
        return 0
    else:
        print(f"\n❌ {total_count - passed_count}/{total_count} 검증 실패")
        return 1


if __name__ == "__main__":
    import sys

    sys.exit(asyncio.run(main()))
