# Retriever 즉시 실행 가능한 개선 사항

## 🎯 Quick Wins (15분 이내)

### 1. V3를 Main Export에 추가 ✅

**현재 문제**: v3가 독립적으로 존재, main retriever에서 import 불가

**해결**:
```python
# src/retriever/__init__.py에 추가
from .v3 import (
    RetrieverV3Service,
    RetrieverV3Config,
    IntentProbability,
    RankedHit,
    ConsensusStats,
    FeatureVector,
    FusedResultV3,
)
```

### 2. Integration Adapter 구현 ✅

**현재 문제**: Multi-index result → V3 service 연동 부재

**해결**: Adapter 클래스 구현

### 3. Unified Config 시작 ✅

**현재 문제**: Config 파편화

**해결**: 통합 config 초안

---

## 구현 시작
