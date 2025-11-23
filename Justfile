# Semantica Codegraph v4 - Just Commands
# Run `just --list` to see all available commands

set shell := ["/bin/zsh", "-lc"]

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
    mkdir -p repos logs
    echo "✅ Created necessary directories (repos, logs)"

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
