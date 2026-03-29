"""Iran-related content filtering."""

import re
from re import Pattern

from src.config import IranFilter
from src.models import Message, SourceType


class IranRelevanceFilter:
    """Filters messages for Iran-related content using keyword matching."""

    def __init__(self, config: IranFilter) -> None:
        """Initialize the filter with configuration."""
        self.config = config
        self._pattern: Pattern[str] | None = None

        if config.enabled and config.keywords:
            # Build regex pattern from keywords (case-insensitive)
            escaped_keywords = [re.escape(kw) for kw in config.keywords]
            pattern_str = r"\b(" + "|".join(escaped_keywords) + r")\b"
            self._pattern = re.compile(pattern_str, re.IGNORECASE)

    @property
    def enabled(self) -> bool:
        """Check if filtering is enabled."""
        return self.config.enabled

    def is_iran_related(self, text: str) -> bool:
        """Check if text contains Iran-related keywords."""
        if not self.enabled or self._pattern is None:
            return True  # If filtering disabled, consider all messages relevant

        return bool(self._pattern.search(text))

    def _keyword_count(self, text: str) -> int:
        """Count the number of keyword matches in text."""
        if not self._pattern:
            return 0
        return len(self._pattern.findall(text))

    def filter_message(self, message: Message) -> bool:
        """Check if a message is Iran-related.

        For RSS messages, requires the keyword in the title OR at least 2
        keyword matches in the full text. This filters out articles where
        Iran is only mentioned tangentially (e.g. a UK politics article
        that mentions "Iran war" once in passing).
        """
        if message.source_type == SourceType.RSS:
            title = message.text.split("\n\n")[0]
            if self.is_iran_related(title):
                return True
            return self._keyword_count(message.text) >= 2
        return self.is_iran_related(message.text)

    def filter_messages(self, messages: list[Message]) -> list[Message]:
        """Filter a list of messages, keeping only Iran-related ones."""
        if not self.enabled:
            return messages

        return [msg for msg in messages if self.filter_message(msg)]
