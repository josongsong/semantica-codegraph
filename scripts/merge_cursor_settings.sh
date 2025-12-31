#!/bin/bash
# ========================================================================
# Merge MCP Settings into Cursor IDE Configuration
# ========================================================================
# 이 스크립트는 생성된 mcp_settings.json을 Cursor IDE 설정에 병합합니다.
#
# 사용법:
#   ./scripts/merge_cursor_settings.sh
#
# 요구사항:
#   - jq (JSON 처리 도구)
#   - Cursor IDE 설치
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
# Detect OS and Settings Path
# ========================================================================

if [[ "$OSTYPE" == "darwin"* ]]; then
    CURSOR_SETTINGS="$HOME/Library/Application Support/Cursor/User/settings.json"
elif [[ "$OSTYPE" == "linux-gnu"* ]]; then
    CURSOR_SETTINGS="$HOME/.config/Cursor/User/settings.json"
else
    error "Unsupported OS: $OSTYPE"
    exit 1
fi

# ========================================================================
# Check Prerequisites
# ========================================================================

info "Checking prerequisites..."

# Check if jq is installed
if ! command -v jq &> /dev/null; then
    error "jq is not installed. Please install it first:"
    echo ""
    echo "  macOS:   brew install jq"
    echo "  Linux:   sudo apt-get install jq"
    echo ""
    exit 1
fi

success "jq is installed"

# Get repository root
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(dirname "$SCRIPT_DIR")"
MCP_SETTINGS="$REPO_ROOT/mcp_settings.json"

# Check if mcp_settings.json exists
if [ ! -f "$MCP_SETTINGS" ]; then
    error "mcp_settings.json not found. Please run setup_mcp_cursor.sh first."
    exit 1
fi

info "Found MCP settings: $MCP_SETTINGS"

# ========================================================================
# Backup Existing Settings
# ========================================================================

if [ -f "$CURSOR_SETTINGS" ]; then
    BACKUP_FILE="${CURSOR_SETTINGS}.backup.$(date +%Y%m%d_%H%M%S)"
    info "Backing up existing settings..."
    cp "$CURSOR_SETTINGS" "$BACKUP_FILE"
    success "Backup created: $BACKUP_FILE"
else
    warning "Cursor settings file not found. Creating new one..."
    CURSOR_SETTINGS_DIR=$(dirname "$CURSOR_SETTINGS")
    mkdir -p "$CURSOR_SETTINGS_DIR"
    echo '{}' > "$CURSOR_SETTINGS"
fi

# ========================================================================
# Merge Settings
# ========================================================================

info "Merging MCP settings into Cursor configuration..."

# Read existing settings
EXISTING_SETTINGS=$(cat "$CURSOR_SETTINGS")
MCP_CONFIG=$(cat "$MCP_SETTINGS")

# Merge using jq
MERGED_SETTINGS=$(jq -s '.[0] * .[1]' <(echo "$EXISTING_SETTINGS") <(echo "$MCP_CONFIG"))

# Write back to settings file
echo "$MERGED_SETTINGS" > "$CURSOR_SETTINGS"

success "Settings merged successfully!"

# ========================================================================
# Verify Merged Settings
# ========================================================================

info "Verifying merged settings..."

if jq -e '.mcpServers.codegraph' "$CURSOR_SETTINGS" > /dev/null 2>&1; then
    success "MCP server configuration verified"
    echo ""
    echo "MCP Server Details:"
    jq '.mcpServers.codegraph' "$CURSOR_SETTINGS"
    echo ""
else
    error "Failed to verify MCP server configuration"
    exit 1
fi

# ========================================================================
# Summary
# ========================================================================

echo ""
echo "========================================="
echo "🎉 Settings Merge Complete!"
echo "========================================="
echo ""
echo "Cursor Settings: $CURSOR_SETTINGS"
echo "Backup: $BACKUP_FILE"
echo ""
echo "📝 Next Steps:"
echo ""
echo "1. Close Cursor IDE completely (Cmd+Q)"
echo "2. Reopen Cursor IDE"
echo "3. Open a project"
echo "4. Test with: @codegraph search \"test\""
echo ""

success "Settings merge script completed!"
