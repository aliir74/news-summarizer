"""Tests for the Telegram bot module."""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.config import Config
from src.models import Summary
from src.telegram_bot import TelegramBot


@pytest.fixture
def bot(sample_config: Config) -> TelegramBot:
    """Create a TelegramBot instance for testing."""
    return TelegramBot(sample_config)


class TestTelegramBot:
    """Tests for the TelegramBot class."""

    async def test_start_client(self, bot: TelegramBot) -> None:
        """Test starting the bot client."""
        with patch("src.telegram_bot.Client") as mock_client_class:
            mock_client = MagicMock()
            mock_client.start = AsyncMock()
            mock_client_class.return_value = mock_client

            await bot.start()

            mock_client_class.assert_called_once()
            # Verify bot_token was passed
            call_kwargs = mock_client_class.call_args.kwargs
            assert "bot_token" in call_kwargs

    async def test_stop_client(self, bot: TelegramBot) -> None:
        """Test stopping the bot client."""
        with patch("src.telegram_bot.Client") as mock_client_class:
            mock_client = MagicMock()
            mock_client.start = AsyncMock()
            mock_client.stop = AsyncMock()
            mock_client_class.return_value = mock_client

            await bot.start()
            await bot.stop()

            mock_client.stop.assert_called_once()

    async def test_stop_without_start(self, bot: TelegramBot) -> None:
        """Test stopping without starting does not raise."""
        await bot.stop()  # Should not raise

    def test_client_property_not_started(self, bot: TelegramBot) -> None:
        """Test accessing client before start raises error."""
        with pytest.raises(RuntimeError) as exc_info:
            _ = bot.client

        assert "not started" in str(exc_info.value)

    async def test_post_summary_success(
        self, bot: TelegramBot, sample_summary: Summary
    ) -> None:
        """Test successful summary posting."""
        with patch("src.telegram_bot.Client") as mock_client_class:
            mock_client = MagicMock()
            mock_client.start = AsyncMock()
            mock_client.send_message = AsyncMock()
            mock_client_class.return_value = mock_client

            await bot.start()
            result = await bot.post_summary(sample_summary)

        assert result is True
        mock_client.send_message.assert_called_once()

    async def test_post_summary_failure(
        self, bot: TelegramBot, sample_summary: Summary
    ) -> None:
        """Test handling of posting failure."""
        with patch("src.telegram_bot.Client") as mock_client_class:
            mock_client = MagicMock()
            mock_client.start = AsyncMock()
            mock_client.send_message = AsyncMock(side_effect=Exception("API Error"))
            mock_client_class.return_value = mock_client

            await bot.start()
            result = await bot.post_summary(sample_summary)

        assert result is False

    async def test_post_summary_correct_channel(
        self, bot: TelegramBot, sample_summary: Summary
    ) -> None:
        """Test that summary is posted to correct channel."""
        with patch("src.telegram_bot.Client") as mock_client_class:
            mock_client = MagicMock()
            mock_client.start = AsyncMock()
            mock_client.send_message = AsyncMock()
            mock_client_class.return_value = mock_client

            await bot.start()
            await bot.post_summary(sample_summary)

            call_kwargs = mock_client.send_message.call_args.kwargs
            assert call_kwargs["chat_id"] == "@test_channel"


class TestLongSummary:
    """Tests for posting long summaries."""

    async def test_post_long_summary_splits_correctly(
        self, bot: TelegramBot
    ) -> None:
        """Test that long summaries are split and sent as multiple messages."""
        long_content = "x" * 5000
        long_summary = Summary(
            content=long_content,
            source_count=10,
            channels=["Channel A", "Channel B"],
            created_at=datetime(2024, 1, 15, 11, 0),
        )

        with patch("src.telegram_bot.Client") as mock_client_class:
            mock_client = MagicMock()
            mock_client.start = AsyncMock()
            mock_client.send_message = AsyncMock()
            mock_client_class.return_value = mock_client

            await bot.start()
            await bot.post_summary(long_summary)

            assert mock_client.send_message.call_count > 1
