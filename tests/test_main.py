"""Tests for the main module."""

import json
from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.config import Config
from src.main import LAST_CHECK_FILE, NewsSummarizer


@pytest.fixture
def news_summarizer(sample_config: Config) -> NewsSummarizer:
    """Create a NewsSummarizer instance for testing."""
    return NewsSummarizer(sample_config)


class TestNewsSummarizer:
    """Tests for the NewsSummarizer class."""

    async def test_start_and_stop(self, news_summarizer: NewsSummarizer) -> None:
        """Test starting and stopping the summarizer."""
        with (
            patch.object(news_summarizer.reader, "start", new_callable=AsyncMock),
            patch.object(news_summarizer.bot, "start", new_callable=AsyncMock),
            patch.object(news_summarizer.reader, "stop", new_callable=AsyncMock),
            patch.object(news_summarizer.bot, "stop", new_callable=AsyncMock),
        ):
            await news_summarizer.start()
            assert news_summarizer._running is True

            await news_summarizer.stop()
            assert news_summarizer._running is False

    async def test_summarize_job_with_messages(
        self, news_summarizer: NewsSummarizer, sample_messages: list, sample_summary: MagicMock
    ) -> None:
        """Test the summarization job when messages are found."""
        with (
            patch.object(
                news_summarizer.reader,
                "get_all_channel_updates",
                new_callable=AsyncMock,
                return_value=sample_messages,
            ),
            patch.object(
                news_summarizer.summarizer,
                "summarize_news",
                return_value=sample_summary,
            ),
            patch.object(
                news_summarizer.bot, "post_summary", new_callable=AsyncMock, return_value=True
            ),
        ):
            await news_summarizer._summarize_job()

            news_summarizer.reader.get_all_channel_updates.assert_called_once()
            news_summarizer.summarizer.summarize_news.assert_called_once_with(sample_messages)
            news_summarizer.bot.post_summary.assert_called_once_with(sample_summary)

    async def test_summarize_job_no_messages(self, news_summarizer: NewsSummarizer) -> None:
        """Test the summarization job when no messages are found."""
        with (
            patch.object(
                news_summarizer.reader,
                "get_all_channel_updates",
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
                news_summarizer.reader,
                "get_all_channel_updates",
                new_callable=AsyncMock,
                return_value=sample_messages,
            ),
            patch.object(
                news_summarizer.summarizer,
                "summarize_news",
                return_value=None,
            ),
            patch.object(news_summarizer.bot, "post_summary", new_callable=AsyncMock) as mock_post,
        ):
            await news_summarizer._summarize_job()

            mock_post.assert_not_called()

    def test_load_last_check_file_exists(
        self, news_summarizer: NewsSummarizer, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test loading last check timestamp from file."""
        # Create a temporary last check file
        last_check = datetime(2024, 1, 15, 10, 0)
        check_file = tmp_path / ".last_check"
        check_file.write_text(json.dumps({"last_check": last_check.isoformat()}))

        # Patch the LAST_CHECK_FILE constant
        with patch("src.main.LAST_CHECK_FILE", check_file):
            news_summarizer._load_last_check()

        assert news_summarizer._last_check == last_check

    def test_load_last_check_file_not_exists(self, news_summarizer: NewsSummarizer) -> None:
        """Test loading last check when file doesn't exist."""
        with patch("src.main.LAST_CHECK_FILE", Path("/nonexistent/.last_check")):
            news_summarizer._load_last_check()

        assert news_summarizer._last_check is None

    def test_load_last_check_invalid_json(
        self, news_summarizer: NewsSummarizer, tmp_path: Path
    ) -> None:
        """Test loading last check with invalid JSON."""
        check_file = tmp_path / ".last_check"
        check_file.write_text("invalid json")

        with patch("src.main.LAST_CHECK_FILE", check_file):
            news_summarizer._load_last_check()

        assert news_summarizer._last_check is None

    def test_save_last_check(
        self, news_summarizer: NewsSummarizer, tmp_path: Path
    ) -> None:
        """Test saving last check timestamp to file."""
        check_file = tmp_path / ".last_check"
        news_summarizer._last_check = datetime(2024, 1, 15, 11, 0)

        with patch("src.main.LAST_CHECK_FILE", check_file):
            news_summarizer._save_last_check()

        # Verify file was written
        assert check_file.exists()
        data = json.loads(check_file.read_text())
        assert "last_check" in data

    def test_save_last_check_none(self, news_summarizer: NewsSummarizer, tmp_path: Path) -> None:
        """Test saving last check when timestamp is None."""
        check_file = tmp_path / ".last_check"
        news_summarizer._last_check = None

        with patch("src.main.LAST_CHECK_FILE", check_file):
            news_summarizer._save_last_check()

        # File should not be created
        assert not check_file.exists()


class TestLastCheckFile:
    """Tests for last check file path."""

    def test_last_check_file_path(self) -> None:
        """Test that LAST_CHECK_FILE is defined correctly."""
        assert LAST_CHECK_FILE == Path(".last_check")
