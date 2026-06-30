"""Confirm a domain can actually receive mail by looking up its MX records.

Uses dnspython when available and falls back to a no-op (assume mail-capable)
if the library is missing, so the rest of the pipeline still works.
"""

from __future__ import annotations

from typing import List, Tuple

try:
    import dns.resolver  # type: ignore
    import dns.exception  # type: ignore
    _HAVE_DNS = True
except Exception:  # pragma: no cover - exercised only without dnspython
    _HAVE_DNS = False

_CACHE: dict[str, Tuple[bool, List[str]]] = {}


def mx_hosts(domain: str, timeout: float = 5.0) -> Tuple[bool, List[str]]:
    """Return (has_mail, mx_hostnames).

    ``has_mail`` is True when the domain publishes MX records (or, lacking
    those, a usable A record — many small domains receive mail on the A host).
    Results are cached per domain for the life of the process.
    """
    domain = domain.lower().strip()
    if domain in _CACHE:
        return _CACHE[domain]

    if not _HAVE_DNS:
        result = (True, [])  # can't check; don't penalise the candidate
        _CACHE[domain] = result
        return result

    resolver = dns.resolver.Resolver()
    resolver.lifetime = timeout
    resolver.timeout = timeout

    hosts: List[str] = []
    try:
        answers = resolver.resolve(domain, "MX")
        hosts = sorted(
            (str(r.exchange).rstrip(".") for r in answers),
            key=lambda h: h,
        )
        result = (True, hosts)
    except (dns.resolver.NoAnswer, dns.resolver.NXDOMAIN,
            dns.resolver.NoNameservers, dns.exception.DNSException):
        # No MX — fall back to checking for an A record.
        try:
            resolver.resolve(domain, "A")
            result = (True, [])
        except dns.exception.DNSException:
            result = (False, [])

    _CACHE[domain] = result
    return result
