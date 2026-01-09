"""Data models for the news summarizer."""

from dataclasses import dataclass, field
from datetime import datetime
from zoneinfo import ZoneInfo

TEHRAN_TZ = ZoneInfo("Asia/Tehran")


@dataclass
class Message:
    """Represents a message from a Telegram channel."""

    id: int
    channel_username: str
    channel_title: str
    text: str
    timestamp: datetime
    url: str = field(default="")

    def __post_init__(self) -> None:
        """Generate URL if not provided."""
        if not self.url and self.channel_username:
            self.url = f"https://t.me/{self.channel_username}/{self.id}"


@dataclass
class Summary:
    """Represents a generated news summary."""

    content: str
    source_count: int
    channels: list[str]
    channel_usernames: list[str] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.now)

    def format_for_telegram(self) -> str:
        """Format the summary for posting to Telegram."""
        # Convert to Tehran timezone
        tehran_time = self.created_at.astimezone(TEHRAN_TZ)
        header = f"📰 خلاصه اخبار - {tehran_time.strftime('%Y-%m-%d %H:%M')} (Tehran)\n"
        header += f"📊 {self.source_count} خبر از {len(self.channels)} کانال\n"

        # Add source channels
        if self.channel_usernames:
            sources = " ".join(f"@{username}" for username in self.channel_usernames)
            header += f"📡 منابع: {sources}\n"

        header += "─" * 20 + "\n\n"
        return header + self.content
