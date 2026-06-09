"""Tests for data models."""

from datetime import datetime

import pytest

from src.cadence import CadenceChangeReason, CadenceDecision, IntensityLevel
from src.models import (
    TEHRAN_TZ,
    Message,
    SourceInfo,
    SourceType,
    Summary,
    build_cadence_notice,
    extract_domain,
    to_persian_digits,
)


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

    def test_to_persian_digits(self) -> None:
        """Test converting integers to Persian digit strings."""
        assert Summary._to_persian_digits(0) == "۰"
        assert Summary._to_persian_digits(5) == "۵"
        assert Summary._to_persian_digits(123) == "۱۲۳"


class TestSummaryFormatMessage:
    """Tests for the Summary.format_message redesign with Shamsi dates."""

    def test_shamsi_date_in_header(self) -> None:
        """Test that Shamsi date appears and Gregorian date does not."""
        tehran_time = datetime(2024, 1, 15, 14, 30, tzinfo=TEHRAN_TZ)
        summary = Summary(
            content="محتوای تست",
            source_count=5,
            channels=["Ch A", "Ch B", "Ch C"],
            created_at=tehran_time,
        )

        formatted = summary.format_message()

        # Jan 2024 falls in Shamsi year 1402
        assert "۱۴۰۲" in formatted
        # Should NOT contain Gregorian date or "(Tehran)"
        assert "2024" not in formatted
        assert "(Tehran)" not in formatted

    def test_no_separator(self) -> None:
        """Test that the old separator line is removed."""
        summary = Summary(
            content="محتوای تست",
            source_count=2,
            channels=["Ch A"],
            created_at=datetime(2024, 1, 15, 14, 30, tzinfo=TEHRAN_TZ),
        )

        formatted = summary.format_message()

        assert "─" not in formatted

    def test_footer_stats_after_content(self) -> None:
        """Test that footer stats appear after the content."""
        content = "این یک محتوای تست است"
        summary = Summary(
            content=content,
            source_count=5,
            channels=["Ch A", "Ch B", "Ch C"],
            created_at=datetime(2024, 1, 15, 14, 30, tzinfo=TEHRAN_TZ),
        )

        formatted = summary.format_message()

        expected_footer = "📡 ۵ خبر از ۳ منبع"
        assert expected_footer in formatted
        # Footer must come after the content
        content_pos = formatted.index(content)
        footer_pos = formatted.index(expected_footer)
        assert footer_pos > content_pos

    def test_plain_format_keeps_raw_links(self) -> None:
        """Test that html=False keeps raw (label | url) text without HTML tags."""
        content = "🔹 خبر مهم (خبرگزاری | https://example.com/news)"
        summary = Summary(
            content=content,
            source_count=1,
            channels=["Ch A"],
            created_at=datetime(2024, 1, 15, 14, 30, tzinfo=TEHRAN_TZ),
        )

        formatted = summary.format_message(html=False)

        assert "(خبرگزاری | https://example.com/news)" in formatted
        assert "<a " not in formatted
        assert "</a>" not in formatted

    def test_html_format_converts_links(self) -> None:
        """Test that html=True (default) converts links to HTML tags."""
        content = "🔹 خبر مهم (خبرگزاری | https://example.com/news)"
        summary = Summary(
            content=content,
            source_count=1,
            channels=["Ch A"],
            created_at=datetime(2024, 1, 15, 14, 30, tzinfo=TEHRAN_TZ),
        )

        formatted = summary.format_message()

        assert '<a href="https://example.com/news">' in formatted
        assert "(خبرگزاری | https://example.com/news)" not in formatted

    def test_no_source_list(self) -> None:
        """Test that the old source list (منابع:) no longer appears."""
        summary = Summary(
            content="محتوای تست",
            source_count=3,
            channels=["Ch A", "Ch B"],
            channel_usernames=["ch_a", "ch_b"],
            sources=[
                SourceInfo(name="ch_a", source_type=SourceType.TELEGRAM),
                SourceInfo(
                    name="BBC Persian", source_type=SourceType.RSS, domain="bbc.co.uk"
                ),
            ],
            created_at=datetime(2024, 1, 15, 14, 30, tzinfo=TEHRAN_TZ),
        )

        formatted = summary.format_message()

        assert "منابع:" not in formatted


class TestSourceInfo:
    """Tests for SourceInfo dataclass."""

    def test_source_info_telegram(self) -> None:
        """Test SourceInfo for Telegram sources."""
        source = SourceInfo(name="channel1", source_type=SourceType.TELEGRAM)
        assert source.name == "channel1"
        assert source.source_type == SourceType.TELEGRAM
        assert source.domain == ""

    def test_source_info_rss(self) -> None:
        """Test SourceInfo for RSS sources."""
        source = SourceInfo(
            name="BBC Persian", source_type=SourceType.RSS, domain="bbc.co.uk"
        )
        assert source.name == "BBC Persian"
        assert source.source_type == SourceType.RSS
        assert source.domain == "bbc.co.uk"


class TestExtractDomain:
    """Tests for extract_domain helper function."""

    def test_extract_domain_simple(self) -> None:
        """Test extracting domain from a simple URL."""
        assert extract_domain("https://example.com/path") == "example.com"

    def test_extract_domain_with_www(self) -> None:
        """Test that www. prefix is removed."""
        assert extract_domain("https://www.bbc.co.uk/news") == "bbc.co.uk"

    def test_extract_domain_with_subdomain(self) -> None:
        """Test that subdomains other than www are preserved."""
        assert extract_domain("https://feeds.bbci.co.uk/news") == "feeds.bbci.co.uk"

    def test_extract_domain_empty(self) -> None:
        """Test empty string returns empty domain."""
        assert extract_domain("") == ""

    def test_extract_domain_invalid(self) -> None:
        """Test invalid URL returns empty string."""
        assert extract_domain("not-a-url") == ""

    def test_extract_domain_http(self) -> None:
        """Test HTTP URLs work correctly."""
        assert extract_domain("http://example.org/feed") == "example.org"


class TestMessageSourceType:
    """Tests for Message source_type field."""

    def test_message_default_source_type(self) -> None:
        """Test that default source type is TELEGRAM."""
        msg = Message(
            id=1,
            channel_username="channel",
            channel_title="Channel",
            text="Text",
            timestamp=datetime.now(),
        )
        assert msg.source_type == SourceType.TELEGRAM

    def test_message_rss_source_type(self) -> None:
        """Test setting RSS source type."""
        msg = Message(
            id=1,
            channel_username="Feed",
            channel_title="Feed",
            text="Text",
            timestamp=datetime.now(),
            url="https://example.com/article",
            source_type=SourceType.RSS,
        )
        assert msg.source_type == SourceType.RSS


class TestToPersianDigits:
    """Tests for the module-level Persian digit converter."""

    def test_converts_int(self) -> None:
        """Test an integer converts to Persian digits."""
        assert to_persian_digits(68) == "۶۸"

    def test_converts_digit_string(self) -> None:
        """Test a digit string converts to Persian digits."""
        assert to_persian_digits("05") == "۰۵"


class TestBuildCadenceNotice:
    """Tests for the Persian cadence-change notice builder."""

    def _decision(
        self,
        previous: int,
        new: int,
        reason: CadenceChangeReason,
        level: IntensityLevel = IntensityLevel.ELEVATED,
    ) -> CadenceDecision:
        return CadenceDecision(
            previous_interval=previous, new_interval=new, level=level, reason=reason
        )

    def test_news_volume_escalation(self) -> None:
        """Test the news-volume variant cites the rise and both intervals."""
        notice = build_cadence_notice(
            self._decision(68, 30, CadenceChangeReason.NEWS_VOLUME)
        )

        assert "افزایش حجم اخبار" in notice
        assert "۶۸" in notice
        assert "۳۰" in notice
        assert "کاهش" in notice

    def test_radar_outage_escalation(self) -> None:
        """Test the radar variant cites internet disruption in Iran."""
        notice = build_cadence_notice(
            self._decision(60, 30, CadenceChangeReason.RADAR_OUTAGE)
        )

        assert "اختلال اینترنت" in notice
        assert "ایران" in notice
        assert "۶۰" in notice
        assert "۳۰" in notice

    def test_calm_decay(self) -> None:
        """Test the decay variant cites the calmer flow and the longer wait."""
        notice = build_cadence_notice(
            self._decision(30, 45, CadenceChangeReason.CALM_DECAY, IntensityLevel.NORMAL)
        )

        assert "آرام" in notice
        assert "۳۰" in notice
        assert "۴۵" in notice
        assert "افزایش" in notice

    def test_every_variant_names_next_wait_time(self) -> None:
        """Test each variant tells readers when to expect the next summary."""
        for reason, new in [
            (CadenceChangeReason.NEWS_VOLUME, 30),
            (CadenceChangeReason.RADAR_OUTAGE, 15),
            (CadenceChangeReason.CALM_DECAY, 45),
        ]:
            notice = build_cadence_notice(self._decision(60, new, reason))
            assert "خلاصه بعدی" in notice
            assert to_persian_digits(new) in notice

    def test_no_html_unsafe_characters(self) -> None:
        """Test the notice is safe to post through the HTML alert path."""
        for reason in CadenceChangeReason:
            notice = build_cadence_notice(self._decision(60, 30, reason))
            assert "<" not in notice
            assert ">" not in notice
            assert "&" not in notice

    def test_unchanged_decision_rejected(self) -> None:
        """Test building a notice for a non-changed decision is an error."""
        decision = CadenceDecision(
            previous_interval=30,
            new_interval=30,
            level=IntensityLevel.NORMAL,
            reason=None,
        )

        with pytest.raises(ValueError):
            build_cadence_notice(decision)
