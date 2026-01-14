"""Tests for the summarizer module."""

from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest

from src.config import Config
from src.models import Message, SourceType
from src.summarizer import SUMMARIZATION_PROMPT, Summarizer


@pytest.fixture
def summarizer(sample_config: Config) -> Summarizer:
    """Create a summarizer instance for testing."""
    return Summarizer(sample_config)


class TestSummarizer:
    """Tests for the Summarizer class."""

    def test_summarize_news_success(
        self, summarizer: Summarizer, sample_messages: list[Message]
    ) -> None:
        """Test successful news summarization."""
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "خلاصه تست شده اخبار فارسی"

        with patch.object(
            summarizer._client.chat.completions, "create", return_value=mock_response
        ):
            summary = summarizer.summarize_news(sample_messages)

        assert summary is not None
        assert summary.content == "خلاصه تست شده اخبار فارسی"
        assert summary.source_count == 3
        assert "Channel One" in summary.channels
        assert "Channel Two" in summary.channels

    def test_summarize_news_empty_messages(self, summarizer: Summarizer) -> None:
        """Test summarization with empty message list."""
        summary = summarizer.summarize_news([])

        assert summary is None

    def test_summarize_news_api_error(
        self, summarizer: Summarizer, sample_messages: list[Message]
    ) -> None:
        """Test handling of API errors."""
        with patch.object(
            summarizer._client.chat.completions,
            "create",
            side_effect=Exception("API Error"),
        ):
            summary = summarizer.summarize_news(sample_messages)

        assert summary is None

    def test_summarize_news_empty_response(
        self, summarizer: Summarizer, sample_messages: list[Message]
    ) -> None:
        """Test handling of empty API response."""
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = None

        with patch.object(
            summarizer._client.chat.completions, "create", return_value=mock_response
        ):
            summary = summarizer.summarize_news(sample_messages)

        assert summary is None

    def test_format_messages(
        self, summarizer: Summarizer, sample_messages: list[Message]
    ) -> None:
        """Test message formatting for LLM prompt."""
        formatted = summarizer._format_messages(sample_messages)

        assert "Channel One" in formatted
        assert "Channel Two" in formatted
        assert "این یک خبر تست است" in formatted
        assert "خبر دوم برای تست" in formatted
        assert "خبر از کانال دوم" in formatted
        assert "---" in formatted  # Separator between messages

    def test_summarizer_uses_correct_model(self, sample_config: Config) -> None:
        """Test that summarizer uses the configured model."""
        sample_config.llm_model = "anthropic/claude-3-haiku"
        summarizer = Summarizer(sample_config)

        messages = [
            Message(
                id=1,
                channel_username="test",
                channel_title="Test",
                text="Test",
                timestamp=datetime.now(),
            )
        ]

        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "Summary"

        with patch.object(
            summarizer._client.chat.completions, "create", return_value=mock_response
        ) as mock_create:
            summarizer.summarize_news(messages)

            # Check that the correct model was used
            call_kwargs = mock_create.call_args.kwargs
            assert call_kwargs["model"] == "anthropic/claude-3-haiku"

    def test_summarization_prompt_contains_instructions(self) -> None:
        """Test that the prompt contains necessary instructions."""
        assert "Persian" in SUMMARIZATION_PROMPT
        assert "summarizer" in SUMMARIZATION_PROMPT.lower()
        assert "{messages}" in SUMMARIZATION_PROMPT

    def test_unique_channels_in_summary(self, summarizer: Summarizer) -> None:
        """Test that duplicate channels are deduplicated."""
        messages = [
            Message(
                id=1,
                channel_username="channel1",
                channel_title="Same Channel",
                text="Message 1",
                timestamp=datetime.now(),
            ),
            Message(
                id=2,
                channel_username="channel1",
                channel_title="Same Channel",
                text="Message 2",
                timestamp=datetime.now(),
            ),
        ]

        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "Summary"

        with patch.object(
            summarizer._client.chat.completions, "create", return_value=mock_response
        ):
            summary = summarizer.summarize_news(messages)

        assert summary is not None
        assert len(summary.channels) == 1
        assert summary.channels[0] == "Same Channel"

    def test_sources_field_populated_with_mixed_types(
        self, summarizer: Summarizer
    ) -> None:
        """Test that sources field is populated with correct source types."""
        messages = [
            Message(
                id=1,
                channel_username="telegram_channel",
                channel_title="Telegram Channel",
                text="Message from Telegram",
                timestamp=datetime.now(),
                source_type=SourceType.TELEGRAM,
            ),
            Message(
                id=2,
                channel_username="RSS Feed",
                channel_title="RSS Feed",
                text="Message from RSS",
                timestamp=datetime.now(),
                url="https://example.com/article",
                source_type=SourceType.RSS,
            ),
        ]

        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "Summary"

        with patch.object(
            summarizer._client.chat.completions, "create", return_value=mock_response
        ):
            summary = summarizer.summarize_news(messages)

        assert summary is not None
        assert len(summary.sources) == 2

        # Check Telegram source
        telegram_source = next(
            s for s in summary.sources if s.source_type == SourceType.TELEGRAM
        )
        assert telegram_source.name == "telegram_channel"
        assert telegram_source.domain == ""

        # Check RSS source
        rss_source = next(s for s in summary.sources if s.source_type == SourceType.RSS)
        assert rss_source.name == "RSS Feed"
        assert rss_source.domain == "example.com"
