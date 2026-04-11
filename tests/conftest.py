"""Shared test fixtures."""

from dataclasses import replace
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.config import Config, DeduplicationConfig, IranFilter, RadarMonitorConfig, RSSFeed
from src.models import Anomaly, AnomalyStatus, Message, SourceType, Summary


@pytest.fixture
def sample_config() -> Config:
    """Create a sample configuration for testing."""
    return Config(
        telegram_api_id=12345,
        telegram_api_hash="test_api_hash",
        telegram_session_string="test_session_string",
        telegram_bot_token="test_bot_token",
        output_channel_id="@test_channel",
        openrouter_api_key="test_openrouter_key",
        summary_interval_minutes=30,
        llm_model="google/gemini-2.5-flash-lite",
        channels=["channel1", "channel2"],
        rss_feeds=[
            RSSFeed(name="Test Feed", url="https://example.com/feed.xml"),
        ],
        iran_filter=IranFilter(enabled=True, keywords=["iran", "tehran", "ایران", "تهران"]),
        deduplication=DeduplicationConfig(enabled=False),
    )


@pytest.fixture
def sample_messages() -> list[Message]:
    """Create sample messages for testing."""
    return [
        Message(
            id=1,
            channel_username="channel1",
            channel_title="Channel One",
            text="این یک خبر تست درباره ایران است.",
            timestamp=datetime(2024, 1, 15, 10, 30),
        ),
        Message(
            id=2,
            channel_username="channel1",
            channel_title="Channel One",
            text="خبر دوم درباره تهران برای تست.",
            timestamp=datetime(2024, 1, 15, 10, 35),
        ),
        Message(
            id=3,
            channel_username="channel2",
            channel_title="Channel Two",
            text="خبر از ایران در کانال دوم.",
            timestamp=datetime(2024, 1, 15, 10, 40),
        ),
    ]


@pytest.fixture
def sample_summary() -> Summary:
    """Create a sample summary for testing."""
    return Summary(
        content="این خلاصه اخبار است. شامل سه خبر از دو کانال می‌باشد.",
        source_count=3,
        channels=["Channel One", "Channel Two"],
        created_at=datetime(2024, 1, 15, 11, 0),
    )


@pytest.fixture
def mock_pyrogram_client() -> MagicMock:
    """Create a mock Pyrogram client."""
    client = MagicMock()
    client.start = AsyncMock()
    client.stop = AsyncMock()
    client.get_chat = AsyncMock()
    client.get_chat_history = MagicMock()
    client.send_message = AsyncMock()
    return client


@pytest.fixture
def mock_openai_client() -> MagicMock:
    """Create a mock OpenAI client."""
    client = MagicMock()
    response = MagicMock()
    response.choices = [MagicMock()]
    response.choices[0].message.content = "خلاصه تست شده اخبار"
    client.chat.completions.create.return_value = response
    return client


@pytest.fixture
def env_vars(monkeypatch: pytest.MonkeyPatch) -> None:
    """Set up required environment variables."""
    monkeypatch.setenv("TELEGRAM_API_ID", "12345")
    monkeypatch.setenv("TELEGRAM_API_HASH", "test_api_hash")
    monkeypatch.setenv("TELEGRAM_SESSION_STRING", "test_session_string")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "test_bot_token")
    monkeypatch.setenv("OUTPUT_CHANNEL_ID", "@test_channel")
    monkeypatch.setenv("OPENROUTER_API_KEY", "test_openrouter_key")


@pytest.fixture
def sample_rss_feed() -> RSSFeed:
    """Create a sample RSS feed configuration for testing."""
    return RSSFeed(name="Test Feed", url="https://example.com/feed.xml")


@pytest.fixture
def sample_iran_filter() -> IranFilter:
    """Create a sample Iran filter configuration for testing."""
    return IranFilter(enabled=True, keywords=["iran", "iranian", "tehran"])


@pytest.fixture
def sample_rss_messages() -> list[Message]:
    """Create sample RSS feed messages for testing."""
    return [
        Message(
            id=12345,
            channel_username="Test Feed",
            channel_title="Test Feed",
            text="Iran announces new economic policy in Tehran",
            timestamp=datetime(2024, 1, 15, 10, 30),
            url="https://example.com/article1",
            source_type=SourceType.RSS,
        ),
        Message(
            id=67890,
            channel_username="Test Feed",
            channel_title="Test Feed",
            text="Weather update for Paris today",
            timestamp=datetime(2024, 1, 15, 10, 35),
            url="https://example.com/article2",
            source_type=SourceType.RSS,
        ),
        Message(
            id=11111,
            channel_username="Test Feed",
            channel_title="Test Feed",
            text="Iranian scientists make breakthrough",
            timestamp=datetime(2024, 1, 15, 10, 40),
            url="https://example.com/article3",
            source_type=SourceType.RSS,
        ),
    ]


@pytest.fixture
def mock_httpx_client() -> MagicMock:
    """Create a mock httpx AsyncClient."""
    client = MagicMock()
    client.get = AsyncMock()
    client.aclose = AsyncMock()
    return client


@pytest.fixture
def sample_rss_xml() -> str:
    """Sample RSS feed XML for testing."""
    return """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>Test Feed</title>
    <item>
      <title>Iran announces new policy</title>
      <link>https://example.com/article1</link>
      <description>Details about Iran's new economic policy.</description>
      <pubDate>Mon, 15 Jan 2024 10:30:00 GMT</pubDate>
    </item>
    <item>
      <title>Weather in Paris</title>
      <link>https://example.com/article2</link>
      <description>Sunny weather expected in Paris.</description>
      <pubDate>Mon, 15 Jan 2024 10:35:00 GMT</pubDate>
    </item>
  </channel>
</rss>"""


@pytest.fixture
def radar_config(sample_config: Config) -> Config:
    """Create a sample configuration with radar monitoring enabled."""
    return replace(
        sample_config,
        cloudflare_api_token="test_cloudflare_token",
        radar_monitor=RadarMonitorConfig(
            enabled=True,
            location="IR",
            interval_minutes=60,
            change_threshold_percent=5.0,
            alert_cooldown_hours=0,
        ),
    )


@pytest.fixture
def sample_anomaly() -> Anomaly:
    """Create a sample Cloudflare anomaly for testing."""
    return Anomaly(
        id="anomaly-123",
        location="IR",
        start_date=datetime(2024, 1, 15, 10, 0, tzinfo=UTC),
        end_date=None,
        status=AnomalyStatus.UNVERIFIED,
        asn=None,
    )


@pytest.fixture
def sample_anomalies_api_response() -> dict:
    """Sample Cloudflare Radar anomalies API response."""
    return {
        "result": {
            "trafficAnomalies": [
                {
                    "uuid": "anomaly-123",
                    "locationCode": "IR",
                    "startDate": "2024-01-15T10:00:00Z",
                    "endDate": None,
                    "status": "UNVERIFIED",
                    "asnNumber": None,
                },
                {
                    "uuid": "anomaly-456",
                    "locationCode": "IR",
                    "startDate": "2024-01-14T08:00:00Z",
                    "endDate": "2024-01-14T12:00:00Z",
                    "status": "VERIFIED",
                    "asnNumber": 12345,
                },
            ]
        }
    }


@pytest.fixture
def sample_timeseries_api_response() -> dict:
    """Sample Cloudflare Radar timeseries API response."""
    return {
        "result": {
            "serie_0": {
                "timestamps": [
                    "2024-01-15T08:00:00Z",
                    "2024-01-15T09:00:00Z",
                    "2024-01-15T10:00:00Z",
                ],
                "values": [0.85, 0.90, 0.80],
            }
        }
    }


@pytest.fixture
def sample_timeseries_drop_response() -> dict:
    """Sample timeseries showing a significant traffic drop (>5%)."""
    return {
        "result": {
            "serie_0": {
                "timestamps": [
                    "2024-01-15T08:00:00Z",
                    "2024-01-15T09:00:00Z",
                    "2024-01-15T10:00:00Z",
                ],
                "values": [0.90, 0.90, 0.80],  # 11.1% drop
            }
        }
    }


@pytest.fixture
def sample_timeseries_spike_response() -> dict:
    """Sample timeseries showing a significant traffic increase (>5%)."""
    return {
        "result": {
            "serie_0": {
                "timestamps": [
                    "2024-01-15T08:00:00Z",
                    "2024-01-15T09:00:00Z",
                    "2024-01-15T10:00:00Z",
                ],
                "values": [0.80, 0.80, 0.90],  # 12.5% increase
            }
        }
    }


@pytest.fixture
def sample_timeseries_stable_response() -> dict:
    """Sample timeseries with stable traffic (no significant change)."""
    return {
        "result": {
            "serie_0": {
                "timestamps": [
                    "2024-01-15T08:00:00Z",
                    "2024-01-15T09:00:00Z",
                    "2024-01-15T10:00:00Z",
                ],
                "values": [0.85, 0.85, 0.86],  # ~1.2% change, below threshold
            }
        }
    }
