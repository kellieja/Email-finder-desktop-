"""Command-line interface — handy for scripting and bulk jobs without the GUI.

    emailfinder "Ada Lovelace" example.com
    emailfinder --bulk contacts.csv --out results.csv
"""

from __future__ import annotations

import argparse
import sys

from . import __version__
from .bulk import process, read_inputs, write_results
from .finder import EmailFinder


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="emailfinder",
        description="Find & verify business email addresses (no SMTP, no API keys).",
    )
    p.add_argument("name", nargs="?", help="Person's full name (single lookup)")
    p.add_argument("domain", nargs="?", help="Company domain (single lookup)")
    p.add_argument("--bulk", metavar="CSV", help="CSV of name,domain rows")
    p.add_argument("--out", metavar="CSV", help="Write bulk results to this CSV")
    p.add_argument("--no-verify", action="store_true",
                   help="Skip Gravatar/GitHub checks (faster)")
    p.add_argument("--no-scrape", action="store_true",
                   help="Skip website scraping")
    p.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    finder = EmailFinder(
        deep_verify=not args.no_verify,
        scrape_site=not args.no_scrape,
    )

    if args.bulk:
        inputs = read_inputs(args.bulk)
        if not inputs:
            print("No usable rows in CSV.", file=sys.stderr)
            return 1

        def progress(done, total, result):
            print(f"[{done}/{total}] {result.name} @ {result.domain} "
                  f"-> {result.best_email or '(none)'} ({result.best_score}%)")

        results = process(inputs, finder, progress=progress)
        if args.out:
            write_results(args.out, results)
            print(f"\nWrote {len(results)} rows to {args.out}")
        return 0

    if args.name and args.domain:
        result = finder.find(args.name, args.domain)
        if result.error:
            print(f"Error: {result.error}", file=sys.stderr)
            return 1
        print(f"\nBest guess: {result.best_email}  ({result.best_score}% confidence)")
        print(f"Domain accepts mail: {'yes' if result.has_mx else 'no'}\n")
        print("All candidates:")
        for c in result.candidates:
            print(f"  {c.score:>3}%  {c.email:<40} [{c.source}] {'; '.join(c.signals)}")
        return 0

    build_parser().print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
