#!/bin/bash
# MCP Inspector Test Script
# 실제 MCP 서버 실행 및 Inspector 테스트

set -e

echo "======================================================================"
echo " MCP Server Test with Inspector"
echo "======================================================================"

# 1. Check if npx is available
if ! command -v npx &> /dev/null; then
    echo "❌ npx not found. Please install Node.js"
    exit 1
fi

echo "✅ npx available"

# 2. Set environment
export PYTHONPATH=.
cd "$(dirname "$0")/.."

echo ""
echo "🚀 Starting MCP Server..."
echo ""

# 3. Run MCP Inspector
npx @modelcontextprotocol/inspector python server/mcp_server/main.py

echo ""
echo "======================================================================"
echo " MCP Inspector started!"
echo " Open browser to http://localhost:5173"
echo "======================================================================"

