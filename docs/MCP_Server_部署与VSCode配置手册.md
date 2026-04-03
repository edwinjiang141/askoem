# AI Gateway MCP Server 部署与 VS Code 配置手册

本文用于在测试环境快速部署本项目的 MCP Server，并在 VS Code 中完成配置和调用测试。

---

## 1. 目标

部署后，你可以在 VS Code 的 MCP 客户端里调用两个工具：

- `oem_login`：使用 OEM 账号登录并获取 `session_id`
- `ask_ops`：执行 4 步流程  
  识别问题 → 调 OEM REST API 取监控数据 → 查知识库 → 组织回答

---

## 2. 测试环境参数

当前已验证的 OEM API 基础地址：

- `https://192.168.30.230:7803/em/api`

当前代码默认配置（`config/metric_map.yaml`）：

- `oem_api.default_base_url: "https://192.168.30.230:7803/em/api"`
- `oem_api.verify_ssl: false`（等效 curl `-k`）

说明：`verify_ssl=false` 只用于测试环境。生产环境必须改为 `true` 并配置有效证书。

---

## 3. Windows 11 安装 Python 3.11+（先做）

如果你怀疑测试机 Python 异常，请先完成本节，再继续部署。

### 3.1 检查当前 Python 状态

在 PowerShell 执行：

```powershell
Get-Command python -ErrorAction SilentlyContinue
Get-Command py -ErrorAction SilentlyContinue
python -V
py -0p
```

期望结果：

- 能看到 `py` 启动器
- 列表里有 `3.11` 或更高版本

如果没有，按 3.2 安装。

### 3.2 使用 winget 安装（推荐）

```powershell
winget install -e --id Python.Python.3.11
```

安装后重新打开 PowerShell，再检查：

```powershell
py -0p
py -3.11 -V
```

### 3.3 使用官网安装包安装（备选）

1. 打开：https://www.python.org/downloads/windows/  
2. 下载 Python 3.11+ 的 Windows Installer（64-bit）  
3. 安装时勾选：
   - `Add python.exe to PATH`
   - `Install launcher for all users (recommended)`
4. 安装完成后重新打开 PowerShell

验证：

```powershell
py -3.11 -V
python -V
```

### 3.4 修复常见问题

如果 `python` 命令仍异常，先关闭 Windows 的别名劫持：

1. 打开 `Settings` -> `Apps` -> `Advanced app settings` -> `App execution aliases`  
2. 关闭 `python.exe` 和 `python3.exe` 的别名开关  
3. 重新打开 PowerShell，再执行：

```powershell
py -3.11 -V
```

建议后续所有部署命令优先使用 `py -3.11`。

---

## 4. 部署前检查

在目标机执行以下检查：

1. Python 版本：`>= 3.10`
2. 可访问 OEM 地址：`https://192.168.30.230:7803`
3. 本项目代码已拷贝到目标目录
4. 已准备可用 OEM 账号密码（每个用户使用自己的账号）

---

## 4.1 推荐目录规范

为避免路径错误，建议统一目录：

- Windows：`E:\edwin\AIGC\askoem`
- Linux：`/opt/askoem`

如果你的目录不同，后续命令中的路径要一起替换。

---

## 5. Windows 部署步骤

假设项目目录：`E:\edwin\AIGC\askoem`

### 5.1 创建虚拟环境并安装依赖

```powershell
cd E:\edwin\AIGC\askoem
py -3.11 -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
```

如果激活报错，使用：

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
```

### 5.2 启动 MCP Server（前台）

```powershell
cd E:\edwin\AIGC\askoem
.\.venv\Scripts\python.exe -m src.mcp_server
```

启动成功后，进程保持运行并等待 MCP 客户端通过 stdio 调用。

注意：这是 MCP stdio 服务。不要在这个终端里手工输入内容或按回车发送空行，否则会触发 JSONRPC 解析错误。

### 5.3 后台运行（可选）

测试时建议先前台运行。  
如果需要后台常驻，可以使用 NSSM 或任务计划程序托管以下命令：

```powershell
E:\edwin\AIGC\askoem\.venv\Scripts\python.exe -m src.mcp_server
```

---

## 6. Linux 部署步骤

假设项目目录：`/opt/askoem`

### 6.1 创建虚拟环境并安装依赖

```bash
cd /opt/askoem
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 6.2 启动 MCP Server（前台）

```bash
cd /opt/askoem
.venv/bin/python -m src.mcp_server
```

注意：这是 MCP stdio 服务。不要在这个终端里手工输入内容或按回车发送空行，否则会触发 JSONRPC 解析错误。

### 6.3 后台运行（可选，systemd）

创建服务文件 `/etc/systemd/system/ai-gateway-mcp.service`：

```ini
[Unit]
Description=AI Gateway MCP Server
After=network.target

[Service]
Type=simple
WorkingDirectory=/opt/askoem
ExecStart=/opt/askoem/.venv/bin/python -m src.mcp_server
Restart=always
RestartSec=3
User=root

[Install]
WantedBy=multi-user.target
```

启用服务：

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now ai-gateway-mcp
sudo systemctl status ai-gateway-mcp
```

---

## 7. 关键配置文件说明

文件：`config/metric_map.yaml`

必须确认以下字段：

- `oem_api.default_base_url`：OEM API 基础地址
- `oem_api.verify_ssl`：测试阶段为 `false`
- `oem_api.endpoints`：保持 `/em/api/...` 路径
- `intent_metric_map`：指标与 metric group 映射

当前实现已适配两种 `oem_base_url` 输入：

- `https://host:port`
- `https://host:port/em/api`

---

## 8. VS Code MCP 配置

不同 VS Code MCP 插件的配置文件路径不同，但配置核心一致：  
`command + args + cwd` 启动本地 MCP Server。

常见做法：

- 工作区级：`.vscode/mcp.json`
- 用户级：插件设置页中的 MCP Servers

请在你使用的 MCP 插件中新增一个 server，字段按下方填写。

### 8.1 Windows 示例

```json
{
  "mcpServers": {
    "ai-gateway-mvp": {
      "command": "E:\\edwin\\AIGC\\askoem\\.venv\\Scripts\\python.exe",
      "args": ["-m", "src.mcp_server"],
      "cwd": "E:\\edwin\\AIGC\\askoem"
    }
  }
}
```

### 8.2 Linux 示例

```json
{
  "mcpServers": {
    "ai-gateway-mvp": {
      "command": "/opt/askoem/.venv/bin/python",
      "args": ["-m", "src.mcp_server"],
      "cwd": "/opt/askoem"
    }
  }
}
```

配置保存后，重启 VS Code 或重启 MCP 插件。

### 8.3 配置后检查

1. 在 VS Code MCP 面板中确认出现 `ai-gateway-mvp`
2. 展开后能看到 `oem_login` 和 `ask_ops`
3. 若看不到，先检查 `command` 路径是否真实存在

---

## 9. VS Code 内测试步骤

### 9.1 第一步：调用 `oem_login`

参数示例：

```json
{
  "oem_base_url": "https://192.168.30.230:7803/em/api",
  "username": "sysman",
  "password": "<你的密码>"
}
```

成功返回示例（结构）：

```json
{
  "ok": true,
  "session_id": "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx",
  "message": "登录成功。后续请求可仅传 session_id。"
}
```

### 9.2 第二步：调用 `ask_ops`（复用 session）

问题 1（内存告警）：

```json
{
  "session_id": "上一步返回的session_id",
  "question": "x9mdbadm01 这台主机为什么有硬件内存告警"
}
```

问题 2（磁盘趋势）：

```json
{
  "session_id": "上一步返回的session_id",
  "question": "x9mceladm01 最近有没有磁盘错误上升"
}
```

成功返回中应包含：

- `answer.conclusion`
- `answer.evidence`
- `answer.next_steps`
- `answer.drill_down`

### 9.3 缺参追问验证

```json
{
  "session_id": "上一步返回的session_id",
  "question": "最近磁盘错误怎么样"
}
```

预期：

- `need_follow_up = true`
- 返回明确追问（例如补充目标名）

---

## 10. 常见问题排查

### 10.0 Python 命令不可用

原因：

- 系统未安装 Python
- 终端中 `python` 或 `python3` 不在 PATH

处理：

- Windows 用绝对路径执行：`E:\edwin\AIGC\askoem\.venv\Scripts\python.exe`
- Linux 用绝对路径执行：`/opt/askoem/.venv/bin/python`

### 10.1 401 Unauthorized

原因：

- 用户名密码错误
- 账号无对应目标权限

处理：

1. 用 curl 先验证账号（你当前方式）  
2. 再调用 `oem_login`

### 10.2 404 Not Found

原因：

- base URL 或 endpoint 配置错误

处理：

1. 确认 `default_base_url` 是否是 `https://<host>:<port>/em/api`
2. 确认 endpoints 是 `/em/api/...` 形态

### 10.3 SSL 错误

原因：

- 测试证书不被信任

处理：

- 测试环境保持 `verify_ssl: false`
- 生产环境必须改为 `true` 并导入有效 CA 证书

### 10.4 MCP 工具看不到

原因：

- VS Code 插件未加载 server
- `command/args/cwd` 配置错误

处理：

1. 重启 VS Code
2. 检查 Python 路径是否存在
3. 在终端手工执行同一命令确认服务可启动

### 10.5 `Invalid JSON: EOF while parsing a value`

现象：

- 日志出现 `JSONRPCMessage` 校验错误，提示 `Invalid JSON` 或 `EOF`

原因：

- stdio MCP 服务收到了非 JSON 输入（通常是终端手工回车产生的空行）
- 通过 shell 包装启动时，有额外输出写入了 stdio

处理：

1. 不要手工在服务终端输入任何字符
2. 在 VS Code MCP 配置中直接使用 Python 可执行文件，不要用 shell 包装命令
3. 使用本文给出的 `command + args + cwd` 配置重启 MCP server

---

## 11. 验收清单（Windows/Linux 通用）

完成以下 6 条即表示部署可用：

1. 终端可以启动 `python -m src.mcp_server`
2. VS Code 中能看到 `ai-gateway-mvp` 及两个工具
3. `oem_login` 调用成功并返回 `session_id`
4. `ask_ops` 能返回 4 段结构化答案
5. 缺参问题会触发 `need_follow_up=true`
6. 第二次 `ask_ops` 复用 `session_id` 不需要重复登录

---

## 12. 安全要求

1. 不要把真实密码写入仓库文件  
2. 账号密码只在工具调用时输入  
3. 生产环境启用 TLS 证书校验（`verify_ssl: true`）  
4. 保持只读调用，不开放高风险写操作

