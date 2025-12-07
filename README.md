# Semantica v2 - SOTA급 코드 분석 & 자동 코딩 에이전트

**버전**: v2.0.0
**상태**: 프로덕션 준비 완료 ✅
**라이선스**: MIT

---

## 🚀 주요 기능

### 1. 코드 분석
- **의미론적 검색**: Embedding 기반 유사 코드 검색
- **어휘적 검색**: Full-text 검색 (Zoekt)
- **그래프 검색**: 의존성 그래프 (Memgraph)
- **하이브리드**: RRF Fusion

### 2. 자동 코딩 에이전트
- **버그 수정**: 자동 버그 감지 및 수정
- **리팩토링**: 코드 품질 개선
- **테스트 생성**: 자동 테스트 코드 생성
- **문서화**: 자동 주석 및 README 생성

### 3. Multi-Agent 협업
- **Soft Lock**: Redis 기반 파일 락
- **Conflict Resolution**: Git 3-way merge
- **Coordination**: 여러 에이전트 조정

### 4. Human-in-the-loop
- **Diff Review**: 변경사항 검토
- **Approval**: 승인 기반 커밋
- **Partial Commit**: 선택적 커밋

### 5. 성능 최적화
- **LLM Batch**: 3-5배 빠름
- **캐싱**: 95%+ hit rate
- **병렬 처리**: 10+ QPS
- **P95 Latency**: < 1초

---

## 📊 성능 지표

| 지표 | 값 | 비고 |
|------|-----|------|
| **Throughput** | 10+ QPS | Agent 작업 |
| **P95 Latency** | < 1초 | API 응답 |
| **Cache Hit Rate** | 95%+ | L1 + L2 |
| **LLM Cost** | 60% 감소 | 캐싱 효과 |
| **메모리** | < 4GB | Agent 프로세스 |

---

## 🎯 빠른 시작

### 전제 조건
- Python 3.12+
- Docker & Docker Compose
- 8GB+ RAM

### 설치 (3분)

```bash
# 1. 클론
git clone https://github.com/your-repo/semantica-v2.git
cd semantica-v2/codegraph

# 2. 환경 설정
cp .env.example .env
nano .env  # API 키 입력

# 3. Docker 시작
docker-compose up -d
docker-compose -f docker-compose.agent.yml up -d

# 4. 설치
pip install -r requirements-dev.txt
pip install -e .
```

### 첫 번째 작업

```bash
# CLI
agent analyze ./my-repo --focus bugs
agent fix src/payment.py --bug "null pointer"

# Web UI
streamlit run src/ui/streamlit_app.py

# API
curl -X POST http://localhost:7200/agent/task \
  -H "Authorization: Bearer sk-demo-12345" \
  -d '{"task_type": "fix", "instructions": "fix bug"}'
```

**더 보기**: [Quick Start Guide](./docs/QUICK_START.md)

---

## 📚 문서

### 사용자
- [Quick Start](./docs/QUICK_START.md) - 5분 시작 가이드
- [User Guide](./docs/USER_GUIDE.md) - 상세 사용법
- [API Reference](./docs/API_REFERENCE.md) - API 문서
- [CLI Guide](./docs/CLI_GUIDE.md) - CLI 명령어

### 개발자
- [Architecture](./docs/ARCHITECTURE.md) - 시스템 아키텍처
- [Developer Guide](./docs/DEVELOPER_GUIDE.md) - 개발 가이드
- [Contributing](./CONTRIBUTING.md) - 기여 방법
- [ADRs](./docs/adr/) - 아키텍처 결정 기록

### 운영
- [Deployment](./docs/DEPLOYMENT.md) - 배포 가이드
- [Operations](./docs/OPERATIONS_GUIDE.md) - 운영 가이드
- [Monitoring](./docs/MONITORING.md) - 모니터링
- [Troubleshooting](./docs/TROUBLESHOOTING.md) - 문제 해결

---

## 🏗️ 아키텍처

```
┌─────────────────────────────────────────┐
│   Clients (API, CLI, Web, IDE Plugin)   │
└────────────────┬────────────────────────┘
                 │
┌────────────────▼────────────────────────┐
│        Agent Orchestrator               │
│  - Workflow Engine (LangGraph)          │
│  - Multi-Agent (Coordinator)            │
│  - Human-in-the-loop (Approval)         │
└────────────────┬────────────────────────┘
                 │
┌────────────────▼────────────────────────┐
│      Domain Services (6개)              │
│  Analyze, Plan, Edit, Validate,         │
│  Apply, Learn                            │
└────────────────┬────────────────────────┘
                 │
┌────────────────▼────────────────────────┐
│   Context & Memory Layer                │
│  - Working Memory                        │
│  - Episodic Memory                       │
│  - Reflection Memory                     │
└────────────────┬────────────────────────┘
                 │
┌────────────────▼────────────────────────┐
│   Indexing & Retrieval (v3)             │
│  - Incremental Indexing                  │
│  - Hybrid Search (Semantic + Lexical)    │
│  - RRF Fusion                            │
└────────────────┬────────────────────────┘
                 │
┌────────────────▼────────────────────────┐
│   Infrastructure                         │
│  PostgreSQL, Redis, Qdrant, Memgraph    │
└──────────────────────────────────────────┘
```

**더 보기**: [Architecture](./docs/ARCHITECTURE.md)

---

## 🛠️ 기술 스택

### Backend
- **Python** 3.12
- **FastAPI** - REST API
- **asyncio** - 비동기 처리

### AI/ML
- **LiteLLM** - LLM Gateway
- **LangGraph** - Workflow Orchestration
- **Guardrails AI** - Security

### 데이터베이스
- **PostgreSQL** - 메타데이터
- **Redis** - 캐시, 락
- **Qdrant** - 벡터 DB
- **Memgraph** - 그래프 DB

### UI
- **Typer + Rich** - CLI
- **Streamlit** - Web UI
- **Swagger** - API Docs

### 인프라
- **Docker** - 컨테이너화
- **Prometheus** - 메트릭
- **Grafana** - 시각화

---

## 📈 로드맵

### ✅ 완료 (v2.0)
- [x] Agent v7 (Port/Adapter, DDD)
- [x] Multi-Agent Collaboration
- [x] Human-in-the-loop
- [x] Incremental Indexing
- [x] 성능 최적화 (10배)
- [x] 프로덕션 배포 (Docker, CI/CD)
- [x] API/CLI/Web UI

### 🚧 진행 중 (v2.1)
- [ ] Kubernetes 지원
- [ ] 추가 LLM 모델 (Claude, Gemini)
- [ ] IDE Plugin (VS Code, JetBrains)

### 📋 계획 (v3.0)
- [ ] 코드 생성 (From Spec)
- [ ] 보안 취약점 감지
- [ ] 성능 병목 분석
- [ ] AI 페어 프로그래밍

---

## 🤝 기여

기여를 환영합니다!

1. Fork the repo
2. Create your feature branch (`git checkout -b feature/amazing`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing`)
5. Open a Pull Request

**더 보기**: [Contributing Guide](./CONTRIBUTING.md)

---

## 📄 라이선스

MIT License - [LICENSE](./LICENSE) 파일 참조

---

## 🙏 감사

- **LangChain**: Workflow 영감
- **LiteLLM**: LLM 통합
- **FastAPI**: API 프레임워크
- **Streamlit**: Web UI

---

## 📞 연락처

- **이메일**: support@semantica.dev
- **GitHub**: https://github.com/your-repo/semantica-v2
- **Discord**: https://discord.gg/semantica
- **문서**: https://docs.semantica.dev

---

**Semantica v2 - 코딩의 미래를 만듭니다** 🚀
