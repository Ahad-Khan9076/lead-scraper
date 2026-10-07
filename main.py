#!/usr/bin/env python3
"""
Lead Scraper CLI
================
Scrape publicly available contact information from websites
and store results for call-centre / email-marketing teams.

Usage examples:
  python main.py scrape example.com another.com
  python main.py scrape --file urls.txt
  python main.py list
  python main.py export --format csv
  python main.py dashboard
"""
import argparse
import logging
import sys
from pathlib import Path

from scrapers.website_scraper import WebsiteContactScraper
from database.models import init_db, get_session, bulk_upsert, get_all_leads
from utils.validators import clean_email, normalize_phone
from utils.exporters import export_csv, export_excel, default_export_name

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("lead_scraper")


def cmd_scrape(args):
    targets = []
    if args.file:
        path = Path(args.file)
        if not path.exists():
            logger.error(f"File not found: {path}")
            sys.exit(1)
        targets = [line.strip() for line in path.read_text().splitlines() if line.strip() and not line.startswith("#")]
    if args.targets:
        targets.extend(args.targets)

    if not targets:
        logger.error("No targets provided. Use positional URLs or --file")
        sys.exit(1)

    logger.info(f"Starting scrape of {len(targets)} target(s)…")
    scraper = WebsiteContactScraper(
        delay=args.delay,
        max_pages_per_domain=args.max_pages,
        respect_robots=not args.ignore_robots,
    )

    raw_contacts = scraper.scrape_many(targets, max_workers=args.workers)

    # Clean & normalise
    cleaned = []
    for c in raw_contacts:
        d = c.to_dict()
        if d.get("email"):
            d["email"] = clean_email(d["email"])
        if d.get("phone"):
            d["phone"] = normalize_phone(d["phone"])
        # Keep only records that have at least email or phone
        if d.get("email") or d.get("phone"):
            cleaned.append(d)

    logger.info(f"Extracted {len(cleaned)} valid contacts")

    if not cleaned:
        logger.warning("No contacts found.")
        return

    init_db()
    session = get_session()
    try:
        count = bulk_upsert(session, cleaned)
        logger.info(f"Upserted {count} leads into database")
    finally:
        session.close()

    if args.export:
        out_name = default_export_name()
        if args.export == "csv":
            path = export_csv(cleaned, Path("data") / f"{out_name}.csv")
        else:
            path = export_excel(cleaned, Path("data") / f"{out_name}.xlsx")
        logger.info(f"Also exported to {path}")


def cmd_list(args):
    init_db()
    session = get_session()
    try:
        leads = get_all_leads(session, status=args.status)
        if not leads:
            print("No leads found.")
            return
        print(f"{'ID':<5} {'Email':<35} {'Phone':<18} {'Company':<25} {'Status':<12}")
        print("-" * 100)
        for lead in leads[: args.limit]:
            print(
                f"{lead.id:<5} {(lead.email or '-'):<35} {(lead.phone or '-'):<18} "
                f"{(lead.company or '-'):<25} {lead.status:<12}"
            )
        print(f"\nShowing {min(len(leads), args.limit)} of {len(leads)} leads")
    finally:
        session.close()


def cmd_export(args):
    init_db()
    session = get_session()
    try:
        leads = get_all_leads(session, status=args.status)
        data = [l.to_dict() for l in leads]
        if not data:
            logger.warning("Nothing to export")
            return
        name = default_export_name()
        if args.format == "csv":
            path = export_csv(data, Path("data") / f"{name}.csv")
        else:
            path = export_excel(data, Path("data") / f"{name}.xlsx")
        logger.info(f"Exported {len(data)} leads → {path}")
    finally:
        session.close()


def cmd_dashboard(args):
    import subprocess
    dash = Path(__file__).parent / "dashboard" / "app.py"
    logger.info("Launching Streamlit dashboard…")
    subprocess.run(["streamlit", "run", str(dash), "--server.headless", "true"])


def main():
    parser = argparse.ArgumentParser(
        description="Lead Scraper – public contact data for call centres & email teams",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # scrape
    p_scrape = sub.add_parser("scrape", help="Scrape one or more websites / domains")
    p_scrape.add_argument("targets", nargs="*", help="URLs or domains")
    p_scrape.add_argument("--file", "-f", help="Text file with one URL/domain per line")
    p_scrape.add_argument("--delay", type=float, default=1.5, help="Delay between requests (seconds)")
    p_scrape.add_argument("--max-pages", type=int, default=8, help="Max pages to check per domain")
    p_scrape.add_argument("--workers", type=int, default=3, help="Parallel workers (keep low)")
    p_scrape.add_argument("--ignore-robots", action="store_true", help="Do NOT respect robots.txt (not recommended)")
    p_scrape.add_argument("--export", choices=["csv", "xlsx"], help="Also export results immediately")
    p_scrape.set_defaults(func=cmd_scrape)

    # list
    p_list = sub.add_parser("list", help="List stored leads")
    p_list.add_argument("--status", help="Filter by status")
    p_list.add_argument("--limit", type=int, default=50)
    p_list.set_defaults(func=cmd_list)

    # export
    p_export = sub.add_parser("export", help="Export leads to CSV/Excel")
    p_export.add_argument("--format", choices=["csv", "xlsx"], default="csv")
    p_export.add_argument("--status", help="Filter by status")
    p_export.set_defaults(func=cmd_export)

    # dashboard
    p_dash = sub.add_parser("dashboard", help="Launch Streamlit dashboard")
    p_dash.set_defaults(func=cmd_dashboard)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
