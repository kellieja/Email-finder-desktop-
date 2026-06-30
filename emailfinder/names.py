"""Normalise a person's name into the parts the pattern generator needs."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

# Tokens that are titles/suffixes, not name parts.
_NOISE = {
    "mr", "mrs", "ms", "miss", "dr", "prof", "sir", "madam",
    "jr", "sr", "ii", "iii", "iv", "phd", "md", "mba", "esq",
}


def slugify(text: str) -> str:
    """Lowercase ASCII, letters only. 'José Núñez' -> 'josenunez'."""
    norm = unicodedata.normalize("NFKD", text)
    ascii_text = norm.encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z]", "", ascii_text.lower())


@dataclass
class Name:
    first: str
    last: str
    middle: str = ""

    @property
    def fi(self) -> str:
        return self.first[:1]

    @property
    def li(self) -> str:
        return self.last[:1]

    @property
    def mi(self) -> str:
        return self.middle[:1]

    @property
    def is_valid(self) -> bool:
        return bool(self.first or self.last)


def parse_name(raw: str) -> Name:
    """Split a free-text name into first / middle / last slugs."""
    tokens = [slugify(t) for t in re.split(r"[\s,]+", raw.strip()) if t]
    tokens = [t for t in tokens if t and t not in _NOISE]

    if not tokens:
        return Name(first="", last="")
    if len(tokens) == 1:
        return Name(first=tokens[0], last="")
    if len(tokens) == 2:
        return Name(first=tokens[0], last=tokens[1])
    # 3+ tokens: first, last, everything between is "middle".
    return Name(first=tokens[0], last=tokens[-1], middle="".join(tokens[1:-1]))
