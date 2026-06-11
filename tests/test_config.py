"""Tests for configuration loading."""

from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from src.config import (
    AdaptiveCadenceConfig,
    Config,
    ConfigError,
    IranFilter,
    _load_sources_yaml,
)


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

    @patch("src.config.load_dotenv")
    def test_config_default_values(
        self, mock_load_dotenv: Any, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
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

        channels, rss_feeds, iran_filter, _, _, _ = _load_sources_yaml(channels_file)

        assert channels == ["channel1", "channel2", "channel3"]
        assert rss_feeds == []
        assert iran_filter.enabled is True

    def test_load_valid_yaml_new_format(self, tmp_path: Path) -> None:
        """Test loading valid YAML file with new telegram_channels format."""
        channels_file = tmp_path / "channels.yaml"
        channels_file.write_text(
            "telegram_channels:\n  - channel1\n  - channel2\n"
        )

        channels, rss_feeds, iran_filter, _, _, _ = _load_sources_yaml(channels_file)

        assert channels == ["channel1", "channel2"]

    def test_load_empty_yaml(self, tmp_path: Path) -> None:
        """Test loading empty YAML file."""
        channels_file = tmp_path / "channels.yaml"
        channels_file.write_text("")

        channels, rss_feeds, iran_filter, _, _, _ = _load_sources_yaml(channels_file)

        assert channels == []
        assert rss_feeds == []
        assert isinstance(iran_filter, IranFilter)

    def test_load_yaml_no_channels_key(self, tmp_path: Path) -> None:
        """Test loading YAML without channels key."""
        channels_file = tmp_path / "channels.yaml"
        channels_file.write_text("other_key: value\n")

        channels, rss_feeds, iran_filter, _, _, _ = _load_sources_yaml(channels_file)

        assert channels == []

    def test_load_yaml_with_none_values(self, tmp_path: Path) -> None:
        """Test loading YAML with null values in channels list."""
        channels_file = tmp_path / "channels.yaml"
        channels_file.write_text("channels:\n  - channel1\n  - \n  - channel2\n")

        channels, rss_feeds, iran_filter, _, _, _ = _load_sources_yaml(channels_file)

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

        channels, rss_feeds, iran_filter, _, _, _ = _load_sources_yaml(channels_file)

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

        channels, rss_feeds, iran_filter, _, _, _ = _load_sources_yaml(channels_file)

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

        channels, rss_feeds, iran_filter, _, _, _ = _load_sources_yaml(channels_file)

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

        channels, rss_feeds, iran_filter, _, _, _ = _load_sources_yaml(channels_file)

        assert iran_filter.enabled is True
        assert iran_filter.keywords == ["iran", "tehran"]

    def test_load_iran_filter_disabled(self, tmp_path: Path) -> None:
        """Test loading disabled Iran filter."""
        channels_file = tmp_path / "channels.yaml"
        channels_file.write_text(
            "iran_filter:\n"
            "  enabled: false\n"
        )

        channels, rss_feeds, iran_filter, _, _, _ = _load_sources_yaml(channels_file)

        assert iran_filter.enabled is False

    def test_load_adaptive_cadence_defaults_when_missing(self, tmp_path: Path) -> None:
        """Test adaptive_cadence falls back to a disabled default when absent."""
        channels_file = tmp_path / "channels.yaml"
        channels_file.write_text("channels:\n  - channel1\n")

        *_, adaptive_cadence = _load_sources_yaml(channels_file)

        assert isinstance(adaptive_cadence, AdaptiveCadenceConfig)
        assert adaptive_cadence.enabled is False
        assert adaptive_cadence.min_interval_minutes == 5
        assert adaptive_cadence.fast_escalation is False

    def test_load_adaptive_cadence_full(self, tmp_path: Path) -> None:
        """Test loading a full adaptive_cadence block with custom values."""
        channels_file = tmp_path / "channels.yaml"
        channels_file.write_text(
            "adaptive_cadence:\n"
            "  enabled: true\n"
            "  min_interval_minutes: 3\n"
            "  max_interval_minutes: 90\n"
            "  baseline_window: 6\n"
            "  elevated_ratio: 1.8\n"
            "  surge_ratio: 3.5\n"
            "  elevated_floor_rate: 0.5\n"
            "  surge_floor_rate: 1.2\n"
            "  decay_factor: 2.0\n"
            "  calm_streak_runs: 3\n"
            "  min_baseline_rate: 0.25\n"
            "  fast_escalation: true\n"
            "  probe_interval_minutes: 2\n"
            "  probe_window_minutes: 12\n"
        )

        *_, adaptive_cadence = _load_sources_yaml(channels_file)

        assert adaptive_cadence.enabled is True
        assert adaptive_cadence.probe_window_minutes == 12
        assert adaptive_cadence.min_interval_minutes == 3
        assert adaptive_cadence.max_interval_minutes == 90
        assert adaptive_cadence.baseline_window == 6
        assert adaptive_cadence.elevated_ratio == 1.8
        assert adaptive_cadence.surge_ratio == 3.5
        assert adaptive_cadence.elevated_floor_rate == 0.5
        assert adaptive_cadence.surge_floor_rate == 1.2
        assert adaptive_cadence.decay_factor == 2.0
        assert adaptive_cadence.calm_streak_runs == 3
        assert adaptive_cadence.min_baseline_rate == 0.25
        assert adaptive_cadence.fast_escalation is True
        assert adaptive_cadence.probe_interval_minutes == 2

    def test_load_adaptive_cadence_partial_fallback(self, tmp_path: Path) -> None:
        """Test a partial adaptive_cadence block falls back per-field."""
        channels_file = tmp_path / "channels.yaml"
        channels_file.write_text(
            "adaptive_cadence:\n"
            "  enabled: true\n"
            "  surge_ratio: 6.0\n"
        )

        *_, adaptive_cadence = _load_sources_yaml(channels_file)

        assert adaptive_cadence.enabled is True
        assert adaptive_cadence.surge_ratio == 6.0
        # Unspecified fields keep their defaults.
        assert adaptive_cadence.min_interval_minutes == 5
        assert adaptive_cadence.elevated_ratio == 2.0
        assert adaptive_cadence.max_interval_minutes is None

    def test_adaptive_cadence_in_config_from_env(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """Test Config.from_env exposes the loaded adaptive_cadence block."""
        monkeypatch.setenv("TELEGRAM_API_ID", "12345")
        monkeypatch.setenv("TELEGRAM_API_HASH", "hash")
        monkeypatch.setenv("TELEGRAM_SESSION_STRING", "session")
        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "token")
        monkeypatch.setenv("OUTPUT_CHANNEL_ID", "@channel")
        monkeypatch.setenv("OPENROUTER_API_KEY", "key")

        channels_file = tmp_path / "channels.yaml"
        channels_file.write_text("adaptive_cadence:\n  enabled: true\n")

        config = Config.from_env(channels_file=channels_file)

        assert config.adaptive_cadence.enabled is True

    def test_config_adaptive_cadence_default_disabled(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """Test adaptive cadence defaults to disabled when no YAML block."""
        monkeypatch.setenv("TELEGRAM_API_ID", "12345")
        monkeypatch.setenv("TELEGRAM_API_HASH", "hash")
        monkeypatch.setenv("TELEGRAM_SESSION_STRING", "session")
        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "token")
        monkeypatch.setenv("OUTPUT_CHANNEL_ID", "@channel")
        monkeypatch.setenv("OPENROUTER_API_KEY", "key")

        config = Config.from_env(channels_file=tmp_path / "nonexistent.yaml")

        assert config.adaptive_cadence.enabled is False

    def test_adaptive_cadence_rejects_non_converging_decay(self) -> None:
        """Test decay_factor <= 1.0 is rejected (would never decay)."""
        with pytest.raises(ConfigError, match="decay_factor"):
            AdaptiveCadenceConfig(decay_factor=1.0)

    def test_adaptive_cadence_rejects_zero_min_interval(self) -> None:
        """Test min_interval_minutes < 1 is rejected."""
        with pytest.raises(ConfigError, match="min_interval_minutes"):
            AdaptiveCadenceConfig(min_interval_minutes=0)

    def test_adaptive_cadence_rejects_zero_probe_interval(self) -> None:
        """Test probe_interval_minutes < 1 is rejected (div-by-zero / bad job)."""
        with pytest.raises(ConfigError, match="probe_interval_minutes"):
            AdaptiveCadenceConfig(probe_interval_minutes=0)

    def test_adaptive_cadence_rejects_zero_baseline_window(self) -> None:
        """Test baseline_window < 1 is rejected (would never trim the window)."""
        with pytest.raises(ConfigError, match="baseline_window"):
            AdaptiveCadenceConfig(baseline_window=0)

    def test_adaptive_cadence_rejects_zero_calm_streak_runs(self) -> None:
        """Test calm_streak_runs < 1 is rejected (no meaningful decay gate)."""
        with pytest.raises(ConfigError, match="calm_streak_runs"):
            AdaptiveCadenceConfig(calm_streak_runs=0)

    def test_adaptive_cadence_rejects_probe_window_below_interval(self) -> None:
        """Test a probe window narrower than the run cadence is rejected."""
        with pytest.raises(ConfigError, match="probe_window_minutes"):
            AdaptiveCadenceConfig(probe_interval_minutes=10, probe_window_minutes=5)

    def test_adaptive_cadence_rejects_negative_elevated_floor(self) -> None:
        """Test a negative elevated_floor_rate is rejected."""
        with pytest.raises(ConfigError, match="elevated_floor_rate"):
            AdaptiveCadenceConfig(elevated_floor_rate=-0.1)

    def test_adaptive_cadence_rejects_surge_floor_below_elevated_floor(self) -> None:
        """Test surge_floor_rate below elevated_floor_rate is rejected."""
        with pytest.raises(ConfigError, match="surge_floor_rate"):
            AdaptiveCadenceConfig(elevated_floor_rate=1.0, surge_floor_rate=0.5)

    def test_adaptive_cadence_parses_floor_rates(self) -> None:
        """Test the absolute floor rates parse from a YAML adaptive_cadence block."""
        defaults = AdaptiveCadenceConfig()
        assert defaults.elevated_floor_rate == 0.75
        assert defaults.surge_floor_rate == 1.5

    def test_invalid_cadence_yaml_propagates_config_error(self, tmp_path: Path) -> None:
        """Test an invalid adaptive_cadence block raises ConfigError on load."""
        channels_file = tmp_path / "channels.yaml"
        channels_file.write_text(
            "adaptive_cadence:\n  enabled: true\n  decay_factor: 1.0\n"
        )

        with pytest.raises(ConfigError, match="decay_factor"):
            _load_sources_yaml(channels_file)

    def test_min_interval_exceeding_summary_rejected(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """Test min_interval_minutes > SUMMARY_INTERVAL_MINUTES is rejected."""
        monkeypatch.setenv("TELEGRAM_API_ID", "12345")
        monkeypatch.setenv("TELEGRAM_API_HASH", "hash")
        monkeypatch.setenv("TELEGRAM_SESSION_STRING", "session")
        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "token")
        monkeypatch.setenv("OUTPUT_CHANNEL_ID", "@channel")
        monkeypatch.setenv("OPENROUTER_API_KEY", "key")
        monkeypatch.setenv("SUMMARY_INTERVAL_MINUTES", "10")

        channels_file = tmp_path / "channels.yaml"
        channels_file.write_text(
            "adaptive_cadence:\n  enabled: true\n  min_interval_minutes: 20\n"
        )

        with pytest.raises(ConfigError, match="cannot exceed"):
            Config.from_env(channels_file=channels_file)

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

        channels, rss_feeds, iran_filter, _, _, _ = _load_sources_yaml(channels_file)

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


class TestConfigCoverage:
    """Tests for config branches missed elsewhere (coverage completeness)."""

    def _set_required_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Set the six required environment variables."""
        monkeypatch.setenv("TELEGRAM_API_ID", "12345")
        monkeypatch.setenv("TELEGRAM_API_HASH", "test_hash")
        monkeypatch.setenv("TELEGRAM_SESSION_STRING", "test_session")
        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "test_token")
        monkeypatch.setenv("OUTPUT_CHANNEL_ID", "@test_channel")
        monkeypatch.setenv("OPENROUTER_API_KEY", "test_key")

    @patch("src.config.load_dotenv")
    def test_test_mode_prefers_test_channels_file(
        self, _mock_dotenv: Any, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """In test mode, config/channels.test.yaml is preferred when present."""
        self._set_required_env(monkeypatch)
        monkeypatch.setenv("TEST_MODE", "true")
        config_dir = tmp_path / "config"
        config_dir.mkdir()
        (config_dir / "channels.test.yaml").write_text("channels:\n  - test_channel\n")
        (config_dir / "channels.yaml").write_text("channels:\n  - prod_channel\n")
        monkeypatch.chdir(tmp_path)

        config = Config.from_env()

        assert config.channels == ["test_channel"]

    @patch("src.config.load_dotenv")
    def test_test_mode_falls_back_to_default_channels_file(
        self, _mock_dotenv: Any, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """In test mode with no test file, config/channels.yaml is used."""
        self._set_required_env(monkeypatch)
        monkeypatch.setenv("TEST_MODE", "true")
        config_dir = tmp_path / "config"
        config_dir.mkdir()
        (config_dir / "channels.yaml").write_text("channels:\n  - prod_channel\n")
        monkeypatch.chdir(tmp_path)

        config = Config.from_env()

        assert config.channels == ["prod_channel"]

    def test_load_sources_yaml_raises_on_os_error(self, tmp_path: Path) -> None:
        """An unreadable sources file raises ConfigError."""
        missing = tmp_path / "does_not_exist.yaml"
        with pytest.raises(ConfigError, match="Could not read sources file"):
            _load_sources_yaml(missing)
