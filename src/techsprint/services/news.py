from __future__ import annotations

from dataclasses import dataclass
from typing import List

import feedparser

from techsprint.utils.logging import get_logger

log = get_logger(__name__)


@dataclass(frozen=True)
class NewsItem:
    title: str
    link: str


@dataclass(frozen=True)
class NewsBundle:
    items: List[NewsItem]

    def as_headlines(self) -> str:
        return "\n".join([f"- {i.title}" for i in self.items])


class NewsService:
    def fetch(self, rss_url: str, max_items: int) -> NewsBundle:
        log.info("Fetching RSS: %s", rss_url)
        feed = feedparser.parse(rss_url)
        entries = getattr(feed, "entries", [])[: max_items or 0]
        items = []
        for e in entries:
            title = getattr(e, "title", "").strip()
            link = getattr(e, "link", "").strip()
            if title:
                items.append(NewsItem(title=title, link=link))
        return NewsBundle(items=items)
