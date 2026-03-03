"""Tests for the fingerprint database module."""

from datetime import datetime
from pathlib import Path

import pytest

from src.database import ArticleFingerprint, FingerprintDatabase


class TestArticleFingerprint:
    """Tests for the ArticleFingerprint dataclass."""

    def test_create_fingerprint(self) -> None:
        """Test creating a fingerprint with all fields."""
        fp = ArticleFingerprint(
            url="https://example.com/article",
            title="Test Article",
            topic="politics",
            entities=["Iran", "EU"],
            event_type="announcement",
            keywords=["nuclear", "deal"],
            source="Reuters",
        )

        assert fp.url == "https://example.com/article"
        assert fp.title == "Test Article"
        assert fp.topic == "politics"
        assert fp.entities == ["Iran", "EU"]
        assert fp.event_type == "announcement"
        assert fp.keywords == ["nuclear", "deal"]
        assert fp.source == "Reuters"
        assert fp.id is None
        assert fp.timestamp is None

    def test_fingerprint_with_id_and_timestamp(self) -> None:
        """Test fingerprint with optional id and timestamp."""
        now = datetime.now()
        fp = ArticleFingerprint(
            url="https://example.com/article",
            title="Test",
            topic="news",
            entities=[],
            event_type="report",
            keywords=[],
            source="BBC",
            id=42,
            timestamp=now,
        )

        assert fp.id == 42
        assert fp.timestamp == now


class TestFingerprintDatabase:
    """Tests for the FingerprintDatabase class."""

    def test_init_db(self, tmp_path: Path) -> None:
        """Test database initialization creates tables."""
        db_path = tmp_path / "test.db"
        db = FingerprintDatabase(db_path)
        db.init_db()

        assert db_path.exists()
        assert db.count() == 0
        db.close()

    def test_store_fingerprint(self, tmp_path: Path) -> None:
        """Test storing a fingerprint."""
        db_path = tmp_path / "test.db"
        db = FingerprintDatabase(db_path)
        db.init_db()

        fp = ArticleFingerprint(
            url="https://example.com/1",
            title="Test Article",
            topic="politics",
            entities=["Iran", "EU"],
            event_type="announcement",
            keywords=["nuclear"],
            source="Reuters",
        )

        result = db.store_fingerprint(fp)
        assert result is True
        assert db.count() == 1
        db.close()

    def test_store_duplicate_url_fails(self, tmp_path: Path) -> None:
        """Test that storing duplicate URL returns False."""
        db_path = tmp_path / "test.db"
        db = FingerprintDatabase(db_path)
        db.init_db()

        fp = ArticleFingerprint(
            url="https://example.com/same",
            title="First",
            topic="news",
            entities=[],
            event_type="report",
            keywords=[],
            source="BBC",
        )

        assert db.store_fingerprint(fp) is True
        assert db.store_fingerprint(fp) is False  # Duplicate
        assert db.count() == 1
        db.close()

    def test_url_exists(self, tmp_path: Path) -> None:
        """Test checking if URL exists."""
        db_path = tmp_path / "test.db"
        db = FingerprintDatabase(db_path)
        db.init_db()

        fp = ArticleFingerprint(
            url="https://example.com/article",
            title="Test",
            topic="news",
            entities=[],
            event_type="report",
            keywords=[],
            source="BBC",
        )

        assert db.url_exists("https://example.com/article") is False
        db.store_fingerprint(fp)
        assert db.url_exists("https://example.com/article") is True
        assert db.url_exists("https://other.com/article") is False
        db.close()

    def test_get_recent_by_topic(self, tmp_path: Path) -> None:
        """Test getting recent fingerprints by topic."""
        db_path = tmp_path / "test.db"
        db = FingerprintDatabase(db_path)
        db.init_db()

        # Store fingerprints with same topic
        for i in range(3):
            fp = ArticleFingerprint(
                url=f"https://example.com/{i}",
                title=f"Article {i}",
                topic="politics",
                entities=["Iran"],
                event_type="report",
                keywords=["test"],
                source="Reuters",
            )
            db.store_fingerprint(fp)

        # Store one with different topic
        fp_other = ArticleFingerprint(
            url="https://example.com/other",
            title="Other",
            topic="sports",
            entities=["Football"],
            event_type="report",
            keywords=["match"],
            source="BBC",
        )
        db.store_fingerprint(fp_other)

        results = db.get_recent_by_topic("politics", days=3)
        assert len(results) == 3
        assert all(r.topic == "politics" for r in results)

        results_sports = db.get_recent_by_topic("sports", days=3)
        assert len(results_sports) == 1
        db.close()

    def test_get_recent_by_topic_returns_parsed_data(self, tmp_path: Path) -> None:
        """Test that retrieved fingerprints have parsed JSON fields."""
        db_path = tmp_path / "test.db"
        db = FingerprintDatabase(db_path)
        db.init_db()

        fp = ArticleFingerprint(
            url="https://example.com/1",
            title="Test",
            topic="news",
            entities=["Iran", "EU", "USA"],
            event_type="announcement",
            keywords=["nuclear", "deal", "sanctions"],
            source="Reuters",
        )
        db.store_fingerprint(fp)

        results = db.get_recent_by_topic("news", days=3)
        assert len(results) == 1
        retrieved = results[0]
        assert retrieved.entities == ["Iran", "EU", "USA"]
        assert retrieved.keywords == ["nuclear", "deal", "sanctions"]
        assert retrieved.id is not None
        assert retrieved.timestamp is not None
        db.close()

    def test_cleanup_old(self, tmp_path: Path) -> None:
        """Test cleanup of old fingerprints."""
        db_path = tmp_path / "test.db"
        db = FingerprintDatabase(db_path)
        db.init_db()

        # Store a fingerprint (it will be recent)
        fp = ArticleFingerprint(
            url="https://example.com/new",
            title="New",
            topic="news",
            entities=[],
            event_type="report",
            keywords=[],
            source="BBC",
        )
        db.store_fingerprint(fp)

        # Cleanup with 0 days should remove everything
        # but we just stored it so it's within the window
        deleted = db.cleanup_old(days=7)
        assert deleted == 0
        assert db.count() == 1
        db.close()

    def test_count(self, tmp_path: Path) -> None:
        """Test counting fingerprints."""
        db_path = tmp_path / "test.db"
        db = FingerprintDatabase(db_path)
        db.init_db()

        assert db.count() == 0

        for i in range(5):
            fp = ArticleFingerprint(
                url=f"https://example.com/{i}",
                title=f"Article {i}",
                topic="news",
                entities=[],
                event_type="report",
                keywords=[],
                source="BBC",
            )
            db.store_fingerprint(fp)

        assert db.count() == 5
        db.close()

    def test_operations_before_init_raise_error(self, tmp_path: Path) -> None:
        """Test that operations before init_db raise RuntimeError."""
        db_path = tmp_path / "test.db"
        db = FingerprintDatabase(db_path)

        fp = ArticleFingerprint(
            url="https://example.com/1",
            title="Test",
            topic="news",
            entities=[],
            event_type="report",
            keywords=[],
            source="BBC",
        )

        with pytest.raises(RuntimeError, match="not initialized"):
            db.store_fingerprint(fp)

        with pytest.raises(RuntimeError, match="not initialized"):
            db.url_exists("https://example.com/1")

        with pytest.raises(RuntimeError, match="not initialized"):
            db.get_recent_by_topic("news")

        with pytest.raises(RuntimeError, match="not initialized"):
            db.cleanup_old()

        with pytest.raises(RuntimeError, match="not initialized"):
            db.count()

    def test_get_recent(self, tmp_path: Path) -> None:
        """Test getting all recent fingerprints across topics."""
        db_path = tmp_path / "test.db"
        db = FingerprintDatabase(db_path)
        db.init_db()

        # Store fingerprints with different topics
        for i, topic in enumerate(["politics", "sports", "economy"]):
            fp = ArticleFingerprint(
                url=f"https://example.com/{i}",
                title=f"Article {i}",
                topic=topic,
                entities=["Iran"],
                event_type="report",
                keywords=["test"],
                source="Reuters",
            )
            db.store_fingerprint(fp)

        results = db.get_recent(days=3)
        assert len(results) == 3
        topics = {r.topic for r in results}
        assert topics == {"politics", "sports", "economy"}
        db.close()

    def test_get_recent_before_init_raises_error(self, tmp_path: Path) -> None:
        """Test that get_recent raises RuntimeError before init_db."""
        db_path = tmp_path / "test.db"
        db = FingerprintDatabase(db_path)

        with pytest.raises(RuntimeError, match="not initialized"):
            db.get_recent()

    def test_close_without_init(self, tmp_path: Path) -> None:
        """Test that close without init is safe."""
        db_path = tmp_path / "test.db"
        db = FingerprintDatabase(db_path)
        db.close()  # Should not raise
