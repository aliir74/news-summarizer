"""Tests for the Telegram bot module."""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.config import Config
from src.models import Summary
from src.telegram_bot import MAX_MESSAGE_LENGTH, TelegramBot


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


class TestMessageSplitting:
    """Tests for message splitting functionality."""

    def test_split_short_message(self, bot: TelegramBot) -> None:
        """Test that short messages are not split."""
        text = "Short message"
        result = bot._split_message(text)

        assert len(result) == 1
        assert result[0] == text

    def test_split_message_at_max_length(self, bot: TelegramBot) -> None:
        """Test message exactly at max length."""
        text = "x" * MAX_MESSAGE_LENGTH
        result = bot._split_message(text)

        assert len(result) == 1

    def test_split_long_message_by_paragraphs(self, bot: TelegramBot) -> None:
        """Test splitting long message by paragraphs."""
        # Create text with multiple paragraphs that exceeds limit
        paragraph = "This is a paragraph. " * 100  # ~2100 chars
        text = f"{paragraph}\n\n{paragraph}\n\n{paragraph}"

        result = bot._split_message(text)

        # Should be split into multiple messages
        assert len(result) > 1
        # Each part should be under the limit
        for part in result:
            assert len(part) <= MAX_MESSAGE_LENGTH

    def test_split_long_single_paragraph(self, bot: TelegramBot) -> None:
        """Test splitting a single very long paragraph."""
        # Create a single long paragraph with sentences
        sentences = [f"This is sentence number {i}. " for i in range(200)]
        text = "".join(sentences)

        result = bot._split_message(text)

        assert len(result) > 1
        for part in result:
            assert len(part) <= MAX_MESSAGE_LENGTH

    def test_split_preserves_content(self, bot: TelegramBot) -> None:
        """Test that splitting preserves all content."""
        paragraph1 = "First paragraph content."
        paragraph2 = "Second paragraph content."
        text = f"{paragraph1}\n\n{paragraph2}"

        result = bot._split_message(text)

        combined = " ".join(result)
        assert "First paragraph" in combined
        assert "Second paragraph" in combined

    def test_split_empty_message(self, bot: TelegramBot) -> None:
        """Test splitting empty message."""
        result = bot._split_message("")

        assert len(result) == 1
        assert result[0] == ""

    async def test_post_long_summary_splits_correctly(
        self, bot: TelegramBot
    ) -> None:
        """Test that long summaries are split and sent as multiple messages."""
        # Create a long summary
        long_content = "خلاصه طولانی. " * 500  # Very long content
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

            # Should have been called multiple times
            assert mock_client.send_message.call_count > 1
