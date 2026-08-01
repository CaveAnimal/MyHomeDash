"""
AI News module — fetches top AI stories from multiple RSS feeds.

No API key required. Uses feedparser to parse RSS feeds.
Returns the top N stories from the last 24 hours, deduplicated.
"""

import hashlib
import logging
from datetime import datetime, timezone, timedelta

import feedparser

from config_loader import get_config

log = logging.getLogger(__name__)


def _parse_entry(entry, source_label: str) -> dict | None:
    """Extract and normalise a single feed entry."""
    title = getattr(entry, "title", "").strip()
    link = getattr(entry, "link", "").strip()
    summary = getattr(entry, "summary", "") or getattr(entry, "description", "") or ""

    # Strip HTML tags crudely
    import re
    summary = re.sub(r"<[^>]+>", "", summary).strip()
    # Truncate to ~200 chars at a sentence boundary
    if len(summary) > 220:
        cut = summary[:220].rfind(". ")
        summary = summary[: cut + 1] if cut > 50 else summary[:220] + "…"

    # Parse publish time
    published = None
    if hasattr(entry, "published_parsed") and entry.published_parsed:
        try:
            published = datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)
        except Exception:
            pass
    if published is None:
        published = datetime.now(tz=timezone.utc)

    if not title or not link:
        return None

    return {
        "title": title,
        "link": link,
        "source": source_label,
        "summary": summary or "No summary available.",
        "published": published,
        "published_str": published.strftime("%b %#d, %H:%M UTC"),  # %#d = Windows no-pad day
        # Dedup key: normalised title hash
        "_key": hashlib.md5(title.lower().strip().encode()).hexdigest(),
    }


def fetch() -> dict:
    """
    Return a dict with a list of top AI news stories.
    Each story: { title, link, source, summary, published_str }
    """
    cfg = get_config()
    news_cfg = cfg.get("news", {})
    max_stories = news_cfg.get("max_stories", 7)
    max_age_hours = news_cfg.get("max_age_hours", 24)
    sources = news_cfg.get("sources", [])

    cutoff = datetime.now(tz=timezone.utc) - timedelta(hours=max_age_hours)

    seen_keys: set[str] = set()
    stories: list[dict] = []

    for src in sources:
        label = src.get("label", "Unknown")
        url = src.get("url", "")
        if not url:
            continue
        try:
            feed = feedparser.parse(url)
            for entry in feed.entries:
                item = _parse_entry(entry, label)
                if item is None:
                    continue
                if item["published"] < cutoff:
                    continue
                if item["_key"] in seen_keys:
                    continue
                seen_keys.add(item["_key"])
                stories.append(item)
        except Exception as exc:
            log.warning("Failed to fetch RSS from %s: %s", label, exc)

    # Sort newest first, cap at max_stories
    stories.sort(key=lambda s: s["published"], reverse=True)
    stories = stories[:max_stories]

    # Remove internal dedup key before returning
    for s in stories:
        s.pop("_key", None)
        s.pop("published", None)  # keep published_str only

    return {
        "stories": stories,
        "count": len(stories),
        "max_age_hours": max_age_hours,
    }
