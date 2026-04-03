from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


@dataclass
class MetricConfig:
    raw: dict[str, Any]

    @property
    def endpoints(self) -> dict[str, str]:
        return self.raw["oem_api"]["endpoints"]

    @property
    def timeout_seconds(self) -> int:
        return int(self.raw["oem_api"].get("timeout_seconds", 20))

    @property
    def default_base_url(self) -> str:
        return str(self.raw["oem_api"].get("default_base_url", "")).strip()

    @property
    def verify_ssl(self) -> bool:
        return bool(self.raw["oem_api"].get("verify_ssl", False))

    @property
    def intent_metric_map(self) -> dict[str, Any]:
        return self.raw["intent_metric_map"]

    @property
    def metric_thresholds(self) -> dict[str, Any]:
        return self.raw["metric_thresholds"]

    @property
    def grafana_links(self) -> dict[str, str]:
        return self.raw["grafana_links"]


def load_metric_config(path: str) -> MetricConfig:
    full_path = Path(path)
    if not full_path.exists():
        raise FileNotFoundError(f"配置文件不存在: {path}")

    data = yaml.safe_load(full_path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("配置文件格式错误: 顶层必须是字典")
    return MetricConfig(raw=data)

