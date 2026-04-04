# 中心化 MCP Server 部署方案（避免每个客户端部署源码）

## 1. 现状问题

当前 Cline 配置采用本地 `command + args`：

```json
"ai-gateway-mvp": {
  "command": "python",
  "args": ["-m", "src.mcp_server"],
  "cwd": "..."
}
```

这种模式要求每个客户端都具备：

- Python 运行环境
- 项目源码
- 依赖安装
- 本地配置维护

维护成本高，版本难统一。

## 2. 目标架构

采用 MCP 标准 `streamable-http` 传输，改为“服务端集中部署 + 客户端远程接入”：

1. 服务端部署一份 AI Gateway MCP。
2. 运行 `python -m src.mcp_server_http`。
3. 各客户端配置远程 MCP 地址接入。

## 3. 本仓库具体实现

新增入口：`src/mcp_server_http.py`

- 复用 `src.mcp_server` 里已经注册好的 `mcp` 对象。
- 仅改变传输层为 `streamable-http`。
- 不修改现有工具逻辑，不影响当前 stdio 用法。

## 4. 运行方式

### 本地验证

```bash
python -m src.mcp_server_http
```

### 保持兼容

- 原有本地模式继续可用：`python -m src.mcp_server`
- 新增中心化模式：`python -m src.mcp_server_http`

## 5. 迁移建议

1. 先保留现有 stdio 客户端配置作为回退。
2. 在测试环境验证远程 MCP 连通性与权限控制。
3. 分批将客户端切换到远程 MCP 配置。
4. 稳定后统一回收本地源码部署模式。
