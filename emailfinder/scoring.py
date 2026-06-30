"""Turn the evidence gathered for a candidate into a 0-99 confidence score.

The scale is deliberately capped below 100: without SMTP verification we can
never be certain, and an honest tool shouldn't claim to be.
"""

from __future__ import annotations

from .models import Candidate

# Base scores by how we found the address.
SCRAPED_BASE = 70      # printed on the company's own site
PATTERN_BASE = 30      # a generated guess

# Bonus for the pattern's prior likelihood (index 0 = most common format).
PATTERN_PRIORS = {
    "first.last": 18, "flast": 14, "firstlast": 12, "first": 10,
    "first_last": 8, "first.l": 7, "last.first": 4, "lastfirst": 3,
    "fl": 2, "last": 1,
}

CAP = 99


def score(candidate: Candidate, *, has_mx: bool,
          gravatar_hit: bool, github_hit: bool, disposable: bool) -> int:
    """Compute and store the confidence score on ``candidate``."""
    if candidate.source == "scraped":
        value = SCRAPED_BASE
        candidate.add_signal("found on company website")
    else:
        value = PATTERN_BASE + PATTERN_PRIORS.get(candidate.pattern, 0)
        candidate.add_signal(f"generated pattern '{candidate.pattern}'")

    if has_mx:
        value += 8
        candidate.add_signal("domain accepts mail (MX)")
    else:
        value -= 25
        candidate.add_signal("no MX records for domain")

    if gravatar_hit:
        value += 15
        candidate.add_signal("Gravatar profile exists")

    if github_hit:
        value += 12
        candidate.add_signal("matched a GitHub commit author")

    if disposable:
        value -= 40
        candidate.add_signal("disposable/throwaway domain")

    candidate.score = max(0, min(CAP, value))
    return candidate.score
