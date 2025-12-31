#!/bin/bash
# MCP Server Startup Script

set -e

echo "🚀 Starting Codegraph MCP Server..."

# Set working directory
cd "$(dirname "$0")/.."

# Set Python path
export PYTHONPATH=.

# Run server
exec python server/mcp_server/main.py

