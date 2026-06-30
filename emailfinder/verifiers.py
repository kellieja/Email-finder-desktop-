"""Multi-signal verification for a candidate email address.

Each verifier returns a small, self-contained result. They never raise — a
network failure simply means "no signal", which scoring treats as neutral.
"""

from __future__ import annotations

import hashlib
import json
import re
import urllib.parse

from . import http_client
from .disposable import is_disposable

# RFC-5322-ish: good enough to reject garbage without rejecting valid edge cases.
_SYNTAX_RE = re.compile(
    r"^[A-Za-z0-9.!#$%&'*+/=?^_`{|}~\-]+@[A-Za-z0-9](?:[A-Za-z0-9\-]{0,61}"
    r"[A-Za-z0-9])?(?:\.[A-Za-z0-9](?:[A-Za-z0-9\-]{0,61}[A-Za-z0-9])?)+$"
)


def valid_syntax(email: str) -> bool:
    """True if the address is syntactically well-formed."""
    return bool(_SYNTAX_RE.match(email)) and len(email) <= 254


def disposable(email: str) -> bool:
    """True if the address is on a known throwaway/disposable domain."""
    domain = email.split("@", 1)[-1].lower()
    return is_disposable(domain)


def gravatar(email: str, timeout: float = 6.0) -> bool:
    """True if a Gravatar profile image exists for this address.

    A hit is strong evidence the address is real and in active use.
    """
    digest = hashlib.md5(email.strip().lower().encode("utf-8")).hexdigest()
    # d=404 makes Gravatar 404 instead of returning a default image.
    url = f"https://www.gravatar.com/avatar/{digest}?d=404"
    return http_client.status_ok(url, timeout=timeout)


def github(email: str, timeout: float = 6.0) -> bool:
    """True if GitHub's public search associates commits with this address.

    Best-effort and unauthenticated, so it may be rate-limited; a failure is
    treated as "no signal" rather than a negative.
    """
    query = urllib.parse.quote(email)
    url = f"https://api.github.com/search/commits?q=author-email:{query}&per_page=1"
    body = http_client.get(url, timeout=timeout)
    if not body:
        return False
    try:
        data = json.loads(body)
    except (ValueError, TypeError):
        return False
    return isinstance(data, dict) and data.get("total_count", 0) > 0
