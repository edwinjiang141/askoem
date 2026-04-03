from __future__ import annotations

from typing import Any

from src.knowledge_base import KbSnippet
from src.oem_client import OemDataBundle


def compose_answer(
    question: str,
    intent_type: str,
    target_name: str | None,
    metric_keys: list[str],
    time_range: str,
    route_key: str,
    thresholds: dict[str, Any],
    grafana_links: dict[str, str],
    bundle: OemDataBundle,
    kb_snippets: list[KbSnippet],
) -> dict[str, Any]:
    evidence_lines: list[str] = []
    for metric in metric_keys:
        t = thresholds.get(metric, {})
        evidence_lines.append(
            f"- 指标 `{metric}` 阈值: Warning {t.get('warning', 'N/A')}, "
            f"Critical {t.get('critical', 'N/A')} {t.get('unit', '')}".strip()
        )

    if bundle.latest_data:
        evidence_lines.append(f"- latestData 条数: {len(bundle.latest_data)}")
    if bundle.metric_time_series:
        evidence_lines.append(f"- metricTimeSeries 条数: {len(bundle.metric_time_series)}")
    evidence_lines.append(f"- incidents 条数: {len(bundle.incidents)}")
    evidence_lines.append(f"- events 条数: {len(bundle.events)}")
    evidence_lines.append(f"- 时间范围: {time_range}")
    if target_name:
        evidence_lines.append(f"- 目标: {target_name}")

    kb_summary = "；".join([f"{x.source}" for x in kb_snippets]) if kb_snippets else "未命中知识片段"
    next_actions = [
        "先确认该异常是否持续存在，而不是一次性波动。",
        "优先检查最新 incident/event 的时间和严重级别。",
        "按知识库 SOP 执行第一条排查步骤，再决定是否升级处理。",
    ]
    link = grafana_links.get(route_key) or grafana_links.get("default", "")

    conclusion = (
        f"已完成 {intent_type} 流程。"
        f"问题: {question}。"
        "系统已完成 OEM 取数与知识库检索。"
    )

    return {
        "conclusion": conclusion,
        "evidence": evidence_lines,
        "next_steps": next_actions,
        "drill_down": {
            "grafana_url": link,
            "kb_sources": [x.source for x in kb_snippets],
            "kb_preview": [x.text[:200] for x in kb_snippets],
        },
    }

