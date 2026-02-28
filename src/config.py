"""Configuration loading and validation."""

import os
from dataclasses import dataclass, field
from pathlib import Path

import yaml
from dotenv import load_dotenv


class ConfigError(Exception):
    """Raised when configuration is invalid or missing."""

    pass


@dataclass
class RSSFeed:
    """Configuration for an RSS feed source."""

    name: str
    url: str


@dataclass
class IranFilter:
    """Configuration for Iran-related content filtering."""

    enabled: bool = True
    keywords: list[str] = field(default_factory=lambda: [
        "iran",
        "iranian",
        "tehran",
        "ایران",
        "تهران",
    ])


@dataclass
class RadarMonitorConfig:
    """Configuration for Cloudflare Radar monitoring."""

    enabled: bool = False
    location: str = "IR"
    interval_minutes: int = 60
    change_threshold_percent: float = 5.0
    alert_cooldown_hours: int = 0  # 0 = alert every hour if threshold met


@dataclass
class Config:
    """Application configuration."""

    # Telegram API credentials
    telegram_api_id: int
    telegram_api_hash: str
    telegram_session_string: str
    telegram_bot_token: str
    output_channel_id: str

    # OpenRouter API
    openrouter_api_key: str

    # Settings
    summary_interval_minutes: int = 30
    llm_model: str = "google/gemma-2-9b-it"

    # Two-stage summarization settings
    two_stage_summarization: bool = False
    english_llm_model: str = "google/gemma-2-9b-it"

    # Telegram channels to monitor
    channels: list[str] = field(default_factory=list)

    # RSS feeds to monitor
    rss_feeds: list[RSSFeed] = field(default_factory=list)

    # Iran filter configuration
    iran_filter: IranFilter = field(default_factory=IranFilter)

    # Cloudflare Radar monitoring
    cloudflare_api_token: str = ""
    radar_monitor: RadarMonitorConfig = field(default_factory=RadarMonitorConfig)

    # Test mode settings
    test_mode: bool = False
    test_summary_interval_minutes: int = 5
    test_output_dir: Path = field(default_factory=lambda: Path("output"))
    test_state_file: Path = field(default_factory=lambda: Path(".last_check.test"))

    @property
    def effective_summary_interval_minutes(self) -> int:
        """Return the appropriate interval based on test mode."""
        return self.test_summary_interval_minutes if self.test_mode else self.summary_interval_minutes

    @property
    def effective_state_file(self) -> Path:
        """Return the appropriate state file based on test mode."""
        return self.test_state_file if self.test_mode else Path(".last_check")

    @classmethod
    def from_env(cls, channels_file: str | Path | None = None) -> "Config":
        """Load configuration from environment variables and channels file."""
        load_dotenv()

        # Determine test mode first
        test_mode = os.getenv("TEST_MODE", "false").lower() == "true"

        # Required environment variables
        required_vars = [
            "TELEGRAM_API_ID",
            "TELEGRAM_API_HASH",
            "TELEGRAM_SESSION_STRING",
            "TELEGRAM_BOT_TOKEN",
            "OUTPUT_CHANNEL_ID",
            "OPENROUTER_API_KEY",
        ]

        missing = [var for var in required_vars if not os.getenv(var)]
        if missing:
            raise ConfigError(f"Missing required environment variables: {', '.join(missing)}")

        # Load sources from YAML file
        channels: list[str] = []
        rss_feeds: list[RSSFeed] = []
        iran_filter = IranFilter()
        radar_monitor = RadarMonitorConfig()

        # Determine channels file based on test mode
        if channels_file is None:
            if test_mode:
                test_channels_path = Path("config/channels.test.yaml")
                if test_channels_path.exists():
                    channels_file = test_channels_path
                else:
                    channels_file = Path("config/channels.yaml")
            else:
                channels_file = Path("config/channels.yaml")

        channels_path = Path(channels_file)
        if channels_path.exists():
            channels, rss_feeds, iran_filter, radar_monitor = _load_sources_yaml(channels_path)

        # Parse API ID as integer
        try:
            api_id = int(os.environ["TELEGRAM_API_ID"])
        except ValueError as e:
            raise ConfigError("TELEGRAM_API_ID must be an integer") from e

        return cls(
            telegram_api_id=api_id,
            telegram_api_hash=os.environ["TELEGRAM_API_HASH"],
            telegram_session_string=os.environ["TELEGRAM_SESSION_STRING"],
            telegram_bot_token=os.environ["TELEGRAM_BOT_TOKEN"],
            output_channel_id=os.environ["OUTPUT_CHANNEL_ID"],
            openrouter_api_key=os.environ["OPENROUTER_API_KEY"],
            summary_interval_minutes=int(os.getenv("SUMMARY_INTERVAL_MINUTES", "30")),
            llm_model=os.getenv("LLM_MODEL", "google/gemma-2-9b-it"),
            two_stage_summarization=os.getenv("TWO_STAGE_SUMMARIZATION", "false").lower() == "true",
            english_llm_model=os.getenv("ENGLISH_LLM_MODEL", "google/gemma-2-9b-it"),
            channels=channels,
            rss_feeds=rss_feeds,
            iran_filter=iran_filter,
            cloudflare_api_token=os.getenv("CLOUDFLARE_API_TOKEN", ""),
            radar_monitor=radar_monitor,
            test_mode=test_mode,
            test_summary_interval_minutes=int(os.getenv("TEST_SUMMARY_INTERVAL_MINUTES", "5")),
            test_output_dir=Path(os.getenv("TEST_OUTPUT_DIR", "output")),
            test_state_file=Path(os.getenv("TEST_STATE_FILE", ".last_check.test")),
        )


def _load_sources_yaml(
    path: Path,
) -> tuple[list[str], list[RSSFeed], IranFilter, RadarMonitorConfig]:
    """Load sources configuration from YAML file."""
    try:
        with open(path) as f:
            data = yaml.safe_load(f)

        if not data:
            return [], [], IranFilter(), RadarMonitorConfig()

        # Load Telegram channels (support both old 'channels' and new 'telegram_channels' keys)
        channels: list[str] = []
        raw_channels = data.get("telegram_channels") or data.get("channels") or []
        if isinstance(raw_channels, list):
            channels = [str(ch) for ch in raw_channels if ch is not None]

        # Load RSS feeds
        rss_feeds: list[RSSFeed] = []
        raw_feeds = data.get("rss_feeds") or []
        if isinstance(raw_feeds, list):
            for feed in raw_feeds:
                if isinstance(feed, dict) and "name" in feed and "url" in feed:
                    rss_feeds.append(RSSFeed(name=feed["name"], url=feed["url"]))

        # Load Iran filter configuration
        iran_filter = IranFilter()
        raw_filter = data.get("iran_filter")
        if isinstance(raw_filter, dict):
            enabled = raw_filter.get("enabled", True)
            keywords = raw_filter.get("keywords")
            if isinstance(keywords, list):
                iran_filter = IranFilter(
                    enabled=bool(enabled),
                    keywords=[str(k) for k in keywords if k is not None],
                )
            else:
                iran_filter = IranFilter(enabled=bool(enabled))

        # Load Cloudflare Radar monitor configuration
        radar_monitor = RadarMonitorConfig()
        raw_radar = data.get("radar_monitor")
        if isinstance(raw_radar, dict):
            radar_monitor = RadarMonitorConfig(
                enabled=bool(raw_radar.get("enabled", False)),
                location=str(raw_radar.get("location", "IR")),
                interval_minutes=int(raw_radar.get("interval_minutes", 60)),
                change_threshold_percent=float(raw_radar.get("change_threshold_percent", 5.0)),
                alert_cooldown_hours=int(raw_radar.get("alert_cooldown_hours", 0)),
            )

        return channels, rss_feeds, iran_filter, radar_monitor

    except yaml.YAMLError as e:
        raise ConfigError(f"Invalid YAML in sources file: {e}") from e
    except OSError as e:
        raise ConfigError(f"Could not read sources file: {e}") from e
