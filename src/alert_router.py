from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from src.llm_classifier import LlmIntentClassifier


@dataclass
class AlertRouteResult:
    scenario: str
    confidence: float
    classifier: str


def classify_alert_scenario(
    question: str,
    alert_scenarios: dict[str, Any],
    llm: LlmIntentClassifier | None = None,
) -> AlertRouteResult:
    """
    告警场景识别（混合模式）：
    1) 先按配置关键词进行规则匹配（稳定、可控）。
    2) 若仅判定为 generic 且置信度低，再调用可选 LLM 分类器兜底。
    说明：分类器只决定“场景标签”，不直接生成处置决策。
    """
    q = question.lower()
    has_alert_word = any(k in q for k in ["告警", "报警", "incident", "event", "事件"])

    for scenario, cfg in alert_scenarios.items():
        keywords = [str(x).lower() for x in cfg.get("keywords", [])]
        if keywords and any(k in q for k in keywords) and has_alert_word:
            return AlertRouteResult(scenario, 0.95, "rule")

    if has_alert_word:
        route = AlertRouteResult("generic_alert", 0.70, "rule")
    else:
        route = AlertRouteResult("generic_alert", 0.45, "rule")

    # 混合模式: 规则不确定时再调用 LLM 分类
    if route.confidence < 0.8 and llm and llm.enabled:
        llm_label = llm.classify_alert(question)
        if llm_label:
            return AlertRouteResult(llm_label, 0.82, "llm_fallback")
    return route
