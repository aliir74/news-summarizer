"""Reflective adaptive summary cadence controller.

Measures news intensity as a pre-dedup filtered message rate (messages per
minute) and maps it to a summary interval: the cadence shortens fast when a
surge breaks out and decays gradually back toward the baseline as things calm.
"""

import json
import logging
import statistics
from enum import Enum
from pathlib import Path

from src.config import Config

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

# One-step promotion table (SURGE is already the ceiling).
_PROMOTION = {
    IntensityLevel.NORMAL: IntensityLevel.ELEVATED,
    IntensityLevel.ELEVATED: IntensityLevel.SURGE,
    IntensityLevel.SURGE: IntensityLevel.SURGE,
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

    def load_state(self) -> None:
        """Public entry point for loading persisted cadence state."""
        self._load_state()

    def save_state(self) -> None:
        """Public entry point for persisting cadence state."""
        self._save_state()

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

    def _baseline(self) -> float:
        """Return the baseline rate: median of the window, floored.

        The min_baseline_rate floor prevents a near-zero history from turning a
        trickle of messages into a false surge (divide-by-near-zero).
        """
        floor = self.config.min_baseline_rate
        if not self._rate_window:
            return floor
        return max(statistics.median(self._rate_window), floor)

    def _compute_level(self, rate: float, *, radar_alert: bool) -> IntensityLevel:
        """Map a message rate (plus the radar signal) to an intensity level.

        The volume-ratio mapping runs first, then a radar outage promotes the
        level one step.
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

        return level

    @staticmethod
    def _promote(level: IntensityLevel) -> IntensityLevel:
        """Bump a level up one step (NORMAL -> ELEVATED -> SURGE)."""
        return _PROMOTION[level]

    @property
    def _ceiling(self) -> int:
        """Return the slowest allowed interval.

        Defaults to the baseline; max_interval_minutes can raise it so quiet
        periods may optionally run slower than the baseline.
        """
        max_interval = self.config.max_interval_minutes
        if max_interval is not None and max_interval > self._baseline_interval:
            return max_interval
        return self._baseline_interval

    def _target_interval(self, level: IntensityLevel) -> int:
        """Map an intensity level to its target interval in minutes."""
        if level is IntensityLevel.SURGE:
            return self.config.min_interval_minutes
        if level is IntensityLevel.ELEVATED:
            return max(round(self._baseline_interval / 2), self.config.min_interval_minutes)
        return self._ceiling

    def record_and_compute(self, rate: float, *, radar_alert: bool = False) -> int:
        """Record a measured rate and return the next summary interval.

        Escalation is immediate (snap to the shorter target); decay is gradual
        (step the interval up by decay_factor each calm run, never overshooting
        the ceiling). The level is computed over the existing window BEFORE the
        new rate is appended so a spike does not damp its own surge signal.
        """
        level = self._compute_level(rate, radar_alert=radar_alert)

        self._rate_window.append(rate)
        if len(self._rate_window) > self.config.baseline_window:
            self._rate_window = self._rate_window[-self.config.baseline_window :]

        target = self._target_interval(level)
        if target < self._current_interval:
            # Escalate now.
            self._current_interval = target
        else:
            # Decay gradually toward the target. Guarantee at least +1 per run so
            # rounding can never stall the interval short of the target.
            stepped = max(
                self._current_interval + 1,
                round(self._current_interval * self.config.decay_factor),
            )
            self._current_interval = min(target, stepped)

        self._current_interval = max(
            self.config.min_interval_minutes, min(self._current_interval, self._ceiling)
        )
        self._current_level = level
        self._save_state()
        return self._current_interval

    def consider_escalation(self, rate: float, *, radar_alert: bool = False) -> int | None:
        """Escalate-only check for the cheap probe between summary runs.

        Returns the shorter interval when the computed level is higher than the
        current level; otherwise returns None and leaves state untouched. It
        never decays and never appends to the baseline window, so the noisy
        short-window probe sample cannot pollute the baseline or relax cadence.
        """
        level = self._compute_level(rate, radar_alert=radar_alert)
        if level.severity <= self._current_level.severity:
            return None

        self._current_level = level
        self._current_interval = max(
            self.config.min_interval_minutes,
            min(self._target_interval(level), self._ceiling),
        )
        self._save_state()
        return self._current_interval
