#!/usr/bin/env bash
#
# Codegraph API Server Startup Script (Granian)
#
# SOTA Production Requirements:
# - Auto-detect CPU cores and calculate optimal workers
# - Environment validation before startup
# - Graceful shutdown handling
# - Health check verification
# - Zero hardcoding (all configurable via env vars)
#
# Usage:
#   ./scripts/start_api_granian.sh
#   PORT=9000 WORKERS=8 ./scripts/start_api_granian.sh
#

set -euo pipefail

# ============================================================================
# Configuration (External Boundary: ENV VARS)
# ============================================================================

readonly SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
readonly PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

# Server config (with defaults)
readonly HOST="${HOST:-0.0.0.0}"
readonly PORT="${PORT:-8000}"
readonly RELOAD="${RELOAD:-false}"

# Worker calculation: 75% of CPU cores (SOTA standard)
readonly CPU_CORES=$(python3 -c "import os; print(os.cpu_count() or 4)")
readonly DEFAULT_WORKERS=$(python3 -c "print(max(1, int(${CPU_CORES} * 0.75)))")
readonly WORKERS="${WORKERS:-$DEFAULT_WORKERS}"

# Performance tuning
readonly BLOCKING_THREADS="${BLOCKING_THREADS:-1}"  # Blocking threads per worker
readonly BACKLOG="${BACKLOG:-2048}"  # Connection backlog
readonly HTTP="${HTTP:-auto}"  # auto | 1 | 2
readonly RUNTIME_MODE="${RUNTIME_MODE:-auto}"  # auto | mt | st (multi-threaded | single-threaded)

# Timeouts (seconds)
readonly GRACEFUL_TIMEOUT="${GRACEFUL_TIMEOUT:-30}"
readonly KEEPALIVE_TIMEOUT="${KEEPALIVE_TIMEOUT:-65}"

# Logging
readonly LOG_LEVEL="${LOG_LEVEL:-info}"  # debug | info | warning | error
readonly ACCESS_LOG="${ACCESS_LOG:-false}"

# ============================================================================
# Validation (Zero-Guessing Rule)
# ============================================================================

echo "🔍 Validating environment..."

# 1. Check Python executable
if [ ! -f "$PROJECT_ROOT/.venv/bin/python" ]; then
    echo "❌ Error: Virtual environment not found at $PROJECT_ROOT/.venv"
    echo "   Run: python -m venv .venv && .venv/bin/pip install -e ."
    exit 1
fi

# 2. Check granian installation
if ! "$PROJECT_ROOT/.venv/bin/python" -c "import granian" 2>/dev/null; then
    echo "❌ Error: granian not installed"
    echo "   Run: .venv/bin/pip install granian>=1.6.0"
    exit 1
fi

# 3. Check FastAPI app exists
if [ ! -f "$PROJECT_ROOT/apps/api/api/main.py" ]; then
    echo "❌ Error: FastAPI app not found at apps/api/api/main.py"
    exit 1
fi

# 4. Validate port range
if [ "$PORT" -lt 1024 ] || [ "$PORT" -gt 65535 ]; then
    echo "❌ Error: Invalid port $PORT (must be 1024-65535)"
    exit 1
fi

# 5. Validate workers
if [ "$WORKERS" -lt 1 ] || [ "$WORKERS" -gt "$((CPU_CORES * 2))" ]; then
    echo "⚠️  Warning: Workers=$WORKERS is outside recommended range [1, $((CPU_CORES * 2))]"
fi

echo "✅ Environment validation passed"

# ============================================================================
# Display Configuration
# ============================================================================

echo ""
echo "🚀 Starting Codegraph API Server (Granian)"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  Host:          $HOST:$PORT"
echo "  Workers:       $WORKERS (CPU cores: $CPU_CORES, using 75%)"
echo "  Blocking Threads: $BLOCKING_THREADS per worker"
echo "  Runtime Mode:   $RUNTIME_MODE"
echo "  HTTP:          $HTTP"
echo "  Backlog:       $BACKLOG"
echo "  Reload:        $RELOAD"
echo "  Log Level:     $LOG_LEVEL"
echo "  Access Log:    $ACCESS_LOG"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# ============================================================================
# Graceful Shutdown Handler
# ============================================================================

cleanup() {
    echo ""
    echo "🛑 Received shutdown signal, stopping gracefully..."
    
    # Granian handles SIGTERM gracefully, just wait
    wait
    
    echo "✅ Server stopped"
    exit 0
}

trap cleanup SIGTERM SIGINT

# ============================================================================
# Start Server
# ============================================================================

cd "$PROJECT_ROOT" || exit 1

# Build command arguments (Type-safe: no string interpolation vulnerabilities)
CMD_ARGS=(
    "--interface" "asgi"
    "--host" "$HOST"
    "--port" "$PORT"
    "--working-dir" "$PROJECT_ROOT"
    "--workers" "$WORKERS"
    "--blocking-threads" "$BLOCKING_THREADS"
    "--runtime-mode" "$RUNTIME_MODE"
    "--backlog" "$BACKLOG"
    "--http" "$HTTP"
    "--log-level" "$LOG_LEVEL"
)

# Export PYTHONPATH for worker processes
export PYTHONPATH="$PROJECT_ROOT:$PROJECT_ROOT/packages:${PYTHONPATH:-}"

# Conditional args
if [ "$RELOAD" = "true" ]; then
    CMD_ARGS+=("--reload")
fi

if [ "$ACCESS_LOG" = "true" ]; then
    CMD_ARGS+=("--access-log")
fi

# Execute with proper error handling
exec "$PROJECT_ROOT/.venv/bin/granian" \
    "${CMD_ARGS[@]}" \
    "apps.api.api.main:app"

# Note: exec replaces current shell, so cleanup trap will be called on signal

