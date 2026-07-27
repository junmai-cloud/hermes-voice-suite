"""Adaptive step-up confirmation for voice-agent side effects.

ContextGuard treats calendar/Notion facts as a usability aid, not as a sole
identity factor. It never executes an action; it only decides whether a
challenge and an explicit action keyword are still required.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class ActionRisk(str, Enum):
    NONE = "none"
    REVERSIBLE = "reversible"
    HIGH = "high"


@dataclass(frozen=True)
class ContextFact:
    """A user-owned fact from a trusted source, never from Web content."""

    question: str
    answer: str
    alternatives: tuple[str, ...] = ()


@dataclass(frozen=True)
class Challenge:
    question: str
    action: str
    keyword: str


@dataclass
class GuardMetrics:
    challenges: int = 0
    passed: int = 0
    rejected: int = 0
    cancelled: int = 0


class ContextGuard:
    """Risk gate with simple, adaptive challenge-response confirmation."""

    def __init__(self, *, cancel_words: tuple[str, ...] = ("止めて", "とめて", "キャンセル", "中止")) -> None:
        self.cancel_words = frozenset(self._normalize(word) for word in cancel_words)
        self.pending: Challenge | None = None
        self._expected: frozenset[str] = frozenset()
        self.metrics = GuardMetrics()

    @staticmethod
    def _normalize(text: str) -> str:
        return "".join(text.split()).lower()

    @staticmethod
    def _normalize_answer(text: str) -> str:
        normalized = ContextGuard._normalize(text).strip("。、.!！?？")
        for suffix in ("です", "だよ", "だね"):
            if normalized.endswith(suffix):
                normalized = normalized[: -len(suffix)]
                break
        return normalized

    def begin(
        self,
        *,
        action: str,
        risk: ActionRisk,
        fact: ContextFact | None = None,
        stt_confidence: float = 1.0,
        anomalous: bool = False,
        keyword: str = "実行して",
    ) -> Challenge | None:
        """Create a challenge when risk, ambiguity, or anomaly warrants it."""
        needs_challenge = risk is ActionRisk.HIGH or stt_confidence < 0.85 or anomalous
        if not needs_challenge:
            self.pending = None
            self._expected = frozenset()
            return None
        if fact is None or not fact.answer.strip():
            # Fail closed: a suspicious action without a trusted fact cannot run.
            self.pending = Challenge("確認できる情報がありません。操作を実行しません。", action, keyword)
            self._expected = frozenset()
        else:
            self.pending = Challenge(fact.question, action, keyword)
            self._expected = frozenset(
                self._normalize_answer(value) for value in (fact.answer, *fact.alternatives) if value.strip()
            )
        self.metrics.challenges += 1
        return self.pending

    def answer(self, text: str) -> bool:
        """Accept only the context answer; never accept a generic 'yes'."""
        if self.pending is None:
            return False
        normalized = self._normalize_answer(text)
        if self._normalize(text) in self.cancel_words:
            self.cancel()
            return False
        if normalized not in self._expected:
            self.metrics.rejected += 1
            self.cancel()
            return False
        self.metrics.passed += 1
        return True

    def authorize_action(self, text: str) -> bool:
        """Require the explicit action keyword after the context challenge."""
        if self.pending is None:
            return False
        if self._normalize(text) != self._normalize(self.pending.keyword):
            return False
        self.pending = None
        self._expected = frozenset()
        return True

    def is_cancel(self, text: str) -> bool:
        return self._normalize(text) in self.cancel_words

    def cancel(self) -> None:
        if self.pending is not None:
            self.metrics.cancelled += 1
        self.pending = None
        self._expected = frozenset()
