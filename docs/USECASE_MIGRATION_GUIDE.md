# Usecase Migration Guide

> **목표**: Clean Architecture 원칙에 따라 pipeline/adapters에서 application usecase를 사용하도록 점진적 마이그레이션

## 📊 현재 상태 vs 목표

### Before (현재)
```
Pipeline/Adapters → Infrastructure (직접 호출)
```

### After (목표)
```
Pipeline/Adapters → Application (UseCase) → Infrastructure
```

---

## 🎯 마이그레이션 우선순위

| 순위 | 분석기 | UseCase | 현재 상태 | 복잡도 |
|------|--------|---------|-----------|--------|
| 1 | Concurrency | `ConcurrencyAnalysisUseCase` | `AsyncRaceDetector` 직접 | ⭐ 낮음 |
| 2 | Effect | `EffectAnalysisUseCase` | `EffectAnalyzer` 직접 | ⭐ 낮음 |
| 3 | Points-To | `PointsToAnalyzer` (application) | `PointsToAnalyzer` 직접 | ⭐⭐ 중간 |
| 4 | Taint | `AnalyzeTaintUseCase` | `TaintAnalyzer` 직접 | ⭐⭐⭐ 높음 |
| 5 | Clone | (없음 - 생성 필요) | `HybridCloneDetector` 직접 | ⭐⭐ 중간 |

---

## 📝 마이그레이션 패턴

### Step 1: UseCase 인터페이스 확인

```rust
// features/concurrency_analysis/application/analyze_concurrency.rs
pub struct ConcurrencyAnalysisUseCase {
    // ...
}

impl ConcurrencyAnalysisUseCase {
    pub fn new() -> Self { ... }
    pub fn analyze(&self, nodes: &[Node], edges: &[Edge]) -> ConcurrencySummary { ... }
}
```

### Step 2: Orchestrator에서 UseCase Import

```rust
// pipeline/end_to_end_orchestrator.rs
// Before:
use crate::features::concurrency_analysis::{AsyncRaceDetector, RaceCondition};

// After:
use crate::features::concurrency_analysis::application::ConcurrencyAnalysisUseCase;
```

### Step 3: execute_l* 메서드 수정

```rust
// Before:
fn execute_l18_concurrency_analysis(...) {
    let detector = AsyncRaceDetector::new();
    detector.analyze(...)
}

// After:
fn execute_l18_concurrency_analysis(...) {
    let usecase = ConcurrencyAnalysisUseCase::new();
    usecase.analyze(...)
}
```

---

## ✅ 체크리스트

### Phase 1: Concurrency & Effect (간단) ✅ DONE
- [x] `ConcurrencyAnalysisUseCase` 연결
- [x] `EffectAnalysisUseCase` 연결
- [x] 테스트 통과 확인

### Phase 2: Points-To (중간) ✅ 이미 완료
- [x] `PointsToAnalyzer` (application) 연결 - 기존에 이미 적용됨
- [x] Config 매핑 확인
- [x] 테스트 통과 확인

### Phase 3: Taint (복잡) - 추후 진행
- [ ] `AnalyzeTaintUseCase` 연결 (async + DI 필요)
- [ ] `IFDSTaintService` 연결 (optional)
- [ ] Config 매핑 확인
- [ ] 테스트 통과 확인

**Note**: Taint UseCase는 async/await와 DI 컨테이너가 필요하여 별도 Phase로 진행

### Phase 4: 나머지 (옵션)
- [ ] Clone Detection UseCase 생성 (필요시)
- [ ] PyO3 API 마이그레이션 (나중)

---

## ⚠️ 주의사항

1. **호환성 유지**: 기존 API 시그니처 변경 금지
2. **점진적 전환**: 한 번에 하나씩
3. **테스트 우선**: 변경 전 테스트 추가
4. **성능 모니터링**: 오버헤드 확인

---

## 📁 관련 파일

| 역할 | 파일 |
|------|------|
| Orchestrator | `pipeline/end_to_end_orchestrator.rs` |
| Concurrency UC | `features/concurrency_analysis/application/analyze_concurrency.rs` |
| Effect UC | `features/effect_analysis/application/analyze_effects.rs` |
| Points-To UC | `features/points_to/application/analyzer.rs` |
| Taint UC | `features/taint_analysis/application/mod.rs` |
