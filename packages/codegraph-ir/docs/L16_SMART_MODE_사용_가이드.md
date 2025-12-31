# L16 RepoMap Smart Mode - 자동 감지 가이드

**날짜**: 2025-12-28
**기능**: 사용 상황에 따라 자동으로 최적 PageRank 모드 선택

---

## 🎯 개요

Smart Mode는 사용 상황을 자동 분석하여 적절한 PageRank 알고리즘을 활성화합니다.

**장점**:
- ✅ 사용자가 직접 설정하지 않아도 됨
- ✅ 상황별 최적 성능/기능 균형
- ✅ 7가지 감지 규칙으로 정확한 판단

---

## 📊 자동 감지 규칙

### Rule 1: 초기 인덱싱
```rust
if context.is_initial_indexing {
    return RecommendedMode::Fast;  // 가장 빠르게
}
```
**예시**: 새 리포지토리를 처음 인덱싱할 때

---

### Rule 2: 명시적 분석 타입
```rust
match analysis_type {
    BugFix => RecommendedMode::AI,                  // PPR 활성화
    ArchitectureReview => RecommendedMode::Architecture,  // HITS 활성화
    RefactoringPlan => RecommendedMode::Full,       // 모두 활성화
    GeneralQuery => RecommendedMode::Fast,          // 빠르게
    // ...
}
```

---

### Rule 3: 아키텍처 리뷰 플래그
```rust
if context.is_architecture_review {
    return RecommendedMode::Architecture;  // HITS for Authority/Hub
}
```

---

### Rule 4: AI 에이전트 플래그
```rust
if context.is_ai_agent {
    return RecommendedMode::AI;  // PPR for context-aware search
}
```

---

### Rule 5: 타겟 파일 존재
```rust
if context.target_file.is_some() {
    return RecommendedMode::AI;  // 특정 파일 기준 탐색
}
```

---

### Rule 6: 쿼리 키워드 분석
```rust
if query.contains("bug") || query.contains("fix") {
    return RecommendedMode::AI;
}
if query.contains("architecture") || query.contains("refactor") {
    return RecommendedMode::Architecture;
}
```

---

### Rule 7: 리포지토리 크기
```rust
if repo_size < 10_000 {
    return RecommendedMode::Full;  // 작은 리포는 Full mode도 빠름
}
```

---

## 🚀 Rust 사용 예시

### 예시 1: 초기 인덱싱 (Fast Mode)

```rust
use codegraph_ir::pipeline::{E2EPipelineConfig, ModeDetectionContext};

let config = E2EPipelineConfig::default()
    .with_smart_pagerank(ModeDetectionContext {
        is_initial_indexing: true,
        ..Default::default()
    });

// 결과: Fast mode (1.19초)
// - enable_personalized: false
// - enable_hits: false
```

---

### 예시 2: AI 에이전트 버그 수정

```rust
use codegraph_ir::pipeline::{E2EPipelineConfig, ModeDetectionContext, AnalysisType};

let config = E2EPipelineConfig::default()
    .with_smart_pagerank(ModeDetectionContext {
        target_file: Some("auth/login.rs".to_string()),
        analysis_type: Some(AnalysisType::BugFix),
        is_ai_agent: true,
        ..Default::default()
    });

// 결과: AI mode (~2.3초)
// - enable_personalized: true  ← PPR 활성화!
// - enable_hits: false
```

**사용 시나리오**:
```rust
// 1. 버그 파일 발견
let bug_file = "auth/login.rs";

// 2. AI mode로 인덱싱
let config = E2EPipelineConfig::default()
    .with_smart_pagerank(ModeDetectionContext {
        target_file: Some(bug_file.to_string()),
        analysis_type: Some(AnalysisType::BugFix),
        ..Default::default()
    });

// 3. 관련 파일만 집중 분석
let result = IRIndexingOrchestrator::new(config).execute()?;

// 4. Personalized PageRank로 관련 파일 찾기
let context = ContextSet::from_file(bug_file);
let related = result.repomap.personalized_pagerank(&context);
// → 버그와 관련된 상위 10개 파일만 AI에게 전달
```

---

### 예시 3: 아키텍처 리뷰

```rust
let config = E2EPipelineConfig::default()
    .with_smart_pagerank(ModeDetectionContext {
        is_architecture_review: true,
        query: Some("analyze repository structure".to_string()),
        ..Default::default()
    });

// 결과: Architecture mode (~2.3초)
// - enable_personalized: false
// - enable_hits: true  ← HITS 활성화!
```

**분석 예시**:
```rust
let result = IRIndexingOrchestrator::new(config).execute()?;

// Authority: 핵심 라이브러리 (많이 참조됨)
let authorities = result.repomap.top_authorities(10);
for (file, score) in authorities {
    println!("Core library: {} (authority: {:.3})", file, score);
}

// Hub: 통합 지점 (많이 참조함)
let hubs = result.repomap.top_hubs(10);
for (file, score) in hubs {
    println!("Integration point: {} (hub: {:.3})", file, score);
}
```

---

### 예시 4: 쿼리 기반 자동 감지

```rust
let config = E2EPipelineConfig::default()
    .with_smart_pagerank(ModeDetectionContext {
        query: Some("fix authentication bug in login flow".to_string()),
        ..Default::default()
    });

// 자동 감지:
// - "fix" 키워드 → AI mode
// - "bug" 키워드 → AI mode
// 결과: AI mode (PPR 활성화)
```

---

### 예시 5: 작은 리포지토리

```rust
let config = E2EPipelineConfig::default()
    .with_smart_pagerank(ModeDetectionContext {
        repo_size: Some(5_000),  // 5K LOC
        ..Default::default()
    });

// 결과: Full mode (~0.4초)
// - 작은 리포는 Full mode도 충분히 빠름
// - 모든 메트릭 사용 가능
```

---

## 🐍 Python API 사용 예시

### PyO3 바인딩 (예정)

```python
from codegraph_ir import E2EPipelineConfig, ModeDetectionContext, AnalysisType

# 예시 1: 초기 인덱싱
config = E2EPipelineConfig.default().with_smart_pagerank(
    ModeDetectionContext(is_initial_indexing=True)
)
# → Fast mode

# 예시 2: AI 버그 수정
config = E2EPipelineConfig.default().with_smart_pagerank(
    ModeDetectionContext(
        target_file="auth/login.py",
        analysis_type=AnalysisType.BugFix,
        is_ai_agent=True,
    )
)
# → AI mode

# 예시 3: 아키텍처 분석
config = E2EPipelineConfig.default().with_smart_pagerank(
    ModeDetectionContext(
        query="analyze repository architecture",
        is_architecture_review=True,
    )
)
# → Architecture mode
```

---

## 🔧 Builder Pattern 사용

### Mutable 방식

```rust
let mut config = E2EPipelineConfig::default();

// Smart mode 적용
let mode = config.configure_smart_pagerank(ModeDetectionContext {
    target_file: Some("src/main.rs".to_string()),
    ..Default::default()
});

println!("Selected mode: {:?}", mode);
println!("Description: {}", mode.description());
println!("Expected time: {}x of Fast mode", mode.time_multiplier());
```

### Fluent 방식 (체이닝)

```rust
let config = E2EPipelineConfig::default()
    .with_smart_pagerank(ModeDetectionContext {
        analysis_type: Some(AnalysisType::RefactoringPlan),
        repo_size: Some(50_000),
        ..Default::default()
    });
```

---

## 📊 모드 비교 (자동 선택 결과)

| 입력 조건 | 선택된 모드 | PPR | HITS | 시간 | 설명 |
|----------|------------|-----|------|------|------|
| `is_initial_indexing=true` | **Fast** | ❌ | ❌ | 1.19s | 빠른 인덱싱 |
| `analysis_type=BugFix` | **AI** | ✅ | ❌ | 2.3s | 컨텍스트 탐색 |
| `target_file="login.rs"` | **AI** | ✅ | ❌ | 2.3s | 특정 파일 기준 |
| `is_architecture_review=true` | **Architecture** | ❌ | ✅ | 2.3s | Authority/Hub |
| `query="refactor"` | **Architecture** | ❌ | ✅ | 2.3s | 키워드 감지 |
| `analysis_type=RefactoringPlan` | **Full** | ✅ | ✅ | 4.2s | 완전 분석 |
| `repo_size=5000` | **Full** | ✅ | ✅ | 0.4s | 작은 리포 |
| (기본값) | **Fast** | ❌ | ❌ | 1.19s | 안전한 선택 |

---

## 🎨 실전 시나리오

### 시나리오 1: Claude Code 버그 수정

```rust
// Claude가 버그를 발견함
let bug_file = "src/auth/session.rs";
let user_query = "Fix authentication timeout bug in session handler";

// Smart mode 자동 감지
let config = E2EPipelineConfig::default()
    .with_smart_pagerank(ModeDetectionContext {
        target_file: Some(bug_file.to_string()),
        query: Some(user_query.to_string()),
        is_ai_agent: true,
        ..Default::default()
    });
// → AI mode (자동)

// 인덱싱
let result = IRIndexingOrchestrator::new(config).execute()?;

// Personalized PageRank로 관련 파일만 찾기
let context = ContextSet::from_file(bug_file);
let related_files = result.repomap.personalized_pagerank(&context).top_n(10);

// Claude: 이 10개 파일만 읽고 수정!
println!("Related files to analyze:");
for (file, score) in related_files {
    println!("  {} (relevance: {:.3})", file, score);
}
```

---

### 시나리오 2: 주간 아키텍처 리포트

```rust
// 매주 월요일 자동 실행
let config = E2EPipelineConfig::default()
    .with_smart_pagerank(ModeDetectionContext {
        is_architecture_review: true,
        query: Some("weekly architecture review".to_string()),
        ..Default::default()
    });
// → Architecture mode (자동)

let result = IRIndexingOrchestrator::new(config).execute()?;

// 리포트 생성
println!("=== Top 10 Core Libraries (High Authority) ===");
for (file, auth) in result.repomap.top_authorities(10) {
    println!("  {} - {:.3} (refactor with care!)", file, auth);
}

println!("\n=== Top 10 Integration Points (High Hub) ===");
for (file, hub) in result.repomap.top_hubs(10) {
    println!("  {} - {:.3} (consider decoupling)", file, hub);
}
```

---

### 시나리오 3: CI/CD 파이프라인

```rust
// PR 머지 전 빠른 검증
let config = E2EPipelineConfig::default()
    .with_smart_pagerank(ModeDetectionContext {
        is_initial_indexing: true,  // 빠른 인덱싱 우선
        ..Default::default()
    });
// → Fast mode (자동)

let start = Instant::now();
let result = IRIndexingOrchestrator::new(config).execute()?;
let elapsed = start.elapsed();

// CI에서 빠른 피드백
assert!(elapsed.as_secs() < 5, "Indexing too slow for CI");
println!("✅ Fast indexing completed in {:?}", elapsed);
```

---

### 시나리오 4: 대화형 탐색 (Cursor/VSCode)

```rust
// 사용자 쿼리에 따라 동적 감지
fn handle_user_query(query: &str) -> Result<Vec<String>> {
    let config = E2EPipelineConfig::default()
        .with_smart_pagerank(ModeDetectionContext {
            query: Some(query.to_string()),
            ..Default::default()
        });

    // 키워드 자동 감지:
    // - "bug", "fix" → AI mode
    // - "architecture", "refactor" → Architecture mode
    // - 기타 → Fast mode

    let result = IRIndexingOrchestrator::new(config).execute()?;
    Ok(result.top_files(20))
}

// 예시
handle_user_query("find files related to authentication bug");
// → AI mode (자동)

handle_user_query("show repository structure");
// → Fast mode (자동)

handle_user_query("identify core libraries for refactoring");
// → Architecture mode (자동)
```

---

## 🔍 감지 결과 확인

### 모드 정보 출력

```rust
use codegraph_ir::pipeline::*;

let context = ModeDetectionContext {
    target_file: Some("main.rs".to_string()),
    ..Default::default()
};

let mut config = E2EPipelineConfig::default();
let mode = config.configure_smart_pagerank(context);

// 선택된 모드 정보
println!("Mode: {:?}", mode);
println!("Description: {}", mode.description());
println!("Time multiplier: {}x", mode.time_multiplier());

// 설정 확인
println!("PPR enabled: {}", config.pagerank_settings.enable_personalized);
println!("HITS enabled: {}", config.pagerank_settings.enable_hits);
println!("Max iterations: {}", config.pagerank_settings.max_iterations);
```

**출력 예시**:
```
Mode: AI
Description: AI mode: Context-aware code navigation
Time multiplier: 2x
PPR enabled: true
HITS enabled: false
Max iterations: 5
```

---

## 💡 팁 & 권장사항

### ✅ DO: Smart Mode 사용

```rust
// Good: 자동 감지
let config = E2EPipelineConfig::default()
    .with_smart_pagerank(context);
```

### ❌ DON'T: 수동 설정 (불필요)

```rust
// Bad: 매번 수동 설정 (번거로움)
let mut config = E2EPipelineConfig::default();
config.pagerank_settings.enable_personalized = true;
config.pagerank_settings.enable_hits = false;
// ...
```

---

### ✅ DO: 컨텍스트 제공

```rust
// Good: 충분한 정보 제공
let context = ModeDetectionContext {
    query: Some(user_query.clone()),
    target_file: Some(current_file.clone()),
    analysis_type: Some(AnalysisType::BugFix),
    is_ai_agent: true,
    ..Default::default()
};
```

### ❌ DON'T: 빈 컨텍스트

```rust
// Bad: 정보 부족 (항상 Fast mode)
let context = ModeDetectionContext::default();
```

---

## 📚 관련 문서

- **L16_알고리즘_가이드.md** - 각 알고리즘 상세 설명
- **L16_런타임_설정_가이드.md** - 수동 설정 방법
- **L16_최종_완성_보고서.md** - 전체 최적화 결과
- **pagerank_mode_detector.rs** - 감지 로직 소스 코드

---

## 🎉 요약

**Smart Mode = 자동으로 최적 선택**

1. ✅ **7가지 감지 규칙**: 초기 인덱싱, 분석 타입, 플래그, 타겟 파일, 쿼리, 리포 크기, 기본값
2. ✅ **4가지 모드**: Fast (1.19s), AI (2.3s), Architecture (2.3s), Full (4.2s)
3. ✅ **간단한 API**: `config.with_smart_pagerank(context)`
4. ✅ **정확한 판단**: 상황별 최적 성능/기능 균형

**사용자가 해야 할 일**: 컨텍스트만 제공하면 끝!

---

**작성일**: 2025-12-28
**버전**: 1.0
**상태**: ✅ 프로덕션 사용 가능
