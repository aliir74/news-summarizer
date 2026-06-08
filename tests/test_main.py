"""Tests for the main module."""

import json
from dataclasses import replace
from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.composite_writer import CompositeOutputWriter
from src.config import Config
from src.file_writer import FileWriter
from src.main import MAX_SEEN_URLS, SEEN_URLS_FILE, NewsSummarizer
from src.telegram_bot import TelegramBot


@pytest.fixture
def news_summarizer(sample_config: Config) -> NewsSummarizer:
    """Create a NewsSummarizer instance for testing."""
    return NewsSummarizer(sample_config)


@pytest.fixture
def test_mode_summarizer(sample_config: Config, tmp_path: Path) -> NewsSummarizer:
    """Create a NewsSummarizer instance with test mode enabled."""
    test_config = Config(
        telegram_api_id=sample_config.telegram_api_id,
        telegram_api_hash=sample_config.telegram_api_hash,
        telegram_session_string=sample_config.telegram_session_string,
        telegram_bot_token=sample_config.telegram_bot_token,
        output_channel_id=sample_config.output_channel_id,
        openrouter_api_key=sample_config.openrouter_api_key,
        channels=sample_config.channels,
        rss_feeds=sample_config.rss_feeds,
        iran_filter=sample_config.iran_filter,
        test_mode=True,
        test_output_dir=tmp_path / "output",
        test_state_file=tmp_path / ".last_check.test",
    )
    return NewsSummarizer(test_config)


class TestNewsSummarizer:
    """Tests for the NewsSummarizer class."""

    async def test_start_and_stop(self, news_summarizer: NewsSummarizer) -> None:
        """Test starting and stopping the summarizer."""
        with (
            patch.object(news_summarizer.telegram_reader, "start", new_callable=AsyncMock),
            patch.object(news_summarizer.rss_reader, "start", new_callable=AsyncMock),
            patch.object(news_summarizer.output_writer, "start", new_callable=AsyncMock),
            patch.object(news_summarizer.telegram_reader, "stop", new_callable=AsyncMock),
            patch.object(news_summarizer.rss_reader, "stop", new_callable=AsyncMock),
            patch.object(news_summarizer.output_writer, "stop", new_callable=AsyncMock),
        ):
            await news_summarizer.start()
            assert news_summarizer._running is True

            await news_summarizer.stop()
            assert news_summarizer._running is False


class TestCadenceLifecycle:
    """Tests for the adaptive cadence controller lifecycle in NewsSummarizer."""

    def test_controller_created_when_enabled(self, cadence_config: Config) -> None:
        """Test the controller is created when adaptive cadence is enabled."""
        summarizer = NewsSummarizer(cadence_config)

        assert summarizer.cadence_controller is not None

    def test_controller_none_when_disabled(self, news_summarizer: NewsSummarizer) -> None:
        """Test the controller stays None when adaptive cadence is disabled."""
        assert news_summarizer.cadence_controller is None

    def test_recent_radar_alert_defaults_false(
        self, news_summarizer: NewsSummarizer
    ) -> None:
        """Test the recent-radar-alert flag starts False."""
        assert news_summarizer._recent_radar_alert is False

    async def test_start_loads_and_stop_saves_state(self, cadence_config: Config) -> None:
        """Test start() loads cadence state and stop() saves it."""
        summarizer = NewsSummarizer(cadence_config)
        assert summarizer.cadence_controller is not None

        with (
            patch.object(summarizer.telegram_reader, "start", new_callable=AsyncMock),
            patch.object(summarizer.rss_reader, "start", new_callable=AsyncMock),
            patch.object(summarizer.output_writer, "start", new_callable=AsyncMock),
            patch.object(summarizer.telegram_reader, "stop", new_callable=AsyncMock),
            patch.object(summarizer.rss_reader, "stop", new_callable=AsyncMock),
            patch.object(summarizer.output_writer, "stop", new_callable=AsyncMock),
            patch.object(summarizer.cadence_controller, "_load_state") as mock_load,
            patch.object(summarizer.cadence_controller, "_save_state") as mock_save,
        ):
            await summarizer.start()
            mock_load.assert_called_once()

            await summarizer.stop()
            mock_save.assert_called_once()

    async def test_summarize_job_with_messages(
        self, news_summarizer: NewsSummarizer, sample_messages: list, sample_summary: MagicMock
    ) -> None:
        """Test the summarization job when messages are found."""
        with (
            patch.object(
                news_summarizer.telegram_reader,
                "get_all_channel_updates",
                new_callable=AsyncMock,
                return_value=sample_messages,
            ),
            patch.object(
                news_summarizer.rss_reader,
                "get_all_feed_updates",
                new_callable=AsyncMock,
                return_value=[],
            ),
            patch.object(
                news_summarizer.summarizer,
                "summarize_news",
                return_value=sample_summary,
            ),
            patch.object(
                news_summarizer.output_writer,
                "post_summary",
                new_callable=AsyncMock,
                return_value=True,
            ),
        ):
            await news_summarizer._summarize_job()

            news_summarizer.telegram_reader.get_all_channel_updates.assert_called_once()
            news_summarizer.rss_reader.get_all_feed_updates.assert_called_once()
            news_summarizer.summarizer.summarize_news.assert_called_once()
            news_summarizer.output_writer.post_summary.assert_called_once_with(sample_summary)

    async def test_summarize_job_no_messages(self, news_summarizer: NewsSummarizer) -> None:
        """Test the summarization job when no messages are found."""
        with (
            patch.object(
                news_summarizer.telegram_reader,
                "get_all_channel_updates",
                new_callable=AsyncMock,
                return_value=[],
            ),
            patch.object(
                news_summarizer.rss_reader,
                "get_all_feed_updates",
                new_callable=AsyncMock,
                return_value=[],
            ),
            patch.object(news_summarizer.summarizer, "summarize_news") as mock_summarize,
        ):
            await news_summarizer._summarize_job()

            mock_summarize.assert_not_called()

    async def test_summarize_job_summary_generation_fails(
        self, news_summarizer: NewsSummarizer, sample_messages: list
    ) -> None:
        """Test the summarization job when summary generation fails."""
        with (
            patch.object(
                news_summarizer.telegram_reader,
                "get_all_channel_updates",
                new_callable=AsyncMock,
                return_value=sample_messages,
            ),
            patch.object(
                news_summarizer.rss_reader,
                "get_all_feed_updates",
                new_callable=AsyncMock,
                return_value=[],
            ),
            patch.object(
                news_summarizer.summarizer,
                "summarize_news",
                return_value=None,
            ),
            patch.object(
                news_summarizer.output_writer, "post_summary", new_callable=AsyncMock
            ) as mock_post,
        ):
            await news_summarizer._summarize_job()

            mock_post.assert_not_called()

    async def test_summarize_job_with_rss_messages(
        self, news_summarizer: NewsSummarizer, sample_rss_messages: list, sample_summary: MagicMock
    ) -> None:
        """Test the summarization job with RSS messages."""
        with (
            patch.object(
                news_summarizer.telegram_reader,
                "get_all_channel_updates",
                new_callable=AsyncMock,
                return_value=[],
            ),
            patch.object(
                news_summarizer.rss_reader,
                "get_all_feed_updates",
                new_callable=AsyncMock,
                return_value=sample_rss_messages,
            ),
            patch.object(
                news_summarizer.summarizer,
                "summarize_news",
                return_value=sample_summary,
            ),
            patch.object(
                news_summarizer.output_writer,
                "post_summary",
                new_callable=AsyncMock,
                return_value=True,
            ),
        ):
            await news_summarizer._summarize_job()

            # Iran filter should filter the messages
            news_summarizer.summarizer.summarize_news.assert_called_once()
            # Should only have Iran-related messages
            # With keywords ["iran", "tehran"], only "Iran announces..." matches
            # (word boundary prevents "Iranian" from matching "iran")
            call_args = news_summarizer.summarizer.summarize_news.call_args[0][0]
            assert len(call_args) == 1
            assert "Iran" in call_args[0].text

    def test_load_last_check_file_exists(
        self, sample_config: Config, tmp_path: Path
    ) -> None:
        """Test loading last check timestamp from file."""
        # Create a temporary last check file
        last_check = datetime(2024, 1, 15, 10, 0)
        check_file = tmp_path / ".last_check"
        check_file.write_text(json.dumps({"last_check": last_check.isoformat()}))

        # Create config with custom state file
        config = Config(
            telegram_api_id=sample_config.telegram_api_id,
            telegram_api_hash=sample_config.telegram_api_hash,
            telegram_session_string=sample_config.telegram_session_string,
            telegram_bot_token=sample_config.telegram_bot_token,
            output_channel_id=sample_config.output_channel_id,
            openrouter_api_key=sample_config.openrouter_api_key,
            test_mode=True,
            test_state_file=check_file,
        )

        summarizer = NewsSummarizer(config)
        summarizer._load_last_check()

        assert summarizer._last_check == last_check

    def test_load_last_check_file_not_exists(self, sample_config: Config, tmp_path: Path) -> None:
        """Test loading last check when file doesn't exist."""
        config = Config(
            telegram_api_id=sample_config.telegram_api_id,
            telegram_api_hash=sample_config.telegram_api_hash,
            telegram_session_string=sample_config.telegram_session_string,
            telegram_bot_token=sample_config.telegram_bot_token,
            output_channel_id=sample_config.output_channel_id,
            openrouter_api_key=sample_config.openrouter_api_key,
            test_mode=True,
            test_state_file=tmp_path / "nonexistent" / ".last_check",
        )

        summarizer = NewsSummarizer(config)
        summarizer._load_last_check()

        assert summarizer._last_check is None

    def test_load_last_check_invalid_json(
        self, sample_config: Config, tmp_path: Path
    ) -> None:
        """Test loading last check with invalid JSON."""
        check_file = tmp_path / ".last_check"
        check_file.write_text("invalid json")

        config = Config(
            telegram_api_id=sample_config.telegram_api_id,
            telegram_api_hash=sample_config.telegram_api_hash,
            telegram_session_string=sample_config.telegram_session_string,
            telegram_bot_token=sample_config.telegram_bot_token,
            output_channel_id=sample_config.output_channel_id,
            openrouter_api_key=sample_config.openrouter_api_key,
            test_mode=True,
            test_state_file=check_file,
        )

        summarizer = NewsSummarizer(config)
        summarizer._load_last_check()

        assert summarizer._last_check is None

    def test_save_last_check(
        self, sample_config: Config, tmp_path: Path
    ) -> None:
        """Test saving last check timestamp to file."""
        check_file = tmp_path / ".last_check"

        config = Config(
            telegram_api_id=sample_config.telegram_api_id,
            telegram_api_hash=sample_config.telegram_api_hash,
            telegram_session_string=sample_config.telegram_session_string,
            telegram_bot_token=sample_config.telegram_bot_token,
            output_channel_id=sample_config.output_channel_id,
            openrouter_api_key=sample_config.openrouter_api_key,
            test_mode=True,
            test_state_file=check_file,
        )

        summarizer = NewsSummarizer(config)
        summarizer._last_check = datetime(2024, 1, 15, 11, 0)
        summarizer._save_last_check()

        # Verify file was written
        assert check_file.exists()
        data = json.loads(check_file.read_text())
        assert "last_check" in data

    def test_save_last_check_none(self, sample_config: Config, tmp_path: Path) -> None:
        """Test saving last check when timestamp is None."""
        check_file = tmp_path / ".last_check"

        config = Config(
            telegram_api_id=sample_config.telegram_api_id,
            telegram_api_hash=sample_config.telegram_api_hash,
            telegram_session_string=sample_config.telegram_session_string,
            telegram_bot_token=sample_config.telegram_bot_token,
            output_channel_id=sample_config.output_channel_id,
            openrouter_api_key=sample_config.openrouter_api_key,
            test_mode=True,
            test_state_file=check_file,
        )

        summarizer = NewsSummarizer(config)
        summarizer._last_check = None
        summarizer._save_last_check()

        # File should not be created
        assert not check_file.exists()


class TestSeenUrls:
    """Tests for seen URLs deduplication."""

    def test_load_seen_urls_file_exists(
        self, news_summarizer: NewsSummarizer, tmp_path: Path
    ) -> None:
        """Test loading seen URLs from file."""
        seen_urls = ["https://example.com/article1", "https://example.com/article2"]
        urls_file = tmp_path / ".seen_urls"
        urls_file.write_text(json.dumps({"urls": seen_urls}))

        with patch("src.main.SEEN_URLS_FILE", urls_file):
            news_summarizer._load_seen_urls()

        assert news_summarizer._seen_urls == set(seen_urls)

    def test_load_seen_urls_file_not_exists(self, news_summarizer: NewsSummarizer) -> None:
        """Test loading seen URLs when file doesn't exist."""
        with patch("src.main.SEEN_URLS_FILE", Path("/nonexistent/.seen_urls")):
            news_summarizer._load_seen_urls()

        assert news_summarizer._seen_urls == set()

    def test_load_seen_urls_invalid_json(
        self, news_summarizer: NewsSummarizer, tmp_path: Path
    ) -> None:
        """Test loading seen URLs with invalid JSON."""
        urls_file = tmp_path / ".seen_urls"
        urls_file.write_text("invalid json")

        with patch("src.main.SEEN_URLS_FILE", urls_file):
            news_summarizer._load_seen_urls()

        assert news_summarizer._seen_urls == set()

    def test_save_seen_urls(
        self, news_summarizer: NewsSummarizer, tmp_path: Path
    ) -> None:
        """Test saving seen URLs to file."""
        urls_file = tmp_path / ".seen_urls"
        news_summarizer._seen_urls = {"https://example.com/article1", "https://example.com/article2"}

        with patch("src.main.SEEN_URLS_FILE", urls_file):
            news_summarizer._save_seen_urls()

        assert urls_file.exists()
        data = json.loads(urls_file.read_text())
        assert "urls" in data
        assert set(data["urls"]) == news_summarizer._seen_urls

    def test_save_seen_urls_limits_size(
        self, news_summarizer: NewsSummarizer, tmp_path: Path
    ) -> None:
        """Test that saving seen URLs limits to MAX_SEEN_URLS."""
        urls_file = tmp_path / ".seen_urls"
        # Create more URLs than the max
        news_summarizer._seen_urls = {f"https://example.com/article{i}" for i in range(MAX_SEEN_URLS + 100)}

        with patch("src.main.SEEN_URLS_FILE", urls_file):
            news_summarizer._save_seen_urls()

        data = json.loads(urls_file.read_text())
        assert len(data["urls"]) == MAX_SEEN_URLS

    async def test_summarize_job_passes_seen_urls_to_rss_reader(
        self, news_summarizer: NewsSummarizer, sample_messages: list, sample_summary: MagicMock
    ) -> None:
        """Test that seen_urls are passed to the RSS reader."""
        news_summarizer._seen_urls = {"https://old.example.com/article1"}

        with (
            patch.object(
                news_summarizer.telegram_reader,
                "get_all_channel_updates",
                new_callable=AsyncMock,
                return_value=sample_messages,
            ),
            patch.object(
                news_summarizer.rss_reader,
                "get_all_feed_updates",
                new_callable=AsyncMock,
                return_value=[],
            ) as mock_rss,
            patch.object(
                news_summarizer.summarizer,
                "summarize_news",
                return_value=sample_summary,
            ),
            patch.object(
                news_summarizer.output_writer, "post_summary", new_callable=AsyncMock, return_value=True
            ),
        ):
            await news_summarizer._summarize_job()

            # Verify seen_urls was passed to get_all_feed_updates
            mock_rss.assert_called_once()
            call_kwargs = mock_rss.call_args[1]
            assert "seen_urls" in call_kwargs
            assert call_kwargs["seen_urls"] == news_summarizer._seen_urls

    async def test_summarize_job_adds_new_rss_urls_to_seen(
        self, news_summarizer: NewsSummarizer, sample_rss_messages: list, sample_summary: MagicMock
    ) -> None:
        """Test that new RSS article URLs are added to seen_urls after processing."""
        news_summarizer._seen_urls = set()

        with (
            patch.object(
                news_summarizer.telegram_reader,
                "get_all_channel_updates",
                new_callable=AsyncMock,
                return_value=[],
            ),
            patch.object(
                news_summarizer.rss_reader,
                "get_all_feed_updates",
                new_callable=AsyncMock,
                return_value=sample_rss_messages,
            ),
            patch.object(
                news_summarizer.summarizer,
                "summarize_news",
                return_value=sample_summary,
            ),
            patch.object(
                news_summarizer.output_writer, "post_summary", new_callable=AsyncMock, return_value=True
            ),
        ):
            await news_summarizer._summarize_job()

            # Only Iran-related messages are filtered and added
            # Based on sample_rss_messages fixture, only the Iran message passes
            assert len(news_summarizer._seen_urls) >= 1


class TestSeenUrlsFile:
    """Tests for seen URLs file path."""

    def test_seen_urls_file_path(self) -> None:
        """Test that SEEN_URLS_FILE is defined correctly."""
        assert SEEN_URLS_FILE == Path(".seen_urls")

    def test_max_seen_urls_constant(self) -> None:
        """Test that MAX_SEEN_URLS is defined."""
        assert MAX_SEEN_URLS == 1000


class TestTestMode:
    """Tests for test mode functionality."""

    def test_uses_file_writer_in_test_mode(self, test_mode_summarizer: NewsSummarizer) -> None:
        """Test that FileWriter is used in test mode."""
        assert isinstance(test_mode_summarizer.output_writer, FileWriter)

    def test_uses_telegram_bot_in_production(self, news_summarizer: NewsSummarizer) -> None:
        """Test that TelegramBot is used in production mode."""
        assert isinstance(news_summarizer.output_writer, TelegramBot)

    def test_uses_test_state_file(self, test_mode_summarizer: NewsSummarizer, tmp_path: Path) -> None:
        """Test that test mode uses separate state file."""
        assert test_mode_summarizer._state_file == tmp_path / ".last_check.test"

    def test_uses_production_state_file(self, news_summarizer: NewsSummarizer) -> None:
        """Test that production mode uses default state file."""
        assert news_summarizer._state_file == Path(".last_check")

    def test_effective_interval_in_test_mode(self, test_mode_summarizer: NewsSummarizer) -> None:
        """Test that test mode uses test interval."""
        assert test_mode_summarizer.config.effective_summary_interval_minutes == 5

    def test_effective_interval_in_production(self, news_summarizer: NewsSummarizer) -> None:
        """Test that production mode uses production interval."""
        assert news_summarizer.config.effective_summary_interval_minutes == 30

    def test_uses_composite_writer_when_bale_enabled(self, sample_config: Config) -> None:
        """Test that CompositeOutputWriter is used when Bale is enabled."""
        bale_config = replace(
            sample_config,
            bale_bot_token="bale_token",
            bale_channel_id="@bale_channel",
        )
        summarizer = NewsSummarizer(bale_config)
        assert isinstance(summarizer.output_writer, CompositeOutputWriter)

    def test_uses_telegram_only_when_bale_disabled(self, sample_config: Config) -> None:
        """Test that only TelegramBot is used when Bale is not configured."""
        summarizer = NewsSummarizer(sample_config)
        assert isinstance(summarizer.output_writer, TelegramBot)
