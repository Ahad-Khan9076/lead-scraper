"""
Public website contact scraper.
Extracts emails, phones, and basic company info from publicly accessible pages.
Respects robots.txt and uses polite rate limiting.
"""
import re
import time
from typing import List, Optional, Set
from urllib.parse import urljoin, urlparse
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests
from bs4 import BeautifulSoup
from fake_useragent import UserAgent
from tenacity import retry, stop_after_attempt, wait_exponential

from .base import BaseScraper, Contact
from .robots import is_allowed

# Common contact-page patterns
CONTACT_PATHS = [
    "/contact", "/contact-us", "/contactus", "/get-in-touch",
    "/about", "/about-us", "/team", "/our-team", "/people",
    "/support", "/help", "/company", "/connect"
]

EMAIL_REGEX = re.compile(
    r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}",
    re.IGNORECASE
)

# Basic phone patterns (international + common local)
PHONE_REGEX = re.compile(
    r"(?:\+?\d{1,3}[\s\-\.]?)?(?:\(?\d{2,4}\)?[\s\-\.]?)?\d{3,4}[\s\-\.]?\d{3,4}"
)

# Filter out obvious non-contact / junk emails
JUNK_EMAIL_PATTERNS = [
    r".*@example\.", r".*@domain\.", r".*@email\.", r".*@sentry\.",
    r".*@wixpress\.", r".*@cloudflare\.", r"noreply@", r"no-reply@",
    r"donotreply@", r"mailer-daemon@", r".*\.png$", r".*\.jpg$",
    r".*\.gif$", r".*\.css$", r".*\.js$", r"webpack@", r"@2x\.",
]


class WebsiteContactScraper(BaseScraper):
    def __init__(
        self,
        delay: float = 1.5,
        max_pages_per_domain: int = 8,
        timeout: int = 15,
        respect_robots: bool = True,
        user_agent: Optional[str] = None,
    ):
        super().__init__(delay=delay, user_agent=user_agent)
        self.max_pages = max_pages_per_domain
        self.timeout = timeout
        self.respect_robots = respect_robots
        try:
            self.ua = UserAgent()
        except Exception:
            self.ua = None

    def _headers(self) -> dict:
        ua = self.user_agent
        if self.ua:
            try:
                ua = self.ua.random
            except Exception:
                pass
        return {
            "User-Agent": ua,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5",
            "Connection": "keep-alive",
        }

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=8))
    def _fetch(self, url: str) -> Optional[str]:
        if self.respect_robots and not is_allowed(url, self.user_agent):
            self.logger.warning(f"Blocked by robots.txt: {url}")
            return None
        resp = requests.get(url, headers=self._headers(), timeout=self.timeout, allow_redirects=True)
        resp.raise_for_status()
        # Only parse HTML
        ctype = resp.headers.get("Content-Type", "")
        if "text/html" not in ctype and "application/xhtml" not in ctype:
            return None
        return resp.text

    def _extract_emails(self, text: str, soup: BeautifulSoup) -> Set[str]:
        emails = set()
        # From mailto links
        for a in soup.select('a[href^="mailto:"]'):
            href = a.get("href", "")
            email = href.replace("mailto:", "").split("?")[0].strip()
            if email:
                emails.add(email.lower())
        # From raw text / scripts
        for match in EMAIL_REGEX.findall(text):
            emails.add(match.lower())
        # Filter junk
        clean = set()
        for e in emails:
            if any(re.match(p, e, re.I) for p in JUNK_EMAIL_PATTERNS):
                continue
            if len(e) > 80 or e.count("@") != 1:
                continue
            clean.add(e)
        return clean

    def _extract_phones(self, text: str, soup: BeautifulSoup) -> Set[str]:
        phones = set()
        # Prefer explicit tel: links – highest confidence
        for a in soup.select('a[href^="tel:"]'):
            href = a.get("href", "")
            phone = href.replace("tel:", "").strip()
            if phone:
                phones.add(phone)
        # From text – require a leading + or parentheses or a common separator pattern
        # and a reasonable length after stripping non-digits
        for match in PHONE_REGEX.findall(text):
            raw = match.strip()
            cleaned = re.sub(r"[^\d+]", "", raw)
            # Skip year ranges, pure numbers that look like years, Fibonacci, etc.
            if not (8 <= len(cleaned.replace("+", "")) <= 15):
                continue
            if re.match(r"^\d{4}-\d{4}$", raw):  # 2001-2026
                continue
            if re.match(r"^\d+ \d+$", raw) and len(cleaned) < 10:
                continue
            if raw.count(" ") > 3:  # too fragmented
                continue
            phones.add(raw)
        return phones

    def _guess_company(self, url: str, soup: BeautifulSoup) -> str:
        # Try <title>, og:site_name, or domain
        title = soup.title.string.strip() if soup.title and soup.title.string else ""
        og = soup.find("meta", property="og:site_name")
        if og and og.get("content"):
            return og["content"].strip()
        if title:
            # Remove common suffixes
            for suffix in [" | Home", " - Home", " | Contact", " - Contact Us"]:
                title = title.replace(suffix, "")
            return title[:80]
        domain = urlparse(url).netloc.replace("www.", "")
        return domain

    def _candidate_urls(self, base_url: str) -> List[str]:
        parsed = urlparse(base_url)
        root = f"{parsed.scheme}://{parsed.netloc}"
        urls = [root]
        for path in CONTACT_PATHS:
            urls.append(urljoin(root, path))
        # Also try the original path if different
        if parsed.path and parsed.path != "/":
            urls.append(base_url)
        return list(dict.fromkeys(urls))  # dedupe preserving order

    def scrape(self, target: str, **kwargs) -> List[Contact]:
        """
        target: full URL or bare domain (e.g. example.com or https://example.com)
        """
        if not target.startswith("http"):
            target = "https://" + target.lstrip("/")

        self.logger.info(f"Scraping {target}")
        contacts: List[Contact] = []
        seen_emails: Set[str] = set()
        seen_phones: Set[str] = set()

        candidates = self._candidate_urls(target)[: self.max_pages]
        company = None
        website = urlparse(target).netloc

        for url in candidates:
            try:
                html = self._fetch(url)
                if not html:
                    continue
                soup = BeautifulSoup(html, "lxml")
                text = soup.get_text(separator=" ", strip=True)

                if not company:
                    company = self._guess_company(url, soup)

                emails = self._extract_emails(html + " " + text, soup)
                phones = self._extract_phones(text, soup)

                for email in emails:
                    if email in seen_emails:
                        continue
                    seen_emails.add(email)
                    conf = "high" if "contact" in url.lower() or "about" in url.lower() else "medium"
                    contacts.append(
                        Contact(
                            email=email,
                            company=company,
                            website=website,
                            source_url=url,
                            source_type="website",
                            confidence=conf,
                            notes=f"Found on {url}",
                        )
                    )

                for phone in phones:
                    if phone in seen_phones:
                        continue
                    seen_phones.add(phone)
                    # Prefer attaching phone to an existing contact if possible,
                    # otherwise create a phone-only record
                    if contacts and not contacts[-1].phone:
                        contacts[-1].phone = phone
                    else:
                        contacts.append(
                            Contact(
                                phone=phone,
                                company=company,
                                website=website,
                                source_url=url,
                                source_type="website",
                                confidence="medium",
                                notes=f"Phone found on {url}",
                            )
                        )

                time.sleep(self.delay)
            except Exception as e:
                self.logger.debug(f"Error on {url}: {e}")
                continue

        self.logger.info(f"Found {len(contacts)} contacts from {target}")
        return contacts

    def scrape_many(self, targets: List[str], max_workers: int = 3, **kwargs) -> List[Contact]:
        """Parallel but still polite (limited workers + per-request delay)."""
        all_contacts: List[Contact] = []
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {executor.submit(self.scrape, t, **kwargs): t for t in targets}
            for future in as_completed(futures):
                try:
                    all_contacts.extend(future.result())
                except Exception as e:
                    self.logger.error(f"Worker failed for {futures[future]}: {e}")
        return all_contacts
