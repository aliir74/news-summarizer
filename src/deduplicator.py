"""News article deduplication using LLM entity extraction."""

import json
import logging
from pathlib import Path

from openai import OpenAI

from src.config import Config
from src.database import ArticleFingerprint, FingerprintDatabase
from src.models import Message

logger = logging.getLogger(__name__)

EXTRACTION_PROMPT = """Extract key information from this news article.
Return JSON only, no explanation.

Article:
{text}

Return this exact JSON structure:
{{
  "topic": "main topic in 1-3 words",
  "entities": ["list", "of", "key", "entities"],
  "event_type": "announcement|reaction|analysis|report|other",
  "keywords": ["3-5", "key", "words"]
}}"""


class Deduplicator:
    """Handles article deduplication using LLM-based feature extraction."""

    def __init__(self, config: Config) -> None:
        """Initialize the deduplicator."""
        self.config = config
        self._dedup_config = config.deduplication
        self._db = FingerprintDatabase(Path(config.dedup_db_path))
        self._client = OpenAI(
            api_key=config.openrouter_api_key,
            base_url="https://openrouter.ai/api/v1",
        )

    def start(self) -> None:
        """Initialize the database."""
        self._db.init_db()
        logger.info("Deduplicator started")

    def stop(self) -> None:
        """Close the database connection."""
        self._db.close()
        logger.info("Deduplicator stopped")

    def extract_features(self, message: Message) -> ArticleFingerprint | None:
        """Extract features from a message using LLM.

        Returns None if extraction fails.
        """
        prompt = EXTRACTION_PROMPT.format(text=message.text[:2000])  # Limit text length

        try:
            response = self._client.chat.completions.create(
                model=self.config.llm_model,
                messages=[
                    {
                        "role": "system",
                        "content": "You are a news analyzer. Extract key features from news articles.",
                    },
                    {"role": "user", "content": prompt},
                ],
                max_tokens=200,
                temperature=0.3,
            )

            content = response.choices[0].message.content
            if not content:
                logger.warning("Empty response from LLM for feature extraction")
                return None

            # Parse JSON response
            data = self._parse_json_response(content)
            if not data:
                return None

            logger.debug(
                f"Extracted features for '{message.text[:50]}...':\n"
                f"  Topic: {data.get('topic', 'unknown')}\n"
                f"  Entities: {data.get('entities', [])}\n"
                f"  Event type: {data.get('event_type', 'other')}\n"
                f"  Keywords: {data.get('keywords', [])}"
            )

            return ArticleFingerprint(
                url=message.url,
                title=message.text[:200],  # Use first 200 chars as title
                topic=data.get("topic", "unknown"),
                entities=data.get("entities", []),
                event_type=data.get("event_type", "other"),
                keywords=data.get("keywords", []),
                source=message.channel_title,
            )

        except Exception as e:
            logger.error(f"Error extracting features: {e}")
            return None

    def _parse_json_response(self, content: str) -> dict | None:
        """Parse JSON from LLM response, handling markdown code blocks."""
        content = content.strip()

        # Remove markdown code blocks if present
        if content.startswith("```"):
            lines = content.split("\n")
            # Remove first and last lines (```json and ```)
            content = "\n".join(lines[1:-1] if lines[-1] == "```" else lines[1:])
            content = content.strip()

        try:
            data = json.loads(content)
            # Validate required fields
            if not isinstance(data.get("topic"), str):
                logger.warning("Invalid topic in LLM response")
                return None
            if not isinstance(data.get("entities"), list):
                logger.warning("Invalid entities in LLM response")
                return None
            return data
        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse LLM response as JSON: {e}")
            logger.debug(f"Response content: {content}")
            return None

    def is_duplicate(self, fingerprint: ArticleFingerprint) -> bool:
        """Check if an article is a duplicate based on entity/topic overlap."""
        # First check if URL already exists
        if self._db.url_exists(fingerprint.url):
            logger.debug(f"Duplicate URL found: {fingerprint.url}")
            return True

        # Get recent articles with same topic
        recent = self._db.get_recent_by_topic(
            fingerprint.topic,
            days=self._dedup_config.ttl_days,
        )

        if not recent:
            logger.debug(
                f"No recent articles with topic '{fingerprint.topic}' found - article is unique"
            )
            return False

        logger.debug(
            f"Comparing against {len(recent)} recent articles with topic '{fingerprint.topic}'"
        )

        new_entities = {e.lower() for e in fingerprint.entities}

        for stored in recent:
            stored_entities = {e.lower() for e in stored.entities}

            # Calculate entity overlap
            overlap = len(stored_entities & new_entities)
            total = len(stored_entities | new_entities)

            if total > 0:
                similarity = overlap / total

                # Log comparison details at DEBUG level
                logger.debug(
                    f"Comparing with stored article:\n"
                    f"  Stored: '{stored.title[:50]}...'\n"
                    f"  Stored entities: {stored.entities}\n"
                    f"  New entities: {list(new_entities)}\n"
                    f"  Overlap: {overlap}/{total} = {similarity:.2%}\n"
                    f"  Threshold: {self._dedup_config.similarity_threshold:.2%}"
                )

                if similarity >= self._dedup_config.similarity_threshold:
                    logger.info(
                        f"DUPLICATE: '{fingerprint.title[:50]}...' "
                        f"matches '{stored.title[:50]}...' "
                        f"(similarity: {similarity:.2%} >= threshold {self._dedup_config.similarity_threshold:.2%})"
                    )
                    return True

        logger.debug(
            f"UNIQUE: '{fingerprint.title[:50]}...' has no duplicates above threshold"
        )
        return False

    def store(self, fingerprint: ArticleFingerprint) -> bool:
        """Store a fingerprint in the database."""
        return self._db.store_fingerprint(fingerprint)

    def cleanup(self) -> int:
        """Remove old fingerprints from the database."""
        return self._db.cleanup_old(days=self._dedup_config.ttl_days)

    def process_messages(self, messages: list[Message]) -> list[Message]:
        """Process messages and return only unique ones.

        For each message:
        1. Extract features using LLM
        2. Check if duplicate
        3. Store fingerprint if unique

        Returns list of unique messages.
        """
        if not self._dedup_config.enabled:
            logger.debug("Deduplication disabled, returning all messages")
            return messages

        logger.info(f"Processing {len(messages)} messages for deduplication")
        unique_messages = []
        duplicates_found = 0
        extraction_failures = 0

        for i, msg in enumerate(messages, 1):
            logger.debug(f"Processing message {i}/{len(messages)}: {msg.text[:50]}...")

            # Extract features
            fingerprint = self.extract_features(msg)

            if fingerprint is None:
                # If extraction fails, keep the message (fail open)
                extraction_failures += 1
                logger.warning(
                    f"Feature extraction failed for message {i}, keeping it (fail open)"
                )
                unique_messages.append(msg)
                continue

            # Check for duplicates
            if self.is_duplicate(fingerprint):
                duplicates_found += 1
                logger.debug(f"Message {i} marked as duplicate, skipping")
                continue

            # Store fingerprint and keep message
            self.store(fingerprint)
            unique_messages.append(msg)
            logger.debug(f"Message {i} is unique, stored fingerprint")

        logger.info(
            f"Deduplication complete: {len(unique_messages)} unique, "
            f"{duplicates_found} duplicates, {extraction_failures} extraction failures"
        )

        return unique_messages
