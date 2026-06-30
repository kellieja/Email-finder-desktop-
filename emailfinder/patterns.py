"""Generate the common corporate email formats for a name + domain.

The order matters: the most statistically common patterns come first so that,
all else being equal, the better guess wins ties during scoring.
"""

from __future__ import annotations

from typing import List

from .models import Candidate
from .names import Name

# (label, function) — label is reported to the user as the matched pattern.
# Functions return "" when they can't be built (e.g. no last name).
_PATTERNS = [
    ("first.last",   lambda n: f"{n.first}.{n.last}" if n.first and n.last else ""),
    ("first",        lambda n: n.first),
    ("firstlast",    lambda n: f"{n.first}{n.last}" if n.first and n.last else ""),
    ("flast",        lambda n: f"{n.fi}{n.last}" if n.first and n.last else ""),
    ("first.l",      lambda n: f"{n.first}.{n.li}" if n.first and n.last else ""),
    ("first_last",   lambda n: f"{n.first}_{n.last}" if n.first and n.last else ""),
    ("lastfirst",    lambda n: f"{n.last}{n.first}" if n.first and n.last else ""),
    ("last.first",   lambda n: f"{n.last}.{n.first}" if n.first and n.last else ""),
    ("fl",           lambda n: f"{n.fi}{n.li}" if n.first and n.last else ""),
    ("last",         lambda n: n.last),
]


def generate(name: Name, domain: str) -> List[Candidate]:
    """Return de-duplicated pattern candidates, most-likely first."""
    domain = domain.lower().strip().lstrip("@")
    seen: set[str] = set()
    out: List[Candidate] = []
    for label, fn in _PATTERNS:
        local = fn(name)
        if not local:
            continue
        email = f"{local}@{domain}"
        if email in seen:
            continue
        seen.add(email)
        out.append(Candidate(email=email, pattern=label, source="pattern"))
    return out
