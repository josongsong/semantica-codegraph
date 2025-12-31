# Git 히스토리 분석

> 코드 진화 추적 및 핫스팟 탐지

---

## 목차

1. [개요](#1-개요)
2. [Churn Analysis](#2-churn-analysis)
3. [Blame & Ownership](#3-blame--ownership)
4. [Co-Change Analysis](#4-co-change-analysis)
5. [Evolution Tracking](#5-evolution-tracking)
6. [통합 방법](#6-통합-방법)

---

## 1. 개요

### 목적
- **핫스팟 탐지**: 자주 변경되는 파일/함수
- **소유권 추적**: 누가 어떤 코드를 작성했는지
- **Co-change 패턴**: 함께 변경되는 파일들
- **코드 진화**: 시간에 따른 품질 변화

### 컴포넌트

```
src/contexts/analysis_indexing/infrastructure/git_history/
├── churn.py          # 변경 빈도 분석
├── blame.py          # 작성자 추적
├── cochange.py       # 동시 변경 패턴
├── evolution.py      # 진화 추적
├── git_service.py    # Git 명령 래퍼
└── enrichment.py     # 메타데이터 강화
```

---

## 2. Churn Analysis

### 개념
**Churn** = 파일/함수가 변경된 횟수

높은 churn = 불안정/복잡/버그 가능성 높음

### 측정 지표

```python
@dataclass
class ChurnMetrics:
    file_path: str

    # Commit 기반
    total_commits: int          # 총 커밋 수
    recent_commits: int         # 최근 3개월

    # Line 기반
    lines_added: int            # 추가된 줄
    lines_deleted: int          # 삭제된 줄
    lines_modified: int         # 수정된 줄

    # 시간 기반
    first_commit: datetime
    last_commit: datetime
    avg_days_between: float     # 평균 변경 주기

    # 작성자
    num_authors: int            # 기여자 수
    primary_author: str         # 주 작성자
```

### 구현

```python
# src/contexts/analysis_indexing/infrastructure/git_history/churn.py
class ChurnAnalyzer:
    def __init__(self, git_service: GitService):
        self.git = git_service

    async def analyze_file_churn(
        self,
        repo_path: Path,
        file_path: str,
        since: datetime | None = None,
    ) -> ChurnMetrics:
        # 1. Git log 가져오기
        commits = await self.git.get_file_history(
            repo_path,
            file_path,
            since=since,
        )

        # 2. Line changes 계산
        added, deleted = 0, 0
        for commit in commits:
            stat = await self.git.get_commit_stat(repo_path, commit, file_path)
            added += stat.lines_added
            deleted += stat.lines_deleted

        # 3. 작성자 분석
        authors = await self.git.get_file_authors(repo_path, file_path)

        return ChurnMetrics(
            file_path=file_path,
            total_commits=len(commits),
            recent_commits=len([c for c in commits if c.date > three_months_ago]),
            lines_added=added,
            lines_deleted=deleted,
            lines_modified=min(added, deleted),
            first_commit=commits[-1].date,
            last_commit=commits[0].date,
            num_authors=len(authors),
            primary_author=max(authors, key=authors.count),
        )
```

### Hot File 탐지

```python
async def detect_hot_files(
    self,
    repo_path: Path,
    threshold_commits: int = 10,
    period_days: int = 90,
) -> list[str]:
    """높은 churn 파일 탐지"""

    since = datetime.now() - timedelta(days=period_days)
    hot_files = []

    for file_path in all_files:
        metrics = await self.analyze_file_churn(repo_path, file_path, since)

        if metrics.recent_commits >= threshold_commits:
            hot_files.append(file_path)

    return hot_files
```

### 성능
- **시간:** ~5초 (1000 파일, git log 캐싱)
- **메모리:** ~20MB
- **최적화:** git log 결과 캐싱 (1시간)

---

## 3. Blame & Ownership

### 개념
**Blame** = 각 줄을 누가 마지막으로 수정했는지

### 소유권 계산

```python
@dataclass
class OwnershipInfo:
    file_path: str

    # 줄 단위 소유권 (누가 몇 줄 작성했는지)
    ownership: dict[str, int]   # {author: line_count}

    # 시간 기반 기여도
    recent_authors: list[str]   # 최근 3개월
    legacy_authors: list[str]   # 그 이전

    # 소유권 분산도
    primary_owner: str          # 50%+ 작성
    secondary_owners: list[str] # 10%+ 작성
    gini_coefficient: float     # 0=균등, 1=집중
```

### 구현

```python
# src/contexts/analysis_indexing/infrastructure/git_history/blame.py
class BlameAnalyzer:
    async def analyze_ownership(
        self,
        repo_path: Path,
        file_path: str,
    ) -> OwnershipInfo:
        # git blame 실행
        blame_output = await self.git.run_blame(repo_path, file_path)

        # 줄 단위 파싱
        ownership = defaultdict(int)
        for line in blame_output.splitlines():
            # ^abc123 (John Doe 2024-12-14 10:30:00 +0900 42) code
            match = re.match(r'\^?([a-f0-9]+)\s+\(([^)]+)\s+(\d{4}-\d{2}-\d{2})', line)
            if match:
                commit, author, date = match.groups()
                author = author.strip()
                ownership[author] += 1

        # 소유권 비율 계산
        total_lines = sum(ownership.values())
        ownership_pct = {
            author: count / total_lines
            for author, count in ownership.items()
        }

        # 주 소유자 결정
        primary = max(ownership_pct, key=ownership_pct.get)
        secondary = [
            author for author, pct in ownership_pct.items()
            if pct >= 0.1 and author != primary
        ]

        return OwnershipInfo(
            file_path=file_path,
            ownership=dict(ownership),
            primary_owner=primary if ownership_pct[primary] >= 0.5 else None,
            secondary_owners=secondary,
            gini_coefficient=self._calculate_gini(ownership_pct),
        )
```

### Gini Coefficient

```python
def _calculate_gini(self, ownership_pct: dict[str, float]) -> float:
    """소유권 불평등도 (0=균등, 1=독점)"""

    values = sorted(ownership_pct.values())
    n = len(values)

    cumsum = 0
    for i, value in enumerate(values):
        cumsum += (i + 1) * value

    return (2 * cumsum) / (n * sum(values)) - (n + 1) / n
```

**해석:**
- 0.0-0.3: 균등 분산 (팀 협업)
- 0.3-0.6: 불균등 (주 작성자 + 기여자)
- 0.6-1.0: 집중 (단일 소유자)

---

## 4. Co-Change Analysis

### 개념
**Co-change** = 동일 커밋에서 함께 변경되는 파일들

높은 co-change = 강한 의존성/논리적 결합

### 데이터 모델

```python
@dataclass
class CoChangePattern:
    file_a: str
    file_b: str

    # 동시 변경 횟수
    cochange_count: int         # 함께 변경된 횟수
    total_changes: int          # 전체 변경 횟수

    # Co-change 강도
    jaccard_index: float        # 0~1 (1=항상 함께)
    support: float              # co-change 비율
    confidence: float           # A 변경 시 B도 변경될 확률

    # 시간 정보
    last_cochange: datetime
    recent_cochanges: int       # 최근 3개월
```

### 구현

```python
# src/contexts/analysis_indexing/infrastructure/git_history/cochange.py
class CoChangeAnalyzer:
    async def analyze_cochanges(
        self,
        repo_path: Path,
        min_support: float = 0.1,  # 최소 10% 동시 변경
    ) -> list[CoChangePattern]:

        # 1. 커밋별 변경 파일 수집
        commit_files: dict[str, set[str]] = {}

        for commit in await self.git.get_all_commits(repo_path):
            files = await self.git.get_changed_files(repo_path, commit)
            commit_files[commit] = set(files)

        # 2. Co-change 패턴 탐지 (빈발 항목 집합)
        patterns = []
        file_changes = defaultdict(int)

        # 파일별 변경 횟수
        for files in commit_files.values():
            for file in files:
                file_changes[file] += 1

        # Pair-wise co-change
        for files in commit_files.values():
            for file_a, file_b in itertools.combinations(files, 2):
                patterns.append((file_a, file_b))

        # 빈도 계산
        cochange_counts = Counter(patterns)

        # CoChangePattern 생성
        results = []
        for (file_a, file_b), count in cochange_counts.items():
            total_a = file_changes[file_a]
            total_b = file_changes[file_b]

            # Jaccard Index: |A ∩ B| / |A ∪ B|
            jaccard = count / (total_a + total_b - count)

            # Support: co-change / total commits
            support = count / len(commit_files)

            # Confidence: co-change / changes(A)
            confidence = count / total_a

            if support >= min_support:
                results.append(CoChangePattern(
                    file_a=file_a,
                    file_b=file_b,
                    cochange_count=count,
                    total_changes=total_a + total_b,
                    jaccard_index=jaccard,
                    support=support,
                    confidence=confidence,
                ))

        return sorted(results, key=lambda x: x.jaccard_index, reverse=True)
```

### 활용

```python
# 강한 co-change 파일 찾기
strong_cochanges = [
    p for p in patterns
    if p.jaccard_index >= 0.5  # 50% 이상 함께 변경
]

# A 변경 시 B도 변경해야 할 확률
if any(p.file_a == "main.py" and p.confidence >= 0.8 for p in patterns):
    print("main.py 변경 시 80% 확률로 다른 파일도 변경 필요")
```

---

## 5. Evolution Tracking

### 개념
시간에 따른 코드 품질 변화 추적

### 추적 지표

```python
@dataclass
class EvolutionMetrics:
    file_path: str
    snapshots: list[EvolutionSnapshot]

@dataclass
class EvolutionSnapshot:
    commit_hash: str
    date: datetime

    # 크기
    lines_of_code: int

    # 복잡도
    cyclomatic_complexity: float
    cognitive_complexity: float

    # 품질
    num_functions: int
    avg_function_length: float
    num_comments: int
    comment_ratio: float

    # 이슈
    num_todos: int
    num_fixmes: int
```

### 구현

```python
# src/contexts/analysis_indexing/infrastructure/git_history/evolution.py
class EvolutionTracker:
    async def track_file_evolution(
        self,
        repo_path: Path,
        file_path: str,
        sample_rate: int = 10,  # 10 커밋마다
    ) -> EvolutionMetrics:

        commits = await self.git.get_file_history(repo_path, file_path)
        snapshots = []

        for i, commit in enumerate(commits[::sample_rate]):
            # Checkout 커밋
            content = await self.git.get_file_at_commit(
                repo_path,
                file_path,
                commit.hash,
            )

            # 메트릭 계산
            snapshot = await self._analyze_content(content, commit)
            snapshots.append(snapshot)

        return EvolutionMetrics(file_path=file_path, snapshots=snapshots)

    async def _analyze_content(
        self,
        content: str,
        commit: Commit,
    ) -> EvolutionSnapshot:

        # AST 파싱
        tree = self.parser.parse(content.encode())

        # 복잡도 계산
        complexity = self._calculate_complexity(tree)

        # 함수 분석
        functions = self._extract_functions(tree)

        return EvolutionSnapshot(
            commit_hash=commit.hash,
            date=commit.date,
            lines_of_code=len(content.splitlines()),
            cyclomatic_complexity=complexity.cyclomatic,
            cognitive_complexity=complexity.cognitive,
            num_functions=len(functions),
            avg_function_length=sum(f.lines for f in functions) / len(functions),
            num_comments=content.count('#'),  # Python
            comment_ratio=content.count('#') / len(content.splitlines()),
        )
```

### 품질 트렌드 분석

```python
async def detect_quality_degradation(
    self,
    metrics: EvolutionMetrics,
) -> list[str]:
    """품질 저하 감지"""

    issues = []
    snapshots = metrics.snapshots

    # 1. 복잡도 증가 (30% 이상)
    if snapshots[-1].cyclomatic_complexity / snapshots[0].cyclomatic_complexity > 1.3:
        issues.append("Complexity increased by >30%")

    # 2. 함수 길이 증가
    if snapshots[-1].avg_function_length / snapshots[0].avg_function_length > 1.5:
        issues.append("Function length increased by >50%")

    # 3. Comment ratio 감소
    if snapshots[-1].comment_ratio < snapshots[0].comment_ratio * 0.5:
        issues.append("Comment ratio dropped by >50%")

    return issues
```

---

## 6. 통합 방법

### IndexingStage 통합

```python
# src/contexts/analysis_indexing/infrastructure/stages/git_stage.py
class GitStage(IndexingStage):
    async def execute(self, ctx: StageContext) -> StageResult:
        git_metadata = await self._collect_basic_metadata(ctx)

        # Git History 분석 (L4 모드만)
        if ctx.mode == IndexingMode.DEEP:
            # Churn
            churn_analyzer = ChurnAnalyzer(self.git_service)
            hot_files = await churn_analyzer.detect_hot_files(ctx.repo_path)

            # Co-change
            cochange_analyzer = CoChangeAnalyzer(self.git_service)
            patterns = await cochange_analyzer.analyze_cochanges(ctx.repo_path)

            # Ownership
            blame_analyzer = BlameAnalyzer(self.git_service)
            ownership = {}
            for file in ctx.files:
                ownership[file] = await blame_analyzer.analyze_ownership(
                    ctx.repo_path,
                    file,
                )

            git_metadata.hot_files = hot_files
            git_metadata.cochange_patterns = patterns
            git_metadata.ownership = ownership

        return StageResult(success=True, data=git_metadata)
```

### RepoMap 강화

```python
# RepoMap에 Git 메트릭 추가
@dataclass
class EnrichedRepoMap:
    tree: RepoTree
    pagerank: dict[str, float]

    # Git 메트릭 추가
    hot_files: list[str]                    # High churn
    cochange_clusters: list[list[str]]      # 함께 변경되는 파일 그룹
    ownership_map: dict[str, str]           # file -> primary owner
```

---

## 성능 최적화

### Git 명령 캐싱

```python
class GitService:
    def __init__(self):
        self._cache: dict[str, Any] = {}
        self._cache_ttl = 3600  # 1시간

    async def get_file_history(self, repo_path: Path, file_path: str):
        cache_key = f"history:{repo_path}:{file_path}"

        if cache_key in self._cache:
            cached, timestamp = self._cache[cache_key]
            if time.time() - timestamp < self._cache_ttl:
                return cached

        # Git 명령 실행
        result = await self._run_git_log(repo_path, file_path)

        self._cache[cache_key] = (result, time.time())
        return result
```

### 병렬 처리

```python
# 파일별 병렬 분석
async def analyze_all_files(files: list[str]) -> dict[str, ChurnMetrics]:
    tasks = [
        analyze_file_churn(repo_path, file)
        for file in files
    ]

    results = await asyncio.gather(*tasks, return_exceptions=True)

    return {
        file: result
        for file, result in zip(files, results)
        if not isinstance(result, Exception)
    }
```

---

## 활용 사례

### 1. 리팩토링 우선순위

```python
# High churn + High complexity = 리팩토링 대상
candidates = []

for file in hot_files:
    metrics = await evolution_tracker.get_latest_metrics(file)

    if metrics.cyclomatic_complexity > 20:
        candidates.append((file, metrics.cyclomatic_complexity))

# 복잡도 순 정렬
candidates.sort(key=lambda x: x[1], reverse=True)
```

### 2. 코드 리뷰 대상

```python
# 소유권 분산도 낮음 + 변경 발생 = 리뷰 필요
for file in changed_files:
    ownership = await blame_analyzer.analyze_ownership(repo_path, file)

    if ownership.gini_coefficient > 0.7:  # 독점적 소유
        print(f"{file}: {ownership.primary_owner}에게 리뷰 요청")
```

### 3. Co-change 기반 PR 제안

```python
# A 파일 변경 시 B 파일도 변경 권장
patterns = await cochange_analyzer.analyze_cochanges(repo_path)

for pattern in patterns:
    if pattern.file_a in pr_files and pattern.confidence > 0.8:
        print(f"Suggestion: Also update {pattern.file_b}")
```

---

## 참고

### 구현 파일
```
src/contexts/analysis_indexing/infrastructure/git_history/
├── churn.py
├── blame.py
├── cochange.py
├── evolution.py
├── git_service.py
└── enrichment.py
```

### 관련 논문
- Nagappan et al. (2006): "Use of Relative Code Churn Measures to Predict System Defect Density"
- D'Ambros et al. (2010): "On the Relationship Between Change Coupling and Software Defects"

---

**Last 
