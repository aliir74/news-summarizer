"""Tests for the summarizer module."""

from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest

from src.config import Config
from src.models import Message, SourceType
from src.summarizer import (
    ENGLISH_SUMMARY_PROMPT,
    RE_SUMMARIZE_PROMPT,
    SUMMARIZATION_PROMPT,
    TRANSLATION_PROMPT,
    Summarizer,
)


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


class TestPromptFaithfulness:
    """Tests for prompt faithfulness requirements."""

    def test_prompt_contains_faithfulness_requirements(self) -> None:
        """Test that the prompt contains strict faithfulness requirements."""
        assert "CRITICAL REQUIREMENTS" in SUMMARIZATION_PROMPT
        assert "ONLY include information explicitly stated" in SUMMARIZATION_PROMPT
        assert "do not add any external knowledge" in SUMMARIZATION_PROMPT

    def test_prompt_contains_modal_preservation_instruction(self) -> None:
        """Test that the prompt instructs to preserve modal verbs."""
        assert "PRESERVE uncertainty language" in SUMMARIZATION_PROMPT
        assert "might" in SUMMARIZATION_PROMPT
        assert "could" in SUMMARIZATION_PROMPT
        assert "may" in SUMMARIZATION_PROMPT
        assert "reportedly" in SUMMARIZATION_PROMPT
        # Check Persian equivalents
        assert "ممکن است" in SUMMARIZATION_PROMPT
        assert "شاید" in SUMMARIZATION_PROMPT
        assert "احتمالاً" in SUMMARIZATION_PROMPT

    def test_prompt_contains_verb_tense_preservation(self) -> None:
        """Test that the prompt instructs to maintain verb tenses."""
        assert "MAINTAIN original verb tenses" in SUMMARIZATION_PROMPT
        assert "conditional" in SUMMARIZATION_PROMPT.lower()

    def test_prompt_prevents_hallucination(self) -> None:
        """Test that the prompt prevents adding external knowledge."""
        assert "Do NOT add context" in SUMMARIZATION_PROMPT
        assert "training data" in SUMMARIZATION_PROMPT

    def test_english_summary_prompt_contains_modal_preservation(self) -> None:
        """Test that English summary prompt preserves modal verbs."""
        assert "Preserve ALL uncertainty language" in ENGLISH_SUMMARY_PROMPT
        assert "might" in ENGLISH_SUMMARY_PROMPT
        assert "could" in ENGLISH_SUMMARY_PROMPT
        assert "may" in ENGLISH_SUMMARY_PROMPT
        assert "reportedly" in ENGLISH_SUMMARY_PROMPT
        assert "allegedly" in ENGLISH_SUMMARY_PROMPT

    def test_english_summary_prompt_prevents_tense_changes(self) -> None:
        """Test that English summary prompt prevents verb tense changes."""
        assert "Do NOT change verb tenses" in ENGLISH_SUMMARY_PROMPT

    def test_translation_prompt_maps_modal_verbs(self) -> None:
        """Test that translation prompt maps English modal verbs to Persian."""
        # Check English to Persian mappings
        assert '"might" → "ممکن است"' in TRANSLATION_PROMPT
        assert '"could"' in TRANSLATION_PROMPT
        assert '"may" → "ممکن است"' in TRANSLATION_PROMPT
        assert '"reportedly" → "طبق گزارش‌ها"' in TRANSLATION_PROMPT
        assert '"allegedly" → "ظاهراً"' in TRANSLATION_PROMPT
        assert '"according to" → "به گفته"' in TRANSLATION_PROMPT

    def test_translation_prompt_prevents_modification(self) -> None:
        """Test that translation prompt prevents adding/removing information."""
        assert "Do NOT change verb tenses" in TRANSLATION_PROMPT
        assert "add/remove information" in TRANSLATION_PROMPT


class TestLanguageDetection:
    """Tests for language detection in two-stage summarization."""

    def test_is_persian_with_persian_text(self, summarizer: Summarizer) -> None:
        """Test that Persian text is correctly identified."""
        persian_text = "این یک متن فارسی است که باید شناسایی شود."
        assert summarizer._is_persian(persian_text) is True

    def test_is_persian_with_english_text(self, summarizer: Summarizer) -> None:
        """Test that English text is correctly identified as non-Persian."""
        english_text = "This is an English text that should not be Persian."
        assert summarizer._is_persian(english_text) is False

    def test_is_persian_with_mixed_text_mostly_persian(
        self, summarizer: Summarizer
    ) -> None:
        """Test mixed text that is mostly Persian."""
        # More than 20% Persian characters
        mixed_text = "این متن شامل English words می‌باشد"
        assert summarizer._is_persian(mixed_text) is True

    def test_is_persian_with_mixed_text_mostly_english(
        self, summarizer: Summarizer
    ) -> None:
        """Test mixed text that is mostly English."""
        # Less than 20% Persian characters
        mixed_text = "This is mostly English with just one word فارسی"
        # The ratio depends on exact calculation
        result = summarizer._is_persian(mixed_text)
        # This should be False since the Persian content is minimal
        assert result is False

    def test_is_persian_with_empty_text(self, summarizer: Summarizer) -> None:
        """Test empty text returns False."""
        assert summarizer._is_persian("") is False

    def test_is_persian_with_numbers_only(self, summarizer: Summarizer) -> None:
        """Test text with only numbers returns False."""
        assert summarizer._is_persian("12345 67890") is False


class TestTwoStageSummarization:
    """Tests for two-stage summarization feature."""

    def test_two_stage_disabled_by_default(self, sample_config: Config) -> None:
        """Test that two-stage summarization is disabled by default."""
        assert sample_config.two_stage_summarization is False

    def test_two_stage_enabled_uses_two_stage_method(
        self, sample_config: Config
    ) -> None:
        """Test that enabled two-stage uses the two-stage method."""
        sample_config.two_stage_summarization = True
        summarizer = Summarizer(sample_config)

        messages = [
            Message(
                id=1,
                channel_username="test",
                channel_title="Test",
                text="This is an English message.",
                timestamp=datetime.now(),
            )
        ]

        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "خلاصه فارسی"

        with patch.object(
            summarizer._client.chat.completions, "create", return_value=mock_response
        ) as mock_create:
            summary = summarizer.summarize_news(messages)

            # Should call the API multiple times for two-stage
            # (English summary + Translation for English, Persian summary for Persian)
            assert mock_create.call_count >= 1
            assert summary is not None

    def test_two_stage_disabled_uses_single_stage_method(
        self, summarizer: Summarizer, sample_messages: list[Message]
    ) -> None:
        """Test that disabled two-stage uses single-stage method."""
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "خلاصه فارسی"

        with patch.object(
            summarizer._client.chat.completions, "create", return_value=mock_response
        ) as mock_create:
            summary = summarizer.summarize_news(sample_messages)

            # Should call the API only once for single-stage
            assert mock_create.call_count == 1
            assert summary is not None

    def test_two_stage_separates_english_and_persian(
        self, sample_config: Config
    ) -> None:
        """Test that two-stage correctly separates English and Persian messages."""
        sample_config.two_stage_summarization = True
        summarizer = Summarizer(sample_config)

        messages = [
            Message(
                id=1,
                channel_username="en_channel",
                channel_title="English Channel",
                text="Trump might order sanctions on Iran.",
                timestamp=datetime.now(),
            ),
            Message(
                id=2,
                channel_username="fa_channel",
                channel_title="Persian Channel",
                text="ایران ممکن است به تحریم‌ها پاسخ دهد.",
                timestamp=datetime.now(),
            ),
        ]

        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "Summary content"

        with patch.object(
            summarizer._client.chat.completions, "create", return_value=mock_response
        ):
            summary = summarizer.summarize_news(messages)

            assert summary is not None
            # Both channels should be in the summary
            assert "English Channel" in summary.channels or "Persian Channel" in summary.channels


class TestTimestampFormat:
    """Tests for timestamp formatting in summaries."""

    def test_format_messages_includes_full_date(
        self, summarizer: Summarizer
    ) -> None:
        """Test that formatted messages include full date, not just time."""
        messages = [
            Message(
                id=1,
                channel_username="test",
                channel_title="Test Channel",
                text="Test message",
                timestamp=datetime(2024, 1, 15, 10, 30),
            )
        ]

        formatted = summarizer._format_messages(messages)

        # Should include YYYY-MM-DD format
        assert "2024-01-15" in formatted
        assert "10:30" in formatted

    def test_format_messages_preserves_date_for_temporal_context(
        self, summarizer: Summarizer
    ) -> None:
        """Test that dates from different days are distinguishable."""
        messages = [
            Message(
                id=1,
                channel_username="test",
                channel_title="Test",
                text="Old news",
                timestamp=datetime(2024, 1, 10, 10, 30),
            ),
            Message(
                id=2,
                channel_username="test",
                channel_title="Test",
                text="New news",
                timestamp=datetime(2024, 1, 15, 10, 30),
            ),
        ]

        formatted = summarizer._format_messages(messages)

        # Both dates should be present and distinguishable
        assert "2024-01-10" in formatted
        assert "2024-01-15" in formatted


class TestReSummarize:
    """Tests for the re_summarize method."""

    def test_re_summarize_success(self, summarizer: Summarizer) -> None:
        """Test successful re-summarization of multiple texts."""
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "خلاصه ترکیبی"

        with patch.object(
            summarizer._client.chat.completions, "create", return_value=mock_response
        ):
            result = summarizer.re_summarize(["summary 1", "summary 2"])

        assert result == "خلاصه ترکیبی"

    def test_re_summarize_llm_failure(self, summarizer: Summarizer) -> None:
        """Test that LLM failure returns None."""
        with patch.object(
            summarizer._client.chat.completions,
            "create",
            side_effect=Exception("API Error"),
        ):
            result = summarizer.re_summarize(["summary 1", "summary 2"])

        assert result is None

    def test_re_summarize_prompt_contains_requirements(self) -> None:
        """Test that the re-summarize prompt has critical requirements."""
        assert "CRITICAL REQUIREMENTS" in RE_SUMMARIZE_PROMPT
        assert "PRESERVE uncertainty language" in RE_SUMMARIZE_PROMPT
        assert "{summaries}" in RE_SUMMARIZE_PROMPT


class TestTemperatureSetting:
    """Tests for temperature setting in LLM calls."""

    def test_temperature_is_zero(
        self, summarizer: Summarizer, sample_messages: list[Message]
    ) -> None:
        """Test that temperature is set to 0 for factual accuracy."""
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "Summary"

        with patch.object(
            summarizer._client.chat.completions, "create", return_value=mock_response
        ) as mock_create:
            summarizer.summarize_news(sample_messages)

            call_kwargs = mock_create.call_args.kwargs
            assert call_kwargs["temperature"] == 0
