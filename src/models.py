"""Data models for the news summarizer."""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum, auto
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

TEHRAN_TZ = ZoneInfo("Asia/Tehran")


class SourceType(Enum):
    """Type of message source."""

    TELEGRAM = auto()
    RSS = auto()


def extract_domain(url: str) -> str:
    """Extract domain from URL, removing www. prefix."""
    try:
        parsed = urlparse(url)
        domain = parsed.netloc
        if domain.startswith("www."):
            domain = domain[4:]
        return domain
    except Exception:
        return ""


@dataclass
class Message:
    """Represents a message from a Telegram channel or RSS feed."""

    id: int
    channel_username: str
    channel_title: str
    text: str
    timestamp: datetime
    url: str = field(default="")
    source_type: SourceType = field(default=SourceType.TELEGRAM)

    def __post_init__(self) -> None:
        """Generate URL if not provided."""
        if not self.url and self.channel_username:
            self.url = f"https://t.me/{self.channel_username}/{self.id}"


@dataclass
class SourceInfo:
    """Information about a news source for display."""

    name: str
    source_type: SourceType
    domain: str = ""


@dataclass
class Summary:
    """Represents a generated news summary."""

    content: str
    source_count: int
    channels: list[str]
    channel_usernames: list[str] = field(default_factory=list)
    sources: list[SourceInfo] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.now)

    def format_for_telegram(self) -> str:
        """Format the summary for posting to Telegram."""
        # Convert to Tehran timezone
        tehran_time = self.created_at.astimezone(TEHRAN_TZ)
        header = f"📰 خلاصه اخبار - {tehran_time.strftime('%Y-%m-%d %H:%M')} (Tehran)\n"
        header += f"📊 {self.source_count} خبر از {len(self.channels)} کانال\n"

        # Add source channels with proper formatting based on source type
        if self.sources:
            formatted = []
            for source in self.sources:
                if source.source_type == SourceType.TELEGRAM:
                    formatted.append(f"@{source.name}")
                else:  # RSS
                    formatted.append(source.domain or source.name)
            header += f"📡 منابع: {' '.join(formatted)}\n"
        elif self.channel_usernames:  # Backward compatibility
            sources = " ".join(f"@{username}" for username in self.channel_usernames)
            header += f"📡 منابع: {sources}\n"

        header += "─" * 20 + "\n\n"
        return header + self.content
