"""Bulk lookups from a CSV file.

The input CSV must have a header row. We auto-detect the two columns we need:

    * a name column   (header contains "name")
    * a domain column  (header contains "domain", "company", "website" or "url")

If headers don't match, the first column is treated as the name and the second
as the domain. Results can be streamed back via a callback (for a live GUI) and
written to an output CSV.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from typing import Callable, Iterable, List, Optional

from .finder import EmailFinder
from .models import Result

NAME_HINTS = ("name", "full name", "person", "contact")
DOMAIN_HINTS = ("domain", "company", "website", "url", "site", "email domain")

RESULT_FIELDS = [
    "name", "domain", "best_email", "confidence",
    "pattern", "source", "has_mx", "signals", "error",
]

ProgressFn = Callable[[int, int, Result], None]


@dataclass
class BulkInput:
    name: str
    domain: str


def detect_columns(header: List[str]) -> tuple[int, int]:
    """Return (name_index, domain_index) for a CSV header row."""
    lower = [h.strip().lower() for h in header]

    def find(hints) -> Optional[int]:
        for i, col in enumerate(lower):
            if any(h in col for h in hints):
                return i
        return None

    name_idx = find(NAME_HINTS)
    domain_idx = find(DOMAIN_HINTS)

    if name_idx is None:
        name_idx = 0
    if domain_idx is None:
        domain_idx = 1 if len(header) > 1 else 0
    if domain_idx == name_idx and len(header) > 1:
        domain_idx = 1 - name_idx if name_idx < 2 else 1
    return name_idx, domain_idx


def read_inputs(path: str) -> List[BulkInput]:
    """Parse a CSV file into a list of (name, domain) rows."""
    rows: List[BulkInput] = []
    with open(path, "r", encoding="utf-8-sig", newline="") as fh:
        # Sniff the delimiter; fall back to comma.
        sample = fh.read(4096)
        fh.seek(0)
        try:
            dialect = csv.Sniffer().sniff(sample, delimiters=",;\t")
        except csv.Error:
            dialect = csv.excel
        reader = csv.reader(fh, dialect)
        try:
            header = next(reader)
        except StopIteration:
            return rows
        name_idx, domain_idx = detect_columns(header)
        for raw in reader:
            if not raw or all(not c.strip() for c in raw):
                continue
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
