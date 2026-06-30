"""A tiny, dependency-free HTTP getter built on urllib.

Honours the standard HTTPS_PROXY / HTTP_PROXY environment variables and uses a
browser-like User-Agent so sites don't immediately reject us. Every call is
wrapped so the caller never has to handle network exceptions.
"""

from __future__ import annotations

import gzip
import ssl
import urllib.error
import urllib.request
from typing import Optional

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36 EmailFinder/1.0"
)

DEFAULT_TIMEOUT = 8.0
MAX_BYTES = 1_500_000  # don't slurp huge pages


def get(url: str, timeout: float = DEFAULT_TIMEOUT) -> Optional[str]:
    """Fetch ``url`` and return decoded text, or ``None`` on any failure."""
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/json;q=0.9,*/*;q=0.8",
            "Accept-Encoding": "gzip",
            "Accept-Language": "en-US,en;q=0.9",
        },
    )
    try:
        ctx = ssl.create_default_context()
        with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
            raw = resp.read(MAX_BYTES)
            if resp.headers.get("Content-Encoding") == "gzip":
                try:
                    raw = gzip.decompress(raw)
                except OSError:
                    pass
            charset = resp.headers.get_content_charset() or "utf-8"
            return raw.decode(charset, errors="replace")
    except (urllib.error.URLError, urllib.error.HTTPError, ssl.SSLError,
            ValueError, TimeoutError, OSError):
        return None


def status_ok(url: str, timeout: float = DEFAULT_TIMEOUT) -> bool:
    """Return True if a HEAD/GET to ``url`` yields a 2xx/3xx status."""
    req = urllib.request.Request(url, method="HEAD", headers={"User-Agent": USER_AGENT})
    try:
        ctx = ssl.create_default_context()
        with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
            return 200 <= resp.status < 400
    except urllib.error.HTTPError as exc:
        # Some servers reject HEAD with 405 but the resource exists.
        return exc.code in (403, 405)
    except (urllib.error.URLError, ssl.SSLError, ValueError, TimeoutError, OSError):
        return False
