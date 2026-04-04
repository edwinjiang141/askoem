from __future__ import annotations

import json
import os
from typing import Optional

import httpx


class LlmIntentClassifier:
    """
    可选的 LLM 分类器（OpenAI 兼容接口）。
    仅在规则识别不确定时调用，避免把识别主路径交给 LLM。
    """

    def __init__(self, timeout_seconds: int = 15):
        self._endpoint = os.getenv("AI_GATEWAY_LLM_ENDPOINT", "").strip()
        self._api_key = os.getenv("AI_GATEWAY_LLM_API_KEY", "").strip()
        self._model = os.getenv("AI_GATEWAY_LLM_MODEL", "deepseek-chat").strip()
        self._timeout = timeout_seconds

    @property
    def enabled(self) -> bool:
        return bool(self._endpoint and self._api_key)

    def classify_alert(self, question: str) -> Optional[str]:
        """
        返回标签之一:
        - cpu_high
        - io_high
        - hardware_hba_disk
        - generic_alert
        """
        if not self.enabled:
            return None
        prompt = (
            "你是运维告警分类器。"
            "仅返回一个标签，不要解释。"
            "可选标签: cpu_high, io_high, hardware_hba_disk, generic_alert。\n"
            f"问题: {question}"
        )
        payload = {
            "model": self._model,
            "temperature": 0,
            "messages": [
                {"role": "system", "content": "你是严格分类器，只输出标签。"},
                {"role": "user", "content": prompt},
            ],
        }
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        try:
            with httpx.Client(timeout=self._timeout) as client:
                resp = client.post(self._endpoint, headers=headers, json=payload)
                resp.raise_for_status()
                data = resp.json()
        except Exception:
            return None

        content = (
            data.get("choices", [{}])[0]
            .get("message", {})
            .get("content", "")
            .strip()
            .lower()
        )
        for label in ("cpu_high", "io_high", "hardware_hba_disk", "generic_alert"):
            if label in content:
                return label
        # 兼容返回 JSON 字符串
        try:
            parsed = json.loads(content)
            if isinstance(parsed, dict):
                label = str(parsed.get("label", "")).strip().lower()
                if label in ("cpu_high", "io_high", "hardware_hba_disk", "generic_alert"):
                    return label
        except Exception:
            pass
        return None
