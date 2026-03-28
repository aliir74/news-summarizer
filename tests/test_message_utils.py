"""Tests for shared message utilities."""

from src.message_utils import MAX_MESSAGE_LENGTH, format_html_links, split_message


class TestSplitMessage:
    """Tests for the split_message function."""

    def test_short_message_not_split(self) -> None:
        """Test that short messages are not split."""
        text = "Short message"
        result = split_message(text)

        assert len(result) == 1
        assert result[0] == text

    def test_message_at_max_length(self) -> None:
        """Test message exactly at max length."""
        text = "x" * MAX_MESSAGE_LENGTH
        result = split_message(text)

        assert len(result) == 1

    def test_split_by_paragraphs(self) -> None:
        """Test splitting long message by paragraphs."""
        paragraph = "This is a paragraph. " * 100  # ~2100 chars
        text = f"{paragraph}\n\n{paragraph}\n\n{paragraph}"

        result = split_message(text)

        assert len(result) > 1
        for part in result:
            assert len(part) <= MAX_MESSAGE_LENGTH

    def test_split_long_single_paragraph(self) -> None:
        """Test splitting a single very long paragraph by sentences."""
        sentences = [f"This is sentence number {i}. " for i in range(200)]
        text = "".join(sentences)

        result = split_message(text)

        assert len(result) > 1
        for part in result:
            assert len(part) <= MAX_MESSAGE_LENGTH

    def test_preserves_content(self) -> None:
        """Test that splitting preserves all content."""
        paragraph1 = "First paragraph content."
        paragraph2 = "Second paragraph content."
        text = f"{paragraph1}\n\n{paragraph2}"

        result = split_message(text)

        combined = " ".join(result)
        assert "First paragraph" in combined
        assert "Second paragraph" in combined

    def test_empty_message(self) -> None:
        """Test splitting empty message."""
        result = split_message("")

        assert len(result) == 1
        assert result[0] == ""

    def test_max_message_length_constant(self) -> None:
        """Test that MAX_MESSAGE_LENGTH is 4096."""
        assert MAX_MESSAGE_LENGTH == 4096


class TestFormatHtmlLinks:
    """Tests for HTML link post-processing."""

    def test_format_source_link_with_url(self) -> None:
        """Test that (source | url) is converted to HTML link."""
        text = "🔹 خبر اول (الجزیره | https://aljazeera.com/article)"
        result = format_html_links(text)
        assert '(<a href="https://aljazeera.com/article">الجزیره</a>)' in result

    def test_format_source_link_without_url(self) -> None:
        """Test that (source) without URL is left as-is."""
        text = "🔹 خبر اول (الجزیره)"
        result = format_html_links(text)
        assert "(الجزیره)" in result

    def test_format_multiple_bullets(self) -> None:
        """Test formatting multiple bullets with mixed links."""
        text = (
            "🔹 خبر اول (الجزیره | https://aljazeera.com/1)\n\n"
            "🔹 خبر دوم (بی‌بی‌سی)\n\n"
            "🔹 خبر سوم (گاردین | https://theguardian.com/2)"
        )
        result = format_html_links(text)
        assert '<a href="https://aljazeera.com/1">الجزیره</a>' in result
        assert "(بی‌بی‌سی)" in result
        assert '<a href="https://theguardian.com/2">گاردین</a>' in result

    def test_format_telegram_source_link(self) -> None:
        """Test that Telegram URLs are also linked."""
        text = "🔹 خبر (کانال تلگرام | https://t.me/channel/123)"
        result = format_html_links(text)
        assert '<a href="https://t.me/channel/123">کانال تلگرام</a>' in result

    def test_no_links_passthrough(self) -> None:
        """Test that text without source patterns passes through escaped."""
        text = "Just plain text without any bullets."
        result = format_html_links(text)
        assert result == "Just plain text without any bullets."

    def test_html_special_chars_escaped(self) -> None:
        """Test that < and > in text are escaped to prevent HTML injection."""
        text = "🔹 خبر <script>alert(1)</script> (منبع | https://example.com)"
        result = format_html_links(text)
        assert "<script>" not in result
        assert "&lt;script&gt;" in result
        # But the link itself should still work
        assert '<a href="https://example.com">منبع</a>' in result
