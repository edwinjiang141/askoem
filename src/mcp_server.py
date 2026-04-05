from __future__ import annotations

import sys
from typing import Any

from mcp.server.fastmcp import FastMCP

from src.metric_config import load_metric_config
from src.service import AskOpsService


CONFIG_PATH = "config/metric_map.yaml"
DEFAULT_KB_PATH = "docs/OEM_Grafana_AI_Gateway_Exadata_Solution_Report.md"
SERVER_VERSION = "0.1.0"

config = load_metric_config(CONFIG_PATH)
service = AskOpsService(config)
mcp = FastMCP("ai-gateway-mvp")


@mcp.tool()
def oem_login(oem_base_url: str | None, username: str, password: str) -> dict[str, Any]:
    """
    使用 OEM 账号登录并创建会话缓存。
    返回 session_id，后续 ask_ops 直接复用。
    """
    session_id = service.login(oem_base_url=oem_base_url or "", username=username, password=password)
    return {
        "ok": True,
        "session_id": session_id,
        "message": "登录成功。后续请求可仅传 session_id。",
    }


@mcp.tool()
def ask_ops(
    question: str,
    session_id: str | None = None,
    oem_base_url: str | None = None,
    username: str | None = None,
    password: str | None = None,
    kb_path: str = DEFAULT_KB_PATH,
) -> dict[str, Any]:
    """
    执行 AI Gateway MVP 4 步流程:
    1) 识别问题
    2) 调 OEM REST API 取监控数据
    3) 查询单文档知识库
    4) 组织结构化回答

    告警类问题会走 AskOpsService 的告警编排分支:
    - 场景识别（规则优先 + 可选LLM兜底）
    - 拉取 incidents/events
    - 返回 SOP 化处理建议
    """
    result = service.ask(
        question=question,
        kb_path=kb_path,
        session_id=session_id,
        oem_base_url=oem_base_url,
        username=username,
        password=password,
    )
    if result.need_follow_up:
        return {
            "ok": False,
            "result": result.follow_up_question,
        }

    return {
        "ok": True,
        "session_id": result.session_id,
        "result": result.final_result,
    }


@mcp.tool()
def health_check() -> dict[str, Any]:
    """
    调试与巡检工具：
    - 验证 MCP 服务是否在线
    - 验证核心 tools 是否已加载
    - 回显关键运行配置（脱敏）
    """
    return {
        "ok": True,
        "server": "ai-gateway-mvp",
        "version": SERVER_VERSION,
        "tools": ["health_check", "oem_login", "ask_ops"],
        "config": {
            "default_base_url": config.default_base_url,
            "verify_ssl": config.verify_ssl,
        },
        "message": "服务在线，核心工具已加载。",
    }


if __name__ == "__main__":
    if sys.stdin.isatty():
        sys.stderr.write(
            "检测到当前为交互终端。\n"
            "src.mcp_server 是 stdio MCP 服务，请通过 VS Code/Cursor 的 MCP 客户端启动，"
            "不要在终端手工输入内容。\n"
        )
        sys.exit(1)
    mcp.run()
