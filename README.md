# Lead Scraper – Public Contact Data Automation

A modular **Python** tool that scrapes **publicly available** business contact information (emails & phone numbers) from websites and presents it in a **Streamlit dashboard**. Designed for internal use by call-centre and email-marketing teams who need a clean, auditable source of leads.

> ⚠️ **Compliance first**  
> This tool only works with public pages, respects `robots.txt` by default, and applies rate limiting.  
> Scraping personal data and using it for cold outreach is heavily regulated (GDPR, CCPA, CAN-SPAM, national do-not-call lists, website Terms of Service).  
> **You** are responsible for having a lawful basis, verifying emails, providing opt-outs, and honouring deletion requests.

---

## Features

| Feature | Description |
|---------|-------------|
| Website contact scraper | Visits common `/contact`, `/about`, `/team` pages and extracts emails + phones |
| robots.txt compliance | Checked automatically (can be disabled only for testing) |
| Rate limiting & polite crawling | Configurable delay + limited concurrency |
| Email & phone cleaning | Basic validation + E.164 phone normalisation |
| SQLite storage | Local, zero-config database with upsert / deduplication |
| Streamlit dashboard | Overview metrics, scrape UI, filterable table, status updates, export |
| CLI | `scrape`, `list`, `export`, `dashboard` commands |
| CSV / Excel export | Ready for CRM / dialer import |

---

## Quick Start

```bash
# 1. Clone / copy the project and enter it
cd lead_scraper

# 2. Create virtual environment (recommended)
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Initialise DB (happens automatically on first run)
python -c "from database.models import init_db; init_db()"

# 5. Scrape a few public sites
python main.py scrape example.com python.org --delay 2

# 6. Launch the dashboard
python main.py dashboard
# or
streamlit run dashboard/app.py
```

Open the browser at the URL Streamlit prints (usually http://localhost:8501).

---

## CLI Reference

```bash
# Scrape one or more domains / URLs
python main.py scrape company1.com https://company2.com/about

# Scrape from a file (one URL per line)
python main.py scrape --file urls.txt --delay 1.5 --max-pages 6 --workers 2

# List stored leads
python main.py list --limit 100
python main.py list --status new

# Export
python main.py export --format csv
python main.py export --format xlsx --status qualified

# Open dashboard
python main.py dashboard
```

---

## Project Layout

```
lead_scraper/
├── scrapers/
│   ├── base.py              # Contact dataclass + abstract scraper
│   ├── robots.py            # robots.txt helper
│   └── website_scraper.py   # Main public-site extractor
├── database/
│   └── models.py            # SQLAlchemy models + CRUD
├── dashboard/
│   └── app.py               # Streamlit UI
├── utils/
│   ├── validators.py        # Email / phone helpers
│   └── exporters.py         # CSV / Excel
├── data/                    # SQLite DB + export files (git-ignored)
├── main.py                  # CLI entry point
├── requirements.txt
└── README.md
```

---

## Adding New Sources

The architecture is intentionally modular. To add another source (e.g. a public directory, RSS feed, or API):

1. Create a new class inheriting from `BaseScraper` in `scrapers/`.
2. Implement the `scrape(target)` method that returns a list of `Contact` objects.
3. Call it from the CLI or the dashboard form the same way as `WebsiteContactScraper`.

Keep the same rules: public data only, rate-limit, log the source URL, minimise personal fields.

---

## Recommended Production Hardening

- Add an external email verification step before any send.
- Maintain a suppression / do-not-contact list and check it on every upsert.
- Schedule recurring scrapes with cron or APScheduler.
- Move the SQLite file to a secure location or switch to PostgreSQL.
- Add authentication to the Streamlit dashboard if it will be exposed.
- Log every scrape job (who ran it, which targets, how many records) for audit purposes.

---

## Disclaimer

This software is provided **as-is for educational and internal research purposes**.  
The authors accept no liability for misuse, legal violations, or damage caused by the tool.  
Always consult your legal / compliance team before using scraped data for outreach.

---

Happy (and responsible) prospecting!
