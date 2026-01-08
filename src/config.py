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

    # Channels to monitor
    channels: list[str] = field(default_factory=list)

    @classmethod
    def from_env(cls, channels_file: str | Path | None = None) -> "Config":
        """Load configuration from environment variables and channels file."""
        load_dotenv()

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

        # Load channels from YAML file
        channels: list[str] = []
        if channels_file is None:
            channels_file = Path("config/channels.yaml")

        channels_path = Path(channels_file)
        if channels_path.exists():
            channels = _load_channels_yaml(channels_path)

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
            channels=channels,
        )


def _load_channels_yaml(path: Path) -> list[str]:
    """Load channel list from YAML file."""
    try:
        with open(path) as f:
            data = yaml.safe_load(f)

        if not data or "channels" not in data:
            return []

        channels = data["channels"]
        if not isinstance(channels, list):
            return []

        # Filter out None values and convert to strings
        return [str(ch) for ch in channels if ch is not None]

    except yaml.YAMLError as e:
        raise ConfigError(f"Invalid YAML in channels file: {e}") from e
    except OSError as e:
        raise ConfigError(f"Could not read channels file: {e}") from e
