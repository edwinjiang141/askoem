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
- `https://host:port/em`（控制台入口，代码会自动拼接 REST 路径）

### 3) MCP 启动说明

该服务是 **stdio MCP server**，应由 VS Code/Cursor/Cline 的 MCP 客户端拉起。  
不要在交互终端手工输入请求内容。

启动命令（供 MCP 配置使用）：

```bash
python -m src.mcp_server
```

### 4) 中心化部署（推荐，避免每个客户端部署源码）

为避免“每个客户端都安装一份 Python 源码”，可使用 MCP 的 `streamable-http` 方式做中心化部署：

```bash
python -m src.mcp_server_http
```

说明：

- `src.mcp_server_http` 与 `src.mcp_server` 复用同一套 tools/逻辑，不改已有功能。
- 服务端集中部署 1 套即可，客户端通过网络连接该 MCP 服务。
- 适合内网统一运维，便于版本管理和灰度升级。

建议架构：

1. 在一台统一服务器部署本项目（或容器化部署）。
2. 运行 `python -m src.mcp_server_http` 暴露 MCP HTTP 服务。
3. Cline/Cursor 客户端改为配置远程 MCP 地址，而不是本地 `command + args`。

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

### 告警问答端到端流程（示例：`当前有哪些告警，如何处理`）

1. **MCP 入口接收问题**  
   `ask_ops` 接收 `question` 后调用 `AskOpsService.ask()`。
2. **问题分流**  
   `ask()` 先判断是否为告警类问题，命中后进入 `_ask_alert()` 分支。
3. **场景识别**  
   `_ask_alert()` 调用 `alert_router`：
   - 规则优先（配置关键词匹配）
   - 低置信度时可选 LLM 兜底分类
4. **参数与上下文提取**  
   从问题中尽量提取目标名/时间提示；若未提供目标，也会继续走模拟 incident + SOP 输出流程。
4. **参数校验**  
   若场景要求目标名（如 CPU/IO），但问题中未给出目标，则返回追问。
5. **OEM 数据采集（只读）**  
   仅拉取：
   - `incidents`
   - `incident events`
6. **SOP 生成**  
   将 `场景 + incidents/events` 送入 `sop_engine`，输出固定模板建议（非 LLM 自由生成）。
   将 `场景 + incidents/events` 送入 `sop_engine`，输出固定模板建议。
7. **结果返回**  
   返回结构化文本（识别结果 + 数据来源 + SOP建议）给 Cline/VS Code。

## 兼容性与容错

- OEM 认证方式：Basic Auth
- 对部分接口参数不兼容时自动降级重试（例如 `targets` 的 `include` 参数）
- 对部分接口不可用时降级处理（例如某些环境 `metricGroups` 可能 404）
- 临时兼容：若测试环境 OEM 版本不支持 `/em/api/incidents`，当前代码会返回一个模拟 incident 以跑通 SOP 链路（代码内保留了恢复真实接口调用的注释位）
- 临时兼容：低版本 OEM 也可能不支持 `.../metricGroups/.../latestData` 相关接口，当前告警流程不依赖该接口，使用“按提问内容构造模拟 incident”方式继续输出 CPU/IO SOP

## 注意事项

- 只读访问，不执行高风险写操作
- 不直连 OEM repository 数据库
- 测试环境可关闭 SSL 校验，生产环境必须开启并使用有效证书
