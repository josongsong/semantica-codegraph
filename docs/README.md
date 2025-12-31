# CodeGraph Documentation

**SOTA-level 코드 분석 및 시맨틱 검색 엔진**

---

## 📚 빠른 시작

| 문서 | 설명 |
|------|------|
| [QUICKSTART.md](./QUICKSTART.md) | 5분 안에 시작하기 |
| [CLEAN_ARCHITECTURE_SUMMARY.md](./CLEAN_ARCHITECTURE_SUMMARY.md) | 시스템 아키텍처 |
| [RUST_ENGINE_API.md](./RUST_ENGINE_API.md) | Rust 엔진 API 레퍼런스 |

---

## 🎯 핵심 기능 가이드

### 분석 기능
| 가이드 | 설명 |
|--------|------|
| [guides/TRCR.md](./guides/TRCR.md) | 보안 취약점 탐지 (304 rules, 49 CWEs) |
| [HEAP_ANALYSIS_API.md](./HEAP_ANALYSIS_API.md) | Separation Logic & Heap 분석 |

### 인프라
| 가이드 | 설명 |
|--------|------|
| [guides/FILE_WATCHER.md](./guides/FILE_WATCHER.md) | 실시간 파일 감지 & 증분 분석 |
| [INDEXING_STRATEGY.md](./INDEXING_STRATEGY.md) | 인덱싱 전략 및 최적화 |
| [BENCHMARK_GUIDE.md](./BENCHMARK_GUIDE.md) | 벤치마크 실행 가이드 |

---

## 🏗️ 아키텍처 및 설계

### RFC (Request for Comments)
**설정 시스템:**
- [RFC-CONFIG-SYSTEM.md](./RFC-CONFIG-SYSTEM.md) - 통합 설정 시스템 (59 settings)

**벤치마크:**
- [RFC-BENCHMARK-SYSTEM.md](./RFC-BENCHMARK-SYSTEM.md) - 벤치마크 시스템 설계

**고급 RFC:**
- [rfcs/](./rfcs/) - 26개 RFC 문서 (최적화, SDK, 캐시 등)

### ADR (Architecture Decision Records)
**핵심 아키텍처:**
- [adr/ADR-070-rust-engine-full-migration.md](./adr/ADR-070-rust-engine-full-migration.md) - Rust 엔진 전환
- [adr/ADR-072-clean-rust-python-architecture.md](./adr/ADR-072-clean-rust-python-architecture.md) - Rust-Python 경계
- [adr/RFC-045-unified-incremental-system.md](./adr/RFC-045-unified-incremental-system.md) - 증분 분석 시스템
- [adr/RFC-071-analysis-primitives-api.md](./adr/RFC-071-analysis-primitives-api.md) - 분석 Primitive API

---

## 🎓 학습 경로

### 초급 (처음 사용자)
1. [QUICKSTART.md](./QUICKSTART.md) - 설치 및 첫 실행
2. [guides/TRCR.md](./guides/TRCR.md) - 보안 분석 데모
3. [RUST_ENGINE_API.md](./RUST_ENGINE_API.md) - 기본 API 이해

### 중급 (기능 활용)
1. [CLEAN_ARCHITECTURE_SUMMARY.md](./CLEAN_ARCHITECTURE_SUMMARY.md) - 전체 구조 이해
2. [guides/FILE_WATCHER.md](./guides/FILE_WATCHER.md) - 증분 분석 활용
3. [HEAP_ANALYSIS_API.md](./HEAP_ANALYSIS_API.md) - 고급 분석 기법
4. [RFC-CONFIG-SYSTEM.md](./RFC-CONFIG-SYSTEM.md) - 설정 최적화

### 고급 (시스템 확장)
1. [adr/](./adr/) - 아키텍처 결정 이해
2. [rfcs/](./rfcs/) - 설계 제안서 읽기
3. [INDEXING_STRATEGY.md](./INDEXING_STRATEGY.md) - 내부 구조 이해
4. [RFC-BENCHMARK-SYSTEM.md](./RFC-BENCHMARK-SYSTEM.md) - 성능 측정

---

## 📖 주요 개념

### Rust 엔진 (L1-L37)
**기본 분석 (L1-L8):**
- L1: AST 파싱
- L2: CFG (Control Flow Graph)
- L3: DFG (Data Flow Graph)
- L4: SSA (Static Single Assignment)
- L5: Dominance 분석
- L6: 타입 추론
- L7: Call Graph
- L8: Points-to 분석

**고급 분석 (L9-L21):**
- L14: Taint 분석 (TRCR)
- L10: Clone Detection
- L13: Cost 분석
- L16: Effect 분석
- L17-L21: RepoMap, PageRank, Slicing

자세한 내용: [RUST_ENGINE_API.md](./RUST_ENGINE_API.md)

### 설정 시스템
- **Preset**: Fast / Balanced / Thorough
- **Stage Override**: 개별 분석 단계 조정
- **YAML**: 완전 커스텀 설정

자세한 내용: [RFC-CONFIG-SYSTEM.md](./RFC-CONFIG-SYSTEM.md)

### 증분 분석
- **파일 감지**: fswatch/watchdog
- **의존성 추적**: import 그래프 기반
- **캐시 전략**: Adaptive cache (LRU + hit rate)

자세한 내용: [guides/FILE_WATCHER.md](./guides/FILE_WATCHER.md)

---

## 🔧 API 레퍼런스

### Python API
```python
import codegraph_ir

# 기본 분석
result = codegraph_ir.run_ir_indexing_pipeline(
    repo_root="/path/to/repo",
    enable_taint=True,
    use_trcr=True
)

# Taint 분석
from codegraph_ir import TaintAnalyzer
analyzer = TaintAnalyzer()
results = analyzer.analyze("/path/to/code")

# 증분 분석
from codegraph_ir import IncrementalAnalyzer
analyzer = IncrementalAnalyzer(watch_mode=True)
analyzer.watch()
```

전체 API: [RUST_ENGINE_API.md](./RUST_ENGINE_API.md)

---

## 📊 성능 벤치마크

| 분석 | 코드 크기 | 시간 | 메모리 |
|------|---------|------|-------|
| L1-L8 (기본) | 10K LOC | 2s | 150MB |
| L14 (TRCR) | 10K LOC | 2s | 180MB |
| Full (L1-L21) | 10K LOC | 5s | 300MB |

자세한 내용: [BENCHMARK_GUIDE.md](./BENCHMARK_GUIDE.md)

---

## 🗂️ 문서 구조

```
docs/
├── README.md                           (이 파일)
├── QUICKSTART.md                       빠른 시작
├── CLEAN_ARCHITECTURE_SUMMARY.md       아키텍처 개요
├── RUST_ENGINE_API.md                  Rust API 레퍼런스
├── HEAP_ANALYSIS_API.md                Heap 분석 API
├── INDEXING_STRATEGY.md                인덱싱 전략
├── BENCHMARK_GUIDE.md                  벤치마크 가이드
├── RFC-CONFIG-SYSTEM.md                설정 시스템
├── RFC-BENCHMARK-SYSTEM.md             벤치마크 시스템
│
├── guides/                             사용 가이드
│   ├── TRCR.md                        보안 분석 가이드
│   └── FILE_WATCHER.md                증분 분석 가이드
│
├── adr/                                아키텍처 결정 (4개)
│   ├── ADR-070-rust-engine-full-migration.md
│   ├── ADR-072-clean-rust-python-architecture.md
│   ├── RFC-045-unified-incremental-system.md
│   └── RFC-071-analysis-primitives-api.md
│
├── rfcs/                               설계 제안서 (26개)
│   ├── RFC-060-SOTA-Agent-Code-Editing.md
│   ├── RFC-RUST-CACHE-*.md
│   ├── RFC-RUST-SDK-*.md
│   └── ...
│
└── archive/                            아카이브
    └── obsolete_reports/               구 보고서 (자동 이동)
```

---

## 🤝 기여 가이드

**문서 작성 원칙:**
1. **팩트 중심**: 구현된 기능만 문서화
2. **경과 제외**: 진행 보고서는 archive로
3. **통합 우선**: 유사 문서는 하나로 통합
4. **예제 포함**: 모든 API는 예제 코드 제공

**RFC/ADR 작성:**
- RFC: 새로운 기능 제안
- ADR: 아키텍처 변경 결정

---

## 📞 지원

- **이슈**: [GitHub Issues](https://github.com/your-repo/issues)
- **문서 업데이트**: 2025-12-29

---

**버전**: v2.1
**상태**: ✅ 프로덕션 준비 완료
