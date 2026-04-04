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
        route_cfg = self._config.alert_scenarios.get(route.scenario, {})
        if route_cfg.get("require_target") and not parsed.target_name:
            return AskOpsResult(
                session_id=session.session_id,
                need_follow_up=True,
                follow_up_question="该告警场景需要目标名称，请补充主机名（例如：host01）。",
                final_result=None,
            )

        incidents = self._oem_client.list_recent_incidents(
            session=session,
            endpoints=self._config.endpoints,
            target_name=parsed.target_name,
            target_type_name=parsed.target_type_name if parsed.target_name else None,
            age_hours=24,
            limit=50,
        )
        events = self._oem_client.list_events_by_incidents(
            session=session,
            endpoints=self._config.endpoints,
            incidents=incidents,
        )

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
