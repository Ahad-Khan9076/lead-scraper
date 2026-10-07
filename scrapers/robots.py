"""
Robots.txt compliance helper.
Always check before scraping any domain.
"""
from urllib.robotparser import RobotFileParser
from urllib.parse import urljoin, urlparse
import logging

logger = logging.getLogger(__name__)

# Simple in-memory cache so we don't re-fetch robots.txt for every URL
_robots_cache: dict[str, RobotFileParser] = {}


def get_robot_parser(base_url: str, user_agent: str = "*") -> RobotFileParser:
    parsed = urlparse(base_url)
    robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"

    if robots_url not in _robots_cache:
        rp = RobotFileParser()
        rp.set_url(robots_url)
        try:
            rp.read()
            logger.info(f"Loaded robots.txt from {robots_url}")
        except Exception as e:
            logger.warning(f"Could not fetch robots.txt for {base_url}: {e}. Assuming allowed.")
            # Fail open for public data, but log it
            rp = RobotFileParser()
            rp.parse([])  # empty = allow all
        _robots_cache[robots_url] = rp

    return _robots_cache[robots_url]


def is_allowed(url: str, user_agent: str = "*") -> bool:
    """Return True if the given URL is allowed by robots.txt."""
    try:
        rp = get_robot_parser(url, user_agent)
        return rp.can_fetch(user_agent, url)
    except Exception as e:
        logger.warning(f"robots.txt check failed for {url}: {e}")
        return True  # fail open, but we still rate-limit
