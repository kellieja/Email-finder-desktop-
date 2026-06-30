# EmailFinder Desktop

Find and verify business email addresses from a simple desktop app — **no SMTP,
no API keys, no subscriptions**. Type a name and a company domain, or upload a
CSV to process a whole list at once.

> Built on the EmailFinder approach: a waterfall of DNS validation, website
> scraping, pattern generation, and multi-signal verification that returns the
> most likely address with a confidence score from 0–99%.

---

## ⬇️ Download & run (no install, no Python)

You don't need to install anything — GitHub builds a ready-to-run app for you:

1. Go to the **[Actions tab](../../actions)** and click the most recent
   **"Build double-click app"** run (green check ✓).
2. Scroll to **Artifacts** at the bottom and download the one for your computer:
   **EmailFinder-Windows**, **EmailFinder-macOS**, or **EmailFinder-Linux**.
3. Unzip it and **double-click** the app:
   - **Windows** → `EmailFinder.exe`
   - **macOS** → `EmailFinder.app` (first time: right-click → **Open** to get past
     the "unidentified developer" warning)
   - **Linux** → `EmailFinder` (you may need: `chmod +x EmailFinder`, then run it)

That's the whole thing — no setup, no commands. (The steps below are only if you'd
rather run it from source.)

---

## ✨ Features

- **Clean, modern desktop GUI** — rounded controls, an accent-coloured theme, and
  confidence badges; nothing to configure, runs on Windows, macOS, Linux.
- **Single lookup** — name + domain → best email, confidence, and all candidates.
- **📤 Bulk CSV upload** — load a list, watch live progress, **export results** to CSV.
- **Confidence scoring** — every guess is scored and labelled High / Medium / Low.
- **Multi-signal verification** — MX records, on-site scraping, Gravatar, GitHub,
  and disposable-domain detection.
- **Also a CLI** — script it: `emailfinder "Ada Lovelace" example.com`.
- **Tiny footprint** — pure Python standard library + one optional dependency.

---

## 🚀 Quick start

```bash
# 1. Get the code
git clone https://github.com/kellieja/email-finder-desktop-.git
cd email-finder-desktop-

# 2. (Recommended) install the one optional dependency for MX checks
pip install -r requirements.txt

# 3. Launch the app
python run.py
```

That's it — the window opens with two tabs: **Single lookup** and **Bulk upload**.

> **No Tkinter?** It ships with most Python installs. If `run.py` says it's
> missing: `sudo apt-get install python3-tk` (Debian/Ubuntu),
> `brew install python-tk` (macOS), or re-run the Windows installer with the
> *tcl/tk* option ticked.

---

## 📤 Bulk upload

1. Open the **Bulk upload** tab and click **Load CSV…**.
2. Your CSV just needs a header row with a **name** column and a
   **domain / company / website** column — they're auto-detected. Otherwise the
   first column is treated as the name and the second as the domain.
3. Click **Run**. Progress streams in live; **Stop** cancels at any time.
4. Click **Export results…** to save a CSV with the best email, confidence,
   matched pattern, and the evidence behind each result.

A ready-to-try file lives at [`examples/sample.csv`](examples/sample.csv):

```csv
name,company domain
Ada Lovelace,example.com
Grace Hopper,navy.mil
```

---

## 🖥️ Command-line usage

The same engine is available without the GUI:

```bash
# Single lookup
emailfinder "Ada Lovelace" example.com

# Bulk, writing results to a file
emailfinder --bulk examples/sample.csv --out results.csv

# Faster run (skip Gravatar/GitHub and site scraping)
emailfinder --bulk contacts.csv --out results.csv --no-verify --no-scrape
```

(If you didn't `pip install` the package, run `python -m emailfinder.cli ...`.)

---

## 🧠 How it works

The lookup runs as a waterfall and scores each candidate on the evidence found:

1. **DNS validation** — does the domain publish MX records (can it receive mail)?
2. **Website scraping** — pull addresses printed on the company's own pages
   (contact, about, team…). These are the strongest signal.
3. **Pattern generation** — build the common corporate formats
   (`first.last@`, `flast@`, `first@`, …) ordered by real-world frequency.
4. **Multi-signal verification** — check syntax, a Gravatar profile, GitHub
   commit authorship, and known disposable domains.
5. **Confidence scoring** — combine all signals into a 0–99% score.

Scores are deliberately capped below 100: without SMTP verification nothing is
ever 100% certain, and the tool won't pretend otherwise.

---

## 🧩 Use as a library

```python
from emailfinder import EmailFinder

finder = EmailFinder(deep_verify=True, scrape_site=True)
result = finder.find("Ada Lovelace", "example.com")

print(result.best_email, result.best_score)
for c in result.candidates:
    print(c.score, c.email, c.signals)
```

---

## 🧪 Tests

Offline unit tests (no network needed):

```bash
python -m pytest          # or: python -m unittest
```

---

## ⚠️ Notes & limitations

- No SMTP verification, so an address can never be confirmed as 100% deliverable.
- Gravatar/GitHub signals only help for people who use those services.
- Use responsibly and in line with applicable privacy laws and each site's terms.

## License

[MIT](LICENSE)
