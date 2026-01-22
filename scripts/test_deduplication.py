#!/usr/bin/env python3
"""Standalone test script for the deduplication system.

This script fetches recent articles from RSS feeds and runs them through
the deduplicator to visualize how deduplication works.

Usage:
    # Basic usage (uses default threshold from config)
    uv run python scripts/test_deduplication.py

    # Override similarity threshold
    uv run python scripts/test_deduplication.py --threshold 0.3

    # Limit number of articles to fetch
    uv run python scripts/test_deduplication.py --limit 20

    # Show verbose output (all similarity comparisons)
    uv run python scripts/test_deduplication.py -v

    # Use a specific database file (for testing)
    uv run python scripts/test_deduplication.py --db /tmp/test_dedup.db

    # Clear the test database before running
    uv run python scripts/test_deduplication.py --clear
"""

import argparse
import asyncio
import json
import logging
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

# Add the project root to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv

from src.config import Config, ConfigError, DeduplicationConfig
from src.database import ArticleFingerprint
from src.deduplicator import Deduplicator
from src.iran_filter import IranRelevanceFilter
from src.models import Message
from src.rss_reader import RSSReader


# ANSI color codes for terminal output
class Colors:
    HEADER = "\033[95m"
    BLUE = "\033[94m"
    CYAN = "\033[96m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    RED = "\033[91m"
    ENDC = "\033[0m"
    BOLD = "\033[1m"


def print_header(text: str) -> None:
    """Print a colored header."""
    print(f"\n{Colors.HEADER}{Colors.BOLD}{'=' * 60}{Colors.ENDC}")
    print(f"{Colors.HEADER}{Colors.BOLD}{text}{Colors.ENDC}")
    print(f"{Colors.HEADER}{Colors.BOLD}{'=' * 60}{Colors.ENDC}\n")


def print_article(index: int, msg: Message, fingerprint: ArticleFingerprint | None) -> None:
    """Print article details with extracted features."""
    print(f"{Colors.CYAN}Article {index}:{Colors.ENDC}")
    print(f"  {Colors.BOLD}Title:{Colors.ENDC} {msg.text[:100]}...")
    print(f"  {Colors.BOLD}Source:{Colors.ENDC} {msg.channel_title}")
    print(f"  {Colors.BOLD}URL:{Colors.ENDC} {msg.url}")
    print(f"  {Colors.BOLD}Time:{Colors.ENDC} {msg.timestamp}")

    if fingerprint:
        print(f"  {Colors.GREEN}Extracted Features:{Colors.ENDC}")
        print(f"    Topic: {fingerprint.topic}")
        print(f"    Entities: {fingerprint.entities}")
        print(f"    Event Type: {fingerprint.event_type}")
        print(f"    Keywords: {fingerprint.keywords}")
    else:
        print(f"  {Colors.RED}Feature extraction failed{Colors.ENDC}")
    print()


def print_comparison(
    article1: ArticleFingerprint,
    article2: ArticleFingerprint,
    similarity: float,
    threshold: float,
    is_duplicate: bool,
) -> None:
    """Print similarity comparison between two articles."""
    status_color = Colors.RED if is_duplicate else Colors.GREEN
    status_text = "DUPLICATE" if is_duplicate else "UNIQUE"

    print(f"{Colors.YELLOW}Comparison:{Colors.ENDC}")
    print(f"  Article A: {article1.title[:50]}...")
    print(f"  Article B: {article2.title[:50]}...")
    print(f"  Topic Match: {article1.topic} == {article2.topic}")
    print(f"  Entities A: {article1.entities}")
    print(f"  Entities B: {article2.entities}")
    print(f"  Similarity: {similarity:.2%} (threshold: {threshold:.2%})")
    print(f"  {status_color}{Colors.BOLD}Result: {status_text}{Colors.ENDC}")
    print()


class VerboseDeduplicator(Deduplicator):
    """Extended Deduplicator with verbose output for testing."""

    def __init__(self, config: Config, verbose: bool = False) -> None:
        super().__init__(config)
        self.verbose = verbose
        self.comparisons: list[dict] = []  # Store comparisons for reporting
        self.fingerprints: list[tuple[Message, ArticleFingerprint | None]] = []

    def extract_features(self, message: Message) -> ArticleFingerprint | None:
        """Extract features and store for reporting."""
        fingerprint = super().extract_features(message)
        self.fingerprints.append((message, fingerprint))
        return fingerprint

    def is_duplicate(self, fingerprint: ArticleFingerprint) -> bool:
        """Check duplicate with verbose comparison logging."""
        # First check URL
        if self._db.url_exists(fingerprint.url):
            if self.verbose:
                print(f"{Colors.RED}URL already exists: {fingerprint.url}{Colors.ENDC}")
            return True

        # Get recent with same topic
        recent = self._db.get_recent_by_topic(
            fingerprint.topic,
            days=self._dedup_config.ttl_days,
        )

        if not recent:
            return False

        new_entities = {e.lower() for e in fingerprint.entities}

        for stored in recent:
            stored_entities = {e.lower() for e in stored.entities}
            overlap = len(stored_entities & new_entities)
            total = len(stored_entities | new_entities)

            if total > 0:
                similarity = overlap / total
                is_dup = similarity >= self._dedup_config.similarity_threshold

                # Store comparison for reporting
                self.comparisons.append({
                    "new": fingerprint,
                    "stored": stored,
                    "similarity": similarity,
                    "threshold": self._dedup_config.similarity_threshold,
                    "is_duplicate": is_dup,
                })

                if self.verbose:
                    print_comparison(
                        stored, fingerprint, similarity,
                        self._dedup_config.similarity_threshold, is_dup
                    )

                if is_dup:
                    return True

        return False


async def fetch_articles(config: Config, limit: int, hours_back: int) -> list[Message]:
    """Fetch recent articles from RSS feeds."""
    rss_reader = RSSReader(config)
    iran_filter = IranRelevanceFilter(config.iran_filter)

    await rss_reader.start()
    try:
        since = datetime.now() - timedelta(hours=hours_back)
        messages = await rss_reader.get_all_feed_updates(since)

        # Apply Iran filter if enabled
        if config.iran_filter.enabled:
            messages = iran_filter.filter_messages(messages)

        return messages[:limit]  # Respect overall limit
    finally:
        await rss_reader.stop()


def generate_report(
    dedup: VerboseDeduplicator,
    unique_messages: list[Message],
    all_messages: list[Message],
) -> None:
    """Generate a summary report."""
    print_header("DEDUPLICATION REPORT")

    print(f"{Colors.BOLD}Summary:{Colors.ENDC}")
    print(f"  Total articles processed: {len(all_messages)}")
    print(f"  Unique articles: {len(unique_messages)}")
    print(f"  Duplicates removed: {len(all_messages) - len(unique_messages)}")
    print(f"  Similarity threshold: {dedup._dedup_config.similarity_threshold:.2%}")
    print()

    # Feature extraction results
    successful = sum(1 for _, fp in dedup.fingerprints if fp is not None)
    failed = len(dedup.fingerprints) - successful
    print(f"{Colors.BOLD}Feature Extraction:{Colors.ENDC}")
    print(f"  Successful: {successful}")
    print(f"  Failed: {failed}")
    print()

    # Topic distribution
    topics: dict[str, int] = {}
    for _, fp in dedup.fingerprints:
        if fp:
            topics[fp.topic] = topics.get(fp.topic, 0) + 1

    if topics:
        print(f"{Colors.BOLD}Topic Distribution:{Colors.ENDC}")
        for topic, count in sorted(topics.items(), key=lambda x: -x[1]):
            print(f"  {topic}: {count}")
        print()

    # Duplicate pairs found
    duplicates = [c for c in dedup.comparisons if c["is_duplicate"]]
    if duplicates:
        print(f"{Colors.BOLD}Duplicate Pairs Found:{Colors.ENDC}")
        for comp in duplicates:
            print(f"  - '{comp['new'].title[:40]}...' matches '{comp['stored'].title[:40]}...'")
            print(f"    Similarity: {comp['similarity']:.2%}")
        print()

    # Unique articles
    print(f"{Colors.BOLD}Unique Articles:{Colors.ENDC}")
    for i, msg in enumerate(unique_messages, 1):
        print(f"  {i}. {msg.text[:60]}... ({msg.channel_title})")


async def main() -> None:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Test the deduplication system with real RSS feed data",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--threshold", "-t",
        type=float,
        help="Override similarity threshold (0.0-1.0, default: from config)",
    )
    parser.add_argument(
        "--limit", "-l",
        type=int,
        default=30,
        help="Maximum number of articles to fetch (default: 30)",
    )
    parser.add_argument(
        "--hours", "-H",
        type=int,
        default=24,
        help="Hours to look back for articles (default: 24)",
    )
    parser.add_argument(
        "--db",
        type=str,
        default=".dedup_test.db",
        help="Database file path (default: .dedup_test.db)",
    )
    parser.add_argument(
        "--clear",
        action="store_true",
        help="Clear the test database before running",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Show verbose output including all similarity comparisons",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output results as JSON",
    )
    parser.add_argument(
        "--show-features",
        action="store_true",
        help="Show extracted features for each article",
    )

    args = parser.parse_args()

    # Set up logging based on verbosity
    log_level = logging.DEBUG if args.verbose else logging.WARNING
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    # Clear test database if requested
    db_path = Path(args.db)
    if args.clear and db_path.exists():
        db_path.unlink()
        print(f"Cleared test database: {db_path}")

    # Load configuration
    load_dotenv()
    try:
        config = Config.from_env()
    except ConfigError as e:
        print(f"Configuration error: {e}", file=sys.stderr)
        sys.exit(1)

    # Override deduplication settings for testing
    if args.threshold is not None:
        config.deduplication = DeduplicationConfig(
            enabled=True,
            similarity_threshold=args.threshold,
            ttl_days=config.deduplication.ttl_days,
        )
    config.dedup_db_path = args.db

    if not args.json:
        print_header("DEDUPLICATION TEST")
        print("Settings:")
        print(f"  Similarity threshold: {config.deduplication.similarity_threshold:.2%}")
        print(f"  TTL days: {config.deduplication.ttl_days}")
        print(f"  Database: {args.db}")
        print(f"  Article limit: {args.limit}")
        print(f"  Hours back: {args.hours}")
        print()

    # Fetch articles
    if not args.json:
        print_header("FETCHING ARTICLES")
        print(f"Fetching up to {args.limit} articles from the last {args.hours} hours...")

    messages = await fetch_articles(config, args.limit, args.hours)

    if not args.json:
        print(f"Fetched {len(messages)} articles")

    if not messages:
        if not args.json:
            print("No articles found. Try increasing --hours or check RSS feeds.")
        return

    # Process through deduplicator
    if not args.json:
        print_header("PROCESSING ARTICLES")

    dedup = VerboseDeduplicator(config, verbose=args.verbose)
    dedup.start()

    try:
        # Show each article and its extracted features if requested
        if args.show_features and not args.json:
            print_header("EXTRACTING FEATURES")
            for i, msg in enumerate(messages, 1):
                fingerprint = dedup.extract_features(msg)
                print_article(i, msg, fingerprint)

            # Reset for actual processing
            dedup.fingerprints = []
            dedup.comparisons = []

        # Process messages
        unique_messages = dedup.process_messages(messages)

        # Generate report
        if args.json:
            output = {
                "total_articles": len(messages),
                "unique_articles": len(unique_messages),
                "duplicates_removed": len(messages) - len(unique_messages),
                "threshold": config.deduplication.similarity_threshold,
                "articles": [
                    {
                        "title": msg.text[:100],
                        "source": msg.channel_title,
                        "url": msg.url,
                    }
                    for msg in unique_messages
                ],
                "duplicate_pairs": [
                    {
                        "article1": comp["new"].title[:100],
                        "article2": comp["stored"].title[:100],
                        "similarity": comp["similarity"],
                    }
                    for comp in dedup.comparisons if comp["is_duplicate"]
                ],
            }
            print(json.dumps(output, indent=2))
        else:
            generate_report(dedup, unique_messages, messages)

    finally:
        dedup.stop()


if __name__ == "__main__":
    asyncio.run(main())
