"""Tests for data models."""

from datetime import datetime

from src.models import TEHRAN_TZ, Message, Summary


class TestMessage:
    """Tests for the Message model."""

    def test_message_creation(self) -> None:
        """Test creating a message with all fields."""
        msg = Message(
            id=123,
            channel_username="test_channel",
            channel_title="Test Channel",
            text="Test message content",
            timestamp=datetime(2024, 1, 15, 10, 30),
        )

        assert msg.id == 123
        assert msg.channel_username == "test_channel"
        assert msg.channel_title == "Test Channel"
        assert msg.text == "Test message content"
        assert msg.timestamp == datetime(2024, 1, 15, 10, 30)

    def test_message_url_generation(self) -> None:
        """Test that URL is auto-generated if not provided."""
        msg = Message(
            id=456,
            channel_username="my_channel",
            channel_title="My Channel",
            text="Content",
            timestamp=datetime.now(),
        )

        assert msg.url == "https://t.me/my_channel/456"

    def test_message_custom_url(self) -> None:
        """Test that custom URL is preserved."""
        custom_url = "https://t.me/custom/789"
        msg = Message(
            id=789,
            channel_username="channel",
            channel_title="Channel",
            text="Content",
            timestamp=datetime.now(),
            url=custom_url,
        )

        assert msg.url == custom_url

    def test_message_empty_username_no_url(self) -> None:
        """Test that empty username results in empty URL."""
        msg = Message(
            id=100,
            channel_username="",
            channel_title="No Username",
            text="Content",
            timestamp=datetime.now(),
        )

        assert msg.url == ""


class TestSummary:
    """Tests for the Summary model."""

    def test_summary_creation(self) -> None:
        """Test creating a summary with all fields."""
        created = datetime(2024, 1, 15, 11, 0)
        summary = Summary(
            content="This is a summary",
            source_count=5,
            channels=["Channel A", "Channel B"],
            created_at=created,
        )

        assert summary.content == "This is a summary"
        assert summary.source_count == 5
        assert summary.channels == ["Channel A", "Channel B"]
        assert summary.created_at == created

    def test_summary_default_timestamp(self) -> None:
        """Test that created_at defaults to now."""
        before = datetime.now()
        summary = Summary(
            content="Test",
            source_count=1,
            channels=["Test"],
        )
        after = datetime.now()

        assert before <= summary.created_at <= after

    def test_format_for_telegram(self) -> None:
        """Test formatting summary for Telegram posting."""
        # Use Tehran timezone for created_at so output matches expected time
        tehran_time = datetime(2024, 1, 15, 14, 30, tzinfo=TEHRAN_TZ)
        summary = Summary(
            content="خلاصه اخبار تست",
            source_count=3,
            channels=["Channel A", "Channel B"],
            channel_usernames=["channel_a", "channel_b"],
            created_at=tehran_time,
        )

        formatted = summary.format_for_telegram()

        # Check header elements
        assert "📰" in formatted
        assert "خلاصه اخبار" in formatted
        assert "2024-01-15 14:30" in formatted
        assert "(Tehran)" in formatted
        assert "📊" in formatted
        assert "3 خبر" in formatted
        assert "2 کانال" in formatted
        # Check source channels
        assert "📡 منابع:" in formatted
        assert "@channel_a" in formatted
        assert "@channel_b" in formatted
        # Check content
        assert "خلاصه اخبار تست" in formatted
        # Check separator
        assert "─" * 20 in formatted

    def test_format_for_telegram_single_channel(self) -> None:
        """Test formatting with a single channel."""
        summary = Summary(
            content="Content",
            source_count=1,
            channels=["Single Channel"],
            created_at=datetime(2024, 1, 15, 12, 0),
        )

        formatted = summary.format_for_telegram()

        assert "1 خبر" in formatted
        assert "1 کانال" in formatted
