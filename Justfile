# Semantica Codegraph v4 - Just Commands
# Run `just --list` to see all available commands

set shell := ["/bin/zsh", "-lc"]

# ========================================================================
# Quick Start & Help
# ========================================================================

# Show this help message with all available commands
help:
    @just --list

# Complete development environment setup (one-time)
dev-setup:
    #!/usr/bin/env zsh
    echo "🚀 Codegraph 개발 환경 설정 시작..."
    echo ""
    echo "1️⃣ Rust 환경 검사..."
    ./scripts/check_rust_env.sh || true
    echo ""
    echo "2️⃣ Rust 개발 도구 설치..."
    ./scripts/install_rust_tools.sh
    echo ""
    echo "3️⃣ Python 개발 환경 설정..."
    uv pip install -e ".[dev]"
    pre-commit install
    echo ""
    echo "4️⃣ 첫 빌드 테스트..."
    cd packages/codegraph-ir && cargo build
    echo ""
    echo "✅ 개발 환경 설정 완료!"
    echo ""
    echo "📚 다음 명령어로 개발을 시작하세요:"
    echo "  just rust-check       # 빠른 체크"
    echo "  just rust-test        # 테스트 실행"
    echo "  just rust-watch       # 실시간 컴파일"
    echo "  bacon                 # 실시간 clippy (권장)"
    echo ""

# Quick health check (environment + build)
health-check:
    #!/usr/bin/env zsh
    echo "🏥 시스템 상태 점검..."
    echo ""
    ./scripts/check_rust_env.sh
    echo ""
    echo "테스트 빌드..."
    cd packages/codegraph-ir && cargo check
    echo ""
    echo "✅ 모든 검사 통과!"

# ========================================================================
# Rust Development (Codegraph-IR)
# ========================================================================

# Quick check without building (fastest, 0.5s)
rust-check:
    cd packages/codegraph-ir && cargo check

# Build Rust packages (incremental, with sccache)
rust-build:
    cd packages/codegraph-ir && cargo build

# Build Rust packages in release mode
rust-build-release:
    cd packages/codegraph-ir && cargo build --release

# Run Rust tests (ultra-fast nextest, 16 cores) - EXCLUDES slow/ignored tests
rust-test:
    cd packages/codegraph-ir && cargo nextest run --no-fail-fast --profile default

# 🚀 Run FAST tests only (TDD mode, <10s target)
rust-test-fast:
    cd packages/codegraph-ir && cargo nextest run --profile fast --profile fast

# 🚀 FASTEST: 단일 테스트만 실행 (TDD용)
rust-test-one TEST:
    cd packages/codegraph-ir && cargo nextest run {{TEST}} --no-capture --profile tdd

# 🔥 5초 TDD: 초고속 피드백
rust-test-tdd:
    cd packages/codegraph-ir && cargo nextest run --profile tdd

# ⚡ 15초: 빠른 검증
rust-test-quick:
    cd packages/codegraph-ir && cargo nextest run --profile fast

# Run ONLY unit tests (fastest, recommended for TDD)
rust-test-unit:
    cd packages/codegraph-ir && cargo nextest run --no-fail-fast -E 'test(/^.*unit.*$/)'

# Run ONLY integration tests
rust-test-integration:
    cd packages/codegraph-ir && cargo nextest run --no-fail-fast -E 'test(/^.*integration.*$/)'

# Run ONLY e2e tests (slower)
rust-test-e2e:
    cd packages/codegraph-ir && cargo nextest run --no-fail-fast -E 'test(/^.*e2e.*$/)'

# Run slow/ignored tests (stress, performance, large benchmarks)
rust-test-slow:
    cd packages/codegraph-ir && cargo nextest run --no-fail-fast -- --ignored

# Run performance tests only
rust-test-perf:
    cd packages/codegraph-ir && cargo nextest run --no-fail-fast -E 'test(/^.*performance.*$/) | test(/^.*benchmark.*$/)'

# Run stress tests only
rust-test-stress:
    cd packages/codegraph-ir && cargo nextest run --no-fail-fast -E 'test(/^.*stress.*$/)'

# Run ALL tests including slow ones (CI용, 시간 오래 걸림)
rust-test-all:
    cd packages/codegraph-ir && cargo nextest run --no-fail-fast
    cd packages/codegraph-ir && cargo nextest run --no-fail-fast -- --ignored

# Run Rust tests for specific package
rust-test-package pkg:
    cd packages/codegraph-ir && cargo nextest run -p {{pkg}}

# Run Rust benchmarks
rust-bench:
    cd packages/codegraph-ir && cargo bench

# Lint Rust code (clippy)
rust-lint:
    cd packages/codegraph-ir && cargo clippy --all-targets --all-features -- -D warnings

# Format Rust code
rust-format:
    cd packages/codegraph-ir && cargo fmt --all

# Check Rust formatting
rust-format-check:
    cd packages/codegraph-ir && cargo fmt --all -- --check

# Full Rust CI pipeline (lint + test)
rust-ci: rust-lint rust-format-check rust-test

# Clean Rust build artifacts
rust-clean:
    cd packages/codegraph-ir && cargo clean

# Watch Rust code and auto-rebuild on changes
rust-watch:
    cd packages/codegraph-ir && cargo watch -x check -x test

# Generate Rust documentation and open in browser
rust-docs:
    cd packages/codegraph-ir && cargo doc --no-deps --open

# Show Rust dependency tree
rust-deps:
    cd packages/codegraph-ir && cargo tree --depth 3

# Show build timing analysis
rust-timings:
    cd packages/codegraph-ir && cargo build --timings

# Check sccache statistics
rust-sccache-stats:
    sccache --show-stats

# Clear sccache cache
rust-sccache-clear:
    sccache --zero-stats

# ========================================================================
# Architecture Boundary Protection (SOLID + Clean Architecture)
# ========================================================================

# 🏛️ 아키텍처 경계 검사 (cargo-deny + 커스텀 테스트)
rust-arch-check:
    #!/usr/bin/env zsh
    echo "🏛️ 아키텍처 경계 검사 시작..."
    echo ""
    echo "1️⃣ cargo-deny: 의존성 규칙 검증..."
    cargo deny check advisories bans licenses sources || true
    echo ""
    echo "2️⃣ 아키텍처 테스트: SOLID 원칙 검증..."
    cd packages/codegraph-ir && cargo test --test architecture_tests
    echo ""
    echo "✅ 아키텍처 검사 완료!"

# 🔍 모듈 구조 시각화 (의존성 그래프)
rust-arch-graph:
    #!/usr/bin/env zsh
    echo "🔍 의존성 그래프 생성 중..."
    cd packages/codegraph-ir
    cargo depgraph --workspace-only | dot -Tpng > ../../docs/_temp/architecture-graph.png
    echo "✅ 그래프 저장됨: docs/_temp/architecture-graph.png"
    open ../../docs/_temp/architecture-graph.png || true

# 🧩 모듈 독립성 검사 (cargo-modules)
rust-arch-modules:
    cd packages/codegraph-ir && cargo modules structure --types

# 🎯 아키텍처 위반 자동 수정 제안
rust-arch-fix:
    #!/usr/bin/env zsh
    echo "🎯 아키텍처 위반 분석 및 수정 제안..."
    echo ""
    echo "Step 1: 순환 의존성 탐지..."
    cd packages/codegraph-ir
    cargo depgraph --workspace-only | grep -E "->.*->" || echo "✅ 순환 의존 없음"
    echo ""
    echo "Step 2: 불필요한 의존성 제거 제안..."
    cargo +nightly udeps || echo "⚠️ nightly 필요: rustup install nightly"
    echo ""
    echo "Step 3: 안전하지 않은 코드 탐지..."
    cargo geiger || echo "⚠️ cargo-geiger 설치 필요: cargo install cargo-geiger"

# 🏛️ Full 아키텍처 검증 (CI용)
rust-arch-ci: rust-arch-check
    @echo ""
    @echo "✅ 전체 아키텍처 검증 완료!"

# ========================================================================
# Python Development
# ========================================================================

# Install package dependencies
install:
    uv pip install -e .

# Install development dependencies and setup pre-commit
dev:
    uv pip install -e ".[dev]"
    pre-commit install

# Clean Python cache files
clean:
    find . -type d -name "__pycache__" -exec rm -rf {} +
    find . -type f -name "*.pyc" -delete
    find . -type f -name "*.pyo" -delete
    find . -type d -name "*.egg-info" -exec rm -rf {} +
    rm -rf build/ dist/ .pytest_cache/ .coverage htmlcov/

# Clean local runtime artifacts (safe, targeted)
clean-local:
    rm -rf data/qdrant_storage data/qdrant_test_verify data/tantivy_index data/tantivy-delta data/repomap data/benchmark_repomap data/lats
    rm -f audit_logs.db inference_benchmark_results.json
    rm -rf logs/

# Run tests with coverage
test:
    pytest tests/ -v --cov=codegraph

# Run tests and generate HTML coverage report
coverage-html:
    pytest --cov=codegraph --cov-report=html

# Run linters (ruff, mypy)
lint:
    ruff check codegraph tests
    mypy codegraph

# Format code with black and ruff
format:
    black codegraph tests
    ruff check codegraph tests --fix

# Full Python CI pipeline (format + lint + test)
python-ci: format lint test
    @echo "✅ Python CI 완료!"

# ========================================================================
# Full Project CI (Rust + Python)
# ========================================================================

# Run complete CI pipeline (Rust + Python)
ci-all: rust-ci python-ci
    @echo ""
    @echo "✅ 전체 CI 파이프라인 완료!"
    @echo "  - Rust: lint + format-check + test ✅"
    @echo "  - Python: format + lint + test ✅"

# Quick check (fast validation before commit)
ci-quick: rust-check lint
    @echo "✅ 빠른 검사 완료!"

# Pre-push check (thorough validation)
ci-pre-push: rust-lint rust-format-check rust-test lint test
    @echo "✅ Push 전 검사 완료!"

# ========================================================================
# Docker Compose Commands
# ========================================================================

# Initial setup: create .env from example
docker-setup:
    #!/usr/bin/env zsh
    if [ ! -f .env ]; then
        cp .env.example .env
        echo "✅ Created .env file from .env.example"
        echo "⚠️  Please edit .env and set OPENAI_API_KEY"
    else
        echo "ℹ️  .env file already exists"
    fi
    mkdir -p logs
    echo "✅ Created necessary directories (logs)"

# Start all services in background
docker-up:
    docker-compose up -d

# Stop all services
docker-down:
    docker-compose down

# Follow logs from all services
docker-logs:
    docker-compose logs -f

# Follow logs from API server only
docker-logs-api:
    docker-compose logs -f api-server

# Show status of all services
docker-ps:
    docker-compose ps

# Check health of all services
docker-health:
    @echo "Checking service health..."
    @docker-compose ps
    @echo ""
    @echo "API Server Health:"
    @curl -f http://localhost:7200/health 2>/dev/null && echo "✅ API Server is healthy" || echo "❌ API Server is not responding"
    @echo ""
    @echo "Qdrant Health:"
    @curl -f http://localhost:7203/ 2>/dev/null && echo "✅ Qdrant is healthy" || echo "❌ Qdrant is not responding"
    @echo ""
    @echo "Zoekt Health:"
    @curl -f http://localhost:7205/ 2>/dev/null && echo "✅ Zoekt is healthy" || echo "❌ Zoekt is not responding"

# Restart all services
docker-restart:
    docker-compose restart

# Restart API server only
docker-restart-api:
    docker-compose restart api-server

# Rebuild and restart all services
docker-rebuild:
    docker-compose up -d --build

# Stop services and remove containers
docker-clean:
    docker-compose down -v

# Open shell in API server container
docker-shell:
    docker-compose exec api-server /bin/bash

# Open PostgreSQL shell
docker-shell-db:
    docker-compose exec postgres psql -U codegraph -d codegraph

# Open Redis CLI
docker-shell-redis:
    docker-compose exec redis redis-cli -a codegraph_redis

# Backup PostgreSQL database
docker-backup-db:
    #!/usr/bin/env zsh
    mkdir -p backups
    docker-compose exec postgres pg_dump -U codegraph codegraph > backups/backup_$(date +%Y%m%d_%H%M%S).sql
    echo "✅ Database backed up to backups/"

# Restore PostgreSQL database (Usage: just docker-restore-db backup.sql)
docker-restore-db FILE:
    docker-compose exec -T postgres psql -U codegraph codegraph < {{FILE}}
    @echo "✅ Database restored from {{FILE}}"

# ========================================================================
# Development Workflows
# ========================================================================

# Start development environment (setup + up + logs)
docker-dev: docker-setup docker-up
    #!/usr/bin/env zsh
    echo ""
    echo "Waiting for services to be ready..."
    sleep 10
    just docker-health
    echo ""
    echo "🚀 Development environment is ready!"
    echo "📖 API Docs: http://localhost:7200/docs"
    echo "📊 Qdrant UI: http://localhost:7203/dashboard"
    echo ""
    just docker-logs

# Stop all services (alias for docker-down)
docker-stop: docker-down

# Run API server locally without Docker
run-api:
    uvicorn apps.api_server.main:app --reload --port 7200

# ========================================================================
# Agent Testing (SOTA CLI)
# ========================================================================

# Run agent test CLI - execute task
agent-test-run TASK REPO=".":
    python scripts/agent_test.py run execute "{{TASK}}" --repo {{REPO}}

# Quick agent test (current directory)
agent-test-quick TASK:
    python scripts/agent_test.py run quick "{{TASK}}"

# Show agent metrics
agent-test-metrics:
    python scripts/agent_test.py metrics show

# Agent test version
agent-test-version:
    python scripts/agent_test.py version

# Example: Fix bug
agent-test-example-fix:
    python scripts/agent_test.py run quick "fix null pointer in payment.py"

# Example: Add tests
agent-test-example-test:
    python scripts/agent_test.py run quick "add unit tests for UserService"

# ========================================================================
# Agent Testing - Extended Commands
# ========================================================================

# Snapshot 관리
agent-test-snapshot-create REPO=".":
    python scripts/agent_test.py snapshot create {{REPO}}

agent-test-snapshot-list REPO=".":
    python scripts/agent_test.py snapshot list {{REPO}}

# Repo 관리
agent-test-repo-info REPO=".":
    python scripts/agent_test.py repo info {{REPO}}

agent-test-repo-select REPO:
    python scripts/agent_test.py repo select {{REPO}}

# Search
agent-test-search-code PATTERN REPO=".":
    python scripts/agent_test.py search code "{{PATTERN}}" --repo {{REPO}}

agent-test-search-semantic QUERY REPO=".":
    python scripts/agent_test.py search semantic "{{QUERY}}" --repo {{REPO}}

# Retriever
agent-test-retriever-list:
    python scripts/agent_test.py retriever list

agent-test-retriever-test QUERY TYPE="basic":
    python scripts/agent_test.py retriever test "{{QUERY}}" --type {{TYPE}}

