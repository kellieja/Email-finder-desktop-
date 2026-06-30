"""EmailFinder — discover and verify business email addresses over plain HTTP.

No SMTP, no API keys, no monthly subscriptions. Give it a person's name and a
company domain and it returns the most likely email address with a confidence
score from 0-99.

Public API:
    from emailfinder import EmailFinder, find_email

    finder = EmailFinder()
    result = finder.find("Ada Lovelace", "example.com")
    print(result.best_email, result.best_score)
"""

from .models import Candidate, Result
from .finder import EmailFinder, find_email

__all__ = ["EmailFinder", "find_email", "Candidate", "Result"]
__version__ = "1.0.0"
