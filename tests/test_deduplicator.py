"""Tests for the deduplicator module."""

from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.config import Config, DeduplicationConfig
from src.database import ArticleFingerprint
from src.deduplicator import Deduplicator
from src.models import Message, SourceType


@pytest.fixture
def mock_config(tmp_path: Path) -> Config:
    """Create a mock config for testing."""
    return Config(
        telegram_api_id=12345,
        telegram_api_hash="hash",
        telegram_session_string="session",
        telegram_bot_token="token",
        output_channel_id="@channel",
        openrouter_api_key="test_key",
        llm_model="test-model",
        deduplication=DeduplicationConfig(
            enabled=True,
            similarity_threshold=0.5,
            ttl_days=3,
        ),
        dedup_db_path=str(tmp_path / ".dedup.db"),
    )


@pytest.fixture
def sample_message() -> Message:
    """Create a sample message for testing."""
    return Message(
        id=1,
        channel_username="test_channel",
        channel_title="Test Channel",
        text="Iran signs nuclear deal with EU in historic agreement",
        timestamp=datetime.now(),
        url="https://example.com/article1",
        source_type=SourceType.RSS,
    )


class TestDeduplicator:
    """Tests for the Deduplicator class."""

    def test_start_stop(self, mock_config: Config) -> None:
        """Test starting and stopping the deduplicator."""
        dedup = Deduplicator(mock_config)
        dedup.start()
        dedup.stop()

    @patch("src.deduplicator.OpenAI")
    def test_extract_features_success(
        self, mock_openai: MagicMock, mock_config: Config, sample_message: Message
    ) -> None:
        """Test successful feature extraction."""
        # Mock the LLM response
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = """{
            "topic": "nuclear_diplomacy",
            "entities": ["Iran", "EU"],
            "event_type": "announcement",
            "keywords": ["nuclear", "deal", "historic"]
        }"""
        mock_openai.return_value.chat.completions.create.return_value = mock_response

        dedup = Deduplicator(mock_config)
        dedup.start()

        fp = dedup.extract_features(sample_message)

        assert fp is not None
        assert fp.topic == "nuclear_diplomacy"
        assert fp.entities == ["Iran", "EU"]
        assert fp.event_type == "announcement"
        assert fp.keywords == ["nuclear", "deal", "historic"]
        assert fp.url == sample_message.url
        assert fp.source == sample_message.channel_title

        dedup.stop()

    @patch("src.deduplicator.OpenAI")
    def test_extract_features_with_markdown_response(
        self, mock_openai: MagicMock, mock_config: Config, sample_message: Message
    ) -> None:
        """Test feature extraction with markdown code blocks."""
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = """```json
{
    "topic": "politics",
    "entities": ["Iran"],
    "event_type": "report",
    "keywords": ["news"]
}
```"""
        mock_openai.return_value.chat.completions.create.return_value = mock_response

        dedup = Deduplicator(mock_config)
        dedup.start()

        fp = dedup.extract_features(sample_message)

        assert fp is not None
        assert fp.topic == "politics"
        dedup.stop()

    @patch("src.deduplicator.OpenAI")
    def test_extract_features_empty_response(
        self, mock_openai: MagicMock, mock_config: Config, sample_message: Message
    ) -> None:
        """Test feature extraction with empty LLM response."""
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = ""
        mock_openai.return_value.chat.completions.create.return_value = mock_response

        dedup = Deduplicator(mock_config)
        dedup.start()

        fp = dedup.extract_features(sample_message)

        assert fp is None
        dedup.stop()

    @patch("src.deduplicator.OpenAI")
    def test_extract_features_invalid_json(
        self, mock_openai: MagicMock, mock_config: Config, sample_message: Message
    ) -> None:
        """Test feature extraction with invalid JSON response."""
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "not valid json"
        mock_openai.return_value.chat.completions.create.return_value = mock_response

        dedup = Deduplicator(mock_config)
        dedup.start()

        fp = dedup.extract_features(sample_message)

        assert fp is None
        dedup.stop()

    @patch("src.deduplicator.OpenAI")
    def test_extract_features_missing_topic(
        self, mock_openai: MagicMock, mock_config: Config, sample_message: Message
    ) -> None:
        """Test feature extraction with missing topic field."""
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = """{
            "entities": ["Iran"],
            "event_type": "report",
            "keywords": ["news"]
        }"""
        mock_openai.return_value.chat.completions.create.return_value = mock_response

        dedup = Deduplicator(mock_config)
        dedup.start()

        fp = dedup.extract_features(sample_message)

        assert fp is None
        dedup.stop()

    @patch("src.deduplicator.OpenAI")
    def test_extract_features_api_error(
        self, mock_openai: MagicMock, mock_config: Config, sample_message: Message
    ) -> None:
        """Test feature extraction with API error."""
        mock_openai.return_value.chat.completions.create.side_effect = Exception(
            "API Error"
        )

        dedup = Deduplicator(mock_config)
        dedup.start()

        fp = dedup.extract_features(sample_message)

        assert fp is None
        dedup.stop()

    def test_is_duplicate_url_match(self, mock_config: Config) -> None:
        """Test duplicate detection by URL match."""
        dedup = Deduplicator(mock_config)
        dedup.start()

        # Store a fingerprint
        fp = ArticleFingerprint(
            url="https://example.com/article",
            title="Test",
            topic="news",
            entities=["Iran"],
            event_type="report",
            keywords=["test"],
            source="Reuters",
        )
        dedup.store(fp)

        # Same URL should be duplicate
        assert dedup.is_duplicate(fp) is True
        dedup.stop()

    def test_is_duplicate_entity_overlap(self, mock_config: Config) -> None:
        """Test duplicate detection by entity overlap."""
        dedup = Deduplicator(mock_config)
        dedup.start()

        # Store original
        original = ArticleFingerprint(
            url="https://example.com/original",
            title="Original Article",
            topic="nuclear_diplomacy",
            entities=["Iran", "EU", "IAEA"],
            event_type="announcement",
            keywords=["nuclear"],
            source="Reuters",
        )
        dedup.store(original)

        # Similar article with 66% entity overlap (2/3)
        similar = ArticleFingerprint(
            url="https://example.com/similar",
            title="Similar Article",
            topic="nuclear_diplomacy",
            entities=["Iran", "EU"],  # 2 out of 3 entities match
            event_type="report",
            keywords=["deal"],
            source="BBC",
        )

        assert dedup.is_duplicate(similar) is True
        dedup.stop()

    def test_is_duplicate_low_overlap(self, mock_config: Config) -> None:
        """Test that low entity overlap is not duplicate."""
        dedup = Deduplicator(mock_config)
        dedup.start()

        original = ArticleFingerprint(
            url="https://example.com/original",
            title="Original",
            topic="politics",
            entities=["Iran", "EU", "USA", "UK"],
            event_type="announcement",
            keywords=["nuclear"],
            source="Reuters",
        )
        dedup.store(original)

        # Only 25% overlap (1 out of 4)
        different = ArticleFingerprint(
            url="https://example.com/different",
            title="Different",
            topic="politics",
            entities=["Iran", "China", "Russia"],
            event_type="report",
            keywords=["trade"],
            source="BBC",
        )

        assert dedup.is_duplicate(different) is False
        dedup.stop()

    def test_is_duplicate_different_topic(self, mock_config: Config) -> None:
        """Test that different topics are not duplicates."""
        dedup = Deduplicator(mock_config)
        dedup.start()

        original = ArticleFingerprint(
            url="https://example.com/original",
            title="Original",
            topic="politics",
            entities=["Iran", "EU"],
            event_type="announcement",
            keywords=["nuclear"],
            source="Reuters",
        )
        dedup.store(original)

        # Same entities but different topic
        different = ArticleFingerprint(
            url="https://example.com/different",
            title="Different",
            topic="sports",  # Different topic
            entities=["Iran", "EU"],
            event_type="report",
            keywords=["football"],
            source="BBC",
        )

        assert dedup.is_duplicate(different) is False
        dedup.stop()

    def test_is_duplicate_case_insensitive(self, mock_config: Config) -> None:
        """Test that entity comparison is case insensitive."""
        dedup = Deduplicator(mock_config)
        dedup.start()

        original = ArticleFingerprint(
            url="https://example.com/original",
            title="Original",
            topic="news",
            entities=["IRAN", "EU"],
            event_type="announcement",
            keywords=["nuclear"],
            source="Reuters",
        )
        dedup.store(original)

        # Same entities in different case
        similar = ArticleFingerprint(
            url="https://example.com/similar",
            title="Similar",
            topic="news",
            entities=["iran", "eu"],  # Lowercase
            event_type="report",
            keywords=["deal"],
            source="BBC",
        )

        assert dedup.is_duplicate(similar) is True
        dedup.stop()

    @patch("src.deduplicator.OpenAI")
    def test_process_messages_filters_duplicates(
        self, mock_openai: MagicMock, mock_config: Config
    ) -> None:
        """Test that process_messages filters duplicates."""
        # Mock LLM responses
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = """{
            "topic": "news",
            "entities": ["Iran", "EU"],
            "event_type": "report",
            "keywords": ["test"]
        }"""
        mock_openai.return_value.chat.completions.create.return_value = mock_response

        dedup = Deduplicator(mock_config)
        dedup.start()

        messages = [
            Message(
                id=1,
                channel_username="ch1",
                channel_title="Channel 1",
                text="Article about Iran and EU",
                timestamp=datetime.now(),
                url="https://example.com/1",
            ),
            Message(
                id=2,
                channel_username="ch2",
                channel_title="Channel 2",
                text="Similar article about Iran and EU",
                timestamp=datetime.now(),
                url="https://example.com/2",
            ),
        ]

        # First message should be kept, second filtered as duplicate
        unique = dedup.process_messages(messages)

        # Both have same extracted features, second should be duplicate
        assert len(unique) == 1
        assert unique[0].url == "https://example.com/1"

        dedup.stop()

    @patch("src.deduplicator.OpenAI")
    def test_process_messages_keeps_failed_extractions(
        self, mock_openai: MagicMock, mock_config: Config
    ) -> None:
        """Test that messages with failed extraction are kept."""
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "invalid json"
        mock_openai.return_value.chat.completions.create.return_value = mock_response

        dedup = Deduplicator(mock_config)
        dedup.start()

        messages = [
            Message(
                id=1,
                channel_username="ch1",
                channel_title="Channel 1",
                text="Article",
                timestamp=datetime.now(),
                url="https://example.com/1",
            ),
        ]

        unique = dedup.process_messages(messages)

        # Message should be kept despite failed extraction
        assert len(unique) == 1

        dedup.stop()

    def test_process_messages_disabled(self, mock_config: Config) -> None:
        """Test that disabled deduplication returns all messages."""
        mock_config.deduplication.enabled = False

        dedup = Deduplicator(mock_config)
        dedup.start()

        messages = [
            Message(
                id=1,
                channel_username="ch1",
                channel_title="Channel 1",
                text="Article 1",
                timestamp=datetime.now(),
                url="https://example.com/1",
            ),
            Message(
                id=2,
                channel_username="ch2",
                channel_title="Channel 2",
                text="Article 2",
                timestamp=datetime.now(),
                url="https://example.com/2",
            ),
        ]

        unique = dedup.process_messages(messages)

        assert len(unique) == 2

        dedup.stop()

    def test_cleanup(self, mock_config: Config) -> None:
        """Test cleanup method."""
        dedup = Deduplicator(mock_config)
        dedup.start()

        # Store and cleanup
        fp = ArticleFingerprint(
            url="https://example.com/1",
            title="Test",
            topic="news",
            entities=[],
            event_type="report",
            keywords=[],
            source="BBC",
        )
        dedup.store(fp)

        deleted = dedup.cleanup()
        assert deleted == 0  # Recent entry not cleaned

        dedup.stop()
