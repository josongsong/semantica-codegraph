#!/bin/bash
# ========================================================================
# Serena MCP Setup Script for Cursor IDE
# ========================================================================
# 이 스크립트는 Cursor IDE에서 Codegraph MCP 서버를 설정합니다.
#
# 사용법:
#   ./scripts/setup_mcp_cursor.sh
#
# 요구사항:
#   - Python 3.10+
#   - OpenAI API Key
#   - Cursor IDE 설치
# ========================================================================

set -e  # Exit on error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# ========================================================================
# Helper Functions
# ========================================================================

info() {
    echo -e "${BLUE}ℹ️  $1${NC}"
}

success() {
    echo -e "${GREEN}✅ $1${NC}"
}

warning() {
    echo -e "${YELLOW}⚠️  $1${NC}"
}

error() {
    echo -e "${RED}❌ $1${NC}"
}

# ========================================================================
# Step 1: Environment Check
# ========================================================================

info "Checking environment..."

# Check Python version
PYTHON_CMD=$(which python3 || echo "")
if [ -z "$PYTHON_CMD" ]; then
    error "Python 3 not found. Please install Python 3.10 or higher."
    exit 1
fi

PYTHON_VERSION=$($PYTHON_CMD --version | cut -d' ' -f2)
info "Python version: $PYTHON_VERSION"

# Check if we're in the correct directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(dirname "$SCRIPT_DIR")"

if [ ! -f "$REPO_ROOT/apps/mcp/mcp/main.py" ]; then
    error "MCP main.py not found. Are you in the correct directory?"
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

# Activate virtual environment
source .venv/bin/activate

# Get Python path in venv
VENV_PYTHON=$(which python)
info "Virtual environment Python: $VENV_PYTHON"

# ========================================================================
# Step 3: Install Dependencies
# ========================================================================

info "Installing dependencies..."

# Check if uv is installed
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
    info "Creating .env from .env.example..."

    if [ -f "$REPO_ROOT/.env.example" ]; then
        cp "$REPO_ROOT/.env.example" "$REPO_ROOT/.env"
        success ".env file created"

        warning "Please edit .env file and add your OPENAI_API_KEY"
        echo ""
        echo "  OPENAI_API_KEY=sk-your-api-key-here"
        echo ""
    else
        error ".env.example not found"
        exit 1
    fi
else
    info ".env file exists"

    # Check if OPENAI_API_KEY is set
    if grep -q "^OPENAI_API_KEY=" "$REPO_ROOT/.env"; then
        OPENAI_KEY=$(grep "^OPENAI_API_KEY=" "$REPO_ROOT/.env" | cut -d'=' -f2)
        if [ -n "$OPENAI_KEY" ] && [ "$OPENAI_KEY" != "sk-your-openai-api-key-here" ]; then
            success "OPENAI_API_KEY is set"
        else
            warning "OPENAI_API_KEY is not configured. Please update .env file."
        fi
    else
        warning "OPENAI_API_KEY not found in .env file. Please add it."
    fi
fi

# ========================================================================
# Step 5: Test MCP Server
# ========================================================================

info "Testing MCP server..."

# Run a quick test (timeout after 5 seconds)
timeout 5 python apps/mcp/mcp/main.py > /dev/null 2>&1 &
MCP_PID=$!

sleep 2

if ps -p $MCP_PID > /dev/null; then
    success "MCP server starts successfully"
    kill $MCP_PID 2>/dev/null || true
else
    warning "MCP server test failed (this is normal if dependencies are missing)"
fi

# ========================================================================
# Step 6: Generate Cursor Settings
# ========================================================================

info "Generating Cursor IDE settings..."

# Detect OS
OS_TYPE="unknown"
if [[ "$OSTYPE" == "darwin"* ]]; then
    OS_TYPE="macos"
    CURSOR_SETTINGS="$HOME/Library/Application Support/Cursor/User/settings.json"
elif [[ "$OSTYPE" == "linux-gnu"* ]]; then
    OS_TYPE="linux"
    CURSOR_SETTINGS="$HOME/.config/Cursor/User/settings.json"
else
    OS_TYPE="windows"
    CURSOR_SETTINGS="$APPDATA/Cursor/User/settings.json"
fi

info "Detected OS: $OS_TYPE"
info "Cursor settings path: $CURSOR_SETTINGS"

# Create settings directory if it doesn't exist
CURSOR_SETTINGS_DIR=$(dirname "$CURSOR_SETTINGS")
if [ ! -d "$CURSOR_SETTINGS_DIR" ]; then
    warning "Cursor settings directory not found. Creating..."
    mkdir -p "$CURSOR_SETTINGS_DIR"
fi

# Generate MCP settings snippet
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
        "CODEGRAPH_WATCH": "true",
        "SEMANTICA_LOG_LEVEL": "INFO"
      }
    }
  }
}
EOF
)

# Save to temporary file
TEMP_SETTINGS="$REPO_ROOT/mcp_settings.json"
echo "$MCP_SETTINGS" > "$TEMP_SETTINGS"

success "MCP settings generated: $TEMP_SETTINGS"

echo ""
info "📝 Next Steps:"
echo ""
echo "1. Open Cursor IDE settings:"
echo "   $CURSOR_SETTINGS"
echo ""
echo "2. Merge the following settings from:"
echo "   $TEMP_SETTINGS"
echo ""
echo "3. Update your OPENAI_API_KEY in the settings if not using .env"
echo ""
echo "4. Restart Cursor IDE"
echo ""
echo "5. Open a project and use @codegraph in the chat"
echo ""

# ========================================================================
# Step 7: Print Summary
# ========================================================================

echo ""
echo "========================================="
echo "🎉 Setup Complete!"
echo "========================================="
echo ""
echo "Repository: $REPO_ROOT"
echo "Python: $VENV_PYTHON"
echo "MCP Server: $REPO_ROOT/apps/mcp/mcp/main.py"
echo ""
echo "For detailed instructions, see:"
echo "  $REPO_ROOT/SERENA_MCP_SETUP.md"
echo ""
echo "To manually start MCP server:"
echo "  source .venv/bin/activate"
echo "  python apps/mcp/mcp/main.py"
echo ""

# ========================================================================
# Optional: Open settings file
# ========================================================================

if command -v code &> /dev/null; then
    read -p "Open settings files in VS Code? (y/n) " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        code "$TEMP_SETTINGS"
        code "$CURSOR_SETTINGS"
    fi
fi

success "Setup script completed!"
