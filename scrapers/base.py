"""
Base scraper interface and common utilities.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


@dataclass
class Contact:
    """Standardized contact / lead record."""
    email: Optional[str] = None
    phone: Optional[str] = None
    name: Optional[str] = None
    title: Optional[str] = None
    company: Optional[str] = None
    website: Optional[str] = None
    source_url: Optional[str] = None
    source_type: str = "website"
    scraped_at: datetime = field(default_factory=datetime.utcnow)
    confidence: str = "medium"  # high / medium / low
    notes: Optional[str] = None
    extra: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "email": self.email,
            "phone": self.phone,
            "name": self.name,
            "title": self.title,
            "company": self.company,
            "website": self.website,
            "source_url": self.source_url,
            "source_type": self.source_type,
            "scraped_at": self.scraped_at.isoformat() if self.scraped_at else None,
            "confidence": self.confidence,
            "notes": self.notes,
            **self.extra,
        }


class BaseScraper(ABC):
    """Abstract base for all scrapers."""

    def __init__(self, delay: float = 1.5, user_agent: Optional[str] = None):
        self.delay = delay
        self.user_agent = user_agent or (
            "Mozilla/5.0 (compatible; LeadScraperBot/1.0; +https://example.com/bot)"
        )
        self.logger = logging.getLogger(self.__class__.__name__)

    @abstractmethod
    def scrape(self, target: str, **kwargs) -> List[Contact]:
        """Scrape a single target (URL, domain, query…). Return list of Contact."""
        pass

    def scrape_many(self, targets: List[str], **kwargs) -> List[Contact]:
        results: List[Contact] = []
        for t in targets:
            try:
                results.extend(self.scrape(t, **kwargs))
            except Exception as e:
                self.logger.error(f"Failed to scrape {t}: {e}")
        return results
