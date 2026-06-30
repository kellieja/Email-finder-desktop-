"""Data structures shared across the pipeline."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List


@dataclass
class Candidate:
    """A single email-address guess plus the evidence gathered for it."""

    email: str
    pattern: str = ""              # which generator produced it (e.g. "first.last")
    source: str = "pattern"        # "scraped" or "pattern"
    score: int = 0                 # 0-99 confidence
    signals: List[str] = field(default_factory=list)  # human-readable evidence

    def add_signal(self, text: str) -> None:
        if text not in self.signals:
            self.signals.append(text)

    def as_dict(self) -> dict:
        return {
            "email": self.email,
            "pattern": self.pattern,
            "source": self.source,
            "score": self.score,
            "signals": "; ".join(self.signals),
        }


@dataclass
class Result:
    """The outcome of a single lookup."""

    name: str
    domain: str
    candidates: List[Candidate] = field(default_factory=list)
    has_mx: bool = False
    error: str = ""

    @property
    def best(self) -> Candidate | None:
        if not self.candidates:
            return None
        return self.candidates[0]

    @property
    def best_email(self) -> str:
        return self.best.email if self.best else ""

    @property
    def best_score(self) -> int:
        return self.best.score if self.best else 0

    def sort(self) -> None:
        """Order candidates best-first (highest score, scraped before guessed)."""
        self.candidates.sort(
            key=lambda c: (c.score, c.source == "scraped"), reverse=True
        )

    def as_row(self) -> dict:
        """Flat dict suitable for a CSV row."""
        best = self.best
        return {
            "name": self.name,
            "domain": self.domain,
            "best_email": self.best_email,
            "confidence": self.best_score,
            "pattern": best.pattern if best else "",
            "source": best.source if best else "",
            "has_mx": "yes" if self.has_mx else "no",
            "signals": "; ".join(best.signals) if best else "",
            "error": self.error,
        }
