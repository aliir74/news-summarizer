"""RSS feed reader using httpx and feedparser."""

import logging
import re
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime

import feedparser
import httpx

from src.config import Config, RSSFeed
from src.models import Message, SourceType

logger = logging.getLogger(__name__)

# Default User-Agent to identify the bot
USER_AGENT = "NewsSummarizer/1.0 (+https://github.com/news-summarizer)"


class RSSReader:
    """Reads news articles from RSS feeds."""

    def __init__(self, config: Config) -> None:
        """Initialize the RSS reader with configuration."""
        self.config = config
        self._client: httpx.AsyncClient | None = None

    async def start(self) -> None:
        """Start the HTTP client."""
        self._client = httpx.AsyncClient(
            timeout=30.0,
            headers={"User-Agent": USER_AGENT},
            follow_redirects=True,
        )
        logger.info("RSS reader client started")

    async def stop(self) -> None:
        """Stop the HTTP client."""
        if self._client:
            await self._client.aclose()
            logger.info("RSS reader client stopped")

    @property
    def client(self) -> httpx.AsyncClient:
        """Get the HTTP client, raising if not started."""
        if self._client is None:
            raise RuntimeError("RSSReader not started. Call start() first.")
        return self._client

    async def get_feed_updates(
        self,
        feed: RSSFeed,
        since: datetime,
        limit: int = 50,
        seen_urls: set[str] | None = None,
    ) -> list[Message]:
        """Fetch recent articles from an RSS feed since the given timestamp.

        Args:
            feed: The RSS feed configuration.
            since: Only include articles newer than this timestamp.
            limit: Maximum number of entries to process from the feed.
            seen_urls: Set of URLs already processed (for deduplication).

        Returns:
            List of new messages from the feed.
        """
        messages: list[Message] = []

        try:
            response = await self.client.get(feed.url)
            response.raise_for_status()

            parsed = feedparser.parse(response.text)

            if parsed.bozo and parsed.bozo_exception:
                logger.warning(f"Feed parsing warning for {feed.name}: {parsed.bozo_exception}")

            for entry in parsed.entries[:limit]:
                # Extract link first for deduplication
                link = str(entry.get("link", ""))

                # Skip if we've already seen this URL
                if seen_urls and link in seen_urls:
                    continue

                # Parse entry timestamp
                entry_time = _parse_entry_time(entry)
                if entry_time is None:
                    # For entries without timestamps, use a time slightly in the past
                    # to avoid them being re-included in every run
                    entry_time = datetime.now(UTC)

                # Skip entries older than since
                since_aware = since if since.tzinfo else since.replace(tzinfo=UTC)
                entry_aware = entry_time if entry_time.tzinfo else entry_time.replace(
                    tzinfo=UTC
                )

                if entry_aware < since_aware:
                    continue

                # Extract text content
                text = _extract_entry_text(entry)
                if not text:
                    continue

                # Generate a stable ID from the link
                entry_id = hash(link) & 0x7FFFFFFF  # Positive 32-bit integer

                messages.append(
                    Message(
                        id=entry_id,
                        channel_username=feed.name,
                        channel_title=feed.name,
                        text=text,
                        timestamp=entry_aware.replace(tzinfo=None),
                        url=link,
                        source_type=SourceType.RSS,
                    )
                )

        except httpx.HTTPError as e:
            logger.error(f"HTTP error fetching feed {feed.name}: {e}")
        except Exception as e:
            logger.error(f"Error processing feed {feed.name}: {e}")

        return messages

    async def get_all_feed_updates(
        self,
        since: datetime,
        limit_per_feed: int = 50,
        seen_urls: set[str] | None = None,
    ) -> list[Message]:
        """Fetch recent articles from all configured RSS feeds.

        Args:
            since: Only include articles newer than this timestamp.
            limit_per_feed: Maximum number of entries to process from each feed.
            seen_urls: Set of URLs already processed (for deduplication).

        Returns:
            List of new messages from all feeds.
        """
        all_messages: list[Message] = []

        for feed in self.config.rss_feeds:
            logger.info(f"Fetching articles from {feed.name}")
            messages = await self.get_feed_updates(feed, since, limit_per_feed, seen_urls)
            all_messages.extend(messages)
            logger.info(f"Found {len(messages)} new articles from {feed.name}")

        # Sort by timestamp, newest first
        all_messages.sort(key=lambda m: m.timestamp, reverse=True)

        return all_messages


def _parse_entry_time(entry: dict) -> datetime | None:
    """Parse the publication time from a feed entry."""
    # Try different date fields
    for date_field in ["published", "updated", "created"]:
        date_str = entry.get(date_field)
        if date_str:
            try:
                return parsedate_to_datetime(date_str)
            except (ValueError, TypeError):
                pass

        # Try parsed version (feedparser provides these)
        parsed_field = f"{date_field}_parsed"
        parsed_time = entry.get(parsed_field)
        if parsed_time:
            try:
                return datetime(*parsed_time[:6], tzinfo=UTC)
            except (ValueError, TypeError):
                pass

    return None


def _clean_text(text: str) -> str:
    """Remove non-Persian/English characters while preserving essential content.

    Keeps:
    - Persian/Arabic script (U+0600-U+06FF and extensions)
    - Latin letters (a-zA-Z)
    - Numbers (0-9)
    - Common punctuation and whitespace
    - Zero-width non-joiner (U+200C) - essential for Persian typography
    """
    # Keep: Persian/Arabic, Latin, digits, common punctuation, ZWNJ
    cleaned = re.sub(
        r"[^\u0600-\u06FF\u0750-\u077F\uFB50-\uFDFF\uFE70-\uFEFF"
        r"a-zA-Z0-9\s.,!?;:\-()\"'@#$%&*/\n\u200C\u060C\u061B\u061F]",
        "",
        text,
    )
    return cleaned.strip()


def _extract_entry_text(entry: dict) -> str:
    """Extract the text content from a feed entry."""
    # Build text from title and description/summary
    parts = []

    title = entry.get("title", "").strip()
    if title:
        parts.append(title)

    # Try to get description or summary
    description = ""
    if "summary" in entry:
        description = entry["summary"]
    elif "description" in entry:
        description = entry["description"]
    elif "content" in entry and entry["content"]:
        # Some feeds use 'content' list
        content = entry["content"]
        if isinstance(content, list) and content:
            description = content[0].get("value", "")

    # Clean up HTML tags (basic)
    if description:
        description = re.sub(r"<[^>]+>", "", description).strip()
        if description:
            parts.append(description)

    # Clean non-Persian/English characters and return
    return _clean_text("\n\n".join(parts))
