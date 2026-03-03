"""Tests for configuration loading."""

from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from src.config import Config, ConfigError, IranFilter, _load_sources_yaml


class TestConfig:
    """Tests for the Config class."""

    def test_config_from_env_success(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """Test loading config from environment variables."""
        # Set required env vars
        monkeypatch.setenv("TELEGRAM_API_ID", "12345")
        monkeypatch.setenv("TELEGRAM_API_HASH", "test_hash")
        monkeypatch.setenv("TELEGRAM_SESSION_STRING", "test_session")
        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "test_token")
        monkeypatch.setenv("OUTPUT_CHANNEL_ID", "@test_channel")
        monkeypatch.setenv("OPENROUTER_API_KEY", "test_key")

        # Create channels file
        channels_file = tmp_path / "channels.yaml"
        channels_file.write_text("channels:\n  - channel1\n  - channel2\n")

        config = Config.from_env(channels_file=channels_file)

        assert config.telegram_api_id == 12345
        assert config.telegram_api_hash == "test_hash"
        assert config.telegram_session_string == "test_session"
        assert config.telegram_bot_token == "test_token"
        assert config.output_channel_id == "@test_channel"
        assert config.openrouter_api_key == "test_key"
        assert config.channels == ["channel1", "channel2"]

    @patch("src.config.load_dotenv")
    def test_config_missing_env_var(
        self, mock_load_dotenv: Any, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test error when required env var is missing."""
        # Only set some env vars
        monkeypatch.setenv("TELEGRAM_API_ID", "12345")
        # Missing: TELEGRAM_API_HASH, etc.

        # Clear other vars that might be set
        for var in [
            "TELEGRAM_API_HASH",
            "TELEGRAM_SESSION_STRING",
            "TELEGRAM_BOT_TOKEN",
            "OUTPUT_CHANNEL_ID",
            "OPENROUTER_API_KEY",
        ]:
            monkeypatch.delenv(var, raising=False)

        with pytest.raises(ConfigError) as exc_info:
            Config.from_env()

        assert "Missing required environment variables" in str(exc_info.value)

    def test_config_invalid_api_id(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test error when API ID is not an integer."""
        monkeypatch.setenv("TELEGRAM_API_ID", "not_a_number")
        monkeypatch.setenv("TELEGRAM_API_HASH", "hash")
        monkeypatch.setenv("TELEGRAM_SESSION_STRING", "session")
        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "token")
        monkeypatch.setenv("OUTPUT_CHANNEL_ID", "@channel")
        monkeypatch.setenv("OPENROUTER_API_KEY", "key")

        with pytest.raises(ConfigError) as exc_info:
            Config.from_env()

        assert "must be an integer" in str(exc_info.value)

    def test_config_default_values(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """Test default values are applied."""
        monkeypatch.setenv("TELEGRAM_API_ID", "12345")
        monkeypatch.setenv("TELEGRAM_API_HASH", "hash")
        monkeypatch.setenv("TELEGRAM_SESSION_STRING", "session")
        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "token")
        monkeypatch.setenv("OUTPUT_CHANNEL_ID", "@channel")
        monkeypatch.setenv("OPENROUTER_API_KEY", "key")

        # Remove optional env vars
        monkeypatch.delenv("SUMMARY_INTERVAL_MINUTES", raising=False)
        monkeypatch.delenv("LLM_MODEL", raising=False)

        # No channels file
        config = Config.from_env(channels_file=tmp_path / "nonexistent.yaml")

        assert config.summary_interval_minutes == 30
        assert config.llm_model == "google/gemini-2.5-flash-lite"
        assert config.channels == []

    def test_config_custom_interval(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """Test custom interval from env var."""
        monkeypatch.setenv("TELEGRAM_API_ID", "12345")
        monkeypatch.setenv("TELEGRAM_API_HASH", "hash")
        monkeypatch.setenv("TELEGRAM_SESSION_STRING", "session")
        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "token")
        monkeypatch.setenv("OUTPUT_CHANNEL_ID", "@channel")
        monkeypatch.setenv("OPENROUTER_API_KEY", "key")
        monkeypatch.setenv("SUMMARY_INTERVAL_MINUTES", "15")
        monkeypatch.setenv("LLM_MODEL", "anthropic/claude-3-haiku")

        config = Config.from_env(channels_file=tmp_path / "nonexistent.yaml")

        assert config.summary_interval_minutes == 15
        assert config.llm_model == "anthropic/claude-3-haiku"

class TestLoadSourcesYaml:
    """Tests for sources YAML loading."""

    def test_load_valid_yaml_old_format(self, tmp_path: Path) -> None:
        """Test loading valid YAML file with old channels format."""
        channels_file = tmp_path / "channels.yaml"
        channels_file.write_text("channels:\n  - channel1\n  - channel2\n  - channel3\n")

        channels, rss_feeds, iran_filter, _, _ = _load_sources_yaml(channels_file)

        assert channels == ["channel1", "channel2", "channel3"]
        assert rss_feeds == []
        assert iran_filter.enabled is True

    def test_load_valid_yaml_new_format(self, tmp_path: Path) -> None:
        """Test loading valid YAML file with new telegram_channels format."""
        channels_file = tmp_path / "channels.yaml"
        channels_file.write_text(
            "telegram_channels:\n  - channel1\n  - channel2\n"
        )

        channels, rss_feeds, iran_filter, _, _ = _load_sources_yaml(channels_file)

        assert channels == ["channel1", "channel2"]

    def test_load_empty_yaml(self, tmp_path: Path) -> None:
        """Test loading empty YAML file."""
        channels_file = tmp_path / "channels.yaml"
        channels_file.write_text("")

        channels, rss_feeds, iran_filter, _, _ = _load_sources_yaml(channels_file)

        assert channels == []
        assert rss_feeds == []
        assert isinstance(iran_filter, IranFilter)

    def test_load_yaml_no_channels_key(self, tmp_path: Path) -> None:
        """Test loading YAML without channels key."""
        channels_file = tmp_path / "channels.yaml"
        channels_file.write_text("other_key: value\n")

        channels, rss_feeds, iran_filter, _, _ = _load_sources_yaml(channels_file)

        assert channels == []

    def test_load_yaml_with_none_values(self, tmp_path: Path) -> None:
        """Test loading YAML with null values in channels list."""
        channels_file = tmp_path / "channels.yaml"
        channels_file.write_text("channels:\n  - channel1\n  - \n  - channel2\n")

        channels, rss_feeds, iran_filter, _, _ = _load_sources_yaml(channels_file)

        assert channels == ["channel1", "channel2"]

    def test_load_invalid_yaml(self, tmp_path: Path) -> None:
        """Test loading invalid YAML file."""
        channels_file = tmp_path / "channels.yaml"
        channels_file.write_text("invalid: yaml: content: [")

        with pytest.raises(ConfigError) as exc_info:
            _load_sources_yaml(channels_file)

        assert "Invalid YAML" in str(exc_info.value)

    def test_load_yaml_channels_not_list(self, tmp_path: Path) -> None:
        """Test loading YAML where channels is not a list."""
        channels_file = tmp_path / "channels.yaml"
        channels_file.write_text("channels: not_a_list\n")

        channels, rss_feeds, iran_filter, _, _ = _load_sources_yaml(channels_file)

        assert channels == []

    def test_load_rss_feeds(self, tmp_path: Path) -> None:
        """Test loading RSS feeds from YAML."""
        channels_file = tmp_path / "channels.yaml"
        channels_file.write_text(
            "rss_feeds:\n"
            "  - name: Feed One\n"
            "    url: https://example.com/feed1.xml\n"
            "  - name: Feed Two\n"
            "    url: https://example.com/feed2.xml\n"
        )

        channels, rss_feeds, iran_filter, _, _ = _load_sources_yaml(channels_file)

        assert len(rss_feeds) == 2
        assert rss_feeds[0].name == "Feed One"
        assert rss_feeds[0].url == "https://example.com/feed1.xml"
        assert rss_feeds[1].name == "Feed Two"

    def test_load_rss_feeds_invalid_format(self, tmp_path: Path) -> None:
        """Test that invalid RSS feed entries are skipped."""
        channels_file = tmp_path / "channels.yaml"
        channels_file.write_text(
            "rss_feeds:\n"
            "  - name: Valid Feed\n"
            "    url: https://example.com/feed.xml\n"
            "  - name: Missing URL\n"  # Missing url
            "  - url: https://example.com/no-name.xml\n"  # Missing name
        )

        channels, rss_feeds, iran_filter, _, _ = _load_sources_yaml(channels_file)

        assert len(rss_feeds) == 1
        assert rss_feeds[0].name == "Valid Feed"

    def test_load_iran_filter(self, tmp_path: Path) -> None:
        """Test loading Iran filter configuration."""
        channels_file = tmp_path / "channels.yaml"
        channels_file.write_text(
            "iran_filter:\n"
            "  enabled: true\n"
            "  keywords:\n"
            "    - iran\n"
            "    - tehran\n"
        )

        channels, rss_feeds, iran_filter, _, _ = _load_sources_yaml(channels_file)

        assert iran_filter.enabled is True
        assert iran_filter.keywords == ["iran", "tehran"]

    def test_load_iran_filter_disabled(self, tmp_path: Path) -> None:
        """Test loading disabled Iran filter."""
        channels_file = tmp_path / "channels.yaml"
        channels_file.write_text(
            "iran_filter:\n"
            "  enabled: false\n"
        )

        channels, rss_feeds, iran_filter, _, _ = _load_sources_yaml(channels_file)

        assert iran_filter.enabled is False

    def test_load_full_config(self, tmp_path: Path) -> None:
        """Test loading full configuration with all sections."""
        channels_file = tmp_path / "channels.yaml"
        channels_file.write_text(
            "telegram_channels:\n"
            "  - channel1\n"
            "rss_feeds:\n"
            "  - name: Test Feed\n"
            "    url: https://example.com/feed.xml\n"
            "iran_filter:\n"
            "  enabled: true\n"
            "  keywords:\n"
            "    - iran\n"
        )

        channels, rss_feeds, iran_filter, _, _ = _load_sources_yaml(channels_file)

        assert channels == ["channel1"]
        assert len(rss_feeds) == 1
        assert iran_filter.enabled is True
        assert iran_filter.keywords == ["iran"]

class TestTestModeConfig:
    """Tests for test mode configuration."""

    def test_test_mode_disabled_by_default(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """Test that test mode is disabled by default."""
        monkeypatch.setenv("TELEGRAM_API_ID", "12345")
        monkeypatch.setenv("TELEGRAM_API_HASH", "hash")
        monkeypatch.setenv("TELEGRAM_SESSION_STRING", "session")
        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "token")
        monkeypatch.setenv("OUTPUT_CHANNEL_ID", "@channel")
        monkeypatch.setenv("OPENROUTER_API_KEY", "key")
        monkeypatch.delenv("TEST_MODE", raising=False)

        config = Config.from_env(channels_file=tmp_path / "nonexistent.yaml")

        assert config.test_mode is False

    def test_test_mode_enabled(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """Test enabling test mode via env var."""
        monkeypatch.setenv("TELEGRAM_API_ID", "12345")
        monkeypatch.setenv("TELEGRAM_API_HASH", "hash")
        monkeypatch.setenv("TELEGRAM_SESSION_STRING", "session")
        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "token")
        monkeypatch.setenv("OUTPUT_CHANNEL_ID", "@channel")
        monkeypatch.setenv("OPENROUTER_API_KEY", "key")
        monkeypatch.setenv("TEST_MODE", "true")

        config = Config.from_env(channels_file=tmp_path / "nonexistent.yaml")

        assert config.test_mode is True

    def test_test_mode_case_insensitive(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """Test that test mode env var is case insensitive."""
        monkeypatch.setenv("TELEGRAM_API_ID", "12345")
        monkeypatch.setenv("TELEGRAM_API_HASH", "hash")
        monkeypatch.setenv("TELEGRAM_SESSION_STRING", "session")
        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "token")
        monkeypatch.setenv("OUTPUT_CHANNEL_ID", "@channel")
        monkeypatch.setenv("OPENROUTER_API_KEY", "key")
        monkeypatch.setenv("TEST_MODE", "TRUE")

        config = Config.from_env(channels_file=tmp_path / "nonexistent.yaml")

        assert config.test_mode is True

    def test_test_mode_interval(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """Test custom test mode interval."""
        monkeypatch.setenv("TELEGRAM_API_ID", "12345")
        monkeypatch.setenv("TELEGRAM_API_HASH", "hash")
        monkeypatch.setenv("TELEGRAM_SESSION_STRING", "session")
        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "token")
        monkeypatch.setenv("OUTPUT_CHANNEL_ID", "@channel")
        monkeypatch.setenv("OPENROUTER_API_KEY", "key")
        monkeypatch.setenv("TEST_MODE", "true")
        monkeypatch.setenv("TEST_SUMMARY_INTERVAL_MINUTES", "2")

        config = Config.from_env(channels_file=tmp_path / "nonexistent.yaml")

        assert config.test_summary_interval_minutes == 2

    def test_effective_interval_production(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """Test effective interval in production mode."""
        monkeypatch.setenv("TELEGRAM_API_ID", "12345")
        monkeypatch.setenv("TELEGRAM_API_HASH", "hash")
        monkeypatch.setenv("TELEGRAM_SESSION_STRING", "session")
        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "token")
        monkeypatch.setenv("OUTPUT_CHANNEL_ID", "@channel")
        monkeypatch.setenv("OPENROUTER_API_KEY", "key")
        monkeypatch.setenv("SUMMARY_INTERVAL_MINUTES", "60")
        monkeypatch.delenv("TEST_MODE", raising=False)

        config = Config.from_env(channels_file=tmp_path / "nonexistent.yaml")

        assert config.effective_summary_interval_minutes == 60

    def test_effective_interval_test_mode(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """Test effective interval in test mode."""
        monkeypatch.setenv("TELEGRAM_API_ID", "12345")
        monkeypatch.setenv("TELEGRAM_API_HASH", "hash")
        monkeypatch.setenv("TELEGRAM_SESSION_STRING", "session")
        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "token")
        monkeypatch.setenv("OUTPUT_CHANNEL_ID", "@channel")
        monkeypatch.setenv("OPENROUTER_API_KEY", "key")
        monkeypatch.setenv("SUMMARY_INTERVAL_MINUTES", "60")
        monkeypatch.setenv("TEST_MODE", "true")
        monkeypatch.setenv("TEST_SUMMARY_INTERVAL_MINUTES", "3")

        config = Config.from_env(channels_file=tmp_path / "nonexistent.yaml")

        assert config.effective_summary_interval_minutes == 3

    def test_effective_state_file_production(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """Test effective state file in production mode."""
        monkeypatch.setenv("TELEGRAM_API_ID", "12345")
        monkeypatch.setenv("TELEGRAM_API_HASH", "hash")
        monkeypatch.setenv("TELEGRAM_SESSION_STRING", "session")
        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "token")
        monkeypatch.setenv("OUTPUT_CHANNEL_ID", "@channel")
        monkeypatch.setenv("OPENROUTER_API_KEY", "key")
        monkeypatch.delenv("TEST_MODE", raising=False)

        config = Config.from_env(channels_file=tmp_path / "nonexistent.yaml")

        assert config.effective_state_file == Path(".last_check")

    def test_effective_state_file_test_mode(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """Test effective state file in test mode."""
        monkeypatch.setenv("TELEGRAM_API_ID", "12345")
        monkeypatch.setenv("TELEGRAM_API_HASH", "hash")
        monkeypatch.setenv("TELEGRAM_SESSION_STRING", "session")
        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "token")
        monkeypatch.setenv("OUTPUT_CHANNEL_ID", "@channel")
        monkeypatch.setenv("OPENROUTER_API_KEY", "key")
        monkeypatch.setenv("TEST_MODE", "true")
        monkeypatch.setenv("TEST_STATE_FILE", ".custom_test_state")

        config = Config.from_env(channels_file=tmp_path / "nonexistent.yaml")

        assert config.effective_state_file == Path(".custom_test_state")

    def test_test_output_dir(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """Test custom test output directory."""
        monkeypatch.setenv("TELEGRAM_API_ID", "12345")
        monkeypatch.setenv("TELEGRAM_API_HASH", "hash")
        monkeypatch.setenv("TELEGRAM_SESSION_STRING", "session")
        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "token")
        monkeypatch.setenv("OUTPUT_CHANNEL_ID", "@channel")
        monkeypatch.setenv("OPENROUTER_API_KEY", "key")
        monkeypatch.setenv("TEST_MODE", "true")
        monkeypatch.setenv("TEST_OUTPUT_DIR", "custom_output")

        config = Config.from_env(channels_file=tmp_path / "nonexistent.yaml")

        assert config.test_output_dir == Path("custom_output")

    def test_default_test_mode_values(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """Test default values for test mode settings."""
        monkeypatch.setenv("TELEGRAM_API_ID", "12345")
        monkeypatch.setenv("TELEGRAM_API_HASH", "hash")
        monkeypatch.setenv("TELEGRAM_SESSION_STRING", "session")
        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "token")
        monkeypatch.setenv("OUTPUT_CHANNEL_ID", "@channel")
        monkeypatch.setenv("OPENROUTER_API_KEY", "key")
        monkeypatch.setenv("TEST_MODE", "true")
        monkeypatch.delenv("TEST_SUMMARY_INTERVAL_MINUTES", raising=False)
        monkeypatch.delenv("TEST_OUTPUT_DIR", raising=False)
        monkeypatch.delenv("TEST_STATE_FILE", raising=False)

        config = Config.from_env(channels_file=tmp_path / "nonexistent.yaml")

        assert config.test_summary_interval_minutes == 5
        assert config.test_output_dir == Path("output")
        assert config.test_state_file == Path(".last_check.test")

class TestBaleConfig:
    """Tests for Bale configuration."""

    def test_bale_enabled_when_both_set(self) -> None:
        """Test bale_enabled is True when both token and channel are set."""
        config = Config(
            telegram_api_id=12345,
            telegram_api_hash="hash",
            telegram_session_string="session",
            telegram_bot_token="token",
            output_channel_id="@channel",
            openrouter_api_key="key",
            bale_bot_token="bale_token",
            bale_channel_id="@bale_channel",
        )
        assert config.bale_enabled is True

    def test_bale_disabled_when_token_missing(self) -> None:
        """Test bale_enabled is False when token is empty."""
        config = Config(
            telegram_api_id=12345,
            telegram_api_hash="hash",
            telegram_session_string="session",
            telegram_bot_token="token",
            output_channel_id="@channel",
            openrouter_api_key="key",
            bale_bot_token="",
            bale_channel_id="@bale_channel",
        )
        assert config.bale_enabled is False

    def test_bale_disabled_when_channel_missing(self) -> None:
        """Test bale_enabled is False when channel is empty."""
        config = Config(
            telegram_api_id=12345,
            telegram_api_hash="hash",
            telegram_session_string="session",
            telegram_bot_token="token",
            output_channel_id="@channel",
            openrouter_api_key="key",
            bale_bot_token="bale_token",
            bale_channel_id="",
        )
        assert config.bale_enabled is False

    def test_bale_disabled_by_default(self) -> None:
        """Test bale_enabled is False by default."""
        config = Config(
            telegram_api_id=12345,
            telegram_api_hash="hash",
            telegram_session_string="session",
            telegram_bot_token="token",
            output_channel_id="@channel",
            openrouter_api_key="key",
        )
        assert config.bale_enabled is False

    def test_bale_from_env(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """Test loading Bale config from environment variables."""
        monkeypatch.setenv("TELEGRAM_API_ID", "12345")
        monkeypatch.setenv("TELEGRAM_API_HASH", "hash")
        monkeypatch.setenv("TELEGRAM_SESSION_STRING", "session")
        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "token")
        monkeypatch.setenv("OUTPUT_CHANNEL_ID", "@channel")
        monkeypatch.setenv("OPENROUTER_API_KEY", "key")
        monkeypatch.setenv("BALE_BOT_TOKEN", "bale_token")
        monkeypatch.setenv("BALE_CHANNEL_ID", "@bale_channel")

        config = Config.from_env(channels_file=tmp_path / "nonexistent.yaml")

        assert config.bale_bot_token == "bale_token"
        assert config.bale_channel_id == "@bale_channel"
        assert config.bale_enabled is True
