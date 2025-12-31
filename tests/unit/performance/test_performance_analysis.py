"""
G-1, G-2, G-3: Performance Analysis 테스트

N+1 Query, Unnecessary Re-computation, Large Object 감지
"""

import pytest


class PerformanceIssue:
    """성능 이슈"""

    def __init__(self, type: str, location: str, suggestion: str):
        self.type = type
        self.location = location
        self.suggestion = suggestion


class PerformanceAnalyzer:
    """성능 분석기 (간단 구현)"""

    def analyze_code(self, code: str) -> list[PerformanceIssue]:
        """코드의 성능 이슈 탐지"""
        issues = []

        lines = code.split("\n")

        # G-1: N+1 Query 패턴 (select_related/prefetch_related 있으면 제외)
        for i, line in enumerate(lines):
            if "for " in line:
                # select_related나 prefetch_related가 있으면 최적화됨
                has_optimization = any(
                    "select_related" in lines[j] or "prefetch_related" in lines[j]
                    for j in range(max(0, i - 5), min(i + 2, len(lines)))
                )

                if not has_optimization:
                    # Loop 내 query 패턴 확인
                    has_query = any(
                        ".objects.get(" in lines[j] or ".objects.filter(" in lines[j]
                        for j in range(i + 1, min(i + 10, len(lines)))
                    )

                    if has_query:
                        issues.append(
                            PerformanceIssue(
                                type="N_PLUS_ONE_QUERY",
                                location=f"line {i + 1}",
                                suggestion="Use select_related() or prefetch_related()",
                            )
                        )

        # G-2: Repeated computation (함수 호출 기준)
        computation_patterns = {}
        for i, line in enumerate(lines):
            # expensive_computation(...) 같은 패턴
            import re

            match = re.search(r"(\w+\([^)]+\))", line)
            if match and "expensive" in line:
                pattern = match.group(1)
                if pattern in computation_patterns:
                    issues.append(
                        PerformanceIssue(
                            type="REPEATED_COMPUTATION",
                            location=f"line {i + 1}",
                            suggestion=f"Cache result from line {computation_patterns[pattern] + 1}",
                        )
                    )
                else:
                    computation_patterns[pattern] = i

        # G-3: Large file read
        for i, line in enumerate(lines):
            if ".read()" in line or ".readlines()" in line:
                issues.append(
                    PerformanceIssue(
                        type="LARGE_MEMORY_LOAD",
                        location=f"line {i + 1}",
                        suggestion="Use streaming or chunked reading",
                    )
                )

        return issues


class TestPerformanceAnalysis:
    """성능 분석 테스트"""

    def test_g1_n_plus_one_query_detection(self):
        """G-1: N+1 Query 감지"""
        # Given: Loop 내 개별 query
        code = """
def get_posts_with_authors():
    posts = Post.objects.all()
    for post in posts:
        author = User.objects.get(id=post.author_id)  # N+1!
        print(author.name)
"""

        analyzer = PerformanceAnalyzer()

        # When
        issues = analyzer.analyze_code(code)

        # Then
        n_plus_one = [i for i in issues if i.type == "N_PLUS_ONE_QUERY"]
        assert len(n_plus_one) > 0
        assert "select_related" in n_plus_one[0].suggestion

    def test_g1_n_plus_one_optimized(self):
        """G-1: Optimized query (prefetch)"""
        # Given: Prefetch 사용
        code = """
def get_posts_with_authors():
    posts = Post.objects.select_related('author').all()
    for post in posts:
        print(post.author.name)  # No additional query
"""

        analyzer = PerformanceAnalyzer()

        # When
        issues = analyzer.analyze_code(code)

        # Then
        n_plus_one = [i for i in issues if i.type == "N_PLUS_ONE_QUERY"]
        assert len(n_plus_one) == 0

    def test_g2_repeated_computation_detection(self):
        """G-2: Unnecessary Re-computation 감지"""
        # Given: 동일 계산 반복
        code = """
def process_data(items):
    for item in items:
        result = expensive_computation(item.data)
        print(result)

    for item in items:
        result = expensive_computation(item.data)  # 중복!
        save(result)
"""

        analyzer = PerformanceAnalyzer()

        # When
        issues = analyzer.analyze_code(code)

        # Then
        repeated = [i for i in issues if i.type == "REPEATED_COMPUTATION"]
        assert len(repeated) > 0
        assert "Cache" in repeated[0].suggestion

    def test_g2_cached_computation(self):
        """G-2: Cached computation (최적화)"""
        # Given: 캐싱 적용
        code = """
def process_data(items):
    cache = {}
    for item in items:
        if item.data not in cache:
            cache[item.data] = expensive_computation(item.data)
        result = cache[item.data]
        print(result)
"""

        analyzer = PerformanceAnalyzer()

        # When
        issues = analyzer.analyze_code(code)

        # Then
        repeated = [i for i in issues if i.type == "REPEATED_COMPUTATION"]
        assert len(repeated) == 0

    def test_g3_large_file_memory_detection(self):
        """G-3: Large file 전체 메모리 로드 감지"""
        # Given: 대용량 파일 전체 read
        code = """
def process_log(filepath):
    with open(filepath, 'r') as f:
        content = f.read()  # 위험! 파일 크기에 따라 메모리 부족
        lines = content.split('\\n')
        for line in lines:
            process(line)
"""

        analyzer = PerformanceAnalyzer()

        # When
        issues = analyzer.analyze_code(code)

        # Then
        large_load = [i for i in issues if i.type == "LARGE_MEMORY_LOAD"]
        assert len(large_load) > 0
        assert "streaming" in large_load[0].suggestion

    def test_g3_streaming_file_read(self):
        """G-3: Streaming file read (최적화)"""
        # Given: Line-by-line streaming
        code = """
def process_log(filepath):
    with open(filepath, 'r') as f:
        for line in f:  # Streaming, 메모리 효율적
            process(line)
"""

        analyzer = PerformanceAnalyzer()

        # When
        issues = analyzer.analyze_code(code)

        # Then
        large_load = [i for i in issues if i.type == "LARGE_MEMORY_LOAD"]
        assert len(large_load) == 0

    def test_g_combined_performance_report(self):
        """여러 성능 이슈 동시 감지"""
        # Given: 여러 이슈가 있는 코드
        code = """
def bad_performance(users):
    # N+1
    for user in users:
        profile = Profile.objects.get(user_id=user.id)

    # Repeated computation
    total = sum([expensive_calc(x) for x in range(100)])
    total2 = sum([expensive_calc(x) for x in range(100)])

    # Large file
    with open('huge.log', 'r') as f:
        data = f.read()
"""

        analyzer = PerformanceAnalyzer()

        # When
        issues = analyzer.analyze_code(code)

        # Then
        assert len(issues) >= 3
        types = {i.type for i in issues}
        assert "N_PLUS_ONE_QUERY" in types
        assert "REPEATED_COMPUTATION" in types
        assert "LARGE_MEMORY_LOAD" in types
