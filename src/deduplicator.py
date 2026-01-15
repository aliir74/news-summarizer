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
            return False

        new_entities = {e.lower() for e in fingerprint.entities}

        for stored in recent:
            stored_entities = {e.lower() for e in stored.entities}

            # Calculate entity overlap
            overlap = len(stored_entities & new_entities)
            total = len(stored_entities | new_entities)

            if total > 0:
                similarity = overlap / total
                if similarity >= self._dedup_config.similarity_threshold:
                    logger.info(
                        f"Duplicate found: '{fingerprint.title[:50]}...' "
                        f"matches '{stored.title[:50]}...' "
                        f"(similarity: {similarity:.2f})"
                    )
                    return True

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

        unique_messages = []
        duplicates_found = 0

        for msg in messages:
            # Extract features
            fingerprint = self.extract_features(msg)

            if fingerprint is None:
                # If extraction fails, keep the message (fail open)
                logger.warning("Feature extraction failed for message, keeping it")
                unique_messages.append(msg)
                continue

            # Check for duplicates
            if self.is_duplicate(fingerprint):
                duplicates_found += 1
                continue

            # Store fingerprint and keep message
            self.store(fingerprint)
            unique_messages.append(msg)

        if duplicates_found > 0:
            logger.info(f"Filtered out {duplicates_found} duplicate messages")

        return unique_messages
