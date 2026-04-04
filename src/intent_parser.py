from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any


INTENT_STATUS = "状态查询"
INTENT_ALERT_SUMMARY = "告警汇总"
INTENT_SINGLE_DIAGNOSIS = "单目标诊断"
INTENT_TREND = "趋势分析"
INTENT_SOP = "SOP问答"
INTENT_RISK = "风险排序"
INTENT_TARGET_LIST = "目标清单"
INTENT_METRIC_LIST = "监控项清单"


def is_alert_related_question(question: str) -> bool:
    q = question.lower()
    return any(k in q for k in ["告警", "报警", "incident", "event", "cpu高", "逻辑读", "物理读", "hba", "disk"])


@dataclass
class ParsedIntent:
    intent_type: str
    target_name: str | None
    target_type_name: str
    metric_keys: list[str]
    time_range: str
    route_key: str | None
    need_follow_up: bool
    follow_up_question: str | None


def _parse_time_range(question: str) -> str:
    q = question.lower()
    if "最近1小时" in question or "1小时" in question:
        return "1h"
    if "最近7天" in question or "7天" in question:
        return "7d"
    if "最近24小时" in question or "24小时" in question:
        return "24h"
    if "最近" in question and "小时" in question:
        return "24h"
    return "24h"


def _extract_target_name(question: str) -> str | None:
    # 支持常见 OEM 目标命名: 字母/数字/点/下划线/短横线
    # 例如 host01, db01, host01.domain.local
    candidates = re.findall(r"[A-Za-z0-9][A-Za-z0-9._-]{1,}", question)
    if not candidates:
        return None

    stop_words = {
        "cpu",
        "host",
        "hosts",
        "metric",
        "metrics",
        "monitor",
        "monitoring",
        "list",
        "show",
        "what",
        "how",
    }
    for raw in candidates:
        word = raw.strip("._-").lower()
        if len(word) < 2:
            continue
        if word in stop_words:
            continue
        # 过滤纯数字
        if word.isdigit():
            continue
        return raw
    return None


def _detect_target_type(question: str) -> str:
    q = question.lower()
    if "数据库" in question or "database" in q:
        return "oracle_database"
    return "host"


def _detect_intent(question: str) -> str:
    q = question.lower()
    if any(k in q for k in ["列出", "清单", "列表", "有哪些"]) and any(
        k in q for k in ["主机", "host", "目标", "监控"]
    ):
        return INTENT_TARGET_LIST
    if any(k in q for k in ["监控项", "指标", "metric", "监控指标"]) and any(
        k in q for k in ["列出", "清单", "列表", "查看", "有哪些"]
    ):
        return INTENT_METRIC_LIST
    if any(k in q for k in ["趋势", "上升", "下降", "变化", "最近"]):
        return INTENT_TREND
    if any(k in q for k in ["告警", "事件", "incident", "event"]) and any(
        k in q for k in ["汇总", "哪些", "最严重", "top"]
    ):
        return INTENT_ALERT_SUMMARY
    if any(k in q for k in ["sop", "怎么处理", "排查步骤", "文档"]):
        return INTENT_SOP
    if any(k in q for k in ["风险", "最危险", "优先处理"]):
        return INTENT_RISK
    if any(k in q for k in ["为什么", "异常", "报警"]):
        return INTENT_SINGLE_DIAGNOSIS
    return INTENT_STATUS


def parse_intent(question: str, intent_metric_map: dict[str, Any]) -> ParsedIntent:
    intent_type = _detect_intent(question)
    time_range = _parse_time_range(question)
    target_name = _extract_target_name(question)
    target_type_name = _detect_target_type(question)

    q = question.lower()
    route_key = None
    metric_keys: list[str] = []
    for item_key, item in intent_metric_map.items():
        hints = [x.lower() for x in item.get("intent_hints", [])]
        if any(h in q for h in hints):
            route_key = item_key
            metric_keys = list(item.get("metric_keys", []))
            break

    if intent_type == INTENT_TARGET_LIST:
        return ParsedIntent(
            intent_type=intent_type,
            target_name=None,
            target_type_name=target_type_name,
            metric_keys=[],
            time_range=time_range,
            route_key=None,
            need_follow_up=False,
            follow_up_question=None,
        )

    if intent_type == INTENT_METRIC_LIST and not target_name:
        return ParsedIntent(
            intent_type=intent_type,
            target_name=None,
            target_type_name=target_type_name,
            metric_keys=[],
            time_range=time_range,
            route_key=None,
            need_follow_up=True,
            follow_up_question="请补充目标名称，例如：查看 <目标名> 的监控项有哪些。",
        )

    if intent_type == INTENT_METRIC_LIST:
        return ParsedIntent(
            intent_type=intent_type,
            target_name=target_name,
            target_type_name=target_type_name,
            metric_keys=[],
            time_range=time_range,
            route_key=None,
            need_follow_up=False,
            follow_up_question=None,
        )

    need_target = intent_type in {INTENT_SINGLE_DIAGNOSIS, INTENT_TREND, INTENT_STATUS}
    if need_target and not target_name:
        return ParsedIntent(
            intent_type=intent_type,
            target_name=None,
            target_type_name=target_type_name,
            metric_keys=metric_keys,
            time_range=time_range,
            route_key=route_key,
            need_follow_up=True,
            follow_up_question="请补充目标名称（例如主机名或数据库名）。",
        )

    if not route_key:
        return ParsedIntent(
            intent_type=intent_type,
            target_name=target_name,
            target_type_name=target_type_name,
            metric_keys=[],
            time_range=time_range,
            route_key=None,
            need_follow_up=True,
            follow_up_question="请指定要查询的监控项，或先提问：<目标名> 的监控项有哪些？",
        )

    return ParsedIntent(
        intent_type=intent_type,
        target_name=target_name,
        target_type_name=target_type_name,
        metric_keys=metric_keys,
        time_range=time_range,
        route_key=route_key,
        need_follow_up=False,
        follow_up_question=None,
    )
