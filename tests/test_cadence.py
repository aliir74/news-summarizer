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

        level = controller._compute_level(10.0, radar_alert=False)

        assert level == IntensityLevel.NORMAL

    def test_surge_when_rate_exceeds_surge_ratio(self, cadence_config: Config) -> None:
        """Test a rate at/above surge_ratio * baseline returns SURGE."""
        controller = AdaptiveCadenceController(cadence_config)
        controller._rate_window = [1.0, 1.0, 1.0, 1.0, 1.0]  # baseline 1.0

        level = controller._compute_level(4.0, radar_alert=False)

        assert level == IntensityLevel.SURGE

    def test_elevated_and_normal_bands(self, cadence_config: Config) -> None:
        """Test the ELEVATED and NORMAL bands relative to the baseline."""
        controller = AdaptiveCadenceController(cadence_config)
        controller._rate_window = [1.0, 1.0, 1.0, 1.0, 1.0]  # baseline 1.0

        assert controller._compute_level(2.0, radar_alert=False) == IntensityLevel.ELEVATED
        assert controller._compute_level(1.0, radar_alert=False) == IntensityLevel.NORMAL

    def test_floor_prevents_trickle_surge(self, cadence_config: Config) -> None:
        """Test a trickle against a near-zero history does not surge (floor)."""
        controller = AdaptiveCadenceController(cadence_config)
        controller._rate_window = [0.0, 0.0, 0.0]  # baseline floored to 0.1

        # 0.2 / 0.1 = 2.0 => ELEVATED, not SURGE.
        level = controller._compute_level(0.2, radar_alert=False)

        assert level == IntensityLevel.ELEVATED

    def test_low_rate_never_surges_regardless_of_text(self, cadence_config: Config) -> None:
        """Regression: a trickle (0.05/min) must never read as SURGE.

        War vocabulary is the steady state of these sources; only volume vs the
        baseline (plus radar) may escalate. The VPS false-surge bug was a single
        keyword hit pinning SURGE at 0.01-0.06 msg/min.
        """
        controller = AdaptiveCadenceController(cadence_config)
        controller._rate_window = [0.05, 0.05, 0.05, 0.05, 0.05]

        level = controller._compute_level(0.05, radar_alert=False)

        assert level == IntensityLevel.NORMAL

    def test_radar_promotes_one_level(self, cadence_config: Config) -> None:
        """Test a radar outage flag bumps the level up by one step."""
        controller = AdaptiveCadenceController(cadence_config)
        controller._rate_window = [1.0, 1.0, 1.0, 1.0, 1.0]

        # NORMAL rate + radar => ELEVATED.
        assert controller._compute_level(1.0, radar_alert=True) == IntensityLevel.ELEVATED
        # ELEVATED rate + radar => SURGE.
        assert controller._compute_level(2.0, radar_alert=True) == IntensityLevel.SURGE


class TestRecordAndCompute:
    """Tests for the full record_and_compute escalate/decay path."""

    def _seed_baseline(self, controller: AdaptiveCadenceController) -> None:
        """Seed a baseline rate of 1.0 messages per minute."""
        controller._rate_window = [1.0, 1.0, 1.0, 1.0, 1.0]

    def test_escalates_immediately_to_surge(self, cadence_config: Config) -> None:
        """Test a surge-level rate snaps straight to the floor interval."""
        controller = AdaptiveCadenceController(cadence_config)
        self._seed_baseline(controller)

        result = controller.record_and_compute(4.0)

        assert result == 5  # min_interval_minutes
        assert controller.current_interval == 5
        assert controller.current_level == IntensityLevel.SURGE

    def test_escalates_to_elevated_half_interval(self, cadence_config: Config) -> None:
        """Test an elevated rate snaps to roughly half the baseline interval."""
        controller = AdaptiveCadenceController(cadence_config)
        self._seed_baseline(controller)

        result = controller.record_and_compute(2.0)  # ratio 2.0 => ELEVATED

        assert result == 15  # round(30 / 2)
        assert controller.current_level == IntensityLevel.ELEVATED

    def test_returns_int(self, cadence_config: Config) -> None:
        """Test the returned interval is an int (APScheduler minutes)."""
        controller = AdaptiveCadenceController(cadence_config)
        self._seed_baseline(controller)

        result = controller.record_and_compute(4.0)

        assert isinstance(result, int)

    def test_decays_gradually_without_overshoot(self, cadence_config: Config) -> None:
        """Test calming grows the interval step by step, capped at baseline."""
        controller = AdaptiveCadenceController(cadence_config)
        self._seed_baseline(controller)
        controller._current_interval = 5
        controller._current_level = IntensityLevel.SURGE

        intervals = [controller.record_and_compute(1.0) for _ in range(6)]

        # Strictly increasing toward the baseline, never overshooting it.
        assert intervals[0] == 8  # round(5 * 1.5)
        assert all(a <= b for a, b in zip(intervals, intervals[1:], strict=False))
        assert max(intervals) == 30  # baseline ceiling
        assert all(i <= 30 for i in intervals)

    def test_never_below_min_interval(self, cadence_config: Config) -> None:
        """Test the interval floor is honored."""
        controller = AdaptiveCadenceController(cadence_config)
        self._seed_baseline(controller)

        for _ in range(5):
            result = controller.record_and_compute(100.0)  # sustained surge
            assert result >= 5

    def test_appends_and_trims_window(self, cadence_config: Config) -> None:
        """Test each call appends a rate and trims to baseline_window."""
        controller = AdaptiveCadenceController(cadence_config)  # baseline_window=5

        for _ in range(7):
            controller.record_and_compute(1.0)

        assert len(controller._rate_window) == 5

    def test_max_interval_ceiling(self, cadence_config: Config) -> None:
        """Test decay can climb above baseline up to max_interval_minutes."""
        controller = AdaptiveCadenceController(cadence_config)
        controller.config.max_interval_minutes = 60
        controller._rate_window = [1.0, 1.0, 1.0, 1.0, 1.0]
        controller._current_interval = 5
        controller._current_level = IntensityLevel.SURGE

        intervals = [controller.record_and_compute(1.0) for _ in range(12)]

        assert max(intervals) == 60
        assert all(i <= 60 for i in intervals)

    def test_state_saved_on_each_call(
        self, cadence_config: Config, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test record_and_compute persists state."""
        state_file = tmp_path / ".cadence_state"
        monkeypatch.setattr("src.cadence.CADENCE_STATE_FILE", state_file)
        controller = AdaptiveCadenceController(cadence_config)
        self._seed_baseline(controller)

        controller.record_and_compute(4.0)

        assert state_file.exists()


class TestConsiderEscalation:
    """Tests for the escalate-only probe path."""

    def _seed_baseline(self, controller: AdaptiveCadenceController) -> None:
        controller._rate_window = [1.0, 1.0, 1.0, 1.0, 1.0]

    def test_escalates_when_level_rises(self, cadence_config: Config) -> None:
        """Test a higher level returns a shorter interval and updates state."""
        controller = AdaptiveCadenceController(cadence_config)
        self._seed_baseline(controller)

        result = controller.consider_escalation(4.0, radar_alert=False)

        assert result == 5
        assert controller.current_interval == 5
        assert controller.current_level == IntensityLevel.SURGE

    def test_returns_none_when_no_escalation(self, cadence_config: Config) -> None:
        """Test a non-rising level returns None and leaves state untouched."""
        controller = AdaptiveCadenceController(cadence_config)
        self._seed_baseline(controller)

        result = controller.consider_escalation(1.0, radar_alert=False)

        assert result is None
        assert controller.current_interval == 30
        assert controller.current_level == IntensityLevel.NORMAL

    def test_never_decays(self, cadence_config: Config) -> None:
        """Test the probe never relaxes an already-tightened cadence."""
        controller = AdaptiveCadenceController(cadence_config)
        self._seed_baseline(controller)
        controller._current_interval = 5
        controller._current_level = IntensityLevel.SURGE

        result = controller.consider_escalation(1.0, radar_alert=False)

        assert result is None
        assert controller.current_interval == 5  # not relaxed

    def test_does_not_append_to_window(self, cadence_config: Config) -> None:
        """Test the probe does not pollute the baseline window."""
        controller = AdaptiveCadenceController(cadence_config)
        self._seed_baseline(controller)
        before = list(controller._rate_window)

        controller.consider_escalation(4.0, radar_alert=False)

        assert controller._rate_window == before

    def test_radar_escalates(self, cadence_config: Config) -> None:
        """Test a radar outage promotes the level via the probe."""
        controller = AdaptiveCadenceController(cadence_config)
        self._seed_baseline(controller)

        result = controller.consider_escalation(1.0, radar_alert=True)

        assert result == 15  # ELEVATED => half the 30min baseline
        assert controller.current_level == IntensityLevel.ELEVATED
