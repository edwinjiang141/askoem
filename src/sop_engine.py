from __future__ import annotations

from typing import Any

from src.oem_client import OemDataBundle


def build_sop_recommendation(
    scenario: str,
    target_name: str | None,
    incidents: list[dict[str, Any]],
    events: list[dict[str, Any]],
    metric_bundle: OemDataBundle | None = None,
) -> str:
    """
    SOP 引擎入口：根据场景标签选择固定模板。
    输入证据仅来自 OEM 告警对象（incidents/events），避免自由推理。
    """
    if scenario == "cpu_high":
        return _cpu_sop(target_name, incidents, events, metric_bundle)
    if scenario == "io_high":
        return _io_sop(target_name, incidents, events, metric_bundle)
    if scenario == "hardware_hba_disk":
        return _hardware_placeholder(target_name, incidents, events)
    return _generic_sop(target_name, incidents, events)


def _cpu_sop(
    target_name: str | None,
    incidents: list[dict[str, Any]],
    events: list[dict[str, Any]],
    metric_bundle: OemDataBundle | None,
) -> str:
    latest_count = len(metric_bundle.latest_data) if metric_bundle else 0
    ts_count = len(metric_bundle.metric_time_series) if metric_bundle else 0
    return (
        f"[CPU高告警SOP] 目标: {target_name or '未指定'}\n"
        f"证据: incidents={len(incidents)}, events={len(events)}, latestData={latest_count}, timeSeries={ts_count}\n"
        "处理建议:\n"
        "1) 先确认是否持续高位: 检查最近1小时/24小时CPU趋势与峰值持续时长。\n"
        "2) 对高CPU主机执行TOP会话/进程定位，优先识别异常SQL、批处理、备份任务。\n"
        "3) 核对同时间窗口的等待事件与IO是否联动升高，避免误判为纯CPU瓶颈。\n"
        "4) 如为计划任务导致且在维护窗口内，可记录并观察；否则执行限流/错峰并升级应用侧排查。\n"
        "5) 复盘阈值: 连续多次触发时，建议补充容量评估与阈值分级告警策略。"
    )


def _io_sop(
    target_name: str | None,
    incidents: list[dict[str, Any]],
    events: list[dict[str, Any]],
    metric_bundle: OemDataBundle | None,
) -> str:
    latest_count = len(metric_bundle.latest_data) if metric_bundle else 0
    ts_count = len(metric_bundle.metric_time_series) if metric_bundle else 0
    return (
        f"[IO读高告警SOP] 目标: {target_name or '未指定'}\n"
        f"证据: incidents={len(incidents)}, events={len(events)}, latestData={latest_count}, timeSeries={ts_count}\n"
        "处理建议:\n"
        "1) 区分逻辑读/物理读: 逻辑读高优先看SQL访问路径；物理读高优先看存储层与缓存命中。\n"
        "2) 对最近告警时段执行Top SQL与执行计划检查，确认是否存在全表扫描/索引失效。\n"
        "3) 对物理读高场景，检查磁盘延迟、队列深度、ASM/文件系统层异常事件。\n"
        "4) 结合业务变更与批任务时间窗，判断是否短时脉冲或持续瓶颈。\n"
        "5) 持续超阈值时，建议先做SQL治理，再评估存储扩容或参数调优。"
    )


def _hardware_placeholder(
    target_name: str | None,
    incidents: list[dict[str, Any]],
    events: list[dict[str, Any]],
) -> str:
    return (
        f"[HBA/Disk硬件告警] 目标: {target_name or '未指定'}\n"
        f"证据: incidents={len(incidents)}, events={len(events)}\n"
        "当前版本仅输出告警数据摘要。该场景SOP待你提供后可按同样机制固化执行。"
    )


def _generic_sop(target_name: str | None, incidents: list[dict[str, Any]], events: list[dict[str, Any]]) -> str:
    return (
        f"[通用告警SOP] 目标: {target_name or '未指定'}\n"
        f"证据: incidents={len(incidents)}, events={len(events)}\n"
        "处理建议:\n"
        "1) 先按严重级别与影响范围排序告警，优先处理Critical与持续告警。\n"
        "2) 关联同时间窗口的指标趋势与事件，确认根因方向（计算/存储/网络/硬件）。\n"
        "3) 按SOP逐项取证，记录每一步观察结果与处置动作。\n"
        "4) 若无现成SOP，走“告警确认-影响评估-根因定位-临时缓解-永久修复-复盘”闭环。"
    )
