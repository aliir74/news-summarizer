"""Data models for the news summarizer."""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum, auto
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

import jdatetime

from src.cadence import CadenceChangeReason, CadenceDecision
from src.message_utils import format_html_links

TEHRAN_TZ = ZoneInfo("Asia/Tehran")

PERSIAN_DIGITS = "۰۱۲۳۴۵۶۷۸۹"


def to_persian_digits(n: int | str) -> str:
    """Convert an integer or digit string to a Persian digit string."""
    return "".join(PERSIAN_DIGITS[int(d)] for d in str(n))


class SourceType(Enum):
    """Type of message source."""

    TELEGRAM = auto()
    RSS = auto()


class AnomalyStatus(Enum):
    """Status of a Cloudflare traffic anomaly."""

    UNVERIFIED = "UNVERIFIED"
    VERIFIED = "VERIFIED"
    FALSE_POSITIVE = "FALSE_POSITIVE"


class AlertType(Enum):
    """Type of radar alert."""

    CLOUDFLARE_ANOMALY = "cloudflare_anomaly"
    TRAFFIC_CHANGE = "traffic_change"


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

    @staticmethod
    def _to_persian_digits(n: int | str) -> str:
        """Convert integer or digit string to Persian digit string."""
        return to_persian_digits(n)

    def format_message(self, *, html: bool = True) -> str:
        """Format the summary for posting to messaging platforms.

        Args:
            html: When True, convert source links to HTML <a> tags (Telegram).
                  When False, keep raw (label | url) text (Bale).
        """
        tehran_time = self.created_at.astimezone(TEHRAN_TZ)
        shamsi = jdatetime.datetime.fromgregorian(datetime=tehran_time)
        month_name = jdatetime.date.j_months_fa[shamsi.month - 1]
        shamsi_date = (
            f"{self._to_persian_digits(shamsi.day)} {month_name}"
            f" {self._to_persian_digits(shamsi.year)}"
        )
        shamsi_time = (
            f"{self._to_persian_digits(f'{shamsi.hour:02d}')}"
            f":{self._to_persian_digits(f'{shamsi.minute:02d}')}"
        )

        header = f"📰 خلاصه اخبار | {shamsi_date} — {shamsi_time}\n\n"
        source_count = self._to_persian_digits(self.source_count)
        channel_count = self._to_persian_digits(len(self.channels))
        footer = f"\n\n📡 {source_count} خبر از {channel_count} منبع"

        body = format_html_links(self.content) if html else self.content
        return header + body + footer


# Persian phrasing for each cadence-change reason.
_CADENCE_REASON_PHRASES = {
    CadenceChangeReason.NEWS_VOLUME: "افزایش حجم اخبار",
    CadenceChangeReason.RADAR_OUTAGE: "اختلال اینترنت در ایران",
    CadenceChangeReason.CALM_DECAY: "آرام‌تر شدن جریان اخبار",
}


def build_cadence_notice(decision: CadenceDecision) -> str:
    """Build the Persian notice explaining why the summary cadence changed.

    Plain text (no HTML) so it is safe through every post_alert path; every
    variant names the next-summary wait time so readers know what to expect.
    """
    if not decision.changed or decision.reason is None:
        raise ValueError("A cadence notice requires a changed decision with a reason")

    escalated = decision.new_interval < decision.previous_interval
    emoji = "⚡️" if escalated else "🕊"
    direction = "کاهش" if escalated else "افزایش"
    previous = to_persian_digits(decision.previous_interval)
    new = to_persian_digits(decision.new_interval)
    reason_phrase = _CADENCE_REASON_PHRASES[decision.reason]
    return (
        f"{emoji} به دلیل {reason_phrase}، فاصله ارسال خلاصه‌ها "
        f"از {previous} به {new} دقیقه {direction} یافت.\n"
        f"خلاصه بعدی حدود {new} دقیقه دیگر ارسال می‌شود."
    )


# Cloudflare Radar monitoring models


@dataclass
class Anomaly:
    """Cloudflare pre-detected traffic anomaly."""

    id: str
    location: str
    start_date: datetime
    end_date: datetime | None
    status: AnomalyStatus
    asn: int | None


@dataclass
class TrafficDataPoint:
    """Single traffic measurement from Cloudflare Radar."""

    timestamp: datetime
    value: float  # Normalized 0-1


@dataclass
class TrafficChange:
    """Detected traffic change between consecutive hours."""

    timestamp: datetime
    previous_value: float
    current_value: float
    change_percent: float  # Positive = increase, negative = decrease

    @property
    def is_drop(self) -> bool:
        """Return True if this represents a traffic drop."""
        return self.change_percent < 0

    @property
    def is_spike(self) -> bool:
        """Return True if this represents a traffic increase."""
        return self.change_percent > 0


@dataclass
class RadarAlert:
    """Alert to be sent to Telegram from Cloudflare Radar monitoring."""

    alert_type: AlertType
    location: str
    timestamp: datetime
    message: str
    change_percent: float | None = None
    anomaly_id: str | None = None
