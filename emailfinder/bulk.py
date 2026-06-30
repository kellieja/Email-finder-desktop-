"""Bulk lookups from a CSV file.

The input CSV must have a header row. We auto-detect the two columns we need —
a *name* column and a *domain/website* column — primarily by looking at the
actual cell values (a web address is the domain; a person's name is the name),
falling back to header keywords. This is robust to columns being in any order
and to vague or missing headers. Results can be streamed back via a callback
(for a live GUI) and written to an output CSV.
"""

from __future__ import annotations

import csv
import re
from dataclasses import dataclass
from typing import Callable, Iterable, List, Optional, Sequence

from .finder import EmailFinder
from .models import Result

NAME_HINTS = ("name", "full name", "person", "contact", "owner", "attorney",
              "agent", "rep", "first", "last")
DOMAIN_HINTS = ("domain", "company", "website", "url", "site", "web", "homepage")

RESULT_FIELDS = [
    "name", "domain", "best_email", "confidence",
    "pattern", "source", "has_mx", "signals", "error",
]

ProgressFn = Callable[[int, int, Result], None]

# Looks like a web address / domain: has a scheme, www, or a dotted host.
_DOMAINISH = re.compile(r"(https?://|www\.|[a-z0-9][a-z0-9\-]*\.[a-z]{2,})", re.I)


@dataclass
class BulkInput:
    name: str
    domain: str


def _looks_like_domain(value: str) -> bool:
    value = value.strip()
    if not value:
        return False
    return bool(_DOMAINISH.search(value))


def _looks_like_name(value: str) -> bool:
    value = value.strip()
    if not value:
        return False
    # Names have no URLs, @, slashes, or digits, and are a few alpha-ish words.
    if re.search(r"[/@:0-9]", value) or "." in value:
        return False
    tokens = value.split()
    if not (1 <= len(tokens) <= 4):
        return False
    return all(re.fullmatch(r"[A-Za-z][A-Za-z'\-]*", t) for t in tokens)


def _score_columns(samples: Sequence[Sequence[str]], ncols: int):
    """Fraction of sampled values in each column that look name-ish / domain-ish."""
    name_score = [0.0] * ncols
    dom_score = [0.0] * ncols
    counts = [0] * ncols
    for row in samples:
        for i in range(ncols):
            val = row[i].strip() if i < len(row) else ""
            if not val:
                continue
            counts[i] += 1
            if _looks_like_domain(val):
                dom_score[i] += 1
            if _looks_like_name(val):
                name_score[i] += 1
    for i in range(ncols):
        if counts[i]:
            name_score[i] /= counts[i]
            dom_score[i] /= counts[i]
    return name_score, dom_score


def detect_columns(header: List[str],
                   samples: Optional[Sequence[Sequence[str]]] = None) -> tuple[int, int]:
    """Return (name_index, domain_index) for a CSV.

    Content wins over headers: if the sampled values clearly show which column
    holds web addresses and which holds people, we trust that. Header keywords
    act as a tie-breaker/booster and as the fallback when there's no data.
    """
    ncols = len(header)
    if ncols == 0:
        return 0, 0
    if ncols == 1:
        return 0, 0

    lower = [h.strip().lower() for h in header]

    def header_hit(hints) -> set[int]:
        return {i for i, col in enumerate(lower) if any(h in col for h in hints)}

    name_hdr = header_hit(NAME_HINTS)
    dom_hdr = header_hit(DOMAIN_HINTS)

    name_score = [0.0] * ncols
    dom_score = [0.0] * ncols
    if samples:
        name_score, dom_score = _score_columns(samples, ncols)

    # Combine content score with a header bonus.
    name_total = [name_score[i] + (0.4 if i in name_hdr else 0.0) for i in range(ncols)]
    dom_total = [dom_score[i] + (0.4 if i in dom_hdr else 0.0) for i in range(ncols)]

    # Pick the domain column first (it's the more distinctive signal).
    domain_idx = max(range(ncols), key=lambda i: (dom_total[i], -i))
    # Name column = best name score among the rest.
    name_candidates = [i for i in range(ncols) if i != domain_idx]
    name_idx = max(name_candidates, key=lambda i: (name_total[i], -i))

    # If nothing scored at all, fall back to first/second column order.
    if max(name_total) == 0 and max(dom_total) == 0:
        return 0, 1
    return name_idx, domain_idx


def _read_rows(path: str) -> tuple[List[str], List[List[str]]]:
    with open(path, "r", encoding="utf-8-sig", newline="") as fh:
        sample = fh.read(4096)
        fh.seek(0)
        try:
            dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|")
        except csv.Error:
            dialect = csv.excel
        reader = csv.reader(fh, dialect)
        try:
            header = next(reader)
        except StopIteration:
            return [], []
        data = [r for r in reader if r and any(c.strip() for c in r)]
    return header, data


def read_inputs(path: str) -> List[BulkInput]:
    """Parse a CSV file into a list of (name, domain) rows."""
    header, data = _read_rows(path)
    if not header:
        return []
    name_idx, domain_idx = detect_columns(header, data[:50])
    rows: List[BulkInput] = []
    for raw in data:
        name = raw[name_idx].strip() if name_idx < len(raw) else ""
        domain = raw[domain_idx].strip() if domain_idx < len(raw) else ""
        if name or domain:
            rows.append(BulkInput(name=name, domain=domain))
    return rows


def process(
    inputs: Iterable[BulkInput],
    finder: Optional[EmailFinder] = None,
    *,
    progress: Optional[ProgressFn] = None,
    should_stop: Optional[Callable[[], bool]] = None,
) -> List[Result]:
    """Run the finder over every input row.

    ``progress(done, total, result)`` is called after each row.
    ``should_stop()`` is polled before each row so a GUI can cancel.
    """
    finder = finder or EmailFinder()
    inputs = list(inputs)
    total = len(inputs)
    results: List[Result] = []
    for i, item in enumerate(inputs, start=1):
        if should_stop and should_stop():
            break
        result = finder.find(item.name, item.domain)
        results.append(result)
        if progress:
            progress(i, total, result)
    return results


def write_results(path: str, results: Iterable[Result]) -> None:
    """Write results to a CSV with a stable column order."""
    with open(path, "w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=RESULT_FIELDS)
        writer.writeheader()
        for result in results:
            writer.writerow(result.as_row())
