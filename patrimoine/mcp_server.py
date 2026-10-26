"""Local MCP server: Claude reads Jules's accounts, markets and alerts, and writes reports and order ideas.

The tools themselves live in `api` (shared with the mobile app); this module only exposes them over MCP.
"""
from __future__ import annotations

from mcp.server.mcpserver import MCPServer

from . import api

server = MCPServer("patrimoine", instructions=api.INSTRUCTIONS)
for _fn in api.TOOLS:
    server.tool()(_fn)


def main() -> None:
    server.run()


if __name__ == "__main__":
    main()
