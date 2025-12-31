# Codegen Loop - Architecture

**
**Scope:** codegen_loop의 구성요소/흐름 요약(Deep Dive의 “요약판”)  

---

## What it does

- 목표 기반으로 patch를 생성하고, ShadowFS 트랜잭션으로 적용/롤백
- 테스트/검증 결과에 따라 루프를 반복하며 수렴

---

## Key Components

- ShadowFS (file overlay/transaction)
- SandboxPort (테스트 실행)
- LLMPort (생성)
- (필요 시) HCGPort (그래프 컨텍스트)

---

## Links

- 상세: `deep-dive.md`

