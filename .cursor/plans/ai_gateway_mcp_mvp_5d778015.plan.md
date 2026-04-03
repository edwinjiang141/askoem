---
name: AI Gateway MCP MVP
overview: 基于现有文档快速落地一个可运行的 MCP Server MVP，跑通“识别问题→OEM REST取数→单文档知识库→结构化回答”4步流程，并支持每用户OEM账号会话缓存认证。
todos:
  - id: bootstrap-mcp
    content: 初始化MCP Server骨架与ask_ops工具入口
    status: pending
  - id: auth-session-cache
    content: 实现每用户OEM认证与会话缓存TTL机制
    status: pending
  - id: intent-and-routing
    content: 实现问题识别与意图到OEM取数映射
    status: pending
  - id: oem-rest-client
    content: 实现OEM REST只读取数能力（latest/timeSeries/incidents/events）
    status: pending
  - id: single-doc-kb
    content: 实现单文档知识库检索并返回证据片段
    status: pending
  - id: compose-answer
    content: 实现固定4段回答模板与证据拼装
    status: pending
  - id: mvp-verification
    content: 完成两个示例问题端到端验证与文档
    status: pending
isProject: false
---

# AI Gateway MCP MVP 实施计划

## 目标

在当前仓库从零搭建一个最小可运行系统，满足：

- 主形态为 MCP Server（可被 VS Code/Cursor 等宿主调用）
- 跑通 4 步闭环：问题识别 → OEM REST 取数 → 单文档知识库检索 → 结构化回答
- OEM 认证使用“每用户账号密码 + 会话缓存”

## 依据文档

- 设计说明：[docs/AI_Gateway_说明.md](docs/AI_Gateway_说明.md)
- 整体方案：[docs/OEM_Grafana_AI_Gateway_Exadata_Solution_Report.md](docs/OEM_Grafana_AI_Gateway_Exadata_Solution_Report.md)
- 项目规则：[.cursor/rules/ai-gateway-mvp.mdc](.cursor/rules/ai-gateway-mvp.mdc)

## 范围与边界

- 只做只读查询，不做自动修复或写操作
- 只覆盖试点指标：`Memory_HardwareCorrupted`、`DiskErrorCount`
- 知识库先用单一运维文档（本地文件检索）
- 回答结构按规则固定 4 段：结论 / 证据 / 下一步建议 / 深挖入口（影响范围并入证据）

## 实现结构（拟新增）

- MCP Server 主程序：`[src/mcp_server.py](src/mcp_server.py)`
- 问题识别器：`[src/intent_parser.py](src/intent_parser.py)`
- OEM REST 客户端：`[src/oem_client.py](src/oem_client.py)`
- 会话与凭据缓存：`[src/auth_session.py](src/auth_session.py)`
- 知识库检索（单文档）：`[src/knowledge_base.py](src/knowledge_base.py)`
- 回答组织器：`[src/answer_composer.py](src/answer_composer.py)`
- 指标与路由配置：`[config/metric_map.yaml](config/metric_map.yaml)`
- MCP 工具说明与运行文档：`[README.md](README.md)`
- 验证脚本/样例请求：`[examples/mcp_requests.md](examples/mcp_requests.md)`

## 数据流（MVP）

```mermaid
flowchart LR
  userClient[UserClient(VSCode/Cursor)] --> mcpTool[AskOpsTool]
  mcpTool --> sessionAuth[SessionAuth]
  sessionAuth --> intentParser[IntentParser]
  intentParser --> oemRouter[OEMDataRouter]
  oemRouter --> oemRest[OEMRestAPI]
  intentParser --> kbRetriever[DocRetriever]
  oemRest --> answerComposer[AnswerComposer]
  kbRetriever --> answerComposer
  answerComposer --> mcpTool
  mcpTool --> userClient
```



## 关键设计点

- 问题识别输出固定字段：`intentType`、`targetName`、`metricKeys`、`timeRange`
- OEM REST 取数按意图路由：
  - 状态/诊断：目标信息 + latestData + timeSeries + incidents/events
  - 趋势：timeSeries + latestData + incidents/events
  - 告警汇总/风险排序：targets + incidents/events + 关键指标最新值
- 会话缓存：按“用户ID+OEM地址”缓存 token/cookie，设置 TTL，到期强制重登
- 单文档知识库：基于标题与关键词匹配返回片段，附来源段落标识
- 回答严格结构化并带证据字段（指标值、阈值、时间范围、相关事件）

## 验收标准

- 可通过 MCP 工具提交自然语言问题并得到结构化回答
- 两个示例问题可跑通：
  - `x9mdbadm01 这台主机为什么有硬件内存告警`
  - `x9mceladm01 最近有没有磁盘错误上升`
- 能看到 OEM 会话复用效果（同会话第二次请求无需再次输入账号密码）
- 缺少关键参数时返回明确追问，不猜测补全
- 错误返回可读（认证失败、目标不存在、OEM接口超时）

## 实施顺序

1. 搭 MCP Server 外壳与 1 个主工具（`ask_ops`）
2. 实现会话登录/缓存与认证中间层
3. 实现问题识别（规则+关键词）与时间范围解析
4. 实现 OEM REST 客户端与按意图取数
5. 实现单文档知识库检索
6. 实现回答组织器并串联全流程
7. 补充示例请求与本地验证步骤

