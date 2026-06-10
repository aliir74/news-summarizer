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
class AdaptiveCadenceConfig:
    """Configuration for the reflective adaptive summary cadence.

    When enabled, the summary interval shortens as news intensity rises (a
    surge) and decays back toward the baseline (summary_interval_minutes) as
    things calm. Intensity is measured as a pre-dedup filtered message rate in
    messages per minute, so the signal is independent of the current window
    length.
    """

    enabled: bool = False
    min_interval_minutes: int = 5  # Floor cadence during a surge
    max_interval_minutes: int | None = None  # Optional ceiling; None caps at baseline
    baseline_window: int = 10  # Number of recent rate samples kept for the baseline
    elevated_ratio: float = 2.0  # rate >= elevated_ratio * baseline => ELEVATED
    surge_ratio: float = 4.0  # rate >= surge_ratio * baseline => SURGE
    decay_factor: float = 1.5  # Multiply interval by this per calm run when decaying
    calm_streak_runs: int = 2  # Consecutive NORMAL full-runs required before decaying
    min_baseline_rate: float = 0.1  # Floor for the baseline rate (messages per minute)
    fast_escalation: bool = False  # Run the cheap escalation probe between summary runs
    probe_interval_minutes: int = 5  # How often the probe runs when fast_escalation is on
    probe_window_minutes: int = 15  # Trailing window the probe measures its rate over

    def __post_init__(self) -> None:
        """Validate the cadence knobs so a misconfiguration cannot silently
        defeat the feature's safety guarantees."""
        if self.min_interval_minutes < 1:
            raise ConfigError("adaptive_cadence.min_interval_minutes must be >= 1")
        if self.probe_interval_minutes < 1:
            raise ConfigError("adaptive_cadence.probe_interval_minutes must be >= 1")
        # The probe averages its rate over probe_window_minutes, decoupled from
        # how often it runs. A window shorter than the run cadence leaves gaps in
        # coverage; a longer window smooths bursts so a single message cluster is
        # not misread as a surge against the (long-window) full-run baseline.
        if self.probe_window_minutes < self.probe_interval_minutes:
            raise ConfigError(
                "adaptive_cadence.probe_window_minutes must be >= probe_interval_minutes"
            )
        if self.baseline_window < 1:
            raise ConfigError("adaptive_cadence.baseline_window must be >= 1")
        # decay_factor must exceed 1.0 or the interval never grows back toward the
        # baseline after a surge, pinning the bot at min_interval_minutes forever.
        if self.decay_factor <= 1.0:
            raise ConfigError("adaptive_cadence.decay_factor must be > 1.0")
        # calm_streak_runs >= 1: with 1 the interval decays on the first calm run
        # (no hysteresis); higher values demand sustained calm before relaxing,
        # which prevents the decay/re-escalate flapping during a bursty surge.
        if self.calm_streak_runs < 1:
            raise ConfigError("adaptive_cadence.calm_streak_runs must be >= 1")


@dataclass
class DeduplicationConfig:
    """Configuration for article deduplication."""

    enabled: bool = True
    similarity_threshold: float = 0.5  # 50% entity overlap = duplicate
    keyword_similarity_threshold: float = 0.3  # 30% keyword overlap required
    ttl_days: int = 3  # Keep fingerprints for 3 days


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
    llm_model: str = "google/gemini-2.5-flash-lite"

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

    # Adaptive (reflective) summary cadence
    adaptive_cadence: AdaptiveCadenceConfig = field(default_factory=AdaptiveCadenceConfig)

    # Bale Messenger (optional)
    bale_bot_token: str = ""
    bale_channel_id: str = ""

    # Deduplication configuration
    deduplication: DeduplicationConfig = field(default_factory=DeduplicationConfig)
    dedup_db_path: str = ".dedup.db"

    # Test mode settings
    test_mode: bool = False
    test_summary_interval_minutes: int = 5
    test_output_dir: Path = field(default_factory=lambda: Path("output"))
    test_state_file: Path = field(default_factory=lambda: Path(".last_check.test"))

    @property
    def bale_enabled(self) -> bool:
        """Return whether Bale output is enabled."""
        return bool(self.bale_bot_token and self.bale_channel_id)

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
        deduplication = DeduplicationConfig()
        adaptive_cadence = AdaptiveCadenceConfig()

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
            (
                channels,
                rss_feeds,
                iran_filter,
                radar_monitor,
                deduplication,
                adaptive_cadence,
            ) = _load_sources_yaml(channels_path)

        # Parse API ID as integer
        try:
            api_id = int(os.environ["TELEGRAM_API_ID"])
        except ValueError as e:
            raise ConfigError("TELEGRAM_API_ID must be an integer") from e

        summary_interval = int(os.getenv("SUMMARY_INTERVAL_MINUTES", "30"))
        # The surge floor cannot be slower than the steady-state baseline, or
        # escalation would "speed up" to a longer interval than normal cadence.
        if (
            adaptive_cadence.enabled
            and adaptive_cadence.min_interval_minutes > summary_interval
        ):
            raise ConfigError(
                f"adaptive_cadence.min_interval_minutes "
                f"({adaptive_cadence.min_interval_minutes}) cannot exceed "
                f"SUMMARY_INTERVAL_MINUTES ({summary_interval})"
            )

        return cls(
            telegram_api_id=api_id,
            telegram_api_hash=os.environ["TELEGRAM_API_HASH"],
            telegram_session_string=os.environ["TELEGRAM_SESSION_STRING"],
            telegram_bot_token=os.environ["TELEGRAM_BOT_TOKEN"],
            output_channel_id=os.environ["OUTPUT_CHANNEL_ID"],
            openrouter_api_key=os.environ["OPENROUTER_API_KEY"],
            summary_interval_minutes=summary_interval,
            llm_model=os.getenv("LLM_MODEL", "google/gemini-2.5-flash-lite"),
            two_stage_summarization=os.getenv("TWO_STAGE_SUMMARIZATION", "false").lower() == "true",
            english_llm_model=os.getenv("ENGLISH_LLM_MODEL", "google/gemma-2-9b-it"),
            channels=channels,
            rss_feeds=rss_feeds,
            iran_filter=iran_filter,
            bale_bot_token=os.getenv("BALE_BOT_TOKEN", ""),
            bale_channel_id=os.getenv("BALE_CHANNEL_ID", ""),
            cloudflare_api_token=os.getenv("CLOUDFLARE_API_TOKEN", ""),
            radar_monitor=radar_monitor,
            adaptive_cadence=adaptive_cadence,
            deduplication=deduplication,
            test_mode=test_mode,
            test_summary_interval_minutes=int(os.getenv("TEST_SUMMARY_INTERVAL_MINUTES", "5")),
            test_output_dir=Path(os.getenv("TEST_OUTPUT_DIR", "output")),
            test_state_file=Path(os.getenv("TEST_STATE_FILE", ".last_check.test")),
        )


def _load_sources_yaml(
    path: Path,
) -> tuple[
    list[str],
    list[RSSFeed],
    IranFilter,
    RadarMonitorConfig,
    DeduplicationConfig,
    AdaptiveCadenceConfig,
]:
    """Load sources configuration from YAML file."""
    try:
        with open(path) as f:
            data = yaml.safe_load(f)

        if not data:
            return (
                [],
                [],
                IranFilter(),
                RadarMonitorConfig(),
                DeduplicationConfig(),
                AdaptiveCadenceConfig(),
            )

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

        # Load deduplication configuration
        deduplication = DeduplicationConfig()
        raw_dedup = data.get("deduplication")
        if isinstance(raw_dedup, dict):
            enabled = raw_dedup.get("enabled", True)
            similarity_threshold = raw_dedup.get("similarity_threshold", 0.5)
            keyword_similarity_threshold = raw_dedup.get("keyword_similarity_threshold", 0.3)
            ttl_days = raw_dedup.get("ttl_days", 3)
            deduplication = DeduplicationConfig(
                enabled=bool(enabled),
                similarity_threshold=float(similarity_threshold),
                keyword_similarity_threshold=float(keyword_similarity_threshold),
                ttl_days=int(ttl_days),
            )

        # Load adaptive cadence configuration
        adaptive_cadence = AdaptiveCadenceConfig()
        raw_cadence = data.get("adaptive_cadence")
        if isinstance(raw_cadence, dict):
            defaults = AdaptiveCadenceConfig()
            raw_max = raw_cadence.get("max_interval_minutes", defaults.max_interval_minutes)
            max_interval = int(raw_max) if raw_max is not None else None
            adaptive_cadence = AdaptiveCadenceConfig(
                enabled=bool(raw_cadence.get("enabled", defaults.enabled)),
                min_interval_minutes=int(
                    raw_cadence.get("min_interval_minutes", defaults.min_interval_minutes)
                ),
                max_interval_minutes=max_interval,
                baseline_window=int(
                    raw_cadence.get("baseline_window", defaults.baseline_window)
                ),
                elevated_ratio=float(
                    raw_cadence.get("elevated_ratio", defaults.elevated_ratio)
                ),
                surge_ratio=float(raw_cadence.get("surge_ratio", defaults.surge_ratio)),
                decay_factor=float(raw_cadence.get("decay_factor", defaults.decay_factor)),
                calm_streak_runs=int(
                    raw_cadence.get("calm_streak_runs", defaults.calm_streak_runs)
                ),
                min_baseline_rate=float(
                    raw_cadence.get("min_baseline_rate", defaults.min_baseline_rate)
                ),
                fast_escalation=bool(
                    raw_cadence.get("fast_escalation", defaults.fast_escalation)
                ),
                probe_interval_minutes=int(
                    raw_cadence.get("probe_interval_minutes", defaults.probe_interval_minutes)
                ),
                probe_window_minutes=int(
                    raw_cadence.get("probe_window_minutes", defaults.probe_window_minutes)
                ),
            )

        return channels, rss_feeds, iran_filter, radar_monitor, deduplication, adaptive_cadence

    except yaml.YAMLError as e:
        raise ConfigError(f"Invalid YAML in sources file: {e}") from e
    except OSError as e:
        raise ConfigError(f"Could not read sources file: {e}") from e
