"""Tests for the Iran relevance filter."""

from datetime import datetime

from src.config import IranFilter
from src.iran_filter import IranRelevanceFilter
from src.models import Message


class TestIranRelevanceFilter:
    """Tests for IranRelevanceFilter class."""

    def test_init_with_keywords(self, sample_iran_filter: IranFilter) -> None:
        """Test filter initialization with keywords."""
        filter_obj = IranRelevanceFilter(sample_iran_filter)
        assert filter_obj.enabled is True
        assert filter_obj._pattern is not None

    def test_init_disabled(self) -> None:
        """Test filter initialization when disabled."""
        config = IranFilter(enabled=False, keywords=["iran"])
        filter_obj = IranRelevanceFilter(config)
        assert filter_obj.enabled is False

    def test_init_empty_keywords(self) -> None:
        """Test filter initialization with empty keywords."""
        config = IranFilter(enabled=True, keywords=[])
        filter_obj = IranRelevanceFilter(config)
        assert filter_obj._pattern is None

    def test_is_iran_related_positive(self, sample_iran_filter: IranFilter) -> None:
        """Test detection of Iran-related text."""
        filter_obj = IranRelevanceFilter(sample_iran_filter)

        assert filter_obj.is_iran_related("News from Iran today")
        assert filter_obj.is_iran_related("Iranian officials meet")
        assert filter_obj.is_iran_related("Conference in Tehran")

    def test_is_iran_related_negative(self, sample_iran_filter: IranFilter) -> None:
        """Test non-Iran-related text is not matched."""
        filter_obj = IranRelevanceFilter(sample_iran_filter)

        assert not filter_obj.is_iran_related("Weather in Paris")
        assert not filter_obj.is_iran_related("Sports news from Germany")
        assert not filter_obj.is_iran_related("Stock market update")

    def test_is_iran_related_case_insensitive(self, sample_iran_filter: IranFilter) -> None:
        """Test case insensitivity of keyword matching."""
        filter_obj = IranRelevanceFilter(sample_iran_filter)

        assert filter_obj.is_iran_related("IRAN in the news")
        assert filter_obj.is_iran_related("iran policy changes")
        assert filter_obj.is_iran_related("IrAn summit")

    def test_is_iran_related_persian_keywords(self) -> None:
        """Test Persian keyword matching."""
        config = IranFilter(enabled=True, keywords=["ایران", "تهران"])
        filter_obj = IranRelevanceFilter(config)

        assert filter_obj.is_iran_related("اخبار ایران امروز")
        assert filter_obj.is_iran_related("هوای تهران")
        assert not filter_obj.is_iran_related("اخبار فرانسه")

    def test_is_iran_related_disabled_filter(self) -> None:
        """Test that disabled filter returns True for all."""
        config = IranFilter(enabled=False, keywords=["iran"])
        filter_obj = IranRelevanceFilter(config)

        assert filter_obj.is_iran_related("Random news")
        assert filter_obj.is_iran_related("Any text at all")

    def test_filter_message(self, sample_iran_filter: IranFilter) -> None:
        """Test filtering a single message."""
        filter_obj = IranRelevanceFilter(sample_iran_filter)

        iran_message = Message(
            id=1,
            channel_username="test",
            channel_title="Test",
            text="News about Iran",
            timestamp=datetime.now(),
        )
        other_message = Message(
            id=2,
            channel_username="test",
            channel_title="Test",
            text="Weather in Paris",
            timestamp=datetime.now(),
        )

        assert filter_obj.filter_message(iran_message) is True
        assert filter_obj.filter_message(other_message) is False

    def test_filter_messages(
        self, sample_iran_filter: IranFilter, sample_rss_messages: list[Message]
    ) -> None:
        """Test filtering a list of messages."""
        filter_obj = IranRelevanceFilter(sample_iran_filter)

        filtered = filter_obj.filter_messages(sample_rss_messages)

        # Should keep "Iran announces..." and "Iranian scientists..."
        # Should filter out "Weather update for Paris..."
        assert len(filtered) == 2
        assert all("iran" in msg.text.lower() for msg in filtered)

    def test_filter_messages_disabled(
        self, sample_rss_messages: list[Message]
    ) -> None:
        """Test that disabled filter returns all messages."""
        config = IranFilter(enabled=False, keywords=["iran"])
        filter_obj = IranRelevanceFilter(config)

        filtered = filter_obj.filter_messages(sample_rss_messages)

        assert len(filtered) == len(sample_rss_messages)

    def test_word_boundary_matching(self, sample_iran_filter: IranFilter) -> None:
        """Test that keywords match on word boundaries only."""
        filter_obj = IranRelevanceFilter(sample_iran_filter)

        # Should match - complete word
        assert filter_obj.is_iran_related("The Iran deal")

        # Word boundaries work correctly
        assert filter_obj.is_iran_related("Iran's policy")
