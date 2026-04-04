from __future__ import annotations

"""
中心化部署入口（不影响现有 stdio 方式）：

- 现有方式: python -m src.mcp_server          (stdio，单机本地)
- 新方式:   python -m src.mcp_server_http     (streamable-http，集中部署)

该文件复用 src.mcp_server 中已注册的全部 MCP tools，不改业务逻辑。
"""

from src.mcp_server import mcp


if __name__ == "__main__":
    # 按 MCP 标准使用 streamable-http 传输，便于客户端远程连接。
    # host/port 由 FastMCP settings 决定（可通过环境变量覆盖）。
    mcp.run(transport="streamable-http")
