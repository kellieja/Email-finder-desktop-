"""The orchestrator that ties the whole waterfall together."""

from __future__ import annotations

from typing import Optional

from . import dns_check, patterns, scraper, scoring, verifiers
from .models import Candidate, Result
from .names import parse_name


class EmailFinder:
    """Find the most likely email for a person at a company domain.

    Parameters
    ----------
    deep_verify:
        When True (default) consult Gravatar and GitHub for extra signal.
        Turn it off for faster, fully-offline-friendly bulk runs.
    scrape_site:
        When True (default) crawl the company site for printed addresses.
    timeout:
        Per-request network timeout in seconds.
    max_candidates:
        Cap how many guesses to keep/verify per lookup.
    """

    def __init__(self, *, deep_verify: bool = True, scrape_site: bool = True,
                 timeout: float = 8.0, max_candidates: int = 8):
        self.deep_verify = deep_verify
        self.scrape_site = scrape_site
        self.timeout = timeout
        self.max_candidates = max_candidates

    def find(self, name: str, domain: str) -> Result:
        domain = _clean_domain(domain)
        result = Result(name=name.strip(), domain=domain)

        parsed = parse_name(name)
        if not domain:
            result.error = "No company domain provided"
            return result
        if not parsed.is_valid:
            result.error = "Could not parse a name"
            return result

        # 1. Does the domain accept mail at all?
        result.has_mx, _hosts = dns_check.mx_hosts(domain, timeout=self.timeout)

        # 2. Anything printed on the site? (highest-signal source)
        scraped: set[str] = set()
        if self.scrape_site:
            scraped = scraper.scrape(domain, timeout=self.timeout)

        # 3. Generated patterns.
        generated = patterns.generate(parsed, domain)

        # Merge, preferring scraped addresses and de-duplicating.
        by_email: dict[str, Candidate] = {}
        for email in scraped:
            by_email[email] = Candidate(email=email, source="scraped", pattern="scraped")
        for cand in generated:
            by_email.setdefault(cand.email, cand)

        candidates = list(by_email.values())[: self.max_candidates]

        # 4. Verify + 5. score each candidate.
        for cand in candidates:
            self._evaluate(cand, result.has_mx)

        result.candidates = candidates
        result.sort()
        return result

    def _evaluate(self, cand: Candidate, has_mx: bool) -> None:
        if not verifiers.valid_syntax(cand.email):
            cand.score = 0
            cand.add_signal("invalid syntax")
            return

        disposable = verifiers.disposable(cand.email)
        gravatar_hit = github_hit = False
        if self.deep_verify and not disposable:
            gravatar_hit = verifiers.gravatar(cand.email, timeout=self.timeout)
            github_hit = verifiers.github(cand.email, timeout=self.timeout)

        scoring.score(
            cand,
            has_mx=has_mx,
            gravatar_hit=gravatar_hit,
            github_hit=github_hit,
            disposable=disposable,
        )


def find_email(name: str, domain: str, **kwargs) -> Result:
    """Convenience one-shot wrapper around :class:`EmailFinder`."""
    return EmailFinder(**kwargs).find(name, domain)


def _clean_domain(domain: str) -> str:
    domain = (domain or "").strip().lower()
    # Accept a full URL or an email and reduce it to a bare domain.
    for prefix in ("https://", "http://"):
        if domain.startswith(prefix):
            domain = domain[len(prefix):]
    domain = domain.split("/", 1)[0]
    if "@" in domain:
        domain = domain.split("@", 1)[-1]
    return domain.removeprefix("www.").strip()
