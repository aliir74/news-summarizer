"""Reflective adaptive summary cadence controller.

Measures news intensity as a pre-dedup filtered message rate (messages per
minute) and maps it to a summary interval: the cadence shortens fast when a
surge breaks out and decays gradually back toward the baseline as things calm.
"""

import json
import logging
import statistics
from collections.abc import Iterable
from enum import Enum
from pathlib import Path

from src.config import Config
from src.models import Message

logger = logging.getLogger(__name__)

# State file for persistence (rate window, current interval, current level)
CADENCE_STATE_FILE = Path(".cadence_state")


class IntensityLevel(str, Enum):
    """News intensity level driving the summary cadence."""

    NORMAL = "NORMAL"
    ELEVATED = "ELEVATED"
    SURGE = "SURGE"

    @property
    def severity(self) -> int:
        """Return an explicit severity rank for ordering comparisons."""
        return _SEVERITY[self]


_SEVERITY = {
    IntensityLevel.NORMAL: 0,
    IntensityLevel.ELEVATED: 1,
    IntensityLevel.SURGE: 2,
}


class AdaptiveCadenceController:
    """Track recent news intensity and map it to a summary interval."""

    def __init__(self, config: Config) -> None:
        """Initialize the controller from configuration.

        The baseline is the production steady-state interval
        (summary_interval_minutes), not effective_summary_interval_minutes, so
        the decay ceiling is correct even in test mode.
        """
        self.config = config.adaptive_cadence
        self._baseline_interval = config.summary_interval_minutes
        self._rate_window: list[float] = []
        self._current_interval = self._baseline_interval
        self._current_level = IntensityLevel.NORMAL

    @property
    def current_interval(self) -> int:
        """Return the current summary interval in minutes."""
        return self._current_interval

    @property
    def current_level(self) -> IntensityLevel:
        """Return the current intensity level."""
        return self._current_level

    def _load_state(self) -> None:
        """Load the rate window, current interval, and level from file."""
        if CADENCE_STATE_FILE.exists():
            try:
                data = json.loads(CADENCE_STATE_FILE.read_text())
                self._rate_window = [float(r) for r in data.get("rate_window", [])]
                self._current_interval = int(
                    data.get("current_interval", self._baseline_interval)
                )
                level_str = data.get("current_level", IntensityLevel.NORMAL.value)
                try:
                    self._current_level = IntensityLevel(level_str)
                except ValueError:
                    self._current_level = IntensityLevel.NORMAL
                logger.info(
                    f"Loaded cadence state: interval={self._current_interval}min, "
                    f"level={self._current_level.value}, "
                    f"window={len(self._rate_window)} samples"
                )
            except (json.JSONDecodeError, KeyError, ValueError) as e:
                logger.warning(f"Could not load cadence state: {e}")

    def _save_state(self) -> None:
        """Save the rate window, current interval, and level to file."""
        try:
            data = {
                "rate_window": self._rate_window,
                "current_interval": self._current_interval,
                "current_level": self._current_level.value,
            }
            CADENCE_STATE_FILE.write_text(json.dumps(data, indent=2))
        except OSError as e:
            logger.warning(f"Could not save cadence state: {e}")

    def has_crisis_keyword(self, messages: Iterable[Message]) -> bool:
        """Return True if any message text contains a configured crisis keyword.

        Matching is case-insensitive substring matching. An empty keyword list
        never matches.
        """
        keywords = self.config.crisis_keywords
        if not keywords:
            return False
        lowered = [kw.lower() for kw in keywords]
        for message in messages:
            text = message.text.lower()
            if any(kw in text for kw in lowered):
                return True
        return False

    def _baseline(self) -> float:
        """Return the baseline rate: median of the window, floored.

        The min_baseline_rate floor prevents a near-zero history from turning a
        trickle of messages into a false surge (divide-by-near-zero).
        """
        floor = self.config.min_baseline_rate
        if not self._rate_window:
            return floor
        return max(statistics.median(self._rate_window), floor)

    def _compute_level(
        self, rate: float, *, crisis_hit: bool, radar_alert: bool
    ) -> IntensityLevel:
        """Map a message rate (plus signals) to an intensity level.

        Ordering matters: the volume-ratio mapping runs first, then a radar
        outage promotes one level, then a crisis keyword hard-sets SURGE last so
        it can never be downgraded.
        """
        # With no baseline history we cannot judge a surge from volume alone.
        if self._rate_window:
            ratio = rate / self._baseline()
            if ratio >= self.config.surge_ratio:
                level = IntensityLevel.SURGE
            elif ratio >= self.config.elevated_ratio:
                level = IntensityLevel.ELEVATED
            else:
                level = IntensityLevel.NORMAL
        else:
            level = IntensityLevel.NORMAL

        if radar_alert:
            level = self._promote(level)

        if crisis_hit:
            level = IntensityLevel.SURGE

        return level

    @staticmethod
    def _promote(level: IntensityLevel) -> IntensityLevel:
        """Bump a level up one step (NORMAL -> ELEVATED -> SURGE)."""
        if level is IntensityLevel.NORMAL:
            return IntensityLevel.ELEVATED
        if level is IntensityLevel.ELEVATED:
            return IntensityLevel.SURGE
        return IntensityLevel.SURGE
