"""Calendar/news briefing composition with a single proactive suggestion."""

from dataclasses import dataclass
from typing import Iterable


@dataclass(frozen=True)
class BriefingItem:
    title: str
    detail: str = ""
    priority: str = "normal"


class BriefingComposer:
    """Build a concise, spoken-friendly briefing without mutating calendars."""

    def __init__(self, *, max_items: int = 8) -> None:
        self.max_items = max_items

    def compose(
        self,
        *,
        today: Iterable[BriefingItem] = (),
        upcoming: Iterable[BriefingItem] = (),
        trends: Iterable[BriefingItem] = (),
        proactive_suggestion: str | None = None,
    ) -> str:
        sections: list[str] = ["今日のブリーフィングです。"]
        self._add_section(sections, "今日の重要事項", list(today))
        self._add_section(sections, "直近の注意事項", list(upcoming))
        self._add_section(sections, "トレンド・参考情報", list(trends))
        if proactive_suggestion:
            sections.extend(["今日の一手です。", proactive_suggestion])
        sections.append("以上です。必要な項目から一つずつ進めましょう。")
        return "\n".join(sections)

    def _add_section(self, sections: list[str], heading: str, items: list[BriefingItem]) -> None:
        if not items:
            return
        sections.append(heading + "。")
        for item in items[: self.max_items]:
            prefix = "最優先。" if item.priority == "high" else ""
            text = f"{prefix}{item.title}"
            if item.detail:
                text += "。" + item.detail
            sections.append(text)
