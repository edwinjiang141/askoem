from __future__ import annotations

"""
中心化部署入口（不影响现有 stdio 方式）：

- 现有方式: python -m src.mcp_server          (stdio，单机本地)
- 新方式:   python -m src.mcp_server_http     (streamable-http，集中部署)

该文件复用 src.mcp_server 中已注册的全部 MCP tools，不改业务逻辑。
"""

import os

from src.mcp_server import mcp


if __name__ == "__main__":
    # 兼容说明：
    # - 一些客户端（含部分 Cline 版本）会先用 GET 访问 /mcp。
    # - streamable-http 在该路径上可能返回 400（协议期望与客户端探测方式不一致）。
    # 因此默认使用 SSE 并挂载到 /mcp，确保 GET /mcp 可正常建立连接。
    #
    # 可通过环境变量覆盖:
    # AI_GATEWAY_MCP_TRANSPORT=sse|streamable-http|stdio
    # AI_GATEWAY_MCP_MOUNT_PATH=/mcp
    transport = os.getenv("AI_GATEWAY_MCP_TRANSPORT", "sse").strip() or "sse"
    mount_path = os.getenv("AI_GATEWAY_MCP_MOUNT_PATH", "/mcp").strip() or "/mcp"
    if transport == "sse":
        mcp.run(transport="sse", mount_path=mount_path)
    else:
        mcp.run(transport=transport)  # streamable-http / stdio
