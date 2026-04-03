# AI Gateway MCP MVP

这个项目实现一个最小可运行的 AI Gateway，跑通以下 4 步流程：

1. 识别问题
2. 调 OEM REST API 取监控数据
3. 查询单文档知识库
4. 组织结构化回答

主交付形态是 MCP Server，支持 VS Code/Cursor 等宿主调用。

## 目录

- `src/mcp_server.py`：MCP Server 入口，提供 `oem_login` 和 `ask_ops` 工具
- `src/service.py`：流程编排
- `src/intent_parser.py`：问题识别
- `src/oem_client.py`：OEM REST 客户端（只读）
- `src/auth_session.py`：每用户会话缓存（TTL 30 分钟）
- `src/knowledge_base.py`：单文档检索
- `src/answer_composer.py`：固定 4 段回答输出
- `config/metric_map.yaml`：指标映射、阈值、接口路径、Grafana 链接

## 快速开始

### 1) 安装依赖

```bash
python -m venv .venv
.venv\\Scripts\\activate
pip install -r requirements.txt
```

### 2) 配置 OEM REST 接口路径

编辑 `config/metric_map.yaml` 的 `oem_api`，确认以下配置：

- `default_base_url`（当前已设置为测试环境 `https://192.168.30.230:7803/em/api`）
- `verify_ssl`（测试阶段建议 `false`，等效 curl 的 `-k`）
- `endpoints`（按官方 `/em/api/...` 路径）

- `targets`
- `metric_time_series`
- `incidents`
- `incident_events`
- `latest_data_by_target`

当前实现兼容两种输入：
- `https://host:port`
- `https://host:port/em/api`

无论传哪种，都会正确拼接到官方端点。

### 3) 启动 MCP Server

```bash
python -m src.mcp_server
```

## MCP 工具

### `oem_login`

输入：
- `oem_base_url`（可选；不传时使用配置里的 `default_base_url`）
- `username`
- `password`

输出：
- `session_id`（后续复用）

### `ask_ops`

输入：
- `question`（必填）
- `session_id`（推荐）
- 或 `oem_base_url + username + password`（没有 session 时）
- `kb_path`（可选，默认用方案文档）

输出：
- 若参数不足：`need_follow_up=true`，返回明确追问
- 若执行成功：固定 4 段答案
  - `conclusion`
  - `evidence`
  - `next_steps`
  - `drill_down`

## 当前支持的试点指标

- `Memory_HardwareCorrupted`
- `DiskErrorCount`

阈值定义在 `config/metric_map.yaml`。

## 认证策略

- 每个用户使用自己的 OEM 账号密码
- 首次登录后缓存 `session_id`
- 会话 TTL 30 分钟，到期后必须重新登录
- 认证方式使用 Basic Auth（符合 OEM REST 文档方式）

## 注意

- 第一阶段只读，不做写操作
- 不直连 OEM repository 数据库
- 知识库当前是单文档匹配，后续可替换为向量检索/RAG

