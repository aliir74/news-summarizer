"""Tests for configuration loading."""

from pathlib import Path

import pytest

from src.config import Config, ConfigError, _load_channels_yaml


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

    def test_config_missing_env_var(self, monkeypatch: pytest.MonkeyPatch) -> None:
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
        assert config.llm_model == "google/gemma-2-9b-it"
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


class TestLoadChannelsYaml:
    """Tests for channel YAML loading."""

    def test_load_valid_yaml(self, tmp_path: Path) -> None:
        """Test loading valid YAML file."""
        channels_file = tmp_path / "channels.yaml"
        channels_file.write_text("channels:\n  - channel1\n  - channel2\n  - channel3\n")

        channels = _load_channels_yaml(channels_file)

        assert channels == ["channel1", "channel2", "channel3"]

    def test_load_empty_yaml(self, tmp_path: Path) -> None:
        """Test loading empty YAML file."""
        channels_file = tmp_path / "channels.yaml"
        channels_file.write_text("")

        channels = _load_channels_yaml(channels_file)

        assert channels == []

    def test_load_yaml_no_channels_key(self, tmp_path: Path) -> None:
        """Test loading YAML without channels key."""
        channels_file = tmp_path / "channels.yaml"
        channels_file.write_text("other_key: value\n")

        channels = _load_channels_yaml(channels_file)

        assert channels == []

    def test_load_yaml_with_none_values(self, tmp_path: Path) -> None:
        """Test loading YAML with null values in channels list."""
        channels_file = tmp_path / "channels.yaml"
        channels_file.write_text("channels:\n  - channel1\n  - \n  - channel2\n")

        channels = _load_channels_yaml(channels_file)

        assert channels == ["channel1", "channel2"]

    def test_load_invalid_yaml(self, tmp_path: Path) -> None:
        """Test loading invalid YAML file."""
        channels_file = tmp_path / "channels.yaml"
        channels_file.write_text("invalid: yaml: content: [")

        with pytest.raises(ConfigError) as exc_info:
            _load_channels_yaml(channels_file)

        assert "Invalid YAML" in str(exc_info.value)

    def test_load_yaml_channels_not_list(self, tmp_path: Path) -> None:
        """Test loading YAML where channels is not a list."""
        channels_file = tmp_path / "channels.yaml"
        channels_file.write_text("channels: not_a_list\n")

        channels = _load_channels_yaml(channels_file)

        assert channels == []
