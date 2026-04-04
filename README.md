# AI Gateway MCP MVP

AI Gateway 的 MCP Server 最小实现，面向 OEM 只读问答场景。

当前主流程：

1. 识别问题意图与目标类型
2. 调用 OEM REST API 取数
3. （按需）查询单文档知识库
4. 返回最终结果文本

## 项目结构

- `src/mcp_server.py`：MCP Server 入口（`oem_login`、`ask_ops`）
- `src/service.py`：主流程编排与结果组织
- `src/intent_parser.py`：意图识别、目标名抽取、目标类型识别
- `src/oem_client.py`：OEM REST 客户端（只读，含兼容降级逻辑）
- `src/auth_session.py`：会话缓存（TTL 30 分钟）
- `src/knowledge_base.py`：单文档检索
- `config/metric_map.yaml`：OEM 接口配置、默认地址、意图映射

## 快速启动

### 1) 安装依赖

Windows PowerShell:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Linux:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2) 检查配置

文件：`config/metric_map.yaml`

关键项：

- `oem_api.default_base_url`
- `oem_api.verify_ssl`（测试环境可用 `false`）
- `oem_api.endpoints.*`

`default_base_url` 支持两种写法：

- `https://host:port`
- `https://host:port/em/api`

### 3) MCP 启动说明

该服务是 **stdio MCP server**，应由 VS Code/Cursor/Cline 的 MCP 客户端拉起。  
不要在交互终端手工输入请求内容。

启动命令（供 MCP 配置使用）：

```bash
python -m src.mcp_server
```

## MCP 工具

### `oem_login`

参数：

- `oem_base_url`（可选，不传则用配置默认值）
- `username`
- `password`

返回：

- `session_id`

### `ask_ops`

参数：

- `question`（必填）
- `session_id`（推荐）
- 或 `oem_base_url + username + password`
- `kb_path`（可选）

返回（当前版本）：

- `ok`
- `session_id`（成功时）
- `result`（仅最终结果文本，不输出中间过程结构）

## 当前支持的通用查询示例

- `列出当前监控主机的信息，并以表格形式返回`
- `查看 19test1 的监控项有哪些`
- `19test1 cpu 利用率多少`
- `host01 最近 CPU 高告警怎么处理`
- `host01 IO 逻辑读或者物理读高告警，给处理建议`

## 告警处理（SOP 固化）

当前实现采用混合识别模式：

- 优先规则识别（稳定可控）
- 规则不确定时再调用可选 LLM 分类（适配 Cline + DeepSeek）

告警数据主来源为 **OEM incidents/events**（当前版本仅读取告警对象，不补充指标明细）。

已内置场景：

- CPU 高告警 SOP
- IO 逻辑读/物理读高告警 SOP
- 通用告警 SOP（无专用 SOP 时兜底）

扩展方式：通过 `config/metric_map.yaml` 的 `alert_scenarios` 增加关键词、是否需要目标名，无需改动核心流程代码。

## 兼容性与容错

- OEM 认证方式：Basic Auth
- 对部分接口参数不兼容时自动降级重试（例如 `targets` 的 `include` 参数）
- 对部分接口不可用时降级处理（例如某些环境 `metricGroups` 可能 404）

## 注意事项

- 只读访问，不执行高风险写操作
- 不直连 OEM repository 数据库
- 测试环境可关闭 SSL 校验，生产环境必须开启并使用有效证书
