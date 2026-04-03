from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass
class KbSnippet:
    source: str
    text: str
    score: int


class SingleDocKnowledgeBase:
    def __init__(self, doc_path: str):
        self._doc_path = Path(doc_path)
        if not self._doc_path.exists():
            raise FileNotFoundError(f"知识库文档不存在: {doc_path}")
        content = self._doc_path.read_text(encoding="utf-8")
        self._paragraphs = [p.strip() for p in content.split("\n\n") if p.strip()]

    def search(self, keywords: list[str], top_k: int = 3) -> list[KbSnippet]:
        if not keywords:
            return []
        lower_keywords = [k.lower() for k in keywords if k.strip()]
        scored: list[KbSnippet] = []
        for idx, para in enumerate(self._paragraphs):
            text_l = para.lower()
            score = sum(1 for k in lower_keywords if k in text_l)
            if score <= 0:
                continue
            scored.append(
                KbSnippet(
                    source=f"{self._doc_path.name}#p{idx + 1}",
                    text=para,
                    score=score,
                )
            )
        scored.sort(key=lambda x: x.score, reverse=True)
        return scored[:top_k]

