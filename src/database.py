"""SQLite database management for article fingerprints."""

import json
import logging
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

# Default database file path
DEFAULT_DB_PATH = Path(".dedup.db")


@dataclass
class ArticleFingerprint:
    """Fingerprint of an article for deduplication."""

    url: str
    title: str
    topic: str
    entities: list[str]
    event_type: str
    keywords: list[str]
    source: str
    id: int | None = None
    timestamp: datetime | None = None


class FingerprintDatabase:
    """Manages SQLite database for article fingerprints."""

    def __init__(self, db_path: Path = DEFAULT_DB_PATH) -> None:
        """Initialize the database connection."""
        self.db_path = db_path
        self._conn: sqlite3.Connection | None = None

    def init_db(self) -> None:
        """Create tables and indexes if they don't exist."""
        self._conn = sqlite3.connect(self.db_path)
        self._conn.row_factory = sqlite3.Row

        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS fingerprints (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                url TEXT UNIQUE NOT NULL,
                title TEXT NOT NULL,
                topic TEXT NOT NULL,
                entities TEXT NOT NULL,
                event_type TEXT NOT NULL,
                keywords TEXT NOT NULL,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                source TEXT NOT NULL
            )
        """)

        self._conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_topic_timestamp ON fingerprints(topic, timestamp)"
        )
        self._conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_timestamp ON fingerprints(timestamp)"
        )

        self._conn.commit()
        logger.info(f"Initialized fingerprint database at {self.db_path}")

    def close(self) -> None:
        """Close the database connection."""
        if self._conn:
            self._conn.close()
            self._conn = None

    def store_fingerprint(self, fp: ArticleFingerprint) -> bool:
        """Store a fingerprint in the database.

        Returns True if stored successfully, False if URL already exists.
        """
        if not self._conn:
            raise RuntimeError("Database not initialized. Call init_db() first.")

        try:
            self._conn.execute(
                """
                INSERT INTO fingerprints (url, title, topic, entities, event_type, keywords, source)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    fp.url,
                    fp.title,
                    fp.topic,
                    json.dumps(fp.entities),
                    fp.event_type,
                    json.dumps(fp.keywords),
                    fp.source,
                ),
            )
            self._conn.commit()
            return True
        except sqlite3.IntegrityError:
            # URL already exists
            logger.debug(f"URL already in database: {fp.url}")
            return False

    def get_recent_by_topic(
        self, topic: str, days: int = 3
    ) -> list[ArticleFingerprint]:
        """Get recent fingerprints with matching topic."""
        if not self._conn:
            raise RuntimeError("Database not initialized. Call init_db() first.")

        cursor = self._conn.execute(
            """
            SELECT id, url, title, topic, entities, event_type, keywords, timestamp, source
            FROM fingerprints
            WHERE topic = ? AND timestamp > datetime('now', ?)
            """,
            (topic, f"-{days} days"),
        )

        results = []
        for row in cursor:
            results.append(
                ArticleFingerprint(
                    id=row["id"],
                    url=row["url"],
                    title=row["title"],
                    topic=row["topic"],
                    entities=json.loads(row["entities"]),
                    event_type=row["event_type"],
                    keywords=json.loads(row["keywords"]),
                    timestamp=datetime.fromisoformat(row["timestamp"]),
                    source=row["source"],
                )
            )
        return results

    def url_exists(self, url: str) -> bool:
        """Check if a URL already exists in the database."""
        if not self._conn:
            raise RuntimeError("Database not initialized. Call init_db() first.")

        cursor = self._conn.execute(
            "SELECT 1 FROM fingerprints WHERE url = ?",
            (url,),
        )
        return cursor.fetchone() is not None

    def cleanup_old(self, days: int = 7) -> int:
        """Remove fingerprints older than specified days.

        Returns the number of deleted rows.
        """
        if not self._conn:
            raise RuntimeError("Database not initialized. Call init_db() first.")

        cursor = self._conn.execute(
            "DELETE FROM fingerprints WHERE timestamp < datetime('now', ?)",
            (f"-{days} days",),
        )
        self._conn.commit()
        deleted = cursor.rowcount
        if deleted > 0:
            logger.info(f"Cleaned up {deleted} old fingerprints")
        return deleted

    def count(self) -> int:
        """Return the total number of fingerprints in the database."""
        if not self._conn:
            raise RuntimeError("Database not initialized. Call init_db() first.")

        cursor = self._conn.execute("SELECT COUNT(*) FROM fingerprints")
        return cursor.fetchone()[0]
