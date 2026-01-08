"""Tests for the Telegram reader module."""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.config import Config
from src.telegram_reader import TelegramReader


@pytest.fixture
def reader(sample_config: Config) -> TelegramReader:
    """Create a TelegramReader instance for testing."""
    return TelegramReader(sample_config)


class TestTelegramReader:
    """Tests for the TelegramReader class."""

    async def test_start_client(self, reader: TelegramReader) -> None:
        """Test starting the Pyrogram client."""
        with patch("src.telegram_reader.Client") as mock_client_class:
            mock_client = MagicMock()
            mock_client.start = AsyncMock()
            mock_client_class.return_value = mock_client

            await reader.start()

            mock_client_class.assert_called_once()
            mock_client.start.assert_called_once()

    async def test_stop_client(self, reader: TelegramReader) -> None:
        """Test stopping the Pyrogram client."""
        with patch("src.telegram_reader.Client") as mock_client_class:
            mock_client = MagicMock()
            mock_client.start = AsyncMock()
            mock_client.stop = AsyncMock()
            mock_client_class.return_value = mock_client

            await reader.start()
            await reader.stop()

            mock_client.stop.assert_called_once()

    async def test_stop_without_start(self, reader: TelegramReader) -> None:
        """Test stopping without starting does not raise."""
        await reader.stop()  # Should not raise

    def test_client_property_not_started(self, reader: TelegramReader) -> None:
        """Test accessing client before start raises error."""
        with pytest.raises(RuntimeError) as exc_info:
            _ = reader.client

        assert "not started" in str(exc_info.value)

    async def test_get_recent_messages(self, reader: TelegramReader) -> None:
        """Test fetching recent messages from a channel."""
        mock_chat = MagicMock()
        mock_chat.title = "Test Channel"

        mock_msg1 = MagicMock()
        mock_msg1.id = 1
        mock_msg1.text = "Message 1"
        mock_msg1.caption = None
        mock_msg1.date = datetime(2024, 1, 15, 10, 30)

        mock_msg2 = MagicMock()
        mock_msg2.id = 2
        mock_msg2.text = "Message 2"
        mock_msg2.caption = None
        mock_msg2.date = datetime(2024, 1, 15, 10, 35)

        mock_msg_old = MagicMock()
        mock_msg_old.id = 0
        mock_msg_old.text = "Old message"
        mock_msg_old.caption = None
        mock_msg_old.date = datetime(2024, 1, 15, 9, 0)  # Before 'since'

        async def mock_history(*args, **kwargs):
            for msg in [mock_msg2, mock_msg1, mock_msg_old]:
                yield msg

        with patch("src.telegram_reader.Client") as mock_client_class:
            mock_client = MagicMock()
            mock_client.start = AsyncMock()
            mock_client.get_chat = AsyncMock(return_value=mock_chat)
            mock_client.get_chat_history = mock_history
            mock_client_class.return_value = mock_client

            await reader.start()

            since = datetime(2024, 1, 15, 10, 0)
            messages = await reader.get_recent_messages("test_channel", since)

        # Should only return messages newer than 'since'
        assert len(messages) == 2
        assert messages[0].id == 2
        assert messages[1].id == 1

    async def test_get_recent_messages_with_caption(self, reader: TelegramReader) -> None:
        """Test fetching messages that have caption instead of text."""
        mock_chat = MagicMock()
        mock_chat.title = "Test Channel"

        mock_msg = MagicMock()
        mock_msg.id = 1
        mock_msg.text = None  # No text
        mock_msg.caption = "Image caption"  # Has caption
        mock_msg.date = datetime(2024, 1, 15, 10, 30)

        async def mock_history(*args, **kwargs):
            yield mock_msg

        with patch("src.telegram_reader.Client") as mock_client_class:
            mock_client = MagicMock()
            mock_client.start = AsyncMock()
            mock_client.get_chat = AsyncMock(return_value=mock_chat)
            mock_client.get_chat_history = mock_history
            mock_client_class.return_value = mock_client

            await reader.start()

            since = datetime(2024, 1, 15, 10, 0)
            messages = await reader.get_recent_messages("test_channel", since)

        assert len(messages) == 1
        assert messages[0].text == "Image caption"

    async def test_get_recent_messages_skip_media_only(
        self, reader: TelegramReader
    ) -> None:
        """Test that messages without text or caption are skipped."""
        mock_chat = MagicMock()
        mock_chat.title = "Test Channel"

        mock_msg_text = MagicMock()
        mock_msg_text.id = 1
        mock_msg_text.text = "Has text"
        mock_msg_text.caption = None
        mock_msg_text.date = datetime(2024, 1, 15, 10, 30)

        mock_msg_media = MagicMock()
        mock_msg_media.id = 2
        mock_msg_media.text = None
        mock_msg_media.caption = None  # Pure media, no text
        mock_msg_media.date = datetime(2024, 1, 15, 10, 35)

        async def mock_history(*args, **kwargs):
            for msg in [mock_msg_media, mock_msg_text]:
                yield msg

        with patch("src.telegram_reader.Client") as mock_client_class:
            mock_client = MagicMock()
            mock_client.start = AsyncMock()
            mock_client.get_chat = AsyncMock(return_value=mock_chat)
            mock_client.get_chat_history = mock_history
            mock_client_class.return_value = mock_client

            await reader.start()

            since = datetime(2024, 1, 15, 10, 0)
            messages = await reader.get_recent_messages("test_channel", since)

        # Only message with text should be returned
        assert len(messages) == 1
        assert messages[0].id == 1

    async def test_get_recent_messages_channel_not_found(
        self, reader: TelegramReader
    ) -> None:
        """Test handling of channel not found error."""
        from pyrogram.errors import UsernameNotOccupied

        with patch("src.telegram_reader.Client") as mock_client_class:
            mock_client = MagicMock()
            mock_client.start = AsyncMock()
            mock_client.get_chat = AsyncMock(side_effect=UsernameNotOccupied)
            mock_client_class.return_value = mock_client

            await reader.start()

            since = datetime(2024, 1, 15, 10, 0)
            messages = await reader.get_recent_messages("nonexistent", since)

        assert messages == []

    async def test_get_recent_messages_private_channel(
        self, reader: TelegramReader
    ) -> None:
        """Test handling of private channel error."""
        from pyrogram.errors import ChannelPrivate

        with patch("src.telegram_reader.Client") as mock_client_class:
            mock_client = MagicMock()
            mock_client.start = AsyncMock()
            mock_client.get_chat = AsyncMock(side_effect=ChannelPrivate)
            mock_client_class.return_value = mock_client

            await reader.start()

            since = datetime(2024, 1, 15, 10, 0)
            messages = await reader.get_recent_messages("private_channel", since)

        assert messages == []

    async def test_get_all_channel_updates(self, reader: TelegramReader) -> None:
        """Test fetching updates from all configured channels."""
        mock_chat = MagicMock()
        mock_chat.title = "Test Channel"

        mock_msg1 = MagicMock()
        mock_msg1.id = 1
        mock_msg1.text = "Message from channel 1"
        mock_msg1.caption = None
        mock_msg1.date = datetime(2024, 1, 15, 10, 30)

        mock_msg2 = MagicMock()
        mock_msg2.id = 2
        mock_msg2.text = "Message from channel 2"
        mock_msg2.caption = None
        mock_msg2.date = datetime(2024, 1, 15, 10, 35)

        call_count = 0

        async def mock_history(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                yield mock_msg1
            else:
                yield mock_msg2

        with patch("src.telegram_reader.Client") as mock_client_class:
            mock_client = MagicMock()
            mock_client.start = AsyncMock()
            mock_client.get_chat = AsyncMock(return_value=mock_chat)
            mock_client.get_chat_history = mock_history
            mock_client_class.return_value = mock_client

            await reader.start()

            since = datetime(2024, 1, 15, 10, 0)
            messages = await reader.get_all_channel_updates(since)

        # Should have messages from both channels
        assert len(messages) == 2
        # Should be sorted by timestamp (newest first)
        assert messages[0].timestamp > messages[1].timestamp
