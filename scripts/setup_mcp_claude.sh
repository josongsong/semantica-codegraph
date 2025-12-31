#!/bin/bash
# ========================================================================
# Serena MCP Setup Script for Claude Code CLI
# ========================================================================
# 이 스크립트는 Claude Code CLI에서 Codegraph MCP 서버를 설정합니다.
#
# 사용법:
#   ./scripts/setup_mcp_claude.sh
#
# 요구사항:
#   - Python 3.10+
#   - Claude Code CLI
#   - OpenAI API Key
# ========================================================================

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

info() { echo -e "${BLUE}ℹ️  $1${NC}"; }
success() { echo -e "${GREEN}✅ $1${NC}"; }
warning() { echo -e "${YELLOW}⚠️  $1${NC}"; }
error() { echo -e "${RED}❌ $1${NC}"; }

# ========================================================================
# Step 1: Environment Check
# ========================================================================

info "Checking environment..."

# Check Claude Code
if ! command -v claude &> /dev/null; then
    warning "Claude Code CLI not found"
    info "Install with: npm install -g @anthropic-ai/claude-code"
    info "Or: brew install claude-code"
    echo ""
    read -p "Continue anyway? (y/n) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
else
    CLAUDE_VERSION=$(claude --version 2>/dev/null || echo "unknown")
    success "Claude Code installed: $CLAUDE_VERSION"
fi

# Check Python
PYTHON_CMD=$(which python3 || echo "")
if [ -z "$PYTHON_CMD" ]; then
    error "Python 3 not found"
    exit 1
fi

PYTHON_VERSION=$($PYTHON_CMD --version | cut -d' ' -f2)
info "Python version: $PYTHON_VERSION"

# Get repo root
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(dirname "$SCRIPT_DIR")"

if [ ! -f "$REPO_ROOT/apps/mcp/mcp/main.py" ]; then
    error "MCP main.py not found"
    exit 1
fi

success "Environment check passed"

# ========================================================================
# Step 2: Virtual Environment Setup
# ========================================================================

info "Setting up virtual environment..."

cd "$REPO_ROOT"

if [ ! -d ".venv" ]; then
    info "Creating virtual environment..."
    python3 -m venv .venv
    success "Virtual environment created"
else
    info "Virtual environment already exists"
fi

source .venv/bin/activate
VENV_PYTHON=$(which python)
info "Virtual environment Python: $VENV_PYTHON"

# ========================================================================
# Step 3: Install Dependencies
# ========================================================================

info "Installing dependencies..."

if command -v uv &> /dev/null; then
    info "Using uv for installation..."
    uv pip install -e .
else
    warning "uv not found, using pip..."
    pip install -e .
fi

success "Dependencies installed"

# ========================================================================
# Step 4: Environment Variables Check
# ========================================================================

info "Checking environment variables..."

if [ ! -f "$REPO_ROOT/.env" ]; then
    warning ".env file not found"
    if [ -f "$REPO_ROOT/.env.example" ]; then
        cp "$REPO_ROOT/.env.example" "$REPO_ROOT/.env"
        success ".env file created from example"
        warning "Please edit .env and add your OPENAI_API_KEY"
    fi
else
    info ".env file exists"
    if grep -q "^OPENAI_API_KEY=" "$REPO_ROOT/.env"; then
        OPENAI_KEY=$(grep "^OPENAI_API_KEY=" "$REPO_ROOT/.env" | cut -d'=' -f2)
        if [ -n "$OPENAI_KEY" ] && [ "$OPENAI_KEY" != "sk-your-openai-api-key-here" ]; then
            success "OPENAI_API_KEY is set"
        else
            warning "OPENAI_API_KEY needs configuration"
        fi
    else
        warning "OPENAI_API_KEY not found in .env"
    fi
fi

# ========================================================================
# Step 5: Generate Claude Code MCP Settings
# ========================================================================

info "Generating Claude Code MCP settings..."

CLAUDE_CONFIG_DIR="$HOME/.claude"
mkdir -p "$CLAUDE_CONFIG_DIR"

# Generate MCP settings for Claude Code
MCP_SETTINGS=$(cat <<EOF
{
  "mcpServers": {
    "codegraph": {
      "command": "$VENV_PYTHON",
      "args": [
        "$REPO_ROOT/apps/mcp/mcp/main.py"
      ],
      "env": {
        "PYTHONPATH": "$REPO_ROOT",
        "CODEGRAPH_REPO_PATH": "\${workspaceFolder}",
        "CODEGRAPH_WATCH": "false",
        "SEMANTICA_LOG_LEVEL": "INFO"
      }
    }
  }
}
EOF
)

# Save to Claude Code config directory
CLAUDE_MCP_CONFIG="$CLAUDE_CONFIG_DIR/mcp_settings.json"
echo "$MCP_SETTINGS" > "$CLAUDE_MCP_CONFIG"

success "MCP settings generated: $CLAUDE_MCP_CONFIG"

# ========================================================================
# Step 6: Test MCP Server
# ========================================================================

info "Testing MCP server..."

timeout 5 python apps/mcp/mcp/main.py > /dev/null 2>&1 &
MCP_PID=$!

sleep 2

if ps -p $MCP_PID > /dev/null; then
    success "MCP server starts successfully"
    kill $MCP_PID 2>/dev/null || true
else
    warning "MCP server test failed (check dependencies)"
fi

# ========================================================================
# Summary
# ========================================================================

echo ""
echo "========================================="
echo "🎉 Claude Code MCP Setup Complete!"
echo "========================================="
echo ""
echo "Configuration file: $CLAUDE_MCP_CONFIG"
echo "Repository: $REPO_ROOT"
echo "Python: $VENV_PYTHON"
echo ""
echo "📝 Next Steps:"
echo ""
echo "1. Start Claude Code in your project directory:"
echo "   cd /path/to/your/project"
echo "   claude"
echo ""
echo "2. Use MCP tools in Claude Code:"
echo "   > Can you search for authentication code?"
echo "   > Analyze the login function"
echo ""
echo "3. Check available tools:"
echo "   > What MCP tools are available?"
echo ""
echo "For detailed instructions, see:"
echo "  $REPO_ROOT/SERENA_CLAUDE_CODE_SETUP.md"
echo ""

success "Setup script completed!"
