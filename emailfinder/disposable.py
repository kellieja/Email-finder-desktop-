"""A compact list of common disposable / throwaway email domains.

Not exhaustive (there are thousands), but it catches the ones that show up most
often. Membership simply lowers a candidate's confidence score.
"""

from __future__ import annotations

DISPOSABLE_DOMAINS = frozenset({
    "10minutemail.com", "20minutemail.com", "33mail.com", "guerrillamail.com",
    "guerrillamail.net", "guerrillamail.org", "sharklasers.com", "grr.la",
    "mailinator.com", "mailinator.net", "mailnesia.com", "maildrop.cc",
    "trashmail.com", "trashmail.net", "throwawaymail.com", "getnada.com",
    "nada.email", "tempmail.com", "temp-mail.org", "tempmailo.com",
    "tempr.email", "dispostable.com", "fakeinbox.com", "yopmail.com",
    "yopmail.net", "mintemail.com", "mohmal.com", "spamgourmet.com",
    "emailondeck.com", "spam4.me", "mailcatch.com", "moakt.com",
    "mailtemp.net", "tmail.ws", "burnermail.io", "harakirimail.com",
    "discard.email", "fakemailgenerator.com", "maileater.com", "inboxbear.com",
    "tempinbox.com", "wegwerfmail.de", "einrot.com", "luxusmail.org",
    "anonbox.net", "byom.de", "owlymail.com", "1secmail.com",
})


def is_disposable(domain: str) -> bool:
    return domain.lower().lstrip("@") in DISPOSABLE_DOMAINS
