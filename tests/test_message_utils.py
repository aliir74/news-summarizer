"""Tests for shared message utilities."""

from src.message_utils import (
    MAX_MESSAGE_LENGTH,
    format_html_links,
    normalize_bullets,
    postprocess_llm_output,
    resolve_source_refs,
    split_message,
)


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


class TestSplitMessageHtml:
    """Tests for HTML-aware message splitting."""

    def test_split_preserves_balanced_html(self) -> None:
        """Test that balanced HTML tags are preserved after splitting."""
        bullet = '🔹 خبر (<a href="https://example.com">منبع</a>)'
        text = "\n\n".join([bullet] * 100)
        messages = split_message(text)
        for msg in messages:
            assert msg.count("<a ") == msg.count("</a>")

    def test_split_strips_unbalanced_html(self) -> None:
        """Test that unbalanced HTML tags are stripped as fallback."""
        # Craft a message where an <a> tag gets split mid-tag
        # by making a single "paragraph" that's too long
        long_text = "x" * 4000 + ' <a href="https://example.com">link text that pushes over</a> ' + "y" * 200
        messages = split_message(long_text)
        for msg in messages:
            assert msg.count("<a ") == msg.count("</a>")


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


class TestNormalizeBullets:
    """Tests for bullet format normalization."""

    def test_asterisk_bullet(self) -> None:
        """Test that * bullet is normalized to 🔹."""
        assert normalize_bullets("* item") == "🔹 item"

    def test_asterisk_with_extra_spaces(self) -> None:
        """Test that *   bullet is normalized to 🔹."""
        assert normalize_bullets("*   item") == "🔹 item"

    def test_dash_bullet(self) -> None:
        """Test that - bullet is normalized to 🔹."""
        assert normalize_bullets("- item") == "🔹 item"

    def test_numbered_bullet_dot(self) -> None:
        """Test that 1. bullet is normalized to 🔹."""
        assert normalize_bullets("1. item") == "🔹 item"

    def test_numbered_bullet_dash(self) -> None:
        """Test that 1- bullet is normalized to 🔹."""
        assert normalize_bullets("1- item") == "🔹 item"

    def test_numbered_bullet_paren(self) -> None:
        """Test that 1) bullet is normalized to 🔹."""
        assert normalize_bullets("1) item") == "🔹 item"

    def test_persian_numbered_bullet(self) -> None:
        """Test that ۱. bullet is normalized to 🔹."""
        assert normalize_bullets("۱. item") == "🔹 item"

    def test_existing_emoji_bullet_unchanged(self) -> None:
        """Test that 🔹 bullet is not double-prefixed."""
        assert normalize_bullets("🔹 item") == "🔹 item"

    def test_multiline_mixed_formats(self) -> None:
        """Test normalization of mixed bullet formats across lines."""
        text = "* first\n- second\n1. third\n🔹 fourth"
        result = normalize_bullets(text)
        assert result == "🔹 first\n🔹 second\n🔹 third\n🔹 fourth"

    def test_mid_line_asterisk_not_touched(self) -> None:
        """Test that asterisks inside text are not affected."""
        text = "this is *bold* text"
        assert normalize_bullets(text) == "this is *bold* text"

    def test_mid_line_dash_not_touched(self) -> None:
        """Test that dashes inside text are not affected."""
        text = "some - text here"
        assert normalize_bullets(text) == "some - text here"


class TestResolveSourceRefs:
    """Tests for source reference resolution."""

    def test_single_ref(self) -> None:
        """Test resolving a single [1] reference."""
        refs = {1: ("BBC Persian", "https://bbc.com/article")}
        result = resolve_source_refs("news [1]", refs)
        assert result == "news (BBC Persian | https://bbc.com/article)"

    def test_multi_ref(self) -> None:
        """Test resolving [1,3] multiple references."""
        refs = {
            1: ("BBC", "https://bbc.com/1"),
            2: ("CNN", "https://cnn.com/2"),
            3: ("AJ", "https://aj.com/3"),
        }
        result = resolve_source_refs("combined news [1,3]", refs)
        assert "(BBC | https://bbc.com/1)" in result
        assert "(AJ | https://aj.com/3)" in result
        assert "CNN" not in result

    def test_persian_digits(self) -> None:
        """Test resolving [۱] with Persian digits."""
        refs = {1: ("الجزیره", "https://aj.com/article")}
        result = resolve_source_refs("خبر [۱]", refs)
        assert result == "خبر (الجزیره | https://aj.com/article)"

    def test_persian_comma_separator(self) -> None:
        """Test resolving [۱،۳] with Persian comma."""
        refs = {
            1: ("BBC", "https://bbc.com/1"),
            3: ("AJ", "https://aj.com/3"),
        }
        result = resolve_source_refs("خبر [۱،۳]", refs)
        assert "(BBC | https://bbc.com/1)" in result
        assert "(AJ | https://aj.com/3)" in result

    def test_unknown_ref_preserved(self) -> None:
        """Test that unknown ref numbers keep original text."""
        refs = {1: ("BBC", "https://bbc.com/1")}
        result = resolve_source_refs("news [99]", refs)
        assert result == "news [99]"

    def test_ref_with_no_url(self) -> None:
        """Test that empty URL produces label without pipe."""
        refs = {1: ("Source", "")}
        result = resolve_source_refs("news [1]", refs)
        assert result == "news (Source)"

    def test_duplicate_ref_numbers_deduped(self) -> None:
        """Test that duplicate numbers in [1,1] are deduped."""
        refs = {1: ("BBC", "https://bbc.com/1")}
        result = resolve_source_refs("news [1,1]", refs)
        assert result == "news (BBC | https://bbc.com/1)"

    def test_multiple_refs_in_text(self) -> None:
        """Test resolving multiple separate [n] patterns in one text."""
        refs = {
            1: ("BBC", "https://bbc.com/1"),
            2: ("AJ", "https://aj.com/2"),
        }
        text = "🔹 first news [1]\n🔹 second news [2]"
        result = resolve_source_refs(text, refs)
        assert "(BBC | https://bbc.com/1)" in result
        assert "(AJ | https://aj.com/2)" in result


class TestPostprocessLlmOutput:
    """Tests for the combined postprocess_llm_output function."""

    def test_combined_normalization_and_refs(self) -> None:
        """Test full pipeline: normalize bullets + resolve refs."""
        refs = {
            1: ("BBC", "https://bbc.com/1"),
            2: ("AJ", "https://aj.com/2"),
        }
        text = "* first news [1]\n- second news [2]"
        result = postprocess_llm_output(text, refs)
        assert result.startswith("🔹 first news")
        assert "(BBC | https://bbc.com/1)" in result
        assert "(AJ | https://aj.com/2)" in result
        assert "*" not in result
        assert "- " not in result

    def test_empty_source_refs(self) -> None:
        """Test with empty refs dict - refs pass through unchanged."""
        text = "🔹 news [1]"
        result = postprocess_llm_output(text, {})
        assert result == "🔹 news [1]"

    def test_no_refs_in_text(self) -> None:
        """Test plain text with no [n] patterns passes through."""
        refs = {1: ("BBC", "https://bbc.com/1")}
        text = "🔹 just a plain bullet"
        result = postprocess_llm_output(text, refs)
        assert result == "🔹 just a plain bullet"
