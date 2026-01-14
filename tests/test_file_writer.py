"""Tests for the file writer module."""

from datetime import datetime
from pathlib import Path

import pytest

from src.config import Config
from src.file_writer import FileWriter
from src.models import Summary


@pytest.fixture
def test_mode_config(sample_config: Config, tmp_path: Path) -> Config:
    """Create a test config with test mode enabled."""
    return Config(
        telegram_api_id=sample_config.telegram_api_id,
        telegram_api_hash=sample_config.telegram_api_hash,
        telegram_session_string=sample_config.telegram_session_string,
        telegram_bot_token=sample_config.telegram_bot_token,
        output_channel_id=sample_config.output_channel_id,
        openrouter_api_key=sample_config.openrouter_api_key,
        test_mode=True,
        test_output_dir=tmp_path / "output",
    )


@pytest.fixture
def file_writer(test_mode_config: Config) -> FileWriter:
    """Create a FileWriter instance for testing."""
    return FileWriter(test_mode_config)


class TestFileWriter:
    """Tests for the FileWriter class."""

    async def test_start_creates_output_dir(
        self, file_writer: FileWriter, test_mode_config: Config
    ) -> None:
        """Test that start creates the output directory."""
        await file_writer.start()
        assert test_mode_config.test_output_dir.exists()

    async def test_stop_does_not_raise(self, file_writer: FileWriter) -> None:
        """Test that stop does not raise."""
        await file_writer.start()
        await file_writer.stop()  # Should not raise

    async def test_post_summary_creates_file(
        self, file_writer: FileWriter, sample_summary: Summary, test_mode_config: Config
    ) -> None:
        """Test that post_summary creates the output file."""
        await file_writer.start()
        result = await file_writer.post_summary(sample_summary)

        assert result is True
        output_file = test_mode_config.test_output_dir / "summaries.txt"
        assert output_file.exists()

    async def test_post_summary_appends(
        self, file_writer: FileWriter, sample_summary: Summary, test_mode_config: Config
    ) -> None:
        """Test that multiple summaries are appended."""
        await file_writer.start()
        await file_writer.post_summary(sample_summary)
        await file_writer.post_summary(sample_summary)

        output_file = test_mode_config.test_output_dir / "summaries.txt"
        content = output_file.read_text()
        # Should have two separators (60 "=" chars per separator, 2 per summary)
        assert content.count("=" * 60) == 4

    async def test_post_summary_contains_content(
        self, file_writer: FileWriter, sample_summary: Summary, test_mode_config: Config
    ) -> None:
        """Test that output contains the summary content."""
        await file_writer.start()
        await file_writer.post_summary(sample_summary)

        output_file = test_mode_config.test_output_dir / "summaries.txt"
        content = output_file.read_text()
        assert sample_summary.content in content

    async def test_post_summary_contains_timestamp(
        self, file_writer: FileWriter, sample_summary: Summary, test_mode_config: Config
    ) -> None:
        """Test that output contains the write timestamp."""
        await file_writer.start()
        await file_writer.post_summary(sample_summary)

        output_file = test_mode_config.test_output_dir / "summaries.txt"
        content = output_file.read_text()
        assert "Written at:" in content

    async def test_post_summary_returns_false_on_error(
        self, test_mode_config: Config
    ) -> None:
        """Test that post_summary returns False on write error."""
        # Create file writer with invalid directory path
        invalid_config = Config(
            telegram_api_id=test_mode_config.telegram_api_id,
            telegram_api_hash=test_mode_config.telegram_api_hash,
            telegram_session_string=test_mode_config.telegram_session_string,
            telegram_bot_token=test_mode_config.telegram_bot_token,
            output_channel_id=test_mode_config.output_channel_id,
            openrouter_api_key=test_mode_config.openrouter_api_key,
            test_mode=True,
            test_output_dir=Path("/nonexistent/path/that/does/not/exist"),
        )
        file_writer = FileWriter(invalid_config)

        summary = Summary(
            content="Test content",
            source_count=1,
            channels=["test"],
            created_at=datetime.now(),
        )

        # Don't call start() so directory isn't created
        result = await file_writer.post_summary(summary)
        assert result is False
