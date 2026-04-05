from __future__ import annotations

"""
中心化部署入口 — 手动构建 ASGI 应用，不依赖 FastMCP.run()

FastMCP.run() 在不同 mcp SDK 版本下参数签名不同，mount_path 也有已知 bug，
因此直接使用底层 SseServerTransport 构建 Starlette 应用，路由完全可控。

启动后端点:
  GET  /sse         SSE 事件流（Cline 连接此 URL）
  POST /messages/   客户端发送 JSON-RPC 消息
  GET  /health      诊断端点（浏览器可访问）

Cline 远程 MCP 配置:
  {
    "ai-gateway-mvp": {
      "url": "http://<server-ip>:8000/sse",
      "type": "sse"
    }
  }
"""

import os
import sys

try:
    import uvicorn
    from starlette.applications import Starlette
    from starlette.requests import Request
    from starlette.routing import Mount, Route
    from starlette.responses import JSONResponse
except ImportError:
    sys.stderr.write(
        "ERROR: uvicorn / starlette 未安装。\n"
        "请执行: pip install uvicorn starlette\n"
    )
    sys.exit(1)

try:
    from mcp.server.sse import SseServerTransport
except ImportError:
    sys.stderr.write(
        "ERROR: mcp.server.sse.SseServerTransport 未找到。\n"
        "请确认 mcp SDK 版本 >= 1.2: pip install --upgrade mcp\n"
    )
    sys.exit(1)

from src.mcp_server import mcp   # 复用已注册的全部 MCP tools

# ---------- 获取内部 Server 对象 ----------
_low_level_server = getattr(mcp, "_mcp_server", None)
if _low_level_server is None:
    _low_level_server = getattr(mcp, "server", None)
if _low_level_server is None:
    sys.stderr.write(
        "ERROR: 无法获取 FastMCP 内部 Server 对象。\n"
        "请检查 mcp SDK 版本。\n"
    )
    sys.exit(1)

# ---------- SSE Transport ----------
# 为什么用 "/messages/"？
# 1. 设计目标：所有从 Cline 客户端过来的 JSON-RPC 消息都通过 POST /messages/ 这个入口转接。
# 2. 体现边界：/messages/ 路径下只做消息转发和推送，不暴露具体工具与模型接口。
# 3. 易于安全管控：可单独做 ACL、限流、审计，不干扰其它 HTTP 路径。
sse_transport = SseServerTransport("/messages/")

# 2. handle_sse 是 SSE 事件流端点处理函数。
#    - 输入：接收前端 Cline 通过 GET /sse 发起的连接（参数为 request: Request）。
#    - 处理步骤：
#         a) 用 sse_transport.connect_sse 方法建立服务器端的 SSE（事件流）连接环境，获取输入输出流。
#         b) 调用底层的 MCP Server 对象（_low_level_server.run），负责实际消息处理流程，传入读写流与初始化选项。
#    - 输出：长连接方式按 SSE 协议推送消息给客户端。
#    - 失败处理：出错时关闭连接（由 Context Manager 自动完成）。
async def handle_sse(request: Request) -> None:
    """SSE 事件流端点 — Cline 通过 GET /sse 连接"""
    async with sse_transport.connect_sse(
        request.scope, request.receive, request._send
    ) as (read_stream, write_stream):
        await _low_level_server.run(
            read_stream,
            write_stream,
            _low_level_server.create_initialization_options(),
        )


async def health(request: Request) -> JSONResponse:
    """诊断端点 — 浏览器访问 http://host:port/health 验证服务存活"""
    return JSONResponse({
        "status": "ok",
        "server": "ai-gateway-mvp",
        "transport": "sse",
        "endpoints": {
            "sse_stream": "/sse",
            "messages": "/messages/",
            "health": "/health",
        },
    })


# 这段代码定义了一个 Starlette 应用实例 app，
# 设置了 Web 路由表 routes，包含三个端点：
# 1. "/health" 路由到健康检查接口 health，提供服务存活状态。
# 2. "/sse" 路由到 handle_sse 异步函数，用于 SSE 事件流连接。
# 3. "/messages/" 路由到 sse_transport.handle_post_message，处理消息 POST。
# 这些路由和端点组成了 AI Gateway MCP Server 的 HTTP 接口。

app = Starlette(
    routes=[
        Route("/health", health),
        Route("/sse", endpoint=handle_sse),
        Mount("/messages/", app=sse_transport.handle_post_message),
    ],
)


if __name__ == "__main__":
    host = os.getenv("AI_GATEWAY_MCP_HTTP_HOST", "0.0.0.0").strip() or "0.0.0.0"
    port = int(os.getenv("AI_GATEWAY_MCP_HTTP_PORT", "8000").strip() or "8000")

    banner = (
        f"\n{'='*60}\n"
        f"  AI Gateway MCP Server (SSE)\n"
        f"  http://{host}:{port}\n"
        f"\n"
        f"  SSE 端点 (Cline URL):  /sse\n"
        f"  消息端点:              /messages/\n"
        f"  诊断端点 (浏览器):     /health\n"
        f"\n"
        f"  Cline 配置:\n"
        f'  {{"url": "http://<server-ip>:{port}/sse", "type": "sse"}}\n'
        f"{'='*60}\n\n"
    )
    sys.stderr.write(banner)

    uvicorn.run(app, host=host, port=port)
