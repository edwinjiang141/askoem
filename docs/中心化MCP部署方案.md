# 中心化 MCP Server 部署方案

## 1. 现状问题

当前 Cline 配置采用本地 `command + args`：

```json
"ai-gateway-mvp": {
  "command": "python",
  "args": ["-m", "src.mcp_server"],
  "cwd": "..."
}
```

每个客户端都需要 Python 环境、源码和依赖，维护成本高。

## 2. 目标架构

改为"服务端集中部署 + 客户端远程接入"：

1. 服务端部署一份 AI Gateway MCP。
2. 运行 `python -m src.mcp_server_http`。
3. 客户端配置远程 URL 接入。

## 3. 实现方式

`src/mcp_server_http.py` 不再使用 `FastMCP.run()`，而是手动构建 Starlette ASGI 应用：

- 使用 MCP SDK 底层 `SseServerTransport` 直接挂载路由
- 避免 `FastMCP.run()` 在不同 SDK 版本下参数签名不兼容的问题
- 避免 `mount_path` 已知 bug（[python-sdk#412](https://github.com/modelcontextprotocol/python-sdk/issues/412)）

启动后创建的端点：

| 端点          | 方法   | 作用                         |
| ------------- | ------ | ---------------------------- |
| `/sse`        | GET    | SSE 事件流，Cline 连接此 URL |
| `/messages/`  | POST   | 客户端发送 JSON-RPC 消息     |
| `/health`     | GET    | 诊断端点，浏览器可访问       |

## 4. 运行方式

### 启动服务

```bash
cd /path/to/askoem
python -m src.mcp_server_http
```

启动后会打印类似：

```
============================================================
  AI Gateway MCP Server (SSE)
  http://0.0.0.0:8000

  SSE 端点 (Cline URL):  /sse
  消息端点:              /messages/
  诊断端点 (浏览器):     /health

  Cline 配置:
  {"url": "http://<server-ip>:8000/sse", "type": "sse"}
============================================================
```

### 环境变量（可选）

```bash
AI_GATEWAY_MCP_HTTP_HOST=0.0.0.0   # 监听地址
AI_GATEWAY_MCP_HTTP_PORT=8000       # 监听端口
```

### 验证服务是否存活

浏览器访问 `http://<server-ip>:8000/health`，应返回：

```json
{
  "status": "ok",
  "server": "ai-gateway-mvp",
  "transport": "sse",
  "endpoints": {
    "sse_stream": "/sse",
    "messages": "/messages/",
    "health": "/health"
  }
}
```

## 5. Cline 配置

在 Cline MCP 配置中添加远程服务器（**注意 URL 以 `/sse` 结尾**）：

```json
"ai-gateway-mvp": {
  "url": "http://<server-ip>:8000/sse",
  "type": "sse"
}
```

如果你的 Cline 版本不支持 `type` 字段，在 Cline MCP Remote Server UI 中手工选择 `SSE`。

> **重要**：URL 必须指向 `/sse` 端点，不是 `/mcp`。
> `/mcp` 路径上没有任何路由，会返回 404。

## 6. 保持兼容

- 原有本地模式继续可用：`python -m src.mcp_server`（stdio）
- 新增中心化模式：`python -m src.mcp_server_http`（SSE over HTTP）

## 7. 调试与巡检

1. **浏览器访问** `http://<server-ip>:8000/health` — 确认服务存活。
2. **Cline 调用** `health_check` 工具 — 确认 MCP 通信正常、工具已加载。
3. 如果 `health_check` 能正常返回，说明 SSE 通道畅通，再进行 `oem_login` 和业务测试。

### 常见问题

| 现象                      | 原因                           | 解决                                          |
| ------------------------- | ------------------------------ | --------------------------------------------- |
| `GET /mcp` → 404          | URL 不对，SSE 端点在 `/sse`     | Cline URL 改为 `http://host:8000/sse`        |
| `GET /mcp` → 405/406      | 用了旧的 streamable-http 配置  | 改用当前 SSE 方案                              |
| Cline 无法发现 tools       | type 未设为 sse                | 配置中加 `"type": "sse"`                      |
| 连接后立即断开             | 网络/防火墙                    | 确认端口 8000 已放通                           |

## 8. 迁移建议

1. 先保留现有 stdio 客户端配置作为回退。
2. 在测试环境验证远程 MCP 连通性。
3. 分批将客户端切换到远程 MCP 配置。
4. 稳定后统一回收本地源码部署模式。
