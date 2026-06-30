"""Offline unit tests — no network required.

Run with:  python -m pytest    (or)    python -m unittest
"""

import csv
import os
import tempfile
import unittest

from emailfinder.bulk import detect_columns, read_inputs, write_results
from emailfinder.disposable import is_disposable
from emailfinder.models import Candidate, Result
from emailfinder.names import parse_name, slugify
from emailfinder.patterns import generate
from emailfinder.scoring import score
from emailfinder.verifiers import disposable, valid_syntax


class TestNames(unittest.TestCase):
    def test_slugify_strips_accents(self):
        self.assertEqual(slugify("José Núñez"), "josenunez")

    def test_two_tokens(self):
        n = parse_name("Ada Lovelace")
        self.assertEqual((n.first, n.last), ("ada", "lovelace"))

    def test_titles_and_suffixes_ignored(self):
        n = parse_name("Dr. Grace Hopper Jr.")
        self.assertEqual((n.first, n.last), ("grace", "hopper"))

    def test_middle_name(self):
        n = parse_name("John Fitzgerald Kennedy")
        self.assertEqual((n.first, n.middle, n.last), ("john", "fitzgerald", "kennedy"))

    def test_single_token(self):
        n = parse_name("Cher")
        self.assertEqual((n.first, n.last), ("cher", ""))
        self.assertTrue(n.is_valid)


class TestPatterns(unittest.TestCase):
    def test_generates_common_formats(self):
        cands = generate(parse_name("Ada Lovelace"), "example.com")
        emails = {c.email for c in cands}
        self.assertIn("ada.lovelace@example.com", emails)
        self.assertIn("alovelace@example.com", emails)
        self.assertIn("ada@example.com", emails)

    def test_first_last_is_top_priority(self):
        cands = generate(parse_name("Ada Lovelace"), "example.com")
        self.assertEqual(cands[0].pattern, "first.last")

    def test_no_duplicates(self):
        cands = generate(parse_name("Ada Lovelace"), "example.com")
        self.assertEqual(len(cands), len({c.email for c in cands}))

    def test_strips_at_and_scheme(self):
        cands = generate(parse_name("Ada Lovelace"), "@EXAMPLE.com")
        self.assertTrue(all(c.email.endswith("@example.com") for c in cands))


class TestVerifiers(unittest.TestCase):
    def test_valid_syntax(self):
        self.assertTrue(valid_syntax("ada.lovelace@example.com"))
        self.assertFalse(valid_syntax("not-an-email"))
        self.assertFalse(valid_syntax("a@@b.com"))

    def test_disposable_detection(self):
        self.assertTrue(is_disposable("mailinator.com"))
        self.assertTrue(disposable("foo@guerrillamail.com"))
        self.assertFalse(disposable("foo@example.com"))


class TestScoring(unittest.TestCase):
    def test_scraped_beats_pattern(self):
        scraped = Candidate("a@x.com", source="scraped", pattern="scraped")
        guess = Candidate("a@x.com", source="pattern", pattern="first")
        s1 = score(scraped, has_mx=True, gravatar_hit=False, github_hit=False, disposable=False)
        s2 = score(guess, has_mx=True, gravatar_hit=False, github_hit=False, disposable=False)
        self.assertGreater(s1, s2)

    def test_capped_at_99(self):
        c = Candidate("a@x.com", source="scraped", pattern="scraped")
        s = score(c, has_mx=True, gravatar_hit=True, github_hit=True, disposable=False)
        self.assertLessEqual(s, 99)

    def test_disposable_penalised(self):
        c = Candidate("a@x.com", source="pattern", pattern="first.last")
        s = score(c, has_mx=True, gravatar_hit=False, github_hit=False, disposable=True)
        self.assertLess(s, 25)

    def test_no_mx_penalised(self):
        c = Candidate("a@x.com", source="pattern", pattern="first.last")
        s = score(c, has_mx=False, gravatar_hit=False, github_hit=False, disposable=False)
        self.assertLess(s, 30)


class TestResult(unittest.TestCase):
    def test_sort_and_best(self):
        r = Result(name="Ada", domain="x.com")
        r.candidates = [
            Candidate("low@x.com", score=20),
            Candidate("high@x.com", score=80),
        ]
        r.sort()
        self.assertEqual(r.best_email, "high@x.com")
        self.assertEqual(r.best_score, 80)


class TestBulk(unittest.TestCase):
    def test_detect_columns_by_header(self):
        self.assertEqual(detect_columns(["Full Name", "Company Domain"]), (0, 1))
        self.assertEqual(detect_columns(["domain", "name"]), (1, 0))

    def test_detect_columns_fallback(self):
        self.assertEqual(detect_columns(["col1", "col2"]), (0, 1))

    def test_detect_columns_by_content_when_swapped(self):
        # Website in column 0, person in column 1, unhelpful headers.
        header = ["col_a", "col_b"]
        samples = [
            ["https://www.dolmanlaw.com", "matthew dolman"],
            ["https://texaslegalgroup.com", "alexander begum"],
            ["https://waynewright.com", "wayne wright"],
        ]
        name_idx, domain_idx = detect_columns(header, samples)
        self.assertEqual(domain_idx, 0)   # the website column
        self.assertEqual(name_idx, 1)     # the person column

    def test_detect_columns_content_overrides_order(self):
        header = ["website", "owner"]
        samples = [["acme.com", "john smith"], ["beta.org", "jane doe"]]
        name_idx, domain_idx = detect_columns(header, samples)
        self.assertEqual((name_idx, domain_idx), (1, 0))

    def test_read_and_write_roundtrip(self):
        tmpdir = tempfile.mkdtemp()
        in_path = os.path.join(tmpdir, "in.csv")
        with open(in_path, "w", newline="", encoding="utf-8") as fh:
            w = csv.writer(fh)
            w.writerow(["name", "domain"])
            w.writerow(["Ada Lovelace", "example.com"])
            w.writerow(["Grace Hopper", "navy.mil"])
        inputs = read_inputs(in_path)
        self.assertEqual(len(inputs), 2)
        self.assertEqual(inputs[0].name, "Ada Lovelace")
        self.assertEqual(inputs[1].domain, "navy.mil")

        out_path = os.path.join(tmpdir, "out.csv")
        r = Result(name="Ada", domain="example.com")
        r.candidates = [Candidate("ada@example.com", score=55, pattern="first")]
        write_results(out_path, [r])
        with open(out_path, encoding="utf-8") as fh:
            rows = list(csv.DictReader(fh))
        self.assertEqual(rows[0]["best_email"], "ada@example.com")
        self.assertEqual(rows[0]["confidence"], "55")


if __name__ == "__main__":
    unittest.main()
