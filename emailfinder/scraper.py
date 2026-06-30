"""Scrape a company's public pages for email addresses on its own domain.

This is the highest-signal step: an address we actually find printed on the
site is far more trustworthy than a generated guess.
"""

from __future__ import annotations

import html
import re
from typing import List, Set

from . import http_client

# Pages most likely to list staff / contact emails.
COMMON_PATHS = [
    "", "/contact", "/contact-us", "/contactus", "/about", "/about-us",
    "/team", "/our-team", "/people", "/staff", "/leadership", "/company",
    "/support", "/help", "/imprint", "/legal",
]

_EMAIL_RE = re.compile(
    r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}", re.IGNORECASE
)

# De-obfuscate common "spam-proofing" before scanning.
_DEOBFUSCATE = [
    (re.compile(r"\s*\[\s*at\s*\]\s*", re.I), "@"),
    (re.compile(r"\s*\(\s*at\s*\)\s*", re.I), "@"),
    (re.compile(r"\s+at\s+", re.I), "@"),
    (re.compile(r"\s*\[\s*dot\s*\]\s*", re.I), "."),
    (re.compile(r"\s*\(\s*dot\s*\)\s*", re.I), "."),
    (re.compile(r"\s+dot\s+", re.I), "."),
]


def _deobfuscate(text: str) -> str:
    text = html.unescape(text)
    for pattern, repl in _DEOBFUSCATE:
        text = pattern.sub(repl, text)
    return text


def _normalise_domain(domain: str) -> str:
    return domain.lower().strip().lstrip("@").removeprefix("www.")


def scrape(domain: str, max_pages: int = 12, timeout: float = 8.0) -> Set[str]:
    """Return the set of on-domain email addresses found across the site."""
    domain = _normalise_domain(domain)
    found: Set[str] = set()
    bases = [f"https://{domain}", f"https://www.{domain}"]

    visited: Set[str] = set()
    fetched = 0
    for base in bases:
        for path in COMMON_PATHS:
            if fetched >= max_pages:
                break
            url = base + path
            if url in visited:
                continue
            visited.add(url)
            page = http_client.get(url, timeout=timeout)
            fetched += 1
            if not page:
                continue
            found.update(_extract(page, domain))
        # If the bare domain already yielded results, don't also crawl www.
        if found:
            break
    return found


def _extract(page: str, domain: str) -> List[str]:
    text = _deobfuscate(page)
    out = []
    for raw in _EMAIL_RE.findall(text):
        email = raw.lower().strip(".")
        # Keep only addresses on the target domain (or a subdomain of it).
        host = email.split("@", 1)[-1]
        if host == domain or host.endswith("." + domain):
            # Skip obvious asset filenames misread as emails.
            if email.endswith((".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg")):
                continue
            out.append(email)
    return out
