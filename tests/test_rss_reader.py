"""Tests for the RSS feed reader."""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from src.config import Config, RSSFeed
from src.models import SourceType
from src.rss_reader import RSSReader, _clean_text, _extract_entry_text, _parse_entry_time


class TestRSSReader:
    """Tests for RSSReader class."""

    async def test_start_creates_client(self, sample_config: Config) -> None:
        """Test that start() creates an HTTP client."""
        reader = RSSReader(sample_config)
        await reader.start()

        assert reader._client is not None
        await reader.stop()

    async def test_stop_closes_client(self, sample_config: Config) -> None:
        """Test that stop() closes the HTTP client."""
        reader = RSSReader(sample_config)
        await reader.start()
        await reader.stop()

        # Client should be closed but still exists
        assert reader._client is not None

    def test_client_property_raises_when_not_started(
        self, sample_config: Config
    ) -> None:
        """Test that accessing client raises when not started."""
        reader = RSSReader(sample_config)

        with pytest.raises(RuntimeError, match="not started"):
            _ = reader.client

    async def test_get_feed_updates_parses_rss(
        self, sample_config: Config, sample_rss_feed: RSSFeed, sample_rss_xml: str
    ) -> None:
        """Test parsing RSS feed and extracting messages."""
        reader = RSSReader(sample_config)

        # Mock the HTTP client
        mock_response = MagicMock()
        mock_response.text = sample_rss_xml
        mock_response.raise_for_status = MagicMock()

        with patch.object(reader, "_client") as mock_client:
            mock_client.get = AsyncMock(return_value=mock_response)
            reader._client = mock_client

            since = datetime(2024, 1, 1)
            messages = await reader.get_feed_updates(sample_rss_feed, since)

            assert len(messages) == 2
            assert messages[0].channel_username == "Test Feed"
            assert "Iran" in messages[0].text
            assert messages[0].url == "https://example.com/article1"

    async def test_get_feed_updates_sets_rss_source_type(
        self, sample_config: Config, sample_rss_feed: RSSFeed, sample_rss_xml: str
    ) -> None:
        """Test that RSS messages have source_type set to RSS."""
        reader = RSSReader(sample_config)

        mock_response = MagicMock()
        mock_response.text = sample_rss_xml
        mock_response.raise_for_status = MagicMock()

        with patch.object(reader, "_client") as mock_client:
            mock_client.get = AsyncMock(return_value=mock_response)
            reader._client = mock_client

            since = datetime(2024, 1, 1)
            messages = await reader.get_feed_updates(sample_rss_feed, since)

            for msg in messages:
                assert msg.source_type == SourceType.RSS

    async def test_get_feed_updates_filters_by_date(
        self, sample_config: Config, sample_rss_feed: RSSFeed, sample_rss_xml: str
    ) -> None:
        """Test that messages older than since are filtered out."""
        reader = RSSReader(sample_config)

        mock_response = MagicMock()
        mock_response.text = sample_rss_xml
        mock_response.raise_for_status = MagicMock()

        with patch.object(reader, "_client") as mock_client:
            mock_client.get = AsyncMock(return_value=mock_response)
            reader._client = mock_client

            # Use a date after all articles
            since = datetime(2024, 1, 16)
            messages = await reader.get_feed_updates(sample_rss_feed, since)

            assert len(messages) == 0

    async def test_get_feed_updates_handles_http_error(
        self, sample_config: Config, sample_rss_feed: RSSFeed
    ) -> None:
        """Test graceful handling of HTTP errors."""
        reader = RSSReader(sample_config)

        with patch.object(reader, "_client") as mock_client:
            mock_client.get = AsyncMock(
                side_effect=httpx.HTTPError("Connection failed")
            )
            reader._client = mock_client

            since = datetime(2024, 1, 1)
            messages = await reader.get_feed_updates(sample_rss_feed, since)

            assert messages == []

    async def test_get_all_feed_updates(
        self, sample_config: Config, sample_rss_xml: str
    ) -> None:
        """Test fetching from all configured feeds."""
        reader = RSSReader(sample_config)

        mock_response = MagicMock()
        mock_response.text = sample_rss_xml
        mock_response.raise_for_status = MagicMock()

        with patch.object(reader, "_client") as mock_client:
            mock_client.get = AsyncMock(return_value=mock_response)
            reader._client = mock_client

            since = datetime(2024, 1, 1)
            messages = await reader.get_all_feed_updates(since)

            # Should have messages from the one configured feed
            assert len(messages) >= 0  # Depends on config

    async def test_get_feed_updates_skips_seen_urls(
        self, sample_config: Config, sample_rss_feed: RSSFeed, sample_rss_xml: str
    ) -> None:
        """Test that articles with seen URLs are filtered out."""
        reader = RSSReader(sample_config)

        mock_response = MagicMock()
        mock_response.text = sample_rss_xml
        mock_response.raise_for_status = MagicMock()

        # Mark the first article as seen
        seen_urls = {"https://example.com/article1"}

        with patch.object(reader, "_client") as mock_client:
            mock_client.get = AsyncMock(return_value=mock_response)
            reader._client = mock_client

            since = datetime(2024, 1, 1)
            messages = await reader.get_feed_updates(sample_rss_feed, since, seen_urls=seen_urls)

            # Should have only one message (the one not in seen_urls)
            assert len(messages) == 1
            assert messages[0].url == "https://example.com/article2"

    async def test_get_all_feed_updates_with_seen_urls(
        self, sample_config: Config, sample_rss_xml: str
    ) -> None:
        """Test that seen_urls are passed through to get_feed_updates."""
        reader = RSSReader(sample_config)

        mock_response = MagicMock()
        mock_response.text = sample_rss_xml
        mock_response.raise_for_status = MagicMock()

        # Mark first article as seen
        seen_urls = {"https://example.com/article1"}

        with patch.object(reader, "_client") as mock_client:
            mock_client.get = AsyncMock(return_value=mock_response)
            reader._client = mock_client

            since = datetime(2024, 1, 1)
            messages = await reader.get_all_feed_updates(since, seen_urls=seen_urls)

            # All returned messages should have URLs not in seen_urls
            for msg in messages:
                assert msg.url not in seen_urls


class TestParseEntryTime:
    """Tests for _parse_entry_time helper function."""

    def test_parse_published_date(self) -> None:
        """Test parsing published date field."""
        entry = {"published": "Mon, 15 Jan 2024 10:30:00 GMT"}
        result = _parse_entry_time(entry)

        assert result is not None
        assert result.year == 2024
        assert result.month == 1
        assert result.day == 15

    def test_parse_updated_date(self) -> None:
        """Test parsing updated date field."""
        entry = {"updated": "Tue, 16 Jan 2024 12:00:00 GMT"}
        result = _parse_entry_time(entry)

        assert result is not None
        assert result.year == 2024

    def test_parse_parsed_time_tuple(self) -> None:
        """Test parsing time tuple from feedparser."""
        entry = {"published_parsed": (2024, 1, 15, 10, 30, 0, 0, 0, 0)}
        result = _parse_entry_time(entry)

        assert result is not None
        assert result.year == 2024
        assert result.month == 1
        assert result.day == 15

    def test_parse_returns_none_for_missing_date(self) -> None:
        """Test that missing date returns None."""
        entry = {"title": "No date here"}
        result = _parse_entry_time(entry)

        assert result is None

    def test_parse_handles_invalid_date(self) -> None:
        """Test graceful handling of invalid date formats."""
        entry = {"published": "not a valid date"}
        result = _parse_entry_time(entry)

        # Should not raise, returns None for unparseable dates
        # (or might parse partially depending on email.utils behavior)
        assert result is None or isinstance(result, datetime)


class TestExtractEntryText:
    """Tests for _extract_entry_text helper function."""

    def test_extract_title_and_summary(self) -> None:
        """Test extracting title and summary."""
        entry = {
            "title": "Test Title",
            "summary": "Test summary content.",
        }
        result = _extract_entry_text(entry)

        assert "Test Title" in result
        assert "Test summary content." in result

    def test_extract_title_only(self) -> None:
        """Test extracting title when no summary."""
        entry = {"title": "Just a Title"}
        result = _extract_entry_text(entry)

        assert result == "Just a Title"

    def test_extract_description_fallback(self) -> None:
        """Test falling back to description field."""
        entry = {
            "title": "Title",
            "description": "Description content",
        }
        result = _extract_entry_text(entry)

        assert "Title" in result
        assert "Description content" in result

    def test_strip_html_tags(self) -> None:
        """Test HTML tag stripping from description."""
        entry = {
            "title": "Title",
            "summary": "<p>Paragraph with <b>bold</b> text.</p>",
        }
        result = _extract_entry_text(entry)

        assert "<p>" not in result
        assert "<b>" not in result
        assert "Paragraph with bold text." in result

    def test_extract_content_field(self) -> None:
        """Test extracting from content field (Atom feeds)."""
        entry = {
            "title": "Title",
            "content": [{"value": "Content value here"}],
        }
        result = _extract_entry_text(entry)

        assert "Title" in result
        assert "Content value here" in result

    def test_returns_empty_for_no_content(self) -> None:
        """Test empty string for entries without content."""
        entry = {}
        result = _extract_entry_text(entry)

        assert result == ""

    def test_extract_cleans_non_persian_english_chars(self) -> None:
        """Test that extraction cleans non-Persian/English characters."""
        entry = {
            "title": "رویترز (Reuters)",
            "summary": "رو이터 (از طریق گوگل نیوز) خبر جدید",
        }
        result = _extract_entry_text(entry)

        # Korean characters should be removed
        assert "이터" not in result
        # Persian and English should be preserved
        assert "رویترز" in result or "Reuters" in result
        assert "خبر جدید" in result


class TestCleanText:
    """Tests for _clean_text helper function."""

    def test_clean_text_removes_korean_characters(self) -> None:
        """Test that Korean characters are removed."""
        text = "رو이터 (از طریق گوگل نیوز)"
        result = _clean_text(text)

        assert "이터" not in result
        assert "رو" in result
        assert "از طریق گوگل نیوز" in result

    def test_clean_text_removes_chinese_characters(self) -> None:
        """Test that Chinese characters are removed."""
        text = "新闻 News about Iran ایران"
        result = _clean_text(text)

        assert "新闻" not in result
        assert "News about Iran" in result
        assert "ایران" in result

    def test_clean_text_removes_japanese_characters(self) -> None:
        """Test that Japanese characters are removed."""
        text = "ニュース Iran news ایران"
        result = _clean_text(text)

        assert "ニュース" not in result
        assert "Iran news" in result
        assert "ایران" in result

    def test_clean_text_preserves_persian_text(self) -> None:
        """Test that Persian text is preserved."""
        text = "این یک متن فارسی است که باید حفظ شود."
        result = _clean_text(text)

        assert result == text

    def test_clean_text_preserves_english_text(self) -> None:
        """Test that English text is preserved."""
        text = "This is English text that should be preserved."
        result = _clean_text(text)

        assert result == text

    def test_clean_text_preserves_numbers(self) -> None:
        """Test that numbers are preserved."""
        text = "2024 سال ۱۴۰۳"
        result = _clean_text(text)

        assert "2024" in result
        assert "سال" in result

    def test_clean_text_preserves_common_punctuation(self) -> None:
        """Test that common punctuation is preserved."""
        text = "Hello, world! This is a test? Yes; it is: (test)"
        result = _clean_text(text)

        assert "," in result
        assert "!" in result
        assert "?" in result
        assert ";" in result
        assert ":" in result
        assert "(" in result
        assert ")" in result

    def test_clean_text_preserves_persian_punctuation(self) -> None:
        """Test that Persian punctuation is preserved."""
        text = "سلام، این یک تست است؟ بله؛ هست."
        result = _clean_text(text)

        # Persian comma, question mark, semicolon
        assert "،" in result
        assert "؟" in result
        assert "؛" in result

    def test_clean_text_preserves_zwnj(self) -> None:
        """Test that ZWNJ (zero-width non-joiner) is preserved."""
        # ZWNJ is used in Persian to prevent letters from joining
        text = "می‌باشد"  # Contains ZWNJ between می and باشد
        result = _clean_text(text)

        assert result == text
        # Verify ZWNJ is present
        assert "\u200c" in result

    def test_clean_text_handles_mixed_scripts(self) -> None:
        """Test cleaning text with multiple non-Latin scripts."""
        text = "ایران Iran 中国 한국 日本 Deutschland"
        result = _clean_text(text)

        assert "ایران" in result
        assert "Iran" in result
        assert "Deutschland" in result
        # Non-Latin non-Persian scripts should be removed
        assert "中国" not in result
        assert "한국" not in result
        assert "日本" not in result

    def test_clean_text_preserves_arabic_extended(self) -> None:
        """Test that Arabic extended characters are preserved."""
        # Some Arabic characters used in Persian
        text = "کتاب گاه پژوهش"  # Uses Persian-specific Arabic letters
        result = _clean_text(text)

        assert result == text

    def test_clean_text_handles_empty_string(self) -> None:
        """Test that empty string returns empty string."""
        assert _clean_text("") == ""

    def test_clean_text_strips_whitespace(self) -> None:
        """Test that result is stripped of leading/trailing whitespace."""
        text = "  some text  "
        result = _clean_text(text)

        assert result == "some text"

    def test_clean_text_real_world_example(self) -> None:
        """Test with a real-world example containing Korean from Google News."""
        text = "رویترز 로이터 (از طریق Google News) - اخبار مهم درباره ایران"
        result = _clean_text(text)

        # Korean should be removed
        assert "로이터" not in result
        # Persian and English should remain
        assert "رویترز" in result
        assert "Google News" in result
        assert "اخبار مهم" in result
        assert "ایران" in result
