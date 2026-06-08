"""Tests for the adaptive cadence controller."""

from pathlib import Path

import pytest

from src.cadence import AdaptiveCadenceController, IntensityLevel
from src.config import Config


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
