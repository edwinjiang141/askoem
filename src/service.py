from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

from src.auth_session import OemSession, SessionCache
from src.alert_router import classify_alert_scenario
from src.intent_parser import INTENT_METRIC_LIST, INTENT_TARGET_LIST, is_alert_related_question, parse_intent
from src.knowledge_base import SingleDocKnowledgeBase
from src.llm_classifier import LlmIntentClassifier
from src.metric_config import MetricConfig
from src.oem_client import OemClient
from src.sop_engine import build_sop_recommendation


@dataclass
class AskOpsResult:
    session_id: str | None
    need_follow_up: bool
    follow_up_question: str | None
    final_result: str | None


class AskOpsService:
    def __init__(self, config: MetricConfig):
        self._config = config
        self._sessions = SessionCache(ttl_minutes=30)
        self._oem_client = OemClient(
            timeout_seconds=config.timeout_seconds,
            verify_ssl=config.verify_ssl,
        )
        self._llm_classifier = LlmIntentClassifier(timeout_seconds=min(config.timeout_seconds, 15))

    def login(self, oem_base_url: str, username: str, password: str) -> str:
        resolved_base_url = oem_base_url or self._config.default_base_url
        if not resolved_base_url:
            raise ValueError("缺少 oem_base_url，且配置中未设置 default_base_url。")
        token = self._oem_client.login(
            base_url=resolved_base_url,
            targets_endpoint=self._config.endpoints["targets"],
            username=username,
            password=password,
        )
        session = self._sessions.create(
            oem_base_url=resolved_base_url,
            username=username,
            password=password,
            token=token,
        )
        return session.session_id

    def ask(
        self,
        question: str,
        kb_path: str,
        session_id: Optional[str] = None,
        oem_base_url: Optional[str] = None,
        username: Optional[str] = None,
        password: Optional[str] = None,
    ) -> AskOpsResult:
        # 告警类问题（例如“当前有哪些告警，如何处理”）的总入口说明：
        # 1) ask() 先做轻量问题分流：若命中告警关键词，直接进入 _ask_alert()。
        # 2) _ask_alert() 中先解析 target（若有），并做场景识别：
        #    - 规则优先（alert_router）
        #    - 低置信度时可选 LLM 兜底分类
        # 3) 基于 OEM REST API 拉取数据（只读）：
        #    - incidents（主）
        #    - incident 对应 events（主）
        # 4) 将“场景 + incidents/events 证据”送入 SOP 引擎，输出固定结构建议文本。
        # 5) 返回 final_result 给 MCP 调用方（Cline/VS Code）。
        # 当前版本刻意不做自动修复动作，也不执行写操作，保证可控和可审计。
        if is_alert_related_question(question):
            return self._ask_alert(question, session_id, oem_base_url, username, password)

        parsed = parse_intent(question, self._config.intent_metric_map)
        if parsed.need_follow_up:
            return AskOpsResult(
                session_id=session_id,
                need_follow_up=True,
                follow_up_question=parsed.follow_up_question,
                final_result=None,
            )

        session = self._resolve_session(
            session_id=session_id,
            oem_base_url=oem_base_url,
            username=username,
            password=password,
        )

        if parsed.intent_type == INTENT_TARGET_LIST:
            host_rows = self._oem_client.list_hosts_with_details(
                session=session,
                endpoints=self._config.endpoints,
                limit=200,
            )
            table = self._format_table(
                rows=host_rows,
                headers=["HostName", "Status", "BootTime", "IP", "OS", "Version"],
            )
            return AskOpsResult(
                session_id=session.session_id,
                need_follow_up=False,
                follow_up_question=None,
                final_result=(
                    f"当前共查询到 {len(host_rows)} 个监控主机。\n{table}"
                ),
            )

        if parsed.intent_type == INTENT_METRIC_LIST and parsed.target_name:
            groups = self._oem_client.list_metric_groups(
                session=session,
                endpoints=self._config.endpoints,
                target_name=parsed.target_name,
                target_type_name=parsed.target_type_name,
                limit=200,
            )
            group_names = [x.get("metricGroupName") for x in groups if isinstance(x.get("metricGroupName"), str)]
            if not group_names:
                group_names = [x.get("name") for x in groups if isinstance(x.get("name"), str)]
            group_names = [x for x in group_names if x]
            preview = group_names[:30]
            return AskOpsResult(
                session_id=session.session_id,
                need_follow_up=False,
                follow_up_question=None,
                final_result=(
                    f"目标 {parsed.target_name} 共查询到 {len(group_names)} 个监控项。"
                    + (f" 监控项(前{len(preview)}个): {', '.join(preview)}" if preview else "")
                ),
            )

        bundle = self._oem_client.fetch_bundle(
            session=session,
            endpoints=self._config.endpoints,
            target_name=parsed.target_name,
            route_config=self._merge_route_target_type(
                self._config.intent_metric_map.get(parsed.route_key or "", {}),
                parsed.target_type_name,
            ),
            time_range=parsed.time_range,
        )

        metric_key = parsed.metric_keys[0] if parsed.metric_keys else "unknown_metric"
        latest_count = len(bundle.latest_data)
        ts_count = len(bundle.metric_time_series)
        incident_count = len(bundle.incidents)
        event_count = len(bundle.events)

        # 单文档知识库仍参与流程，但仅用于补充最终一句建议，不输出中间细节。
        kb_tip = ""
        try:
            kb = SingleDocKnowledgeBase(kb_path)
            kb_keywords = [parsed.intent_type, metric_key]
            if parsed.target_name:
                kb_keywords.append(parsed.target_name)
            snippets = kb.search(kb_keywords, top_k=1)
            if snippets:
                kb_tip = f" 建议参考知识库: {snippets[0].source}。"
        except Exception:
            kb_tip = ""

        final_result = (
            f"已完成查询。目标: {parsed.target_name}，监控项: {metric_key}，时间范围: {parsed.time_range}。"
            f" 获取到 latestData {latest_count} 条，timeSeries {ts_count} 条，incidents {incident_count} 条，events {event_count} 条。"
            f"{kb_tip}"
        )

        return AskOpsResult(
            session_id=session.session_id,
            need_follow_up=False,
            follow_up_question=None,
            final_result=final_result,
        )

    def _ask_alert(
        self,
        question: str,
        session_id: Optional[str],
        oem_base_url: Optional[str],
        username: Optional[str],
        password: Optional[str],
    ) -> AskOpsResult:
        # _ask_alert() = 告警处理编排主流程（面向“当前有哪些告警，如何处理”）
        #
        # 输入：
        # - question: 用户自然语言问题
        # - session_id 或认证参数: 用于 OEM REST 只读访问
        #
        # 输出：
        # - AskOpsResult.final_result: 包含场景识别 + 证据来源 + SOP 建议
        #
        # 子步骤：
        # A. 会话解析：复用已有登录态（或按参数新建会话）
        # B. 意图解析：提取 target_name / target_type（若问题中有对象）
        # C. 场景识别：rule-first, LLM-fallback（由 alert_router 实现）
        # D. 规则校验：若场景要求 target 但未提供，则返回追问
        # E. 数据采集：仅采 incidents + events（OEM 主路径）
        # F. SOP 生成：调用 sop_engine 输出场景化处置建议
        session = self._resolve_session(
            session_id=session_id,
            oem_base_url=oem_base_url,
            username=username,
            password=password,
        )
        parsed = parse_intent(question, self._config.intent_metric_map)
        route = classify_alert_scenario(
            question=question,
            alert_scenarios=self._config.alert_scenarios,
            llm=self._llm_classifier,
        )

        incidents = self._oem_client.list_recent_incidents(
            session=session,
            endpoints=self._config.endpoints,
            target_name=parsed.target_name,
            target_type_name=parsed.target_type_name if parsed.target_name else None,
            scenario=route.scenario,
            question=question,
            age_hours=24,
            limit=50,
        )
        events = self._oem_client.list_events_by_incidents(
            session=session,
            endpoints=self._config.endpoints,
            incidents=incidents,
        )

        # 统一返回格式（供前端/插件稳定渲染）：
        # - 第一行：场景识别结果（可审计）
        # - 第二行：数据来源说明（避免“模型臆断”）
        # - 其后：SOP建议正文（固定步骤）
        final_result = (
            f"告警识别结果: {route.scenario} (classifier={route.classifier}, confidence={route.confidence:.2f})\n"
            "数据来源: OEM incidents/events（主）\n"
            + build_sop_recommendation(
                scenario=route.scenario,
                target_name=parsed.target_name,
                incidents=incidents,
                events=events,
                metric_bundle=None,
            )
        )
        return AskOpsResult(
            session_id=session.session_id,
            need_follow_up=False,
            follow_up_question=None,
            final_result=final_result,
        )

    @staticmethod
    def _merge_route_target_type(route_config: dict[str, Any], target_type_name: str) -> dict[str, Any]:
        merged = dict(route_config)
        merged["target_type_name"] = target_type_name
        return merged

    @staticmethod
    def _format_table(rows: list[dict[str, str]], headers: list[str]) -> str:
        if not rows:
            return "未查询到数据。"
        width: dict[str, int] = {h: len(h) for h in headers}
        for row in rows:
            for h in headers:
                width[h] = max(width[h], len(str(row.get(h, "-"))))

        def fmt_line(values: list[str]) -> str:
            return " ".join(v.ljust(width[h]) for v, h in zip(values, headers))

        header_line = fmt_line(headers)
        dash_line = fmt_line(["-" * len(h) for h in headers])
        row_lines = [fmt_line([str(r.get(h, "-")) for h in headers]) for r in rows]
        return "\n".join([header_line, dash_line, *row_lines])

    def _resolve_session(
        self,
        session_id: Optional[str],
        oem_base_url: Optional[str],
        username: Optional[str],
        password: Optional[str],
    ) -> OemSession:
        if session_id:
            session = self._sessions.get(session_id)
            if session:
                return session
            raise ValueError("session_id 无效或已过期，请重新登录。")

        if not oem_base_url or not username or not password:
            fallback_base = oem_base_url or self._config.default_base_url
            if fallback_base and username and password:
                oem_base_url = fallback_base
            else:
                raise ValueError("缺少认证参数。请提供 session_id，或提供 oem_base_url + username + password。")
        new_session_id = self.login(oem_base_url=oem_base_url, username=username, password=password)
        session = self._sessions.get(new_session_id)
        if not session:
            raise RuntimeError("会话创建失败，请重试。")
        return session
