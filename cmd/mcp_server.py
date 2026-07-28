"""
MCP Server 入口 —— Cursor / Claude Code 配置:
{
  "mcpServers": { "tiny-claw": {
    "command": "python3",
    "args": ["cmd/mcp_server.py"],
    "cwd": "/path/to/py-tiny-claw"
  }}}
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from tiny_claw.mcp_server import main

main()
