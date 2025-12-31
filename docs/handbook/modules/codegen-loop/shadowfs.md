# Codegen Loop - ShadowFS

**
**Scope:** codegen_loop에서 ShadowFS/Transaction이 맡는 역할 요약  

---

## Why ShadowFS

- 에이전트가 파일을 변경할 때 **원본을 오염시키지 않고**
- diff/rollback/검증 루프를 안전하게 수행하기 위함

---

## Links

- 상세(3-layer 구조/엣지케이스/이벤트): `deep-dive.md`

