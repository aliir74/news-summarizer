"""Tests for the adaptive cadence controller."""

from datetime import datetime
from pathlib import Path

import pytest

from src.cadence import AdaptiveCadenceController, IntensityLevel
from src.config import Config
from src.models import Message


def _msg(text: str) -> Message:
    """Build a minimal Message with the given text."""
    return Message(
        id=1,
        channel_username="ch",
        channel_title="Ch",
        text=text,
        timestamp=datetime(2024, 1, 15, 10, 0),
    )


class TestIntensityLevel:
    """Tests for the IntensityLevel enum."""

    def test_string_values(self) -> None:
        """Test the enum has the expected string values."""
        assert IntensityLevel.NORMAL.value == "NORMAL"
        assert IntensityLevel.ELEVATED.value == "ELEVATED"
        assert IntensityLevel.SURGE.value == "SURGE"

    def test_severity_ordering(self) -> None:
        """Test levels have an explicit severity order for comparison."""
        assert IntensityLevel.NORMAL.severity < IntensityLevel.ELEVATED.severity
        assert IntensityLevel.ELEVATED.severity < IntensityLevel.SURGE.severity


class TestControllerInit:
    """Tests for AdaptiveCadenceController initialization."""

    def test_initializes_to_baseline(self, cadence_config: Config) -> None:
        """Test a fresh controller starts at the baseline interval, empty window."""
        controller = AdaptiveCadenceController(cadence_config)

        assert controller.current_interval == cadence_config.summary_interval_minutes
        assert controller.current_level == IntensityLevel.NORMAL
        assert controller._rate_window == []

    def test_baseline_uses_prod_interval_not_test(self, cadence_config: Config) -> None:
        """Test the baseline is summary_interval_minutes (not the test interval)."""
        controller = AdaptiveCadenceController(cadence_config)

        assert controller._baseline_interval == 30


class TestStatePersistence:
    """Tests for cadence state save/load round-trip."""

    def test_state_round_trip(
        self, cadence_config: Config, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test the rate window, interval, and level round-trip through disk."""
        state_file = tmp_path / ".cadence_state"
        monkeypatch.setattr("src.cadence.CADENCE_STATE_FILE", state_file)

        controller = AdaptiveCadenceController(cadence_config)
        controller._rate_window = [0.5, 1.2, 3.4]
        controller._current_interval = 7
        controller._current_level = IntensityLevel.ELEVATED
        controller._save_state()

        loaded = AdaptiveCadenceController(cadence_config)
        loaded._load_state()

        assert loaded._rate_window == [0.5, 1.2, 3.4]
        assert loaded.current_interval == 7
        assert loaded.current_level == IntensityLevel.ELEVATED

    def test_load_missing_file_keeps_defaults(
        self, cadence_config: Config, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test loading when no state file exists leaves defaults intact."""
        state_file = tmp_path / ".cadence_state"
        monkeypatch.setattr("src.cadence.CADENCE_STATE_FILE", state_file)

        controller = AdaptiveCadenceController(cadence_config)
        controller._load_state()

        assert controller.current_interval == 30
        assert controller._rate_window == []

    def test_load_corrupt_file_keeps_defaults(
        self, cadence_config: Config, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test loading a corrupt state file degrades gracefully."""
        state_file = tmp_path / ".cadence_state"
        state_file.write_text("not json {{{")
        monkeypatch.setattr("src.cadence.CADENCE_STATE_FILE", state_file)

        controller = AdaptiveCadenceController(cadence_config)
        controller._load_state()

        assert controller.current_interval == 30


class TestBaseline:
    """Tests for the rate baseline computation."""

    def test_empty_window_returns_floor(self, cadence_config: Config) -> None:
        """Test the baseline is the configured floor when no history exists."""
        controller = AdaptiveCadenceController(cadence_config)

        assert controller._baseline() == pytest.approx(0.1)

    def test_median_of_window(self, cadence_config: Config) -> None:
        """Test the baseline is the median of the rate window."""
        controller = AdaptiveCadenceController(cadence_config)
        controller._rate_window = [1.0, 2.0, 3.0]

        assert controller._baseline() == pytest.approx(2.0)

    def test_floor_applies_to_near_zero_history(self, cadence_config: Config) -> None:
        """Test a near-zero history is floored so a trickle is not a surge."""
        controller = AdaptiveCadenceController(cadence_config)
        controller._rate_window = [0.0, 0.0, 0.0]

        assert controller._baseline() == pytest.approx(0.1)


class TestComputeLevel:
    """Tests for intensity level computation from a message rate."""

    def test_empty_window_returns_normal(self, cadence_config: Config) -> None:
        """Test no baseline history means NORMAL regardless of the rate."""
        controller = AdaptiveCadenceController(cadence_config)

        level = controller._compute_level(10.0, crisis_hit=False, radar_alert=False)

        assert level == IntensityLevel.NORMAL

    def test_surge_when_rate_exceeds_surge_ratio(self, cadence_config: Config) -> None:
        """Test a rate at/above surge_ratio * baseline returns SURGE."""
        controller = AdaptiveCadenceController(cadence_config)
        controller._rate_window = [1.0, 1.0, 1.0, 1.0, 1.0]  # baseline 1.0

        level = controller._compute_level(4.0, crisis_hit=False, radar_alert=False)

        assert level == IntensityLevel.SURGE

    def test_elevated_and_normal_bands(self, cadence_config: Config) -> None:
        """Test the ELEVATED and NORMAL bands relative to the baseline."""
        controller = AdaptiveCadenceController(cadence_config)
        controller._rate_window = [1.0, 1.0, 1.0, 1.0, 1.0]  # baseline 1.0

        assert (
            controller._compute_level(2.0, crisis_hit=False, radar_alert=False)
            == IntensityLevel.ELEVATED
        )
        assert (
            controller._compute_level(1.0, crisis_hit=False, radar_alert=False)
            == IntensityLevel.NORMAL
        )

    def test_floor_prevents_trickle_surge(self, cadence_config: Config) -> None:
        """Test a trickle against a near-zero history does not surge (floor)."""
        controller = AdaptiveCadenceController(cadence_config)
        controller._rate_window = [0.0, 0.0, 0.0]  # baseline floored to 0.1

        # 0.2 / 0.1 = 2.0 => ELEVATED, not SURGE.
        level = controller._compute_level(0.2, crisis_hit=False, radar_alert=False)

        assert level == IntensityLevel.ELEVATED

    def test_crisis_keyword_forces_surge(self, cadence_config: Config) -> None:
        """Test a crisis hit forces SURGE even at a normal rate."""
        controller = AdaptiveCadenceController(cadence_config)
        controller._rate_window = [1.0, 1.0, 1.0, 1.0, 1.0]

        level = controller._compute_level(0.1, crisis_hit=True, radar_alert=False)

        assert level == IntensityLevel.SURGE

    def test_radar_promotes_one_level(self, cadence_config: Config) -> None:
        """Test a radar outage flag bumps the level up by one step."""
        controller = AdaptiveCadenceController(cadence_config)
        controller._rate_window = [1.0, 1.0, 1.0, 1.0, 1.0]

        # NORMAL rate + radar => ELEVATED.
        assert (
            controller._compute_level(1.0, crisis_hit=False, radar_alert=True)
            == IntensityLevel.ELEVATED
        )
        # ELEVATED rate + radar => SURGE.
        assert (
            controller._compute_level(2.0, crisis_hit=False, radar_alert=True)
            == IntensityLevel.SURGE
        )

    def test_crisis_not_downgraded_by_radar_ordering(self, cadence_config: Config) -> None:
        """Test crisis SURGE is never downgraded when radar also fires."""
        controller = AdaptiveCadenceController(cadence_config)
        controller._rate_window = [1.0, 1.0, 1.0, 1.0, 1.0]

        level = controller._compute_level(0.1, crisis_hit=True, radar_alert=True)

        assert level == IntensityLevel.SURGE


class TestHasCrisisKeyword:
    """Tests for crisis keyword detection."""

    def test_detects_persian_keyword(self, cadence_config: Config) -> None:
        """Test a Persian crisis keyword is detected."""
        controller = AdaptiveCadenceController(cadence_config)

        assert controller.has_crisis_keyword([_msg("خبر فوری: جنگ آغاز شد")]) is True

    def test_detects_english_case_insensitive(self, cadence_config: Config) -> None:
        """Test English keywords match case-insensitively."""
        controller = AdaptiveCadenceController(cadence_config)

        assert controller.has_crisis_keyword([_msg("Breaking: WAR declared")]) is True

    def test_no_keyword_returns_false(self, cadence_config: Config) -> None:
        """Test benign messages do not trigger a crisis hit."""
        controller = AdaptiveCadenceController(cadence_config)

        assert controller.has_crisis_keyword([_msg("Weather is sunny today")]) is False

    def test_empty_keyword_list_never_matches(self, cadence_config: Config) -> None:
        """Test an empty crisis_keywords list never matches."""
        controller = AdaptiveCadenceController(cadence_config)
        controller.config.crisis_keywords = []

        assert controller.has_crisis_keyword([_msg("war missile جنگ")]) is False
